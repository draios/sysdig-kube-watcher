import os
import copy
import json
import requests
import sys
import hashlib
import traceback
sys.path.insert(0, '../python-sdc-client')
from sdcclient import SdcClient
import time
from time import gmtime, strftime

TEAM_NOT_EXISTING_ERR = 'Could not find team'
USER_NOT_FOUND_ERR = 'User not found'
EXISTING_CHANNEL_ERR = 'A channel with name:'
ALL_SYSDIG_ANNOTATIONS = [ 'sysdigTeamMembers', 'sysdigDashboards', 'sysdigAlertEmails', 'sysdigAlerts' ]
K8S_CA_CRT_FILE_NAME = '/var/run/secrets/kubernetes.io/serviceaccount/ca.crt'
K8S_BEARER_TOKEN_FILE_NAME = '/var/run/secrets/kubernetes.io/serviceaccount/token'
K8S_DEFAULT_DNS_NAME = 'kubernetes'

class Logger(object):
    @staticmethod
    def log(str, severity='info'):
        time = strftime('%Y-%m-%d %H:%M:%S', gmtime())
        print '%s - %s - %s' % (time, severity, str)

###############################################################################
# This class parses the annotations of a kubernetes object (namespace, 
# deployment...) and applies the appropriate SDC team configuration
###############################################################################
class KubeObjParser(object):
    def __init__(self, type, customer_admin_sdclient, customer_id, sdc_url, team_prefix):
        self._customer_admin_sdclient = customer_admin_sdclient
        self._customer_id = customer_id
        self._sdc_url = sdc_url
        self._team_prefix = team_prefix
        self._type = type

    def parse(self, objdata):
        user_id_map = {}

        ###################################################################
        # TEAM CREATION
        ###################################################################
        obj_name = objdata['metadata']['name']
        team_members = objdata['metadata']['annotations'].get('sysdigTeamMembers', '').split(',')
        trecipients = objdata['metadata']['annotations'].get('sysdigAlertEmails', '').split(',')
        tdashboards = objdata['metadata']['annotations'].get('sysdigDashboards', '').split(',')
        alertsj = objdata['metadata']['annotations'].get('sysdigAlerts', json.dumps([]))

        if self._type == 'deployment' or self._type == 'service':
            ns_name = objdata['metadata']['namespace']
            team_name = "%s%s_%s_%s" % (self._team_prefix, self._type, ns_name, obj_name)
        elif self._type == 'namespace':
            ns_name = objdata['metadata']['name']
            team_name = "%s%s_%s" % (self._team_prefix, self._type, ns_name)
        else:
            Logger.log('unrecognized type argument', 'error')
            return False

        #
        # Resolve the user emails.
        # Add the users that are not part of sysdig cloud yet.
        #
        for o in team_members:
            uname = o.strip()
            res = self._customer_admin_sdclient.get_user(uname)
            if res[0] == False:
                if res[1] == USER_NOT_FOUND_ERR:
                    Logger.log("adding user " + uname)
                    res = self._customer_admin_sdclient.create_user_invite(uname)
                    res = self._customer_admin_sdclient.get_user(uname)
                    Logger.log("User added")
                    if res[0] == False:
                        Logger.log('cannot get user %s: %s' % (uname, res[1]), 'error')
                        continue
                else:
                    Logger.log('cannot get user %s: %s' % (uname, res[1]), 'error')
                    continue

            user_id_map[uname] = res[1]['id']

        if len(user_id_map) == 0:
            Logger.log('No users specified for this team. Skipping.', 'error')
            return False

        #
        # Normalize alert recipients
        #
        recipients = []
        for r in trecipients:
            recipients.append(r.strip())

        #
        # Normalize the dashboards list
        #
        dashboards = []
        for d in tdashboards:
            dashboards.append(d.strip())

        #
        # Parse the alerts json
        #
        alerts = []

        try:
            alerts = json.loads(alertsj)
        except ValueError:
            Logger.log('Invalid JSON in the "alerts" field', 'error')
            return False

        # XXX This is here for testing purposes only
        # res = self._customer_admin_sdclient.delete_team(team_name)

        #
        # Check the existence of the team and create it if it doesn't exist
        #
        team_exists = True

        res = self._customer_admin_sdclient.get_team(team_name)
        if res[0] == False:
            if res[1] == TEAM_NOT_EXISTING_ERR:
                team_exists = False
                new_memberships = dict(map(lambda u: (u, 'ROLE_TEAM_EDIT'), user_id_map.keys()))
        else:
            teaminfo = res[1]
            teamid = teaminfo['id']
            old_memberships = dict(map(lambda m: (m['userId'], m['role']), teaminfo['userRoles']))
            new_memberships = dict(map(lambda u: (u, 'ROLE_TEAM_EDIT') if user_id_map[u] not in old_memberships else (u, old_memberships[user_id_map[u]]), user_id_map.keys()))

        if team_exists:
            # Team exists. Detect if there are users to add and edit the team users list.
            newusers = []
            team_uids = set(old_memberships.keys())

            if team_uids != set(user_id_map.values()):
                Logger.log("Detected modified %s %s, editing team %s" % (self._type, obj_name, team_name))
                newusers.append([u for u in user_id_map.keys() if user_id_map[u] not in team_uids])

                res = self._customer_admin_sdclient.edit_team(team_name, memberships=new_memberships)
                if res[0] == False:
                    Logger.log('Team editing failed: ' + res[1], 'error')
                    return False
        else:
            Logger.log("Detected new %s %s, adding team %s" % (self._type, obj_name, team_name))

            # Team doesn't exist. Try to create it.
            if self._type == 'deployment':
                flt = 'kubernetes.namespace.name = "%s" and kubernetes.deployment.name = "%s"' % (ns_name, obj_name)
            elif self._type == 'service':
                flt = 'kubernetes.namespace.name = "%s" and kubernetes.service.name = "%s"' % (ns_name, obj_name)
            elif self._type == 'namespace':
                flt = 'kubernetes.namespace.name = "%s"' % ns_name
            desc = 'automatically generated team based on deployment annotations'
            res = self._customer_admin_sdclient.create_team(team_name, filter=flt, description=desc, show='container', memberships=new_memberships)
            if res[0] == False:
                Logger.log('Team creation failed: ' + res[1], 'error')
                return False
            teamid = res[1]['team']['id']
            newusers = user_id_map.keys()

        ###################################################################
        # TEAM CONFIGURATION
        ###################################################################

        #
        # If we have alerts, create a notification channel and point the
        # alerts at it.
        #
        if alerts:

            Logger.log('adding notification recipients')

            #
            # These steps can be done as the admin user since notification
            # channels have global scope and alerts has team scope, and admin
            # users are members of all teams.
            #
            res = self._customer_admin_sdclient.get_user_api_token(self._customer_id, team_name)
            if res[0] == False:
                Logger.log('Can\'t fetch token for user ' + user, 'error')
                return False
            else:
                utoken_t = res[1]

            teamclient = SdcClient(utoken_t, self._sdc_url)

            #
            # Add the email notification channel. This will silently fail
            # if it has already been created.
            #
            res = teamclient.create_email_notification_channel(team_name, recipients)
            if not res[0]:
                if res[1][:20] != EXISTING_CHANNEL_ERR:
                    Logger.log('Error setting email recipient: ' + res[1], 'error')
                    return False

            #
            # Get the notification channel ID to use for the alerts.
            #
            notify_channels = [{'type': 'EMAIL', 'name': team_name}]
            res = teamclient.get_notification_ids(notify_channels)
            if not res[0]:
                Logger.log("cannot create the email notification channel: " + res[1], 'error')
                return False
            notification_channel_ids = res[1]

            #
            # Make sure the members of the email notification channel are current.
            # Since we searched for the channel by name, there should only be one. But
            # since get_notification_ids() returns a list, treat it as such.
            #
            for channel_id in notification_channel_ids:
                res = teamclient.get_notification_channel(channel_id)
                if not res[0]:
                    Logger.log("cannot find the email notification channel: " + res[1], 'error')
                    return False
                c = res[1]
                current_recip = c['options']['emailRecipients']
                if set(current_recip) == set(recipients):
                    Logger.log('email recipients have not changed since last update', 'info')
                else:
                    Logger.log('email recipients have changed - updating', 'info')
                    c['options']['emailRecipients'] = copy.deepcopy(recipients)
                    teamclient.update_notification_channel(c)

            #
            # Add the Alerts
            #
            res = teamclient.get_alerts()
            if not res[0]:
                Logger.log("cannot get user alerts: " + res[1], 'error')
                return False

            cur_alerts = res[1]['alerts']

            for a in alerts:
                aname = a.get('name', '')

                #
                # Check if this alert already exists
                #
                skip = False
                for ca in cur_alerts:
                    if ca['name'] == aname and 'annotations' in ca:
                        skip = True
                        break

                if skip:
                    #
                    # Alert already exists, skip the creation
                    #
                    continue

                Logger.log('adding alert %s' % aname)

                res = teamclient.create_alert(aname,  # Alert name.
                    a.get('description', ''), # Alert description.
                    a.get('severity', 6), # Syslog-encoded severity. 6 means 'info'.
                    a.get('timespan', 60000000), # The alert will fire if the condition is met for at least 60 seconds.
                    a.get('condition', ''), # The condition.
                    a.get('segmentBy', []), # Segmentation. We want to check this metric for every process on every machine.
                    a.get('segmentCondition', 'ANY'), # in case there is more than one tomcat process, this alert will fire when a single one of them crosses the 80% threshold.
                    a.get('filter', ''), # Filter. We want to receive a notification only if the name of the process meeting the condition is 'tomcat'.
                    notification_channel_ids,
                    a.get('enabled', True),
                    {'engineTeam': team_name + aname})
                if not res[0]:
                    Logger.log('Error creating alert: ' + res[1], 'error')

        #
        # Go through the list of new users and set them up for this team
        #
        for user in user_id_map.keys():

            #
            # First of all, we need to impersonate the users in this team
            # so that we can configure their workplace. This is
            # currently a little bit tricky because it involves:
            # - finding the user token using the admin API
            # - logging in with the new user token
            #
            Logger.log('impersonating user ' + user)

            res = self._customer_admin_sdclient.get_user_api_token(user, team_name)
            if res[0] == False:
                Logger.log('Can\'t fetch token for user ' + user, 'error')
                return False
            else:
                utoken_t = res[1]

            teamclient = SdcClient(utoken_t, self._sdc_url)

            Logger.log('waiting for activation of user ' + user)

            while True:
                res = teamclient.get_user_token()
                if res[0] == True:
                    break
                else:
                    time.sleep(3)

            #
            # Now that we are in the right user context, we can start to apply the
            # configurations. First of all we set a default kube-friendly grouping hierarchy.
            # We do this only is the user is new to the group, because we don't want to
            # pollute the grouping of existing users.
            #
            if user in newusers:
                Logger.log('setting grouping')
                if self._type == 'service':
                    res = teamclient.set_explore_grouping_hierarchy(['kubernetes.namespace.name', 'kubernetes.service.name', 'kubernetes.pod.name', 'container.id'])
                else:
                    res = teamclient.set_explore_grouping_hierarchy(['kubernetes.namespace.name', 'kubernetes.deployment.name', 'kubernetes.pod.name', 'container.id'])

                if res[0] == False:
                    Logger.log('Failed setting team grouping: ' + res[1], 'error')
                    return False

            #
            # Add the dashboards
            #
            res = teamclient.get_dashboards()
            if not res[0]:
                Logger.log('Error getting the dasboards list: ' + res[1], 'error')
                break
            existing_dasboards = res[1]['dashboards']

            for d in dashboards:
                skip = False
                for ex in existing_dasboards:
                    if ex['name'] == d:
                        if ex['isShared'] and 'annotations' in ex and ex['annotations'].get('engineTeam') == team_name + d:
                            # dashboard already exists. Skip adding it
                            skip = True
                            break

                if skip:
                    continue

                Logger.log('adding dasboard ' + d)
                res = teamclient.create_dashboard_from_view(d, d, None, True, {'engineTeam': team_name + d, 'ownerUser': user})
                if not res[0]:
                    Logger.log('Error creating dasboard: ' + res[1], 'error')


