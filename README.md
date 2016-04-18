### Kubernetes Enabler User Guide

### Introduction
--------------------------------------
Kubernetes Enabler is used in conjunction with TIBCO Silver Fabric to create and manage a Kubernetes cluster, and to do continuous deployment
of Kubernetes based applications.

This Enabler was developed and tested using Kubernetes version 1.20. 
However, it is expected to  work  with other compatible later versions of Kubernetes. 

### Solution Architecture
---------------------------------------------------

This Enabler creates and manages a multiple node Kubernetes cluster, with Kubernetes Master and Worker nodes.
The Kubernetes Master nodes can be setup in a high-availability setup. Kubernetes requires the use of a *etcd key store*, therefore, this Enabler 
requires an *etcd* key store. For production use, an etcd key store is expected to be running
in a highly available configuration. For development use, the etcd key store may comprise of a single node. You can use the *etcd-enabler* available in this
 repository for setting up an etcd key store required for kubernetes. The *etcd-enabler* supports a highly available setup for running etcd. 

At a point in time, this Enabler assumes that a given host is part of a *single* Kubernetes cluster.
For each host in the Kubernetes cluster, this Enabler requires two different Docker daemons running on the host:

1. Bootstrap Docker Daemon
2. Main Docker Daemon

The Bootstrap Docker Daemon is used to run following Docker containers on *Master* node:

1. Kubernetes  `apiserver`
2. Kubernetes  `scheduler`
3. Kubernetes  `controller-manager`
4. Kubernetes  `kubelet`
5. Kubernetes  `proxy`

The Bootstrap Docker Daemon is used to run following Docker containers on *Worker* node:

1. Kubernetes  `kubelet`
2. Kubernetes  `poxy`

All the containers using the Bootstrap Docker Daemon use `host` networking.

In addition, on each node in the Kubernetes cluster, this enabler configures and starts Flannel overlay netwok.

At the time of the Silver Fabric Component (based on this this Enabler) startup, if the Main Docker Daemon is not configured to use the Flannel network bridge, 
this Enabler  reconfigures the Main Docker Daemon to use the Flannel network bridge as the default Docker bridge, and restarts the Main Docker Daemon. 
The Main Docker Daemon reconfiguration and restart is done via a  shell script, [`configure-dameon.sh`] (src/main/resources/content/bin/configure-daemon.sh).
This shell script may need to be customized depending on how Docker has been enabled on a host.

### Building the Enabler
--------------------------------------
This Enabler project builds a `Silver Fabric Enabler Grid Library`. The Enabler Grid Library can be built using Maven. 
The Grid Library file is created under target directory created by Maven.

### Installing the Enabler
--------------------------------------
Installation of the `Kubernetes Enabler` is done by copying the `Kubernetes Enabler Grid Library` from the `target` 
project folder to the `SF_HOME/webapps/livecluster/deploy/resources/gridlib` folder on the Silver Fabric Broker. 

### Enabling Docker on the Silver Fabric Engine host
--------------------------------------------------------------------
Silver Fabric Engine host needs to be `Docker enabled` before it can run Silver Fabric Components that use this Enabler. 
The main steps for Docker enabling a Silver Fabric Engine host are as follows:

1. Install `Docker 1.10.0` or later runtime on Silver Fabric Engine host
    * See [Install Docker] for details
2. Configure `Password-less sudo` or non-root Docker access for the OS user running Silver Fabric Engine so the OS user running Silver Fabric Engine is able to run Docker CLI commands without password prompting:
    * If sudo is not required, the password-less requirement still holds
3. Configure `Docker Remote API` to run on a TCP port
    * See [Configure Docker Remote API] for details
4. Configure `Docker Daemon storage-driver Option`
    * Configure Docker dameon `storage-driver` option to use a non-looback driver
    * See [Docker Daemon reference] for details
    * See [Docker Storage blog] for additional details
