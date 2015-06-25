#!/bin/bash
set -ea

mkdir -p ~/script
tar -xf $1 -C ~/script
sudo docker exec cfy /bin/bash -c "cd /tmp/home/script; ./run.sh"
sudo rm -rf ~/script
