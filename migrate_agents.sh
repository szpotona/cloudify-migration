 #!/bin/bash

set -e

BASE_DIR=$(dirname $(readlink -e $0))
. $BASE_DIR/common.sh

function cleanup {
    rm -f /tmp/script.tar.gz
}
trap cleanup EXIT

function usage_exit {
    error "Usage: $SCRIPT_NAME (install|uninstall) (3.1|3.2) cli_venv cli_dir" 1
}

#$1 - manager virtualenv path - it depends on version
#$2 - operation - either migration_install or migration_uninstall
#$3 - result script path
function prepare_agents_script {
    mkdir -p /tmp/agents_script
    cp $BASE_DIR/common_agents/* /tmp/agents_script
    cd /tmp/agents_script
    mv run.sh.template run.sh
    sed -i s@__MANAGER_ENV__@$1@ run.sh
    sed -i s@__OPERATION__@$2@ run.sh
    tar -cvf $3 *
    cd /tmp
    rm -rf /tmp/agents_script
}

if [[ $# != 4 ]]; then
    usage_exit
fi

case $1 in
    install)
        OPERATION=migration_install
        ;;
    uninstall)
        OPERATION=migration_uninstall
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

prepare_agents_script $MANAGER_VENV $OPERATION /tmp/script.tar.gz
activate_cli $CLOUDIFY_PATH $VENV_PATH
run_operation /tmp/script.tar.gz $RUNNER
