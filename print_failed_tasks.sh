#!/bin/bash

set -e

BASE_DIR=$(dirname $(readlink -e $0))
. $BASE_DIR/common.sh

if [[ $# != 2 ]]; then
    echo "Usage: $0 cli_venv cli_dir"
    exit 1
fi

VENV_PATH=$(absolute_path $1)
CLOUDIFY_PATH=$(absolute_path $2)


activate_cli $CLOUDIFY_PATH $VENV_PATH
python $BASE_DIR/print_failed_tasks.py

