## sysdig-kube-watcher
This python scripts acts as a bridge between the Kubernetes API and the Sysdig Cloud teams framework. It continuosly polls the Kubernetes API for changes and reflects the changes into the Sysdig Cloud user's teams structure.

Once running, the script allows to create and confi. By using annotations, the user can decorate namespaces, replicasets and services. sysdig-kube-watcher understands these decorations, tracks their changes and applies them to Sysdig Cloud by using the Sysdig Cloud python API.

Note that you can dynamically change the annotations of a Kubernetes object and this script will be able to apply only the differences to the team.

## Installation

Make sure to have the [python-sdc-client](https://github.com/draios/python-sdc-client) library installed in the system with pip or its source tree in the same directory as sysdig-kube-watcher.

## Usage

```python main.py <kube_url> <customer_admin_token> <sdc_admin_token>```

where:
- **kube_url** is the URL where the Kubernetes API can be found. E.g. _http:://127.0.0.1:8080_.
- **customer_admin_token** is the token of one of the admin users for the customer. This is needed to create and configure teams on behalf of the customer.
- **sdc_admin_token** is the sysdig cloud admin token (i.e. the token for the user 'admin'). This is currently required to impersonate arbitrary users in the team and configure their environments. 

## Annotating Kubernetes Objects

Currently, the following three types of Kubernetes objects can be annotated:
- namespaces
- deployments
- services

### Supported Annotations
- **sysdigTeamMembers**: a comma separated list of Sysdig Cloud user email addresses. If a user corresponding to one of the email addresses already exists, it will be added to the new team. If it doesn't, the user will be created and an activation email will be sent to the email address.
- **sysdigDashboards**: comma separated list of Explore view names that will be used as sources to create dasboards. The dasboards will be available to all of the users in the team and they will have the scope of the full source Kubernetes object. For example, if the object is a namespace, the dasboard will have the scope of the full namespace.
- **sysdigAlertEmails**: comma separated list of email addresses that will receive the notifications for the alerts specified in the _sysdigAlerts_ section. 
- **sysdigAlerts**: a string containing a JSON array of objects, each of which describes an alert to add to this team. The syntax of the alert objects is the same as the REST API one see https://sysdig.gitbooks.io/sysdig-cloud-api/content/rest_api/alerts.html. 

### Example
```
    sysdigTeamMembers: demo-kube@draios.com, ld+133@degio.org
    sysdigDashboards: Service Overview, MySQL/PostgreSQL
    sysdigAlertEmails: ld@sysdig.com, devs@sysdig.com
    sysdigAlertSlackChannel: srvc-wordpress-prod
    sysdigAlerts: | 
     [ 
       {
          "name" : "Slow Response Time",
          "description" : "Average service response time is too high",
          "enabled" : true,
          "severity" : 3,
          "timespan" : 60,
          "condition" : "avg(net.request.time) > 500000000"        
        },
        {
          "name" : "High pod CPU",
          "description" : "CPU usage too high for one of the service pods",
          "enabled" : true,
          "severity" : 3,
          "timespan" : 60,
          "segmentBy" : [ "container.id" ],
          "segmentCondition" : "ANY",
          "condition" : "timeAvg(cpu.used.percent) > 80"            
        }
      ]
```

## Current Limitations
1. The script doesn't make use of the Kubernetes watch API, so its scalability is very limited.
2. The script doesn't support any kind of authentication or encryption when connecting to the Kubernetes API.
3. Currently, the script requires the sysdig cloud admin token, which prevents it from being used by an end user. The reason for it is that the API doesn't offer any way for a customer admin to get the API token of another customer user or to impersonate another customer user.

#1 and #2 can be solved by either using [this python library](https://github.com/kubernetes-incubator/client-python) or by embedding this script in the backend and offering it as a service. #3 will require product changes.
