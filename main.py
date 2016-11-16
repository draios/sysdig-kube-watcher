import requests
import json
import sys
sys.path.insert(0, '../python-sdc-client')
from sdcclient import SdcClient
from kube_obj_parser import KubeObjParser
import time

SDC_URL = 'https://app-staging2.sysdigcloud.com'
KUBE_URL = 'http://192.168.131.216:8080'

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
# Instantiate the customer admin SDC client
#
ca_sdclient = SdcClient(customer_admin_token, SDC_URL)

print "SDC client instantiated"

#
# Go in a loop dwtwcting kubernetes changes
#
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
        parser = KubeObjParser(ca_sdclient, sysdig_superuser_token, SDC_URL)
        parser.parse(deployment)
        print 'team added'

    #
    # We cycled through all of the deployments. Wait 3 seconds before checking
    # for changes
    #
    time.sleep(3)
