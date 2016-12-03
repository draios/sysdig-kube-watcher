## sysdig-kube-watcher
This Python script provides a way to automatically synchronize your Sysdig Cloud Teams settings with details from your Kubernetes infrastructure.

The script acts as a bridge between the Kubernetes API and the Sysdig Cloud Teams framework. It continuously polls the Kubernetes API for changes and reflects the changes into the Sysdig Cloud user's Teams structure. By using annotations, the user can decorate Kubernetes namespaces, deployments, and services with configuration that will be recognized by the script. As the annotations appear or change, sysdig-kube-watcher understands these decorations, tracks their changes, and applies them to Sysdig Cloud by using the Sysdig Cloud Python API.

Note that you can dynamically change the annotations of a Kubernetes object and this script will be able to apply only the differences to the Team.

## Installation

Make sure to have the [python-sdc-client](https://github.com/draios/python-sdc-client) library installed in the system with pip or its source tree in the same directory as sysdig-kube-watcher.

## Usage

```python main.py <kube_url> <customer_admin_token>```

where:
- **kube_url** is the URL where the Kubernetes API can be found. E.g. _http:://127.0.0.1:8080_.
- **customer_admin_token** is the Sysdig Cloud API token of one of your admin users. This is needed because only admin users are capable of creating and configuring Teams.

## Annotating Kubernetes Objects

Currently, the following three types of Kubernetes objects can be annotated:
- namespaces
- deployments
- services

### Supported Annotations
- **sysdigTeamMembers**: a comma separated list of Sysdig Cloud user email addresses. If a user corresponding to one of the email addresses already exists, it will be added to the new Team. If it doesn't, the user will be created and an activation email will be sent to the email address.
- **sysdigDashboards**: comma separated list of Explore view names that will be used as sources to create dashboards. The dashboards will be available to all of the users in the Team and they will have the scope of the full source Kubernetes object. For example, if the object is a namespace, the dashboard will have the scope of the full namespace.
- **sysdigAlertEmails**: comma separated list of email addresses that will receive the notifications for the alerts specified in the _sysdigAlerts_ section. 
- **sysdigAlerts**: a string containing a JSON array of objects, each of which describes an alert to add to this Team. The syntax of the alert objects is the same as used with the REST API (see https://sysdig.gitbooks.io/sysdig-cloud-api/content/rest_api/alerts.html).

### Example
```
    sysdigTeamMembers: demo-kube@draios.com, ld+133@degio.org
    sysdigDashboards: Service Overview, MySQL/PostgreSQL
    sysdigAlertEmails: ld@sysdig.com, devs@sysdig.com
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

These items can be solved by either using [this Python library](https://github.com/kubernetes-incubator/client-python) or by embedding this script in the backend and offering it as a service.
