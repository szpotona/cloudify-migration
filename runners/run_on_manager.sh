#!/bin/bash
set -eax


mkdir -p /tmp/script
cp $1 /tmp/script/script.tar.gz
tar -xf /tmp/script/script.tar.gz -C /tmp/script/
/bin/bash -c "cd /tmp/script; ./run.sh"
rm -rf /tmp/script

