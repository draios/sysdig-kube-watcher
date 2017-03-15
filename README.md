## sysdig-kube-watcher
This Python script provides a way to automatically synchronize your Sysdig Cloud [Teams](https://support.sysdigcloud.com/hc/en-us/articles/115000274683) settings with details from your Kubernetes infrastructure.

The script acts as a bridge between the Kubernetes API and the Sysdig Cloud Teams framework. It continuously polls the Kubernetes API for changes and reflects the changes into the Sysdig Cloud user's Teams structure. By using annotations, the user can decorate Kubernetes namespaces, deployments, and services with configuration that will be recognized by the script. As the annotations appear or change, sysdig-kube-watcher understands these decorations, tracks their changes, and applies them to Sysdig Cloud by using the [Sysdig Cloud Python API](https://github.com/draios/python-sdc-client).

## Running as a Kubernetes Deployment (recommended)

Modify the `kubewatcher.yaml` file provided in this repository to reflect your environment, then install with:

`# kubectl create -f kubewatcher.yaml`

Configurable parameters in `kubewatcher.yaml`:

* `SDC_ADMIN_TOKEN` - The Sysdig Cloud API Token of an admin user in your environment. This is needed because only admin users are capable of creating and configuring Teams.
* `SDC_URL` (optional) - The URL you use to access Sysdig Cloud. The default is set for SaaS users, but will need to be changed if you have an [on-premise install](https://support.sysdigcloud.com/hc/en-us/articles/206519903-On-Premises-Installation-Guide).
* `SDC_SSL_VERIFY` - Whether SSL cert verification will be attempted when Kubewatcher connects to `SDC_URL`. SaaS users should leave at its default of `"true"`, while [on-premise installs](https://support.sysdigcloud.com/hc/en-us/articles/206519903-On-Premises-Installation-Guide) will typically need to set this to `"false"`.
* `TEAM_PREFIX` (optional) - A string that will be prepended to the names of Teams and Notification Channels automatically created by Kubewatcher. This will make them easier to identify in the Sysdig Cloud UI.

From inside the pod where it runs, Kubewatcher will automatically attempt to contact the Kubernetes API server at the DNS name `kubernetes` using the credential and certificate bundle as described in the docs [here](https://kubernetes.io/docs/user-guide/accessing-the-cluster/#accessing-the-api-from-a-pod).

## Running Manually (not recommended)

Clone this repository and ensure all requirements are installed (currently [python-sdc-client](https://github.com/draios/python-sdc-client)).

```
# git clone https://github.com/draios/sysdig-kube-watcher.git
# cd sysdig-kube-watcher
# pip install -r requirements.txt
```

Use environment variables for the same settings described in the previous section when starting the script. In addition, the env variable `KUBE_URL` must be set to the URL for accessing your Kubernetes API server. When running manually, Kubewatcher currently supports only [direct access over HTTP](http://kubernetes.io/docs/user-guide/accessing-the-cluster/#directly-accessing-the-rest-api).

```
SDC_ADMIN_TOKEN="abcdef01-2345-6789-abcd-ef0123456789" \
SDC_URL="https://app.sysdigcloud.com" \
KUBE_URL="http://10.0.2.15:8080" \
TEAM_PREFIX="KW-" \
python kubewatcher.py
```

### Supported Annotations

Currently, the following three types of Kubernetes objects can be annotated:
- Namespaces
- Deployments
- Services

The following annotations are recognized by Kubewatcher:

- **sysdigTeamMembers**: A comma-separated list of Sysdig Cloud user email addresses. If a user corresponding to one of the email addresses already exists, it will be added to the new Team. If it doesn't, the user will be created and an activation email will be sent to the email address.
- **sysdigDashboards**: A comma-separated list of Explore view names that will be used as sources to create dashboards. The dashboards will be available to all of the users in the Team and they will have the scope of the full source Kubernetes object that was annotated. For example, if the object is a namespace, the dashboard will have the scope of the full namespace.
- **sysdigAlertEmails**: A comma-separated list of email addresses that will receive the notifications for the alerts specified in the _sysdigAlerts_ section. 
- **sysdigAlerts**: A string containing a JSON array of objects, each of which describes an alert to add to this Team. The syntax of the alert objects is the same as used with the REST API (see https://sysdig.gitbooks.io/sysdig-cloud-api/content/rest_api/alerts.html).

### Example

Assume we have an existing Kubernetes deployment `hello-world` and we edit its configuration.

`# kubectl edit deployment hello-world`

Now we the following under `metadata:` / `annotations:`

```
    sysdigTeamMembers: mary@example.com, joe@example.com
    sysdigDashboards: Service Overview, MySQL/PostgreSQL
    sysdigAlertEmails: sleepless@example.com
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

If we watch the Kubewatcher log as the edits are saved, we can observe the changes being made to Sysdig Cloud via the API. The script polls the Kubernetes API every two seconds and makes changes immediately.


```
2017-01-04 19:53:44 - info - Reading the Kubernetes API
2017-01-04 19:53:46 - info - Reading the Kubernetes API
2017-01-04 19:53:48 - info - Reading the Kubernetes API
2017-01-04 19:53:48 - info - discovered new deployment hello-world
2017-01-04 19:53:49 - info - Detected new deployment hello-world, adding team KW-deployment_default_hello-world
2017-01-04 19:53:50 - info - adding notification recipients
2017-01-04 19:53:51 - info - email recipients have not changed since last update
2017-01-04 19:53:51 - info - adding alert Slow Response Time
2017-01-04 19:53:52 - info - adding alert High pod CPU
2017-01-04 19:53:52 - info - impersonating user mary@example.com
2017-01-04 19:53:53 - info - waiting for activation of user mary@example.com
2017-01-04 19:53:53 - info - setting grouping
2017-01-04 19:53:53 - info - adding dasboard Service Overview
2017-01-04 19:53:54 - info - adding dasboard MySQL/PostgreSQL
2017-01-04 19:53:55 - info - impersonating user joe@example.com
2017-01-04 19:53:56 - info - waiting for activation of user joe@example.com
2017-01-04 19:53:56 - info - setting grouping
2017-01-04 19:53:59 - info - Reading the Kubernetes API
2017-01-04 19:54:01 - info - Reading the Kubernetes API
2017-01-04 19:54:03 - info - Reading the Kubernetes API
```

## Configuration Changes

Changes to the Team membership (**sysdigTeamMembers**) and Notification Channels (**sysdigAlertEmails**) always _replace_ any existing configuration. If you remove an email address in the annotations for the Kubernetes object, it will be removed in the corresponding Sysdig Cloud setting. As a result, making direct changes to these settings in the Sysdig Cloud UI is not recommended, since any future change to the Kubernetes object annotations may revert your change. You should always make these configuration changes via the annotations in Kubernetes. The use of the `TEAM_PREFIX` setting may help your users identify these Kubewatcher-created items and hence know not to edit them via the Sysdig Cloud UI.

Changes to the dashboards and alerts (triggered by **sysdigDashboards** and **sysdigAlerts**) will only ever _add configuration_ to Sysdig Cloud. Previously-added dashboards and alerts are never modified or deleted by subsequent updates from Kubewatcher. This is to prevent any changes by users from being reverted. If you want to delete a dashboard or alert that was previously created by Kubewatcher, delete it via the Sysdig Cloud UI and then delete it from the annotations for the corresponding Kubernetes object.

## Current Limitations

The script currently polls the Kubernetes API, which does not scale well. An enhancement that could address this would use the [watch](https://github.com/kubernetes-incubator/client-python) feature of the Kubernetes API.
