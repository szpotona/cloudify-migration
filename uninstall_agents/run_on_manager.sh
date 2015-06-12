#!/bin/bash
set -eax


sudo mkdir -p /tmp/script
sudo cp $1 /tmp/script/script.tar.gz
sudo tar -xf /tmp/script/script.tar.gz -C /tmp/script/
sudo /bin/bash -c "cd /tmp/script; ./run.sh"

