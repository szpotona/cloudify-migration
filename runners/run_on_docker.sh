#!/bin/bash
set -eax

DOCKER_ID=`sudo docker ps -q`
DOCKER_PATH=`sudo find /var/lib/docker/devicemapper/mnt/ -name "$DOCKER_ID*" | grep "$DOCKER_ID[a-fA-F0-9]*$"`

sudo mkdir -p $DOCKER_PATH/rootfs/tmp/script
sudo cp $1 $DOCKER_PATH/rootfs/tmp/script/script.tar.gz
sudo tar -xf $DOCKER_PATH/rootfs/tmp/script/script.tar.gz -C $DOCKER_PATH/rootfs/tmp/script/
sudo docker exec $DOCKER_ID /bin/bash -c "cd /tmp/script; ./run.sh"

