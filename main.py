import requests
import json
import sys
sys.path.insert(0, '../python-sdc-client')
from sdcclient import SdcClient
from kube_obj_parser import KubeObjParser, KubeURLParser

SDC_URL = 'https://app-staging2.sysdigcloud.com'
KUBE_URL = 'http://192.168.131.141:8080'

print "Script Starting"

def log(str):
    print str

customer_admin_token = sys.argv[1]
sysdig_superuser_token = sys.argv[2]

#
# Instantiate the customer admin SDC client
#
ca_sdclient = SdcClient(customer_admin_token, SDC_URL)

#
# Go in a loop detecting kubernetes changes
#
while True:
    log("Reading the Kubernetes API")

    #
    # Parse the namespaces
    #
#    urlparser = KubeURLParser('namespace', ca_sdclient, sysdig_superuser_token, SDC_URL)
#    urlparser.parse(KUBE_URL + '/api/v1/namespaces')

    #
    # Parse the deployments
    #
#    urlparser = KubeURLParser('deployment', ca_sdclient, sysdig_superuser_token, SDC_URL)
#    urlparser.parse(KUBE_URL + '/apis/extensions/v1beta1/deployments')

    #
    # Parse the services
    #
    urlparser = KubeURLParser('service', ca_sdclient, sysdig_superuser_token, SDC_URL)
    urlparser.parse(KUBE_URL + '/api/v1/services')

    #
    # Sleep a bit before checking again for changes
    #
    time.sleep(5)
