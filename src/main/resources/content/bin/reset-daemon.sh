#!/bin/sh

exitCode=0
cat "$DOCKER_CONFIG_PATH"

if grep -q "$DOCKER_BRIDGE" "$DOCKER_CONFIG_PATH"; then
	echo "$DOCKER_CONFIG_PATH is already configured with $DOCKER_BRIDGE"
elif grep -q "$DOCKER_BRIDGE" "$DOCKER_CONFIG_PATH"; then
	echo "$DOCKER_CONFIG_PATH is already configured with $DOCKER_BRIDGE"
elif [ "$FORCE_RECONFIG" = "true" ]; then

	echo "sudo systemctl stop docker"
	sudo systemctl stop docker
	
	# Delete  existing FLANNEL_BRIDGE
	echo "sudo ip link set dev $FLANNEL_BRIDGE down"
	sudo ip link set dev $FLANNEL_BRIDGE down

	echo "sudo brctl delbr $FLANNEL_BRIDGE"
	sudo brctl delbr $FLANNEL_BRIDGE

	echo "Reset main docker daemon"
	sed "s/-b=\([a-zA-Z0-9]\)*/-b=$DOCKER_BRIDGE/g"  "$DOCKER_CONFIG_PATH" > /tmp/docker.config.1
	sed "s/--bridge=\([a-zA-Z0-9]\)*/--bridge=$DOCKER_BRIDGE/g"  /tmp/docker.config.1  > /tmp/docker.config.2
	sed "s/--bip=\([0-9\.]\)*//g"  /tmp/docker.config.2  > /tmp/docker.config.3

	if [ $? -eq 0 ]; then
		sudo cp  /tmp/docker.config.3 $DOCKER_CONFIG_PATH
		sudo rm /tmp/docker.config.*

		echo "sudo systemctl start docker"	
		sudo systemctl start docker
	else
		exitCode=1
	fi
else
	echo "Docker daemon needs to be reset, but FORCE_RECONFIG is not set to 'true'"
	exitCode=1
fi


cat "$DOCKER_CONFIG_PATH"
exit $exitCode