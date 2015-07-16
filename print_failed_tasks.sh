#!/bin/bash

set -e

BASE_DIR=$(dirname $(readlink -e $0))
. $BASE_DIR/common.sh

function usage_exit {
    error "Usage: $SCRIPT_NAME [-w workflow_id] cli_venv cli_dir" 1
}

WORKFLOW_ID=hosts_software_uninstall
while getopts w: opt; do
    case $opt in
        w)
            WORKFLOW_ID=$OPTARG
            ;;
        \?)
            usage_exit
            ;;
    esac
done
shift $((OPTIND - 1))

if [[ $# != 2 ]]; then
    usage_exit
fi

VENV_PATH=$(absolute_path $1)
CLOUDIFY_PATH=$(absolute_path $2)


activate_cli $CLOUDIFY_PATH $VENV_PATH
python $BASE_DIR/print_failed_tasks.py $WORKFLOW_ID
