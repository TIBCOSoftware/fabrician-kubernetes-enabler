import os
import time
import sys
import os.path
import stat
import re
import socket
import uuid
import ast
from uuid import UUID
from jarray import array

import distutils.dir_util
from subprocess import call

from java.lang import Boolean
from java.nio import ByteBuffer
from java.io import File
from java.io import FileOutputStream
from java.util.zip import ZipFile
from java.util.zip import ZipEntry
from java.util.zip import ZipInputStream

from com.datasynapse.fabric.util import ContainerUtils
from com.datasynapse.fabric.common import RuntimeContextVariable
from com.datasynapse.fabric.common import ActivationInfo
from com.datasynapse.fabric.common import ArchiveActivationInfo
from com.datasynapse.fabric.container import ArchiveDetail

class Kubernetes:
    
    def __init__(self, additionalVariables):
        " initialize Kubernetes Enabler"
     
        self.__sudo = Boolean.parseBoolean(getVariableValue("USE_SUDO", "false"))
            
        self.__dockerBootstrapSock = getVariableValue("DOCKER_BOOTSTRAP_SOCK")
        if not self.__dockerBootstrapSock:
            raise Exception("DOCKER_BOOTSTRAP_SOCK is required")

        self.__etcdEndpoints = getVariableValue("ETCD_ENDPOINTS")
        if not self.__etcdEndpoints:
            raise Exception("ETCD_ENDPOINTS is required")
            
        self.__secure = Boolean.parseBoolean(getVariableValue("SECURE_API_SERVER", "false"))
    
        self.__listenAddress = getVariableValue("LISTEN_ADDRESS")
        self.__insecureAddress = "0.0.0.0"
        if self.__secure:
           self.__insecureAddress = "127.0.0.1"
        self.__insecurePort=getVariableValue("INSECURE_PORT", "8080")
        self.__securePort = getVariableValue("SECURE_PORT", "6443")
        
        self.__dockerAddr = self.__listenAddress + ":" + getVariableValue("DCKER_PORT", "2375")
        
        self.__basedir = getVariableValue("CONTAINER_WORK_DIR")
        
        bindir=os.path.join(self.__basedir, "bin")
        changePermissions(bindir)
        
        self.__running = None
        self.__dockerContainerName=None
        self.__dockerImage = None
        self.__command = None
        self.__mountVolumes = None
        self.__commandArgs=None
        
        self.__stats = []
        self.__dockerStats = {}
        self.__initStats()
        
        self.__runningContainers=[]
        
        self.__nodeType = None
        
        self.__apiServerUrl= getVariableValue("API_SERVER_URL")
        
        if not self.__apiServerUrl:
            if self.__secure:
                self.__apiServerUrl = "https://" + self.__listenAddress + ":" + self.__securePort
            else:
                self.__apiServerUrl = "http://" + self.__listenAddress + ":" + self.__insecurePort
                
            runtimeContext.addVariable(RuntimeContextVariable("API_SERVER_URL", self.__apiServerUrl, RuntimeContextVariable.STRING_TYPE, "Kubernetes API server URL", True, RuntimeContextVariable.NO_INCREMENT))
            self.__nodeType = "master"
            self.__configureMasterNode()
        else:
            self.__nodeType = "worker"
            self.__configureWorkerNode()
   
        self.__deploydir = getVariableValue("KUBERNETES_DEPLOY_DIRECTORY")
        mkdir_p(self.__deploydir)
        
        self.__lockExpire = int(getVariableValue("LOCK_EXPIRE", "300000"))
        self.__lockWait = int(getVariableValue("LOCK_WAIT", "30000"))
        
        self.__lockExpire = int(getVariableValue("LOCK_EXPIRE", "300000"))
        self.__lockWait = int(getVariableValue("LOCK_WAIT", "30000"))
   
        self.__archiveFiles = {}
        self.__etcdctlImage = getVariableValue("ETCDCTL_DOCKER_IMAGE")
        self.__detach = Boolean.parseBoolean(getVariableValue("DETACH_KUBERNETES_ON_SHUTDOWN", "false"))
    
    def __configureMasterNode(self):
        
        hyperkube=getVariableValue("HYPERKUBE_DOCKER_IMAGE",)
        
        self.__dockerImage = [hyperkube, hyperkube, hyperkube, hyperkube, hyperkube]
        self.__dockerContainerName=["apiserver",  "controller-manager",  "scheduler", "kubelet","kube-proxy"]
        self.__command = ["/hyperkube", "/hyperkube", "/hyperkube", "/hyperkube", "/hyperkube"]
        
        kubernetesConfig = getVariableValue("KUBERNETES_DATA_DIR")
        if not kubernetesConfig:
            kubernetesConfig = os.path.join(self.__basedir, "data")
        
        self.__mountVolumes = ["--volume="+kubernetesConfig+":/srv/kubernetes"]
        self.__mountVolumes.extend(["--volume="+kubernetesConfig+":/srv/kubernetes"])
        self.__mountVolumes.extend(["--volume="+kubernetesConfig+":/srv/kubernetes"])
        args=["--volume=/:/rootfs:ro",
              "--volume=/sys:/sys:ro",
              "--volume=/var/lib/docker/:/var/lib/docker:rw",
              "--volume=/var/lib/kubelet/:/var/lib/kubelet:rw",
              "--volume=/var/run:/var/run:rw",
              "--volume="+kubernetesConfig+":/srv/kubernetes"]
        self.__mountVolumes.extend([list2str(args)])
        self.__mountVolumes.extend(["--volume="+kubernetesConfig+":/srv/kubernetes"])
        
        componentName=proxy.container.currentDomain.name
        args = [  "apiserver",
              "--service-cluster-ip-range=" + getVariableValue("SERVICE_CLUSTER_IP_RANGE"),
              "--service-node-port-range="+getVariableValue("SERVICE_NODE_PORT_RANGE"),
              "--insecure-bind-address="+self.__insecureAddress,
              "--bind-address="+self.__listenAddress,
              "--insecure-port=" + self.__insecurePort,
              "--secure-port=" + self.__securePort,
              "--client-ca-file=/srv/kubernetes/ca.crt",
              "--basic-auth-file=/srv/kubernetes/basic_auth.csv",
              "--min-request-timeout=300",
              "--tls-cert-file=/srv/kubernetes/server.cert",
              "--tls-private-key-file=/srv/kubernetes/server.key",
              "--token-auth-file=/srv/kubernetes/known_tokens.csv",
              "--etcd-servers="+self.__etcdEndpoints,
              "--etcd-prefix=" +"/registry/"+componentName,
              "--v=4"]
        
        extraArgs = getVariableValue("APISERVER_EXTRA_ARGS")
        if extraArgs:
            args.extend(extraArgs.split())
            
        self.__commandArgs = [list2str(args) + " --admission-control=NamespaceLifecycle,LimitRanger,SecurityContextDeny,ServiceAccount,ResourceQuota"]
        
        masterAddr = self.__insecureAddress + ":"+self.__insecurePort
        args = [ "controller-manager", 
                "--master="+masterAddr, 
                "--service-account-private-key-file=/srv/kubernetes/server.key",
                "--root-ca-file=/srv/kubernetes/ca.crt",
                "--leader-elect=true",
                "--min-resync-period=3m",
                "--v=2"]
        
        extraArgs = getVariableValue("CONTROLLER_MANAGER_EXTRA_ARGS")
        if extraArgs:
            args.extend(extraArgs.split())
        self.__commandArgs.extend([list2str(args)])
        
        args = [ "scheduler", 
                "--master="+masterAddr, 
                "--leader-elect=true",
                "--v=2"]
        extraArgs = getVariableValue("SCHEDULER_EXTRA_ARGS")
        if extraArgs:
            args.extend(extraArgs.split())
        self.__commandArgs.extend([list2str(args)])
        
        args = ["kubelet",
                "--api-servers="+self.__apiServerUrl,
                "--address="+self.__listenAddress,
                "--enable-server",  
                "--hostname-override="+self.__listenAddress, 
                "--kubeconfig=/srv/kubernetes/kubeconfig.yaml",
                "--v=2",
                "--containerized"]
        
        cloudProvider = getVariableValue("CLOUD_PROVIDER")
        cloudConfig = getVariableValue("CLOUD_CONFIG")
         
        if cloudProvider and cloudConfig:
            args.extend(["--cloud-provider="+cloudProvider, "--cloud-config="+cloudConfig])
        
        clusterDns=getVariableValue("CLUSTER_DNS")
        clusterDomain=getVariableValue("CLUSTER_DOMAIN")
        
        if clusterDns:
            args.append(" --cluster-dns="+clusterDns)
        
        if clusterDomain:
            args.append("--cluster-domain="+clusterDomain)
        
        extraArgs = getVariableValue("KUBELET_EXTRA_ARGS")
        if extraArgs:
            args.extend(extraArgs.split())
            
        self.__commandArgs.extend([list2str(args)])
        
        args = [  "proxy", 
                "--master="+self.__apiServerUrl,
                "--bind-address="+self.__listenAddress,
                "--hostname-override=" + self.__listenAddress,
                "--proxy-mode=iptables", 
                "--v=2", 
                "--kubeconfig=/srv/kubernetes/kubeconfig.yaml"]
        
        extraArgs = getVariableValue("PROXY_EXTRA_ARGS")
        if extraArgs:
            args.extend(extraArgs.split())
        self.__commandArgs.extend([list2str(args)])
        
        self.__networkMode = ['--net=host --privileged --pid=host',
                              '--net=host --privileged --pid=host',
                              '--net=host --privileged --pid=host',
                              '--net=host --privileged --pid=host',
                              '--net=host --privileged --pid=host']
        self.__running=[False, False, False, False, False]
        
    def __configureWorkerNode(self):
        hyperkube=getVariableValue("HYPERKUBE_DOCKER_IMAGE",)
       
        kubernetesConfig = getVariableValue("KUBERNETES_DATA_DIR")
        if not kubernetesConfig:
            kubernetesConfig = os.path.join(self.__basedir, "data")
            
        self.__dockerImage = [hyperkube, hyperkube]
        self.__dockerContainerName=["kubelet", "kube-proxy"]
        self.__command = ["/hyperkube", "/hyperkube", ""]
        args=[" --volume=/:/rootfs:ro",
              "--volume=/sys:/sys:ro",
              "--volume=/var/lib/docker/:/var/lib/docker:rw",
              "--volume=/var/lib/kubelet/:/var/lib/kubelet:rw",
              "--volume=/var/run:/var/run:rw",
              "--volume="+kubernetesConfig+":/srv/kubernetes"]
        self.__mountVolumes=[list2str(args), "--volume="+kubernetesConfig+":/srv/kubernetes"]
        
        args = ["kubelet",
                "--api-servers="+self.__apiServerUrl,
                "--address="+self.__listenAddress,
                "--enable-server",  
                "--v=2",
                 "--kubeconfig=/srv/kubernetes/kubeconfig.yaml",
                "--containerized"]
        
        cloudProvider = getVariableValue("CLOUD_PROVIDER")
        cloudConfig = getVariableValue("CLOUD_CONFIG")
         
        if cloudProvider and cloudConfig:
            args.extend(["--cloud-provider="+cloudProvider, "--cloud-config="+cloudConfig])
        
        extraArgs = getVariableValue("KUBELET_EXTRA_ARGS")
        if extraArgs:
            args.extend(extraArgs.split())
        self.__commandArgs = [list2str(args)]
        
        args = [  "proxy", 
                "--master="+self.__apiServerUrl,
                "--bind-address="+self.__listenAddress,
                "--hostname-override=" + self.__listenAddress,
                "--proxy-mode=iptables", 
                "--v=2", 
                "--kubeconfig=/srv/kubernetes/kubeconfig.yaml"]
        
        extraArgs = getVariableValue("PROXY_EXTRA_ARGS")
        if extraArgs:
            args.extend(extraArgs.split())
        self.__commandArgs.extend([list2str(args)])
        
        self.__networkMode = ['--net=host --privileged --pid=host',
                              '--net=host --privileged --pid=host']
        self.__running=[False, False]
    
    def __createFlanneldNetwork(self):
        "create flanneld network"
        
        flanneldNetwork = getVariableValue("FLANNEL_NETWORK", "172.37.0.0/16")
        jsonConfig= '{"Network" : "' + str(flanneldNetwork) + '"}'
        
        logger.info("Json config for flannel network:" + jsonConfig)
        etcdPrefix = getVariableValue("FLANNEL_ETCD_PREFIX", "/coreos.com/network")
        cmdList = ['sudo', 'docker', '-H', self.__dockerBootstrapSock,  "run", "--net=host",  "--name=etcdctl", self.__etcdctlImage]
        cmdList.extend(["--endpoint", self.__etcdEndpoints, "set", etcdPrefix + "/config", jsonConfig ])
        
        logger.info("Executing:" + list2str(cmdList))
        self.__rmBoot("etcdctl")
        retcode = call(cmdList)
        logger.info("Return code" + `retcode`)
         
        if retcode == 0:
            flannelImage = getVariableValue("FLANNEL_DOCKER_IMAGE")
            flanneldCmd = getVariableValue("FLANNELD_CMD_PATH")
            
            ipMasq = getVariableValue("FLANNEL_IPMASQ", "true")
            iface = getVariableValue("FLANNEL_IFACE", "eth0")
            cmdList = ['sudo', 'docker', '-H', self.__dockerBootstrapSock,  "run", "--detach", "--net=host", "--privileged", "--volume=/dev/net:/dev/net", "--name=flannel", flannelImage]
            cmdList.extend([flanneldCmd,"--etcd-endpoints="+self.__etcdEndpoints,  "--etcd-prefix=" + etcdPrefix, "--ip-masq="+ipMasq,"--iface="+iface ])
            logger.info("Run flannel container:" + list2str(cmdList))
            retcode = call(cmdList)
            logger.info("Run flannel container return code:" + `retcode`)
            
            if retcode == 0:
                ntry = 0;
                while ntry < 3:
                    time.sleep(60)
                    ntry+=1
                    cmdList=["sudo", "docker", "-H",   self.__dockerBootstrapSock,  "exec",  "flannel",  "cat",  "/run/flannel/subnet.env"]
                    path = os.path.join(self.__basedir, "subnet.env")
                    file=open(path, "w")
                    logger.info("Run flannel container:" + list2str(cmdList))
                    retcode = call(cmdList, stdout=file)
                    logger.info("Run flannel container return code:" + `retcode`)
                    file.close()
                    if retcode == 0:
                        break
                
                if retcode ==0:
                    file=open(path, "r")
                    flannelSubnet=None
                    flannelMtu=None
                    lines=file.readlines()
                    for line in lines:
                        row = line.split("=")
                        if row[0] == "FLANNEL_SUBNET":
                            flannelSubnet=row[1].strip()
                        elif row[0] == "FLANNEL_MTU":
                            flannelMtu = row[1].strip()
                    if flannelSubnet and flannelMtu:                          
                          os.environ["FLANNEL_SUBNET"]=flannelSubnet
                          os.environ["FLANNEL_MTU"]=flannelMtu
                          bindir=os.path.join(self.__basedir, "bin")
                          cmd=os.path.join(bindir, "configure-daemon.sh")
                          if os.path.isfile(cmd):
                              cmdList=[cmd]
                              logger.info("Executing:" + list2str(cmdList))
                              retcode = call(cmdList)
                              logger.info("Return code:" + `retcode`)
                        
    def __isFlannelContainerRunning(self):
        running = False
        file = None
        try:
            path = os.path.join(self.__basedir , "docker.ps")
            file = open(path, "w")
            cmdList = ["sudo", "docker", "-H",   self.__dockerBootstrapSock, "ps", "--filter", "name=flannel"]
      
            logger.info("Executing:" + list2str(cmdList))
            retcode = call(cmdList, stdout=file)
            logger.info("Return code:" + `retcode`)
            file.close()
            
            file = open(path, "r")
            lines = file.readlines()
            running=len(lines) > 1
            if not running:
                cmdList = ["sudo", "docker", "-H",   self.__dockerBootstrapSock, "rm", "--force", "--volumes", "flannel"]
                logger.info("Docker rm flannel:" + list2str(cmdList))
                retcode = call(cmdList)
                logger.info("Docker rm flannel return code:" + `retcode`)
           
        finally:
            if file:
                file.close()
            
        return running
   
    def __lock(self):
        "get global lock"
        self.__locked = ContainerUtils.acquireGlobalLock(self.__etcdEndpoints, self.__lockExpire, self.__lockWait)
        if not self.__locked:
            raise "Unable to acquire global lock:" + self.__etcdEndpoints
    
    def __unlock(self):
        "unlock global lock"
        if self.__locked:
            ContainerUtils.releaseGlobalLock(self.__etcdEndpoints)
            self.__locked = None
    
    def __writeStats(self):
        "write running container stats output"
        
        file = None
        try:
            for rc in self.__runningContainers:
                cid=rc["Id"]
                path=os.path.join(self.__basedir, cid+".stats")
                file = open(path, "w")
            
                cmdList = ["docker", "-H", self.__dockerAddr, "stats", "--no-stream=true", cid]
                if self.__sudo:
                    cmdList.insert(0, "sudo")
                    retcode = call(cmdList, stdout=file)
        finally:
            if file:
                file.close()

    def __initStats(self):
        self.__dockerStats["Docker CPU Usage %"] = float(0)
        self.__dockerStats["Docker Memory Usage (MB)"] = float(0)
        self.__dockerStats["Docker Memory Limit (MB)"] = float(0)
        self.__dockerStats["Docker Memory Usage %"] = float(0)
        self.__dockerStats["Docker Network Input (MB)"] = float(0)
        self.__dockerStats["Docker Network Output (MB)"] = float(0)
        self.__dockerStats["Docker Block Input (MB)"] = float(0)
        self.__dockerStats["Docker Block Output (MB)"] = float(0)
            
    def __readStats(self):
        "read stats output"
        file = None
        
        try:
            self.__initStats()
            for rc in self.__runningContainers:
                cid=rc["Id"]
                path=os.path.join(self.__basedir, cid+".stats")
                
                if os.path.isfile(path):
                    file = open(path, "r")
                    lines = file.readlines()
                    for line in lines:
                        row = line.replace('%','').replace('/','').split()
                        if row and len(row) == 15:
                            self.__dockerStats["Docker CPU Usage %"] += float(row[1])
                            self.__dockerStats["Docker Memory Usage (MB)"] += convertToMB(row[2], row[3])
                            self.__dockerStats["Docker Memory Limit (MB)"] = max(self.__dockerStats["Docker Memory Limit (MB)"], convertToMB(row[4], row[5]))
                            self.__dockerStats["Docker Memory Usage %"] += float(row[6])
                            self.__dockerStats["Docker Network Input (MB)"] += convertToMB(row[7], row[8])
                            self.__dockerStats["Docker Network Output (MB)"] += convertToMB(row[9], row[10])
                            self.__dockerStats["Docker Block Input (MB)"] += convertToMB(row[11], row[12])
                            self.__dockerStats["Docker Block Output (MB)"] += convertToMB(row[13], row[14])
        except:
            type, value, traceback = sys.exc_info()
            logger.warning("__readStats error:" + `value`)
        finally:
            if file:
                file.close()
                
    def __runBoot(self, index):
        "run boot docker container"
        
        logger.info("Enter __runBoot")
        self.__rmBoot(listItem(self.__dockerContainerName, index))
        cmdList = ["docker", "-H", self.__dockerBootstrapSock,"run", "--detach=true"]
        
        network = listItem(self.__networkMode, index)
        if network:
            cmdList = cmdList + network.split()
            
        mountVolumes = listItem(self.__mountVolumes, index)
        if mountVolumes:
            cmdList = cmdList + mountVolumes.split()
            
        cmdList.append("--name=" + listItem(self.__dockerContainerName, index))
       
        image = listItem(self.__dockerImage, index)
        
        cmdList.append(image)
    
        command = listItem(self.__command, index)
        if command:
            cmdList.append(command)
            
        commandArgs = listItem(self.__commandArgs, index)
        if commandArgs:
            args = commandArgs.split()
            if args:
                cmdList.extend(args)
      
        if self.__sudo:
            cmdList.insert(0, "sudo")
            
        logger.info("Executing:" + list2str(cmdList))
        retcode = call(cmdList)
        logger.info("Return code:" + `retcode`)
        
        if retcode != 0:
            raise Exception("Error return code:" + str(retcode))
            
        logger.info("Exit __runBoot")
        
    def __stopBoot(self, name):
        "stop boot container"
        
        logger.info("Enter __stop")
        cmdList = ["docker", "-H", self.__dockerBootstrapSock,"stop", name]
       
        if self.__sudo:
            cmdList.insert(0, "sudo")
        
        logger.info("Stop docker container:" + list2str(cmdList))
        retcode = call(cmdList)
        logger.info("Stop docker container return code:" + `retcode`)
        
        logger.info("Exit __stop")
    
        
    def __rmBoot(self, name):
        "remove boot container"
        
        logger.info("Enter __rm")
        cmdList = ["docker", "-H", self.__dockerBootstrapSock, "rm", "--force", "--volumes" , name]
        
        if self.__sudo:
            cmdList.insert(0, "sudo")
            
        logger.info("Executing:" + list2str(cmdList))
        retcode = call(cmdList)
        logger.info("Return code:" + `retcode`)
        logger.info("Exit __rm")
        
    def __startFlannelNetwork(self):
        try:
            self.__lock()
            if not self.__isFlannelContainerRunning():
                self.__createFlanneldNetwork()
        finally:
            self.__unlock()
    
    def __setupFiles(self):
        
        bindir=os.path.join(self.__basedir, "bin")
        cmd=os.path.join(bindir, "setup-files.sh")
        if os.path.isfile(cmd):
            cmdList=[cmd]
            logger.info("Executing:" + list2str(cmdList))
            retcode = call(cmdList)
            logger.info("Return code:" + `retcode`)
    
    def __buildAndPush(self, image, dockerContext):
        "build image"
        
        try:
            cmdList = ["docker", "build", "-t", image]
            options = getVariableValue("DOCKER_BUILD_OPTIONS")
            if options:
                cmdList = cmdList + options.split()
                
            if self.__sudo:
                cmdList.insert(0, "sudo")
                
            cmdList.append(dockerContext)
            
            logger.info("Executing:" + list2str(cmdList))
            retcode = call(cmdList)
            logger.info("Return code:" + `retcode`)
            if retcode ==0:
                self.__push(image)
                distutils.dir_util.remove_tree(dockerContext)
                
        except:
            type, value, traceback = sys.exc_info()
            logger.warning("__buildAndPush error:" + `value`)
    
    def __loginRegistry(self, registryServer, registryUsername, registryPassword, registryEmail):
        "login docker registry"
        
        success = False
        try:
            cmdList = ["docker", "login",  
                        "--username=" +registryUsername, 
                        "--password="+registryPassword,
                        "--email="+registryEmail, registryServer]

            if self.__sudo:
                cmdList.insert(0, "sudo")
            
            logger.info("Executing:" + list2str(cmdList))
            retcode = call(cmdList)
            success = (retcode == 0)
            logger.info("Return code:" + `retcode`)
        except:
            type, value, traceback = sys.exc_info()
            logger.warning("__loginRegistry error:" + `value`)
        
        return success
            
    def __push(self, image):
        "push image"
        
        try:
            cmdList = ["docker", "push",  image]

            if self.__sudo:
                cmdList.insert(0, "sudo")
            
            logger.info("Executing:" + list2str(cmdList))
            retcode = call(cmdList)
            logger.info("Return code:" + `retcode`)
        except:
            type, value, traceback = sys.exc_info()
            logger.warning("__push error:" + `value`)
            
    def start(self):
        "start enabler"

        logger.info("Enter start")
        copyContainerEnvironment()
        self.__setupFiles()
        
        self.__startFlannelNetwork()
        llen = len(self.__dockerContainerName)
        for index in range(llen):
            self.__running[index]=self.__isBootContainerRunning(listItem(self.__dockerContainerName, index))
            if not self.__running[index]:
                self.__runBoot(index)
            else:
                if (not self.__isBootContainerValid(index)):
                    forceReconfig = Boolean.parseBoolean(getVariableValue("FORCE_RECONFIG", "true"))
                    if forceReconfig:
                        self.__runBoot(index)
                    else:
                        raise Exception("FORCE_RECONFIG is not 'true' and running Kubernetes master is not using current key store")
                else:
                    logger.info("Using running container:" + listItem(self.__dockerContainerName, index))
        
        logger.info("Exit start")
    
    def stop(self):
        "stop enabler"
        logger.info("Enter stop")
        
        if not self.__detach:
            copyContainerEnvironment()
            for index in range(len(self.__dockerContainerName) - 1, -1, -1):
                self.__stopBoot(listItem(self.__dockerContainerName, index))
            
            bindir=os.path.join(self.__basedir, "bin")
            cmd=os.path.join(bindir, "reset-daemon.sh")
            if os.path.isfile(cmd):
                cmdList=[cmd]
                logger.info("Executing:" + list2str(cmdList))
                retcode = call(cmdList)
                logger.info("Return code:" + `retcode`)
                
            self.__stopBoot("flannel")
            
        logger.info("Exit stop")
         
    def cleanup(self):
        "cleanup"
        
        logger.info("Enter cleanup")
        if not self.__detach:
            copyContainerEnvironment()
            for index in range(len(self.__dockerContainerName) - 1, -1, -1):
                self.__rmBoot(listItem(self.__dockerContainerName, index))
            
            self.__rmBoot("flannel")
            
        logger.info("Exit cleanup")
    
  
                
    def isRunning(self):
        copyContainerEnvironment()  
        
        running = True
        try:
            running = self.__isBootContainerRunning("flannel")
            
            if not running:
                logger.warning("Flannel is not running: Will try to restart Flannel network")
                os.environ['FORCE_RECONFIG']="false"
                self.__createFlanneldNetwork()
                running = self.__isBootContainerRunning("flannel")
            
            if running:
                llen = len(self.__dockerContainerName)
                for index in range(llen):
                    name = listItem(self.__dockerContainerName, index)
                    self.__running[index]=self.__isBootContainerRunning(name)
                    if not self.__running[index]:
                        logger.warning("Will try to restart:"+name)
                        self.__runBoot(index)
                        self.__running[index]=self.__isBootContainerRunning(name)
                        if not self.__running[index]:
                            running = False
                            logger.severe(name + " restart failed!")
                            break
                        
                if running:
                    self.__updateRunningContainers()
            else:
                logger.severe("Flannel restart failed!")
                        
        except:
            type, value, traceback = sys.exc_info()
            logger.warning("isRunning error:" + `value`)
        
        if not running and self.__detach:
            logger.warning("Running condition failed: Ignored because component is running in detached mode")
            
        return self.__detach or running

    def __isBootContainerValid(self, index):
        valid = False
        file = None
        try:
            path = os.path.join(self.__basedir , "docker.inspect")
            file = open(path, "w")
            name=listItem(self.__dockerContainerName, index)
            cmdList = ["docker", "-H",   self.__dockerBootstrapSock, "inspect",  name ]
      
            if self.__sudo:
                cmdList.insert(0, "sudo")
                
            logger.fine("Executing:" + list2str(cmdList))
            retcode = call(cmdList, stdout=file)
            logger.fine("Return code:" + `retcode`)
            file.close()
            
            file = open(path, "r")
            lines = file.readlines()
            
            for line in lines:
                if name == "apiserver":
                     valid = line.find(self.__etcdEndpoints) >= 0
                elif name == "kubelet":
                    valid = line.find(self.__apiServerUrl) >= 0
                if valid:
                    break;
        except:
            type, value, traceback = sys.exc_info()
            logger.warning("__isBootContainerValid error:" + `value`)
        finally:
            if file:
                file.close()
            
        return  valid
    
    def __isBootContainerRunning(self, name):
        file = None
        running = False
        try:
            path = os.path.join(self.__basedir , "docker.ps")
            file = open(path, "w")
            cmdList = ["docker", "-H",   self.__dockerBootstrapSock, "ps", "--filter", "name="+name ]
      
            if self.__sudo:
                cmdList.insert(0, "sudo")
                
            logger.fine("Executing:" + list2str(cmdList))
            retcode = call(cmdList, stdout=file)
            logger.fine("Return code:" + `retcode`)
            file.close()
            
            file = open(path, "r")
            lines = file.readlines()
            running=len(lines) > 1
        finally:
            if file:
                file.close()
        
        return running
    
    
    def hasStarted(self):
        copyContainerEnvironment()  
        
        started = True
        try:
            started = self.__isBootContainerRunning("flannel")
            if started:
                llen = len(self.__dockerContainerName)
                for index in range(llen):
                    self.__running[index]=self.__isBootContainerRunning(listItem(self.__dockerContainerName, index))
                    if not self.__running[index]:
                        started = False
                        break
                    
        except:
            started=False
            type, value, traceback = sys.exc_info()
            logger.warning("hasStarted error:" + `value`)
        
        return True
    
    def __updateActivationInfo(self, info, update=False):
        
        file = None
        file2=None
        try:
            path = os.path.join(self.__basedir , "curl.out")
            file2 = open(path, "w")
        
            path = os.path.join(self.__basedir , "kube.info")
            file = open(path, "w")
            
            cmdList = ["curl", "http://" + self.__dockerAddr +"/info"]
      
            if self.__sudo:
                cmdList.insert(0,"sudo")
            retcode = call(cmdList, stdout=file, stderr=file2)
            file.close()
            file = open(path, "r")
            lines = file.readlines()
           
            if lines and len(lines) >0:
                json = lines[0]
                jsonDict=parseJson(json)
                needUpdate = False
                
                curValue = info.getProperty("DockerContainers")
                newValue = str(jsonDict['Containers'])
                if curValue != newValue:
                    info.setProperty("DockerContainers", newValue)
                    needUpdate = True
                
                curValue = info.getProperty("DockerContainersRunning")
                newValue = str(jsonDict['ContainersRunning'])
                if curValue != newValue:
                    info.setProperty("DockerContainersRunning", newValue)
                    needUpdate = True
                
                curValue = info.getProperty("DockerContainersStopped")
                newValue = str(jsonDict['ContainersStopped'])
                if curValue != newValue:
                    info.setProperty("DockerContainersStopped", newValue)
                    needUpdate = True
                
                curValue = info.getProperty("DockerImages")
                newValue = str(jsonDict['Images'])
                if curValue != newValue:
                    info.setProperty("DockerImages", newValue)
                    needUpdate = True
                    
                if update and needUpdate:
                    proxy.container.updateActivationInfoProperties(info)
        except:
            type, value, traceback = sys.exc_info()
            logger.severe("update activation info error:" + `value`)
        finally:
            if file:
                file.close()
            if file2:
                file2.close()
                
    def installActivationInfo(self, info):
        "install activation info"
        info.setProperty("KubernetesNodeType", self.__nodeType)
        self.__updateActivationInfo(info, update=False)
         
    def __getMainRunningContainers(self):        
        file = None
        file2=None
        try:
            self.__runningContainers=[]
            path = os.path.join(self.__basedir , "curl.out")
            file2 = open(path, "w")
        
            path = os.path.join(self.__basedir , "running.containers")
            file = open(path, "w")
           
            cmdList = ["curl", "http://" + self.__dockerAddr +"/containers/json"]
      
            if self.__sudo:
                cmdList.insert(0,"sudo")
            retcode = call(cmdList, stdout=file, stderr=file2)
            
            file.close()
            file = open(path, "r")
            lines = file.readlines()
            if lines and len(lines) >0:
                json = lines[0]
                containerList=parseJson(json)
                for container in containerList:
                    info={}
                    id=container.get("Id", None)
                    if id:
                        info["Id"]=id
                        self.__runningContainers.append(info)
                    else:
                        logger.warning("Unexpected: id is missing in container info")
        except:
            type, value, traceback = sys.exc_info()
            logger.severe("__getMainRunningContainers error:" + `value`)
        finally:
            if file:
                file.close()
            if file2:
                file2.close()
    
    def __updateRunningContainers(self):
        "update running containers"
        
        self.__getMainRunningContainers()
        self.__writeStats()
        self.__readStats()
        info = proxy.container.getActivationInfo()
        self.__updateActivationInfo(info, update=True)
             
    def getArchive(self, archiveName):
        file = None
        try:
            path = self.__archiveFiles[archiveName]
            if path and os.path.isfile(path):
                file = File(path)
                logger.info("Get archive:"+`path`)
        except:
            type, value, traceback = sys.exc_info()
            logger.severe("getArchive:" + `value`)
            
        return file
    
    def __getImageTag(self, dir):
        file=None
        image=None
        try:
            path=os.path.join(dir, "image-tag")
            if os.path.isfile(path):
                file = open(path)
                lines=file.readlines()
                if len(lines) > 0:
                    image=lines[0]
        except:
            type, value, traceback = sys.exc_info()
            logger.severe("__getImageTag error:" + `value`)
        finally:
            if file:
                file.close()
        
        return image
            
    def __buildImages(self, dir, registryServer, registryUsername, registryPassword, registryEmail):
        
        login=self.__loginRegistry(registryServer, registryUsername, registryPassword, registryEmail)
        
        if login:
            subdirs=[d[0] for d in os.walk(dir)]
            for subdir in subdirs:
                if os.path.isfile(os.path.join(subdir, "Dockerfile")):
                    image=self.__getImageTag(subdir)
                    if not image:
                        raise Exception("image tag not found")
                    self.__buildAndPush(image, subdir)
        else:
            raise Exception("Docker registry login faield")
    
    def __cancelDeploy(self, archiveName, properties):
        try:
            self.archiveUndeploy(archiveName, properties)
        except:
            pass
        finally:
            raise Exception("Archive deploy failed:" + archiveName)
     
    def archiveDeploy(self, archiveName, archiveLocators, properties):
        
        try:
            if self.__nodeType != "master":
                raise Exception("Not Kubernetes master")
            
            archiveZip = str(ContainerUtils.retrieveAndConfigureArchiveFile(proxy.container, archiveName, archiveLocators,  properties))
            if archiveZip[-4:] != ".zip":
                 raise Exception("Archive must be a ZIP file containing Kubernetes YAML or JSON files")
             
            logger.info("Deploying archive:" + archiveZip)
            
            project = getArchiveDeployProperty("project-name", properties,  None)
            if not project:
                raise Exception("project-name deploy property is required")
             
            dir = os.path.join(self.__deploydir,  archiveName, project)
            if os.path.isdir(dir):
                raise Exception("Archive is already deployed: undeploy before new deploy")
            extractZip(archiveZip, dir)
             
            registryServer=getArchiveDeployProperty("registry-server", properties,  None)
            registryUsername=getArchiveDeployProperty("registry-username", properties,  None)
            registryPassword=getArchiveDeployProperty("registry-password", properties,  None)
            registryEmail=getArchiveDeployProperty("registry-email", properties,  None)
           
            if registryServer and registryUsername and registryPassword and registryEmail:
                self.__buildImages(dir, registryServer, registryUsername, registryPassword, registryEmail)
            else:
                logger.info("Skipping build images phase: Not applicable")
            
            self.__archiveFiles[archiveName]=archiveZip
        except:
           self.__cancelDeploy(archiveName, properties)
            
    def archiveUndeploy(self, archiveName,  properties):
        try:
            if self.__nodeType != "master":
                raise Exception("Not a Kubernetes master")

            logger.info("Undeploying archive:" + archiveName)
            project = getArchiveDeployProperty("project-name", properties,  None)
            
            if not project:
                raise Exception("project-name deploy property is required")
         
            dir = os.path.join(self.__deploydir,  archiveName, project )
            if os.path.isdir(dir):
                self.__archiveFiles.pop(archiveName, None)
                distutils.dir_util.remove_tree(dir)
                path = os.path.join(self.__deploydir,  archiveName)
                os.rmdir(path)
        except:
            type, value, traceback = sys.exc_info()
            logger.severe("archiveUndeploy error:" + `value`)
            raise
      
        
    def archiveStart(self, archiveName,  properties):
        
        archiveActivationInfo = None
        try:
            if self.__nodeType != "master":
                raise Exception("Not a Kubernetes master")
            
            logger.info("Starting archive:" + archiveName)
            project = getArchiveDeployProperty("project-name", properties,  None)
            if not project:
                raise Exception("project-name deploy property is required")
          
            dir = os.path.join(self.__deploydir,  archiveName, project)
            if not os.path.isdir(dir):
                raise Exception("Archive is not deployed:" + archiveName)
            
            insecureUrl="http://"+self.__insecureAddress + ":"+ self.__insecurePort
            kubectlImage = getVariableValue("KUBECTL_DOCKER_IMAGE")
            
            orderList=None
            createOrder = getArchiveDeployProperty("create-order", properties,  None)
            if createOrder:
                orderList=createOrder.split(",")
                
            if orderList:
                for file in orderList:
                    cmdList = ['sudo', 'docker', '-H', self.__dockerBootstrapSock,  "run", "--net=host",  "--volume="+dir+":/spec-data", "--name=kubectl", kubectlImage]
                    cmdList.extend(["--server", insecureUrl,  "create", "-f", "/spec-data/"+file])
                    logger.info("Executing:" + list2str(cmdList))
                    self.__rmBoot("kubectl")
                    retcode = call(cmdList)
                    logger.info("Return code" + `retcode`)
                    if retcode != 0:
                        break
            else:
                cmdList = ['sudo', 'docker', '-H', self.__dockerBootstrapSock,  "run", "--net=host",  "--volume="+dir+":/spec-data", "--name=kubectl", kubectlImage]
                cmdList.extend(["--server", insecureUrl,  "create", "-f", "/spec-data"])
                logger.info("Executing:" + list2str(cmdList))
                self.__rmBoot("kubectl")
                retcode = call(cmdList)
                logger.info("Return code" + `retcode`)
           
            if retcode == 0:
                archiveActivationInfo = ArchiveActivationInfo(archiveName, project)
            else:
                raise Exception("Archive start failed")
          
        except:
            type, value, traceback = sys.exc_info()
            logger.severe("archiveStart error:" + `value`)
            raise
        
        return archiveActivationInfo
        
    def archiveStop(self, archiveName,  archiveId, properties):
        try:
            if self.__nodeType != "master":
                raise Exception("Not a Kubernetes master")

            logger.info("Stopping archive:" + archiveName)
            project = getArchiveDeployProperty("project-name", properties,  None)
            if not project:
                raise Exception("project-name deploy property is required")
         
            dir = os.path.join(self.__deploydir,  archiveName, project )
            if os.path.isdir(dir):
                kubectlImage = getVariableValue("KUBECTL_DOCKER_IMAGE")
                insecureUrl="http://"+self.__insecureAddress + ":"+ self.__insecurePort
                cmdList = ['sudo', 'docker', '-H', self.__dockerBootstrapSock,  "run", "--net=host",  "--volume="+dir+":/spec-data", "--name=kubectl", kubectlImage]
                cmdList.extend(["--server", insecureUrl,  "delete", "-f", "/spec-data"])
        
                logger.info("Executing:" + list2str(cmdList))
                self.__rmBoot("kubectl")
                retcode = call(cmdList)
                logger.info("Return code" + `retcode`)
                if retcode != 0:
                    raise Exception("Archive stop failed:" + archiveName)
        except:
            type, value, traceback = sys.exc_info()
            logger.severe("archiveStop error:" + `value`)
            raise
    
    def __detectYaml(self, path):
        file = None
        map={"namespace" :"default"}
        try:
            file=open(path, "r")
            lines=file.readlines()
            metadata=False
            for line in lines:
                kv=line.split(":")
                if len(kv) < 2:
                    continue
                
                key=kv[0].strip()
                value=kv[1].strip()
                if key:
                    indent = len(line) - len(line.lstrip(' '))
                    if indent == 0 and (key == "apiVersion" or key == "kind"):
                        map[key]=value
                    elif indent == 0 and key == "metadata":
                        metadata = True
                    elif metadata and (key == "name" or key == "namespace"):
                        map[key]=value
                    elif metadata and indent == 0:
                        break;
        except:
            type, value, traceback = sys.exc_info()
            logger.severe("__detectYaml error:" + `value`)
        finally:
            if file:
                file.close()
        return map
    
    def __detectJson(self, path):
        "detect Json"
        file = None
        map={"namespace" :"default"}
        try:
            file=open(path, "r")
            lines=file.readlines()
            json=""
            for line in lines:
                json = json + " " + line
            
            if len(json) > 0:
                dict=parseJson(json)
                map["kind"]=dict["kind"]
                map["apiVersion"]=dict["apiVersion"]
                metadata=dict["metadata"]
                map["name"]=metadata.get("name")
                map["namespace"]=metadata.get("namespace", "default")
        except:
            type, value, traceback = sys.exc_info()
            logger.severe("__detectJson error:" + `value`)
        finally:
            if file:
                file.close()
                
        return map
    
    def __detectFile(self, path):
        map=None
        try:
            list=path.rsplit(".",1)
            if list and len(list) == 2:
                suffix = str(list[1]).lower()
                if suffix == "yaml" or suffix == "yml":
                    map= self.__detectYaml(path)
                elif suffix == "json":
                    map = self.__detectJson(path)
        except:
            type, value, traceback = sys.exc_info()
            logger.severe("__detectJsonKind error:" + `value`)
        
        return map
    
    def __verifyResource(self, map):
        "verify context"
        file = None
        file2=None
        verified = False
        
        try:
            namespace=map.get("namespace", "default")
            name=map["name"]
            kind=map["kind"]
            apiVersion=map.get("apiVersion", "v1")
            
            path = os.path.join(self.__basedir , "curl.out")
            file2 = open(path, "w")
        
            path = os.path.join(self.__basedir , kind+".json")
            file = open(path, "w")
            
            insecureUrl="http://"+self.__insecureAddress + ":"+ self.__insecurePort
            resource="/api/"+ apiVersion + "/namespaces/" + namespace + "/"+kind.lower() +"s/"+name
            cmdList = ["curl", insecureUrl+ resource]
      
            if self.__sudo:
                cmdList.insert(0,"sudo")
            retcode = call(cmdList, stdout=file, stderr=file2)
            file.close()
        
            map=self.__detectFile(path)
            verified = (map.get("kind") == kind and map.get("name") == name)
        except:
            type, value, traceback = sys.exc_info()
            logger.severe("__verifyResource error:" + `value`)
        finally:
            if file:
                file.close()
            if file2:
                file2.close()
        
        return verified
        
    def archiveDetect(self):
        archiveDetail=[]
        try:
            if self.__nodeType == "master":
                archives=[ name for name in os.listdir(self.__deploydir) if os.path.isdir(os.path.join(self.__deploydir, name)) ]
                for archive in archives:
                    dir = os.path.join(self.__deploydir, archive)
                    if os.path.isdir(dir):
                        projects=[ name for name in os.listdir(dir) if os.path.isdir(os.path.join(dir, name)) ]
                        for project in projects:
                            projectdir=os.path.join(dir, project)
                            if os.path.isdir(projectdir):
                                files = [f for f in os.listdir(projectdir) if os.path.isfile(os.path.join(projectdir, f))]
                                running=[]
                                for file in files:
                                    path=os.path.join(projectdir, file)
                                    dict=self.__detectFile(path)
                                    if dict:
                                        kind=dict.get("kind")
                                        name=dict.get("name")
                                        namespace=dict.get("namespace","default")
                                        apiVersion=dict.get("apiVersion","v1")
                                        if kind and name and self.__verifyResource(dict):
                                            resource="/api/"+ apiVersion + "/namespaces/" + namespace + "/"+kind.lower() +"s/"+name
                                            running.append(resource)
                                if len(running) > 0:
                                    logger.fine("Detected deployed archive:"+ archive +":"+ project +":running:"+ str(running))
                                    archiveDetail.append(ArchiveDetail(archive, True, False, list2str(running)))
        except:
            type, value, traceback = sys.exc_info()
            logger.severe("archiveDetect error:" + `value`)
        
        return array(archiveDetail, ArchiveDetail)
    
   
    def getStat(self, statName):
        " get statistic"
        return self.__dockerStats[statName]

