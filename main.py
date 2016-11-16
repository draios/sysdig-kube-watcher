import requests
import json
import sys
sys.path.insert(0, '../python-sdc-client')
from sdcclient import SdcClient
import metadata_fetcher
import time

SDC_URL = 'https://app-staging2.sysdigcloud.com'
KUBE_URL = 'http://192.168.131.216:8080'

TEAM_NOT_EXISTING_ERR = 'Could not find team'
USER_NOT_FOUND_ERR = 'User not found'
EXISTING_CHANNEL_ERR = 'A channel with name:'


print "Script Starting"

def log(str):
    print str

class AdminUsersFetcher(object):
    def __init__(self, sdc_token, sdc_url='https://app.sysdigcloud.com'):
        self._sdc_url = sdc_url
        self._sdc_token = sdc_token

    def fetch_user_token(self, token, username):
        #
        # setup the headers
        #
        hdrs = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}

        #
        # Iterate through the agents to find users with at least one agent
        #
        r = requests.get(self._sdc_url + "/api/admin/user/%s/token" % username, headers=hdrs)

        return r.json()['token']['key']


customer_admin_token = sys.argv[1]
sysdig_superuser_token = sys.argv[2]

#
# Instantiate the SDC client
#
sdc_token = customer_admin_token
sdclient = SdcClient(sdc_token, SDC_URL)

print "SDC client instantiated"

while True:
    #
    # Parse the deployments
    #
    print "Reading the Kubernetes API"

    '''
    try:
        resp = requests.get(KUBE_URL + '/apis/extensions/v1beta1/deployments')
    except:
        continue

    rdata = json.loads(resp.content)
    '''

    if True:
        with open('data.json', 'r') as outfile:
            deployment = json.load(outfile)
#    for deployment in rdata['items']:
        if 'annotations' in deployment['metadata']:
            if 'sysdigTeamMembers' in deployment['metadata']['annotations']:
                uids = []
                users = []

                ###################################################################
                # TEAM CREATION
                ###################################################################
                ns_name = deployment['metadata']['namespace']
                depl_name = deployment['metadata']['name']
                team_members = deployment['metadata']['annotations']['sysdigTeamMembers'].split(',')
                trecipients = deployment['metadata']['annotations']['sysdigAlertEmails'].split(',')
                tdashboards = deployment['metadata']['annotations']['sysdigDashboards'].split(',')
                alertsj = deployment['metadata']['annotations']['sysdigAlerts']

                team_name = "deployment_%s_%s" % (ns_name, depl_name)

                print "Detected annotations for team " + team_name

                #
                # Resolve the user emails
                #
                for o in team_members:
                    uname = o.strip()
                    res = sdclient.get_user(uname)
                    if res[0] == False:
                        if res[1] == USER_NOT_FOUND_ERR:
                            print "adding user " + uname
                            res = sdclient.create_user_invite(uname)
                            res = sdclient.get_user(uname)
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
                    continue

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
                    continue

                # XXX Clean this up
                res = sdclient.delete_team(team_name)

                #
                # Check the existence of the team and create it if it doesn't exist
                #
                team_exists = True

                res = sdclient.get_team(team_name)
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

                        res = sdclient.edit_team(team_name, users=users)
                        if res[0] == False:
                            print 'Team editing failed: ', res[1]
                            continue
                    else:
                        continue
                else:
                    # Team doesn't exist. Try to create it.
                    flt = 'kubernetes.namespace.name = "%s" and kubernetes.deployment.name = "%s"' % (ns_name, depl_name)
                    desc = 'automatically generated team based on deployment annotations'
                    res = sdclient.create_team(team_name, filter=flt, description=desc, show='container', users=users)
                    if res[0] == False:
                        print 'Team creation failed: ', res[1]
                        continue
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

                    ufetcher = metadata_fetcher.UsersFetcher(sysdig_superuser_token, SDC_URL)
                    res = ufetcher.fetch_user_token(user, teamid)
                    if res[0] == False:
                        print 'Can\'t fetch token for user ', user
                        continue
                    else:
                        utoken_t = res[1]

                    teamclient = SdcClient(utoken_t, SDC_URL)

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
                    res = teamclient.set_explore_grouping_hierarchy(['kubernetes.namespace.name', 'kubernetes.deployment.name', 'kubernetes.pod.name', 'container.id'])
                    if res[0] == False:
                        print 'Failed setting team grouping: ', res[1]
                        continue

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
                            continue

                    #
                    # Add the Alerts
                    #
                    print 'adding alerts'

                    notify_channels = [{'type': 'EMAIL', 'emailRecipients': recipients}]
                    res = sdclient.get_notification_ids(notify_channels)
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

                print 'team added'

    time.sleep(3)
