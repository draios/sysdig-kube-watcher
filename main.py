import requests
import json
import sys
sys.path.insert(0, '../python-sdc-client')
from sdcclient import SdcClient
import metadata_fetcher
import time

SDC_URL = 'https://app-staging2.sysdigcloud.com'
KUBE_URL = 'http://192.168.131.175:8080'

'''
sdclient = SdcClient('2e59fab4-92ba-4bc6-acf3-35ba26c00624', SDC_URL)
#res = sdclient.set_explore_grouping_hierarchy(['kubernetes.namespace.name', 'kubernetes.deplyment.name', 'kubernetes.pod.name', 'container.id', ])
for d in ['Service Overview', 'MySQL/PostgreSQL']:
    res = sdclient.create_dashboard_from_view(d, d, None)
'''
TEAM_NOT_EXISTING_ERR = 'Could not find team'
USER_NOT_FOUND_ERR = 'User not found'
EXISTING_CHANNEL_ERR = 'A channel with name:'


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

while True:
    #
    # Parse the deployments
    #
    try:
        resp = requests.get(KUBE_URL + '/apis/extensions/v1beta1/deployments')
    except:
        continue

    rdata = json.loads(resp.content)

    for deployment in rdata['items']:
        if 'annotations' in deployment['metadata']:
            if 'teamMembers' in deployment['metadata']['annotations']:
                uids = []
                users = []

                ###################################################################
                # TEAM CREATION
                ###################################################################
                ns_name = deployment['metadata']['namespace']
                depl_name = deployment['metadata']['name']
                team_members = deployment['metadata']['annotations']['teamMembers'].split(',')
                trecipients = deployment['metadata']['annotations']['alert-recipients'].split(',')
                tdashboards = deployment['metadata']['annotations']['dashboards'].split(',')
                alertsj = deployment['metadata']['annotations']['alerts']

                team_name = "deployment_%s_%s" % (ns_name, depl_name)

                #
                # Resolve the user emails
                #
                for o in team_members:
                    uname = o.strip()
                    res = sdclient.get_user(uname)
                    if res[0] == False:
                        if res[1] == USER_NOT_FOUND_ERR:
                            res = sdclient.create_user_invite(uname)
                            res = sdclient.get_user(uname)
                            if res[0] == False:
                                log('cannot get user %s: %s' % (uname, res[1]))
                                continue
                        else:
                            log('cannot get user %s: %s' % (uname, res[1]))
                            continue

                    uids.append(res[1]['id'])
                    users.append(uname)

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
                #res = sdclient.delete_team(team_name)

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

                print 'adding team ' + team_name

                ###################################################################
                # TEAM CONFIGURATION
                ###################################################################

                #
                # First of all, we need to impersonate the users in this team
                # so that we can configure their workplace. This is
                # currently a little bit tricky because it involves:
                # - finding the user token using the admin API
                # - with the user token, jump to the new team
                # - get the user token for the team
                # - loging with the new user token
                #
                print 'impersonating user ' + newusers[0]

                ufetcher = metadata_fetcher.UsersFetcher(sysdig_superuser_token, SDC_URL)
                utoken = ufetcher.fetch_user_token(newusers[0])

                usdclient = SdcClient(utoken, SDC_URL)

                while True:
                    res = usdclient.get_user_token()
                    if res[0] == True:
                        break
                    else:
                        time.sleep(3)

                res = usdclient.switch_user_team(teamid)
                if res[0] == False:
                    print 'Team creation failed: ', res[1]
                    continue

                res = usdclient.get_user_token()
                if res[0] == False:
                    print 'Team creation failed: ', res[1]
                    continue

                utoken_t = res[1]

                teamclient = SdcClient(utoken_t, SDC_URL)

                #
                # Now that we are in the right user context, we can start to apply the
                # configurations. Here we set the grouping hierarchy.
                #
                print 'setting grouping'
                res = teamclient.set_explore_grouping_hierarchy(['kubernetes.namespace.name', 'kubernetes.deployment.name', 'kubernetes.pod.name', 'container.id', ])
                if res[0] == False:
                    print 'Failed setting team grouping: ', res[1]
                    continue

                #
                # Add the dashboards
                #
                for d in dashboards:
                    print 'adding dasboard ' + d
                    res = teamclient.create_dashboard_from_view(d, d, None)
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