5. Configure `Docker Daemon selinux-enabled Option`
    * Configure Docker dameon selinux-enabled appropriately. During the development and testing of this Enabler, `--selinux-enabled=false` options was used. 
    * See [Docker and SELinux] for additional information

After you have completed the steps noted above, restart Silver Fabric Engine Daemon so that it will register the host with Silver Fabric Broker as `Docker Enabled`. 
It is recommended that you setup and enable `systemd` services for Silver Fabric Engine Daemon and Docker Daemon 
so both these services automatically startup when the host operating system is booted up.

### Configuring Main Docker Daemon on the Silver Fabric Engine host
------------------------------------------------------------------------------------------

Create a file [`/etc/sysconfig/docker`](scripts/docker) and specify Docker OPTIONS in this file.

Note the name of the default bridge in the Docker OPTIONS is set to `sfdocker0` and not `docker0`. The reason for this is that the default `docker0` name interferes
with Silver Fabric Engine Daemon startup, which, by default, is configured to use the first network interface available in the alphabetical order. 
To avoid this interference, one solution is to create a network bridge named `sfdocker0` using following commands (tested
on Centos 7):

* sudo brctl addbr sfdocker0
* sudo ip addr add 172.17.0.1/16  dev sfdocker0
* sudo ip link set dev sfdocker0 up

To make this bridge persistent on reboot, create a file named [`/etc//sysconfig/network-scripts/ifcfg-sfdocker0`] (scripts/ifcfg-sfdocker0)

In [`/usr/lib/systemd/system/docker.service`](scripts/docker.service)  file add  `/etc/sysconfig/docker` as the `EnviornmentFile`.
Enable Main Docker daemon service using the command shown below:

* sudo systemctl enable docker.service

### Enabling Bootstrap Docker on the Silver Fabric Engine host
--------------------------------------------------------------------------------
The steps for enabling the Bootstrap Docker daemon are described below.

1. Create [`/etc/sysconfig/docker-bootstrap`](scripts/docker-bootstrap) file to specify Bootstrap Docker daemon OPTIONS 
2. Create [`/usr/lib/systemd/system/docker-bootstrap.socket`](scripts/docker-bootstrap.socket).
3. Create [`/usr/lib/systemd/system/docker-bootstrap.service`](scripts/docker-bootstrap.service).

Enable Bootstrap Docker Daemon `systemd` service using the command shown below:

* sudo systemctl enable docker-bootstrap.service

### Kubernetes Feature Support
---------------------------------------------------
This Docker Enabler does not restrict any native Kubernetes  features.

### Configuring Silver Fabric Engine Resource Preference
-------------------------------------------------------------------------

Since not all Silver Fabric Engine hosts managed by a single Silver Fabric Broker may be Docker enabled, a [Resource Preference rule] using `Docker Enabled` engine property must be configured in any Silver Fabric Component using this Enabler. This enables Silver Fabric Broker to allocate Components that are based on this Enabler exclusively to Docker enabled hosts. 
Failure to use the suggested [Resource Preference rule] may result in the Components to be allocated to hosts that are not Docker enabled, 
resulting in Silver Fabric Component activation failure. In addition, you may optionally use the `Docker VersionInfo` engine property to 
select Docker enabled hosts with a specific Docker version.

### Silver Fabric Enabler Features
--------------------------------------------
This Enabler supports following Silver Fabric Enabler features:

* Application Logging Support
* Archive Management Support
* HTTP Support

The archive management feature supports  `deploy`, `undeploy`, `start` and `stop` of Kubernetes project Zip archives, 
using Silver Fabric continuous deployment (CD) REST API. See [Silver Fabric Cloud Administration Guide] for details on Silver Fabric CD REST API.

Silver Fabric CD target criteria must be specified as follows:

