## sysdig-kube-watcher
This python scripts acts as a bridge between the Kubernetes API and the Sysdig Cloud teams framework. It continuosly polls the Kubernetes API for changes and reflects the changes into the Sysdig Cloud user's teams structure.

The logic of sysdig-kube-watcher is based on Kubernetes annotations. By using annotations, the user can decorate namespaces, replicasets and services. sysdig-kube-watcher understands these decorations, tracks their changes and applies them to Sysdig Cloud by usinf the Sysdig Cloud python API.

## Installation

## Usage


## Annotatin Kubernetes Objects

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
