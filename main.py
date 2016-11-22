import requests
import json
import sys
import time
import traceback
sys.path.insert(0, '../python-sdc-client')
from sdcclient import SdcClient
from kube_obj_parser import KubeObjParser, KubeURLParser, Logger

SDC_URL = 'https://app-staging2.sysdigcloud.com'
KUBE_URL = 'http://192.168.131.141:8080'

def log(str, severity='info'):
    Logger.log(str, severity)

customer_admin_token = sys.argv[1]
sysdig_superuser_token = sys.argv[2]

log("Script Starting")

#
# Instantiate the customer admin SDC client
#
ca_sdclient = SdcClient(customer_admin_token, SDC_URL)

res = ca_sdclient.get_user_info()
if res[0] == False:
    Logger.log('can\'t retrieve user info: ' + res[1])
    sys.exit(0)

customer_id = res[1]['user']['username']

#
# Allocate the parsers.
# Note: the parsers keep state, so we allocate them during startup and then we
# use them in the main loop
#
urlparser_ns = KubeURLParser('namespace', ca_sdclient, customer_id, sysdig_superuser_token, SDC_URL)
urlparser_depl = KubeURLParser('deployment', ca_sdclient, customer_id, sysdig_superuser_token, SDC_URL)
urlparser_srvc = KubeURLParser('service', ca_sdclient, customer_id, sysdig_superuser_token, SDC_URL)

#
# MAIN LOOP
#
while True:
    log("Reading the Kubernetes API")

    try:
        #
        # Parse the namespaces
        #
    #    urlparser_ns.parse(KUBE_URL + '/api/v1/namespaces')

        #
        # Parse the deployments
        #
        urlparser_depl.parse(KUBE_URL + '/apis/extensions/v1beta1/deployments')

        #
        # Parse the services
        #
    #    urlparser_srvc.parse(KUBE_URL + '/api/v1/services')
    except:
        log(sys.exc_info()[1], 'error')
        traceback.print_exc()

    #
    # Sleep a bit before checking again for changes
    #
    time.sleep(2)
