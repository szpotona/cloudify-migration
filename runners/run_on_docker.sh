#!/bin/bash
set -ea

mkdir -p ~/script
cp $1 ~/script/script.tar.gz
cd ~/script
tar -xf script.tar.gz
sudo docker exec cfy /bin/bash -c "cd /tmp/home/script; ./run.sh"
cd ~
sudo rm -rf ~/script

