#!/bin/bash

set -e

BASE_DIR=$(dirname $(readlink -e $0))
. $BASE_DIR/common.sh

function usage_exit {
    error "Usage: $SCRIPT_NAME [-o (install|uninstall)] cli_venv cli_dir" 1
}

OPERATION_ID=uninstall
while getopts o: opt; do
    case $opt in
        o)
            OPERATION_ID=$OPTARG
            ;;
        \?)
            usage_exit
            ;;
    esac
done
shift $((OPTIND - 1))

case $OPERATION_ID in
    install)
        WORKFLOW_ID=hosts_software_install
        ;;
    uninstall)
        WORKFLOW_ID=hosts_software_uninstall
        ;;
    *)
        usage_exit
        ;;
esac


if [[ $# != 2 ]]; then
    usage_exit
fi

VENV_PATH=$(absolute_path $1)
CLOUDIFY_PATH=$(absolute_path $2)


activate_cli $CLOUDIFY_PATH $VENV_PATH
python $BASE_DIR/print_failed_tasks.py $WORKFLOW_ID

