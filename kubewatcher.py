import os
import requests
import json
import sys
import time
import traceback
sys.path.insert(0, '../python-sdc-client')
from sdcclient import SdcClient
from kube_obj_parser import KubeObjParser, KubeURLParser, Logger

def log(str, severity='info'):
    Logger.log(str, severity)
    sys.stdout.flush()

log("Kubewatcher Starting")

SDC_URL = os.getenv('SDC_URL', 'https://app.sysdigcloud.com')
SDC_ADMIN_TOKEN = os.getenv('SDC_ADMIN_TOKEN')
DEFAULT_KUBE_URL = 'http://localhost:8080'
DEFAULT_TEAM_PREFIX = ''

if not SDC_ADMIN_TOKEN:
    log('Did not find API Token for an Admin user at env variable "SDC_ADMIN_TOKEN". Exiting.', 'error')
    sys.exit(1)
    
kube_url = os.getenv('KUBE_URL')
team_prefix = os.getenv('TEAM_PREFIX', DEFAULT_TEAM_PREFIX)

if not kube_url:
    kube_url = DEFAULT_KUBE_URL
    log('Did not find Kubernetes API server URL at env variable "KUBE_URL". Trying ' + kube_url, 'info')

#
# Instantiate the customer admin SDC client
#
ca_sdclient = SdcClient(SDC_ADMIN_TOKEN, SDC_URL)

res = ca_sdclient.get_user_info()
if res[0] == False:
    Logger.log('Can\'t retrieve info for Admin user: ' + res[1] + '. Exiting.', 'error')
    sys.exit(1)

customer_id = res[1]['user']['username']

#
# Allocate the parsers.
# Note: the parsers keep state, so we allocate them during startup and then we
# use them in the main loop
#
urlparser_ns = KubeURLParser('namespace', ca_sdclient, customer_id, SDC_URL, team_prefix)
urlparser_depl = KubeURLParser('deployment', ca_sdclient, customer_id, SDC_URL, team_prefix)
urlparser_srvc = KubeURLParser('service', ca_sdclient, customer_id, SDC_URL, team_prefix)

#
# MAIN LOOP
#
while True:
    log("Reading the Kubernetes API")

    try:
        #
        # Parse the namespaces
        #
        urlparser_ns.parse(kube_url + '/api/v1/namespaces')

        #
        # Parse the deployments
        #
        urlparser_depl.parse(kube_url + '/apis/extensions/v1beta1/deployments')

        #
        # Parse the services
        #
        urlparser_srvc.parse(kube_url + '/api/v1/services')
    except:
        log(sys.exc_info()[1], 'error')
        traceback.print_exc()

    #
    # Sleep a bit before checking again for changes
    #
    time.sleep(2)
