#!/bin/sh

exitCode=0
cat "$DOCKER_CONFIG_PATH"

if grep -q "$FLANNEL_BRIDGE" "$DOCKER_CONFIG_PATH"; then
	echo "$DOCKER_CONFIG_PATH is already configured with Flannel bridge"
elif grep -q "$FLANNEL_BRIDGE" "$DOCKER_CONFIG_PATH"; then
	echo "$DOCKER_CONFIG_PATH is already configured with Flannel bridge"
elif [ "$FORCE_RECONFIG" = "true" ]; then

	# Delete any existing bridge with the same name as FLANNEL_BRIDGE
	echo "sudo ip link set dev $FLANNEL_BRIDGE down"
	sudo ip link set dev $FLANNEL_BRIDGE down

	echo "sudo brctl delbr $FLANNEL_BRIDGE"
	sudo brctl delbr $FLANNEL_BRIDGE

	# Create a new bridge, add flannel subnet ip addr, set flannel mtu, and bring it up
	echo "sudo brctl addbr $FLANNEL_BRIDGE"
	sudo brctl addbr $FLANNEL_BRIDGE

	echo "sudo ip addr add $FLANNEL_SUBNET  dev  $FLANNEL_BRIDGE"
	sudo ip addr add $FLANNEL_SUBNET  dev  $FLANNEL_BRIDGE

	echo "sudo ip link set dev  $FLANNEL_BRIDGE mtu $FLANNEL_MTU"
	sudo ip link set dev  $FLANNEL_BRIDGE mtu $FLANNEL_MTU

	echo "sudo ip link set dev  $FLANNEL_BRIDGE up"
	sudo ip link set dev  $FLANNEL_BRIDGE up

	echo "Force reconfiguration of main docker daemon"
	sed "s/-b=\([a-zA-Z0-9]\)*/-b=$FLANNEL_BRIDGE/g"  "$DOCKER_CONFIG_PATH" > /tmp/docker.config.1
	sed "s/--bridge=\([a-zA-Z0-9]\)*/--bridge=$FLANNEL_BRIDGE/g"  /tmp/docker.config.1  > /tmp/docker.config.2
	sed "s/--bip=\([0-9\.]\)*//g"  /tmp/docker.config.2  > /tmp/docker.config.3

	if [ $? -eq 0 ]; then
		sudo cp  /tmp/docker.config.3 $DOCKER_CONFIG_PATH
		sudo rm /tmp/docker.config.*

		echo "sudo systemctl stop docker"
		sudo systemctl stop docker
		
		sleep 5
		echo "sudo systemctl start docker"	
		sudo systemctl start docker
	else
		exitCode=1
	fi
else
	echo "Docker daemon is not using $FLANNEL_BRIDGE bridge and FORCE_RECONFIG is not set to 'true'"
	exitCode=1
fi


cat "$DOCKER_CONFIG_PATH"
exit $exitCode