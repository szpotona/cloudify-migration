#!/bin/bash
set -ea

function cleanup {
    rm -rf /tmp/script
}
trap cleanup EXIT

mkdir -p /tmp/script
cp $1 /tmp/script/script.tar.gz
tar -xf /tmp/script/script.tar.gz -C /tmp/script/
/bin/bash -c "cd /tmp/script; ./run.sh"
