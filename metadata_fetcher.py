import os
import json
import requests
from sdcclient import SdcClient
import sys

#
# This class retrieves the credentials information of all the users
#
class UsersFetcher(object):
    def __init__(self, sdc_token, sdc_url='https://app.sysdigcloud.com'):
        self._sdc_url = sdc_url
        self._sdc_token = sdc_token

    def fetch_user_token(self, username):
        #
        # setup the headers
        #
        hdrs = {'Authorization': 'Bearer ' + self._sdc_token, 'Content-Type': 'application/json'}

        #
        # Iterate through the agents to find users with at least one agent
        #
        r = requests.get(self._sdc_url + "/api/admin/user/%s/token" % username, headers=hdrs)

        return r.json()['token']['key']
