#!/bin/bash
set -ea

function cleanup {
    rm -rf ~/script
}
trap cleanup EXIT

mkdir -p ~/script
tar -xf $1 -C ~/script
sudo docker exec cfy /bin/bash -c "cd /tmp/home/script; ./run.sh"