def changePermissions(dir):
    logger.info("chmod:" + dir)
    os.chmod(dir, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
      
    for dirpath, dirnames, filenames in os.walk(dir):
        for dirname in dirnames:
            dpath = os.path.join(dirpath, dirname)
            os.chmod(dpath, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
           
        for filename in filenames:
               filePath = os.path.join(dirpath, filename)
               os.chmod(filePath, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                

def convertToMB(value, unit):
    unit = unit.lower()
    value = float(value)
    if unit == "gb":
        value = value * 1000.0
    elif unit == "b":
        value = value / 1000.0
        
    return value
    
def parseJson(json):
    json=json.replace('null','None')
    json=json.replace('false','False')
    json=json.replace('true','True')
    jsonObject=ast.literal_eval(json.strip())
    return jsonObject
    
def parseJsonDictionary(map, select, output):
    for key,value in map.iteritems():
        if key == select:
            output.append(value)
        elif type(value) is dict:
            parseJsonDictionary(value,select, output)
        elif type(value) is list:
            parseJsonList(value, select, output)

def parseJsonList(itemlist, select, output):
           
    for item in itemlist:
        if type(item) is dict:
            parseJsonDictionary(item, select, output)
        elif type(item) is list:
            parseJsonList(item, select, output)
        else:
            if len(itemlist) == 2:
                if itemlist[0] == select:
                    output.append(itemlist[1])
                break

def getArchiveDeployProperty(name, properties, default, parse=False):
    value = default
    
    try:
        if properties:
            value = properties.getProperty(name)
            if value and parse:
                value = Boolean.parseBoolean(value)
    except:
        pass
    
    return value

def extractZip(zip, dest):
    "extract zip archive to dest directory"
    
    logger.info("Begin extracting:" + zip + " --> " +dest)
    mkdir_p(dest)
    zipfile = ZipFile(zip)

    entries = zipfile.entries()
    while entries.hasMoreElements():
        entry = entries.nextElement()

        if entry.isDirectory():
            mkdir_p(os.path.join(dest, entry.name))
        else:
            newFile = File(dest, entry.name)
            mkdir_p(newFile.parent)
            zis = zipfile.getInputStream(entry)
            fos = FileOutputStream(newFile)
            nread = 0
            buffer = ByteBuffer.allocate(1024)
            while True:
                nread = zis.read(buffer.array(), 0, 1024)
                if nread <= 0:
                        break
                fos.write(buffer.array(), 0, nread)

            fos.close()
            zis.close()

    logger.info("End extracting:" + str(zip) + " --> " + str(dest))
     
     
def isUUID(uuid_string):
    valid = False
    try:
        val = UUID(uuid_string)
        valid = True
    except ValueError:
        valid = False

    return valid

def ping(host, port):
    success = False
    s = None
    try:
        s = socket.socket()
        s.connect((host, int(port)))
        success = True
    except:
        type, value, traceback = sys.exc_info()
        logger.fine("ping failed:" + `value`)
    finally:
        if s:
            s.close()
    
    return success
    
def listItem(list, index, useDefault=False):
    item = None
    if list:
        llen = len(list)
        if llen > index:
            item = list[index].strip()
        elif useDefault and llen == 1:
            item = list[0].strip()
    
    return item

def list2str(list):
    content = str(list).strip('[]')
    content =content.replace(",", " ")
    content =content.replace("u'", "")
    content =content.replace("'", "")
    return content

def mkdir_p(path, mode=0700):
    if not os.path.isdir(path):
        logger.info("Creating directory:" + path)
        os.makedirs(path, mode)
        
def copyContainerEnvironment():
    count = runtimeContext.variableCount
    for i in range(0, count, 1):
        rtv = runtimeContext.getVariable(i)
        if rtv.type == "Environment":
            os.environ[rtv.name] = rtv.value
    
    os.unsetenv("LD_LIBRARY_PATH")
    os.unsetenv("LD_PRELOAD")
    
def getVariableValue(name, value=None):
    "get runtime variable value"
    var = runtimeContext.getVariable(name)
    if var != None:
        value = var.value
    
    return value

def doInit(additionalVariables):
    "do init"
    docker = Kubernetes(additionalVariables)
             
    # save mJMX MBean server as a runtime context variable
    dockerRcv = RuntimeContextVariable("KUBERNETES_OBJECT", docker, RuntimeContextVariable.OBJECT_TYPE)
    runtimeContext.addVariable(dockerRcv)


def doStart():
    docker = getVariableValue("KUBERNETES_OBJECT")
        
    if docker:
        docker.start()
    
def doShutdown():
    try:
        docker = getVariableValue("KUBERNETES_OBJECT")
        
        if docker:
            docker.stop()
    except:
        type, value, traceback = sys.exc_info()
        logger.severe("Unexpected error in Kubernetes:doShutdown:" + `value`)
    finally:
        proxy.doShutdown()
    
def hasContainerStarted():
    started = False
    try:
        docker = getVariableValue("KUBERNETES_OBJECT")
        
        if docker:
            started = docker.hasStarted()
            if started:
                logger.info("Kubernetes node has started!")
            else:
                logger.info("Kubernetes node starting...")
    except:
        type, value, traceback = sys.exc_info()
        logger.severe("Unexpected error in Kubernetes:hasContainerStarted:" + `value`)
    
    return started

def cleanupContainer():
    try:
        docker = getVariableValue("KUBERNETES_OBJECT")
        
        if docker:
            docker.cleanup()
    except:
        type, value, traceback = sys.exc_info()
        logger.severe("Unexpected error in Kubernetes:cleanup:" + `value`)
    finally:
        proxy.cleanupContainer()
            
    
def isContainerRunning():
    running = False
    try:
        docker = getVariableValue("KUBERNETES_OBJECT")
        if docker:
            running = docker.isRunning()
    except:
        type, value, traceback = sys.exc_info()
        logger.severe("Unexpected error in Kubernetes:isContainerRunning:" + `value`)
    
    return running

def doInstall(info):
    " do install of activation info"

    logger.info("doInstall:Enter")
    try:
        docker = getVariableValue("KUBERNETES_OBJECT")
        if docker:
            docker.installActivationInfo(info)
    except:
        type, value, traceback = sys.exc_info()
        logger.severe("Unexpected error in Kubernetes:doInstall:" + `value`)
    finally:
        proxy.doInstall(info)
        
    logger.info("doInstall:Exit")
    
def getContainerStartConditionPollPeriod():
    poll = getVariableValue("START_POLL_PERIOD", "10000")
    return int(poll)
    
def getContainerRunningConditionPollPeriod():
    poll = getVariableValue("RUNNING_POLL_PERIOD", "60000")
    return int(poll)


def archiveDeploy(name, locators,properties):
    "archive deploy"

    logger.info("archiveDeploy:Enter")
    docker = getVariableValue("KUBERNETES_OBJECT")
    if docker:
        docker.archiveDeploy(name, locators, properties)
        
    logger.info("archiveDeploy::Exit")
    
def archiveUndeploy(name, properties):
    "archive deploy"

    logger.info("archiveUndeploy:Enter")
    docker = getVariableValue("KUBERNETES_OBJECT")
    if docker:
         docker.archiveUndeploy(name, properties)
  
    logger.info("archiveUndeploy::Exit")
    
def archiveStart(name, properties):
    "archive start"

    docker = getVariableValue("KUBERNETES_OBJECT")
    if docker:
        return docker.archiveStart(name, properties)
    
def archiveDetect():
    "archive detect"

    docker = getVariableValue("KUBERNETES_OBJECT")
    if docker:
        return docker.archiveDetect()
    
def getArchive(name):
    "get archive"

    file=None
    docker = getVariableValue("KUBERNETES_OBJECT")
    if docker:
        file=docker.getArchive(name)
        
    return file
        
def archiveStop(name, id, properties):
    "archive stop"

    logger.info("archiveStart:Enter")
    docker = getVariableValue("KUBERNETES_OBJECT")
    if docker:
        docker.archiveStop(name, id, properties)
        
    logger.info("archiveStop::Exit")


def getStatistic(statName):
    stat = None
    try:
        docker = getVariableValue("KUBERNETES_OBJECT")
        if docker:
            stat = docker.getStat(statName)
    except:
        type, value, traceback = sys.exc_info()
        logger.severe("Unexpected error in Kubernetes:getStatistic:" + `value`)
    return stat

