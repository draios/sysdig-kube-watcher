import os
import json
import requests
import sys
sys.path.insert(0, '../python-sdc-client')
from sdcclient import SdcClient
import metadata_fetcher
import time

TEAM_NOT_EXISTING_ERR = 'Could not find team'
USER_NOT_FOUND_ERR = 'User not found'
EXISTING_CHANNEL_ERR = 'A channel with name:'

###############################################################################
# This class parses the annotations of a kubernetes object (namespace, 
# deployment...) and applies the appropriate SDC team configuration
###############################################################################
class KubeObjParser(object):
    def __init__(self, type, customer_admin_sdclient, sysdig_superuser_token, sdc_url):
        self._customer_admin_sdclient = customer_admin_sdclient
        self._sysdig_superuser_token = sysdig_superuser_token
        self._sdc_url = sdc_url
        self._type = type

    def parse(self, objdata):
        uids = []
        users = []

        ###################################################################
        # TEAM CREATION
        ###################################################################
        obj_name = objdata['metadata']['name']
        team_members = objdata['metadata']['annotations']['sysdigTeamMembers'].split(',')
        trecipients = objdata['metadata']['annotations']['sysdigAlertEmails'].split(',')
        tdashboards = objdata['metadata']['annotations']['sysdigDashboards'].split(',')
        alertsj = objdata['metadata']['annotations']['sysdigAlerts']
        if self._type == 'deployment' or self._type == 'service':
            ns_name = objdata['metadata']['namespace']
            team_name = "%s_%s_%s" % (self._type, ns_name, obj_name)
        elif self._type == 'namespace':
            ns_name = objdata['metadata']['name']
            team_name = "%s_%s" % (self._type, ns_name)
        else:
            log('unrecognized type argument')
            return False

        print "Detected annotations for team " + team_name

        #
        # Resolve the user emails
        #
        for o in team_members:
            uname = o.strip()
            res = self._customer_admin_sdclient.get_user(uname)
            if res[0] == False:
                if res[1] == USER_NOT_FOUND_ERR:
                    print "adding user " + uname
                    res = self._customer_admin_sdclient.create_user_invite(uname)
                    res = self._customer_admin_sdclient.get_user(uname)
                    print "User added"
                    if res[0] == False:
                        log('cannot get user %s: %s' % (uname, res[1]))
                        continue
                else:
                    log('cannot get user %s: %s' % (uname, res[1]))
                    continue

            uids.append(res[1]['id'])
            users.append(uname)

        if len(users) == 0:
            log('No users specified for this team')
            return False

        print "Parsing annotations"

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
            print 'Invalid JSON in the "alerts" field'
            return False

        # XXX Clean this up
        res = self._customer_admin_sdclient.delete_team(team_name)

        #
        # Check the existence of the team and create it if it doesn't exist
        #
        team_exists = True

        res = self._customer_admin_sdclient.get_team(team_name)
        if res[0] == False:
            if res[1] == TEAM_NOT_EXISTING_ERR:
                team_exists = False
        else:
            teaminfo = res[1]
            teamid = teaminfo['id']

        if team_exists:
            # Team exists. Detect if there are users to add and edit the team users list.
            if teaminfo['users'] != uids:
                newusers = []
                for j in range(0, len(uids)):
                    if not uids[j] in teaminfo['users']:
                        newusers.append(users[j])

                res = self._customer_admin_sdclient.edit_team(team_name, users=users)
                if res[0] == False:
                    print 'Team editing failed: ', res[1]
                    return False
            else:
                return True
        else:
            # Team doesn't exist. Try to create it.
            if self._type == 'deployment':
                flt = 'kubernetes.namespace.name = "%s" and kubernetes.deployment.name = "%s"' % (ns_name, obj_name)
            elif self._type == 'service':
                flt = 'kubernetes.namespace.name = "%s" and kubernetes.service.name = "%s"' % (ns_name, obj_name)
            elif self._type == 'namespace':
                flt = 'kubernetes.namespace.name = "%s"' % ns_name
            desc = 'automatically generated team based on deployment annotations'
            res = self._customer_admin_sdclient.create_team(team_name, filter=flt, description=desc, show='container', users=users)
            if res[0] == False:
                print 'Team creation failed: ', res[1]
                return False
            teamid = res[1]['team']['id']
            newusers = users

        print 'added team ' + team_name

        ###################################################################
        # TEAM CONFIGURATION
        ###################################################################

        #
        # Go through the list of new users and set them up for this team
        #
        for user in newusers:
            #
            # First of all, we need to impersonate the users in this team
            # so that we can configure their workplace. This is
            # currently a little bit tricky because it involves:
            # - finding the user token using the admin API
            # - logging in with the new user token
            #
            print 'impersonating user ' + user

            ufetcher = metadata_fetcher.UsersFetcher(self._sysdig_superuser_token, self._sdc_url)
            res = ufetcher.fetch_user_token(user, teamid)
            if res[0] == False:
                print 'Can\'t fetch token for user ', user
                return False
            else:
                utoken_t = res[1]

            teamclient = SdcClient(utoken_t, self._sdc_url)

            print 'waiting for activation of user ' + user

            while True:
                res = teamclient.get_user_token()
                if res[0] == True:
                    break
                else:
                    time.sleep(3)

            #
            # Now that we are in the right user context, we can start to apply the
            # configurations. First of all we set a default kube-friendly grouping hierarchy.
            #
            print 'setting grouping'
            if self._type == 'service':
                res = teamclient.set_explore_grouping_hierarchy(['kubernetes.namespace.name', 'kubernetes.service.name', 'kubernetes.pod.name', 'container.id'])
            else:
                res = teamclient.set_explore_grouping_hierarchy(['kubernetes.namespace.name', 'kubernetes.deployment.name', 'kubernetes.pod.name', 'container.id'])

            if res[0] == False:
                print 'Failed setting team grouping: ', res[1]
                return False

            #
            # Add the dashboards
            #
            print 'adding dashboards'

            res = teamclient.get_dashboards()
            if not res[0]:
                print 'Error getting the dasboards list: ', res[1]
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

                print 'adding dasboard ' + d
                res = teamclient.create_dashboard_from_view(d, d, None, True, {'engineTeam': team_name + d})
                if not res[0]:
                    print 'Error creating dasboard: ', res[1]

            #
            # Add the notification recipients
            #
            print 'adding notification recipients'
            res = teamclient.create_email_notification_channel('Email Channel', recipients)
            if not res[0]:
                if res[1][:20] != EXISTING_CHANNEL_ERR:
                    print 'Error setting email recipient: ', res[1]
                    return False

            #
            # Add the Alerts
            #
            print 'adding alerts'

            notify_channels = [{'type': 'EMAIL', 'emailRecipients': recipients}]
            res = self._customer_admin_sdclient.get_notification_ids(notify_channels)
            if not res[0]:
                print "Could not get IDs and hence not creating the alert: " + res[1]
                sys.exit(-1)
            notification_channel_ids = res[1]

            for a in alerts:
                res = teamclient.create_alert(a.get('name', ''),  # Alert name.
                    a.get('description', ''), # Alert description.
                    a.get('severity', 6), # Syslog-encoded severity. 6 means 'info'.
                    a.get('timespan', 60000000), # The alert will fire if the condition is met for at least 60 seconds.
                    a.get('condition', ''), # The condition.
                    a.get('segmentBy', []), # Segmentation. We want to check this metric for every process on every machine.
                    a.get('segmentCondition', 'ANY'), # in case there is more than one tomcat process, this alert will fire when a single one of them crosses the 80% threshold.
                    a.get('filter', ''), # Filter. We want to receive a notification only if the name of the process meeting the condition is 'tomcat'.
                    notification_channel_ids,
                    a.get('enabled', True))
                if not res[0]:
                    print 'Error creating alert: ', res[1]

###############################################################################
# This class parses the annotations of the kubernetes objects in a particular 
# API endoint (namespaces, deployments...) and applies the appropriate SDC 
# team configuration for each of the objects.
###############################################################################
class KubeURLParser(object):
    def __init__(self, type, customer_admin_sdclient, sysdig_superuser_token, sdc_url):
        self._customer_admin_sdclient = customer_admin_sdclient
        self._sysdig_superuser_token = sysdig_superuser_token
        self._sdc_url = sdc_url
        self._type = type

    def parse(self, url):
        try:
            resp = requests.get(url)
        except:
            return False

        rdata = json.loads(resp.content)

        if 'items' in rdata:
    #    if True:
    #        with open('data.json', 'r') as outfile:
    #            deployment = json.load(outfile)
            for deployment in rdata['items']:
                if 'annotations' in deployment['metadata'] and 'sysdigTeamMembers' in deployment['metadata']['annotations']:
                    parser = KubeObjParser(self._type, self._customer_admin_sdclient, self._sysdig_superuser_token, self._sdc_url)
                    parser.parse(deployment)
                    print 'team added'

        #
        # We cycled through all of the deployments. Wait 3 seconds before checking
        # for changes
        #
