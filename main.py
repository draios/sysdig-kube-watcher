import requests
import json
import sys
sys.path.insert(0, '/home/loris/python-sdc-client')
from sdcclient import SdcClient

SDC_URL='https://app-staging2.sysdigcloud.com'

#
# Instantiate the SDC client
#
sdc_token = sys.argv[1]
sdclient = SdcClient(sdc_token, SDC_URL)

#
# Parse the deployments
#
resp = requests.get('http://127.00.1:8080/apis/extensions/v1beta1/deployments')

rdata = json.loads(resp.content)

for deployment in rdata['items']:
#	print rdata[deployment]['metadata']
	if 'annotations' in deployment['metadata']:
		if 'monitoring-team' in deployment['metadata']['annotations']:
			print '***************************'
			print deployment['metadata']['name']
			print deployment['metadata']['annotations']['monitoring-team']


