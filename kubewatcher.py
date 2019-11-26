import os
import requests
import json
import sys
import time
import traceback
from sdcclient import SdcClient
from kube_obj_parser import KubeObjParser, KubeURLParser, Logger
# fix the 'InsecureRequestWarning' error
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

def log(str, severity='info'):
    Logger.log(str, severity)
    sys.stdout.flush()

log("Kubewatcher Starting")

DEFAULT_SDC_URL = 'https://app.sysdigcloud.com'
SDC_URL = os.getenv('SDC_URL')
if not SDC_URL:
    log('No SDC_URL specified. Defaulting to ' + DEFAULT_SDC_URL + '.', 'info')
    os.environ['SDC_URL'] = DEFAULT_SDC_URL

SDC_ADMIN_TOKEN = os.getenv('SDC_ADMIN_TOKEN')
if not SDC_ADMIN_TOKEN:
    log('Did not find API Token for an Admin user at env variable "SDC_ADMIN_TOKEN". Exiting.', 'error')
    sys.exit(1)
    
DEFAULT_TEAM_PREFIX = ''
team_prefix = os.getenv('TEAM_PREFIX', DEFAULT_TEAM_PREFIX)

KUBE_URL = os.getenv('KUBE_URL')
if not KUBE_URL:
    log('Did not find Kubernetes API server URL at env variable "KUBE_URL". Will attempt to autodiscover.', 'info')

#
# Instantiate the customer admin SDC client
#
log('SDC_URL = ' + SDC_URL, 'info')
ca_sdclient = SdcClient(SDC_ADMIN_TOKEN, SDC_URL)

res = ca_sdclient.get_user_info()
if res[0] == False:
    Logger.log('Can\'t retrieve info for Sysdig Cloud Admin user: ' + res[1] + '. Exiting.', 'error')
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
        urlparser_ns.parse(KUBE_URL, '/api/v1/namespaces')

        #
        # Parse the deployments
        #
        urlparser_depl.parse(KUBE_URL, '/apis/extensions/v1beta1/deployments')

        #
        # Parse the services
        #
        urlparser_srvc.parse(KUBE_URL, '/api/v1/services')
    except:
        log(sys.exc_info()[1], 'error')
        traceback.print_exc()

    #
    # Sleep a bit before checking again for changes
    #
    time.sleep(2)