* ActivationInfoProperty(KubernetesNodeType)=master
* EnablerName=Kubernetes Enabler
* EnablerVersion=1.2.0`

Silver Fabric CD deployment properties are shown below:

* project-name=*name of project, e.g. webappV2*

The project Zip archive must contain Kubernetes Yaml or Json based configuration files. Example projects
are incldued under examples folder.

### Silver Fabric Enabler Statistics
-------------------------------------------

Components using this Enabler can track following Docker container statistics for each Kubernetes node:

| Docker Container Statistic|Description|
|---------|-----------|
|`Docker CPU Usage %`|Docker CPU usage percentage|
|`Docker Memory Usage %`|Docker memory usage percentage|
|`Docker Memory Usage (MB)`|Docker memory usage (MB)|
|`Docker Memory Limit (MB)`|Docker Memory Limit (MB)|
|`Docker Network Input (MB)`|Docker network input (MB)|
|`Docker Network Output (MB)`|Docker network output (MB)|
|`Docker Block Output (MB)`|Docker block device output (MB)|
|`Docker Block Input (MB)`|Docker block device input (MB)|

The Enabler statistics contain a sum of the statistics from all the Docker containers managed by the Main Docker Daemon
on a given Kubernetes node. 

### Silver Fabric Runtime Context Variables
--------------------------------------------------------

The Enabler provides following Silver Fabric runtime variables.

### Runtime Variable List:
--------------------------------

|Variable Name|Default Value|Type|Description|Export|Auto Increment|
|---|---|---|---|---|---|
|`ETCD_ENDPOINTS`|| String| REQUIRED: A comma-delimited list of etcd endpoints, e.g. http://foo:4001" |false|None|
|`CLOUD_PROVIDER`|| String| Cloud provider|false|None|
|`CLOUD_CONFIG`|| String| Cloud config file|false|None|
|`CLUSTER_NAME`|kube-cluster| String| Kubernetes cluster name |false|None|
|`CLUSTER_DNS`|| String| Kubernetes cluster DNS|false|None|
|`CLUSTER_DOMAIN`|| String| Kubernetes cluster Domain|false|None|
|`DOCKER_BOOTSTRAP_SOCK`|unix:///var/run/docker-bootstrap.sock| String| Docker daemon socket for running Kubernetes containers is required: This is not the Main Docker Daemon. |false|None|
|`DOCKER_BRIDGE`|sfdocker0| Environment| Main daemon Docker bridge |false|None|
|`DOCKER_PORT`|2375| Environment| Docker daemon TCP port |false|None|
|`ETCDCTL_DOCKER_IMAGE`|tenstartups/etcdctl| String| Etcdctl docker imageh|false|None|
|`FLANNEL_BRIDGE`|sfdocker1| Environment| Main daemon Flannel Docker bridge |false|None|
|`FLANNEL_NETWORK`|172.27.0.1/16| Flannel network CIDR notation |false|None|
|`FLANNEL_NETWORK_IP_RANGE`|172.27.0.1/24| Flannel network IP range |false|None|
|`FLANNEL_IPMASQ`|true| Whether to do IP masquerade with Flannel network |false|None|
|`FLANNEL_IFACE`|eth0| Network inerface used with Flannel network|false|None|
|`KUBECONFIG`${CONTAINER_WORK_DIR}/config/kubeconfig| String| Kubernetes kube config file |false|None|
|`FLANNEL_ETCD_PREFIX`|/coreos.com/network| String| Flannel network etcd store prefix|false|None|
|`FLANNEL_DOCKER_IMAGE`|quay.io/coreos/flannel:0.5.5| String| Flanneld docker image|false|None|
|`FLANNELD_CMD_PATH`|/opt/bin/flanneld| String| Flannel docker image flanneld path|false|None|
|`HYPERKUBE_DOCKER_IMAGE`|gcr.io/google_containers/hyperkube-amd64:v1.2.0| String| Hyperkube Docker image|false|None|
|`KUBECTL_DOCKER_IMAGE`|tlachlanevenson/k8s-kubectl| String| Kubectl docker image|false|None|
|`KUBERNETES_ADMIN_PASSWORD`|admin| String| Kubernetes admin password"|false|None|
|`KUBERNETES_CERT_GROUP`|kube-cert| String| Kubernetes certificate group|false|None|
|`KUBERNETES_DATA_DIR`|| String| Kubernetes data directory for certs, etc.|false|None|
|`INSECURE_PORT`|8080| String| Inscure port|false|None|
|`SECURE_API_SERVER`|flase| String| Flag to secure A{I serverwith SSL and authentication|false|None|
|`SECURE_PORT`|6443| String| Secure http port|false|None|
|`SERVICE_CLUSTER_IP_RANGE`|172.47.0.0/16| String| Service cluster ip range|false|None|
|`SERVICE_NODE_PORT_RANGE`|60001-64999| String| Service node port range"|false|None|
|`APISERVER_EXTRA_ARGS`|| String| Api server extra args|false|None|
|`KUBELET_EXTRA_ARGS`|| String| Kubelet extra args|false|None|
|`CONTROLLER_MANAGER_EXTRA_ARGS`|| String| Controller manager extra args|false|None|
|`SCHEDULER_EXTRA_ARGS`|| String| Scheduler extra args|false|None|
|`PROXY_EXTRA_ARGS`|| String| Proxy extra args|false|None|
|`DETACH_KUBERNETES_ON_SHUTDOWN`|false| String| Whether to detach Kubernetes on shutdown of component. If true, Kubernetes cluster is not stopped when component is shutdown.|false|None|
|`FORCE_RECONFIG`|true| Environment| Force reconfiguration and restart of main docker daemon if it is not using flannel network. |false|None|
|`KUBERNETES_DEPLOY_DIRECTORY`|${CONTAINER_WORK_DIR}/deploy| Environment| Kubernetes deploy directory: Use a shared directory for high-availability.|false|None|
|`DOCKER_BUILD_OPTIONS`|--quiet=false --no-cache=true --rm=true| Environment| Docker build options|false|None|
|`USE_SUDO`|false| String| Run Docker with 'sudo'. The 'sudo' command must not prompt for password! |false|None|

### Component and Stack configuration:
---------------------------------------------------

Master and Worker nodes are defined as seaprate Components. Both the Components require
`ETCD_ENDPOINTS` runtime variable. The Worker node must depend on a Master node Component. You may
run any number of Master or Worker nodes in a Stack configuration. At minimal, you need 1 `etcd-enabler` based Component,
1 `kubernetes-enabler` based Master node Component, and 1 `kubernetes-enabler` based Worker node Component, which must
depend on the Master node. Both the Master and Worker node Components must depend on the
`etcd-enabler` based Component.

To configure SSL, you must include following files in the Component under the `data` directory and set
`SECURE_API_SERVER` to `true`:

1. `server.key`
2. `server.cert`
3. `ca.crt`
4. `kubecfg.crt`
5. `kubecfg.key`

[Install Docker]:<https://docs.docker.com/installation/>
[Docker Multi-host Networking]:<https://docs.docker.com/engine/userguide/networking/get-started-overlay/>
[Configure Docker Remote API]:http://www.virtuallyghetto.com/2014/07/quick-tip-how-to-enable-docker-remote-api.html
[Docker and SELinux]:<http://www.projectatomic.io/docs/docker-and-selinux/>
[Resource Preference rule]:<https://github.com/fabrician/docker-enabler/blob/master/src/main/resources/images/docker_resource_preference.gif>
[Docker Daemon reference]:<https://docs.docker.com/engine/reference/commandline/daemon/>
[Docker Storage blog]:<http://www.projectatomic.io/blog/2015/06/notes-on-fedora-centos-and-docker-storage-drivers/>
[Silver Fabric Cloud Administration Guide]:<https://docs.tibco.com/pub/silver_fabric/5.7.1/doc/pdf/TIB_silver_fabric_5.7.1_cloud_administration.pdf>