###############################################################################
# This class parses the annotations of the kubernetes objects in a particular 
# API endoint (namespaces, deployments...) and applies the appropriate SDC 
# team configuration for each of the objects.
###############################################################################
class KubeURLParser(object):
    def __init__(self, type, customer_admin_sdclient, customer_id, sdc_url, team_prefix):
        self._customer_admin_sdclient = customer_admin_sdclient
        self._customer_id = customer_id
        self._sdc_url = sdc_url
        self._team_prefix = team_prefix
        self._type = type
        self._md5s = {}
        self._parser = KubeObjParser(self._type, self._customer_admin_sdclient, self._customer_id, self._sdc_url, self._team_prefix)

    def parse(self, url, endpoint):
        resp = self._kube_get(url, endpoint)
        rdata = json.loads(resp.content)

#        while not 'j' in locals():
#            j = 1
#            with open('data.json', 'r') as outfile:
#                deployment = json.load(outfile)
        if 'items' in rdata:
            for deployment in rdata['items']:
                if 'annotations' in deployment['metadata'] and any (sysdig_annotation in deployment['metadata']['annotations'] for sysdig_annotation in ALL_SYSDIG_ANNOTATIONS):
                    #
                    # Calculate the MD5 checksum of the whole annotations of 
                    # this object
                    #
                    hash = hashlib.md5(str(deployment['metadata']['annotations'])).hexdigest()

                    #
                    # If the MD5 of the annotations corresponds to the stored 
                    # one, skip this object, otherwise process it
                    #
                    if deployment['metadata']['uid'] in self._md5s:
                        if self._md5s[deployment['metadata']['uid']] == hash:
                            continue
                        else:
                            Logger.log('detected changes in %s %s' % (self._type, deployment['metadata']['name']))
                    else:
                        Logger.log('discovered new %s %s' % (self._type, deployment['metadata']['name']))

                    #
                    # Store the hash
                    #
                    self._md5s[deployment['metadata']['uid']] = hash

                    #
                    # Parse the object and add/modify the sysdig cloud team accordingly
                    #
                    try:
                        self._parser.parse(deployment)
                    except:
                        Logger.log(sys.exc_info()[1], 'error')
                        traceback.print_exc()
                        continue

    def _kube_get(self, url, endpoint):
        headers = {}
        k8s_cert_existed = False
        
        if os.path.exists(K8S_BEARER_TOKEN_FILE_NAME) and os.stat(K8S_BEARER_TOKEN_FILE_NAME).st_size > 0:
            try:
                with open(K8S_BEARER_TOKEN_FILE_NAME, 'r') as tokenfile:
                    headers = {'Authorization': 'Bearer ' + tokenfile.read() }
            except:
                Logger.log(sys.exc_info()[1], 'error')
                traceback.print_exc()
                sys.exit(1)
        else:
            Logger.log('Connect Kubernetes API server failed: Could not find bearer token at ' + K8S_BEARER_TOKEN_FILE_NAME + '. Exiting.')
            sys.exit(1)
        if os.path.exists(K8S_CA_CRT_FILE_NAME) and os.stat(K8S_CA_CRT_FILE_NAME).st_size > 0:
            k8s_cert_existed = True

        if url:
            if k8s_cert_existed:
                return requests.get(url + endpoint, verify = K8S_CA_CRT_FILE_NAME, headers=headers)
        else:
            kube_service_port = os.getenv('KUBERNETES_SERVICE_PORT_HTTPS')
            if kube_service_port is None:
                Logger.log('Autodiscover of Kubernetes API server failed:' +
                           'Could not find env variable KUBERNETES_SERVICE_PORT_HTTPS. Exiting.')
                sys.exit(1)
            if k8s_cert_existed:
                return requests.get('https://' + K8S_DEFAULT_DNS_NAME + ':' + kube_service_port + endpoint,
                                    verify = K8S_CA_CRT_FILE_NAME,
                                    headers=headers)
