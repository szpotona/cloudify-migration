 #!/bin/bash

set -e

BASE_DIR=$(dirname $(readlink -e $0))
. $BASE_DIR/common.sh

function cleanup {
    rm -f /tmp/script.tar.gz
}
trap cleanup EXIT

function usage_exit {
    error "Usage: $SCRIPT_NAME [-d deployment_id] (install|uninstall) (3.1|3.2) cli_venv cli_dir [auth_config]" 1
}

#$1 - manager virtualenv path - it depends on version
#$2 - operation - either migration_install or migration_uninstall
#$3 - path to custom authentication configuration
#$4 - result script path
#$5 - optional - deployment id
function prepare_agents_script {
    rm -rf /tmp/agents_script
    mkdir -p /tmp/agents_script
    cp $BASE_DIR/common_agents/* /tmp/agents_script
    cd /tmp/agents_script
    mv run.sh.template run.sh
    sed -i s@__MANAGER_ENV__@$1@ run.sh
    sed -i s@__OPERATION__@$2@ run.sh
    cp $3 auth_config.yaml
    rm -f deployment_id
    if [ -n "$5" ]; then
        echo -n $5 > deployment_id
    fi
    tar -cf $4 *
    cd /tmp
    rm -rf /tmp/agents_script
}

DEPLOYMENT_ID=""
while getopts d: opt; do
    case $opt in
        d)
            DEPLOYMENT_ID=$OPTARG
            ;;
        \?)
            usage_exit
            ;;
    esac
done
shift $((OPTIND - 1))



if [[ $# -lt 4 ]]; then
    usage_exit
fi

case $1 in
    install)
        OPERATION=install
        ;;
    uninstall)
        OPERATION=uninstall
        ;;
    *)
        usage_exit
        ;;
esac

case $2 in
    3.1)
        RUNNER=run_on_manager.sh
        MANAGER_VENV=/opt/manager
        ;;
    3.2)
        RUNNER=run_on_docker.sh
        MANAGER_VENV=/opt/manager/env
        ;;
    *)
        usage_exit
        ;;
esac

VENV_PATH=$(absolute_path $3)
CLOUDIFY_PATH=$(absolute_path $4)
if [[ $# -gt 4 ]]; then
    AUTH_CONFIG_PATH=$(absolute_path $5)
else
    # creating empty dummy config file for simplicity:
    AUTH_CONFIG_PATH=/tmp/auth_config_6534.yaml
    DELETE_AUTH_CONFIG=1
    touch $AUTH_CONFIG_PATH
fi

echo "Preparing operation script"
prepare_agents_script $MANAGER_VENV $OPERATION $AUTH_CONFIG_PATH /tmp/script.tar.gz $DEPLOYMENT_ID
if [[ $DELETE_AUTH_CONFIG -eq 1 ]]; then
    rm $AUTH_CONFIG_PATH
fi
echo "Operation script prepared, running operation $OPERATION"
activate_cli $CLOUDIFY_PATH $VENV_PATH
supplement_credentials $2
run_operation /tmp/script.tar.gz $RUNNER
echo "Operation $OPERATION completed"

