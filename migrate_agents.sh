 #!/bin/bash

set -e

BASE_DIR=$(dirname $(readlink -e $0))
. $BASE_DIR/common.sh

function cleanup {
    rm -rf $SCRIPT_PATH $TMP_DIR $DELETE_AUTH_CONFIG_PATH
}
trap cleanup EXIT

function usage_exit {
    error "Usage: $SCRIPT_NAME [-d deployment_id] [-n attempts_limit] (install|uninstall) (3.1|3.2|3.2.1|auto) cli_venv cli_dir [auth_config]" 1
}

#$1 - manager virtualenv path - it depends on version
#$2 - operation - either migration_install or migration_uninstall
#$3 - path to custom authentication configuration
#$4 - result script path
#$5 - number of failed tasks
#$6 - optional - deployment id
function prepare_agents_script {
    TMP_DIR=$(mktemp -d)
    cp $BASE_DIR/common_agents/* $TMP_DIR
    cd $TMP_DIR
    mv run.sh.template run.sh
    sed -i s@__MANAGER_ENV__@$1@ run.sh
    sed -i s@__OPERATION__@$2@ run.sh
    sed -i s@__MAX_ATTEMPTS__@$5@ run.sh
    cp $3 auth_config.yaml
    if [ -n "$6" ]; then
        echo -n $6 > deployment_id
    fi
    tar -cf $4 *
    cd -
}

DEPLOYMENT_ID=""
MAX_ATTEMPTS=-1
while getopts d:n: opt; do
    case $opt in
        d)
            DEPLOYMENT_ID=$OPTARG
            ;;
        n)
            MAX_ATTEMPTS=$OPTARG
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

VENV_PATH=$(absolute_path $3)
CLOUDIFY_PATH=$(absolute_path $4)

if [[ $# -gt 4 ]]; then
    AUTH_CONFIG_PATH=$(absolute_path $5)
else
    # creating empty dummy config file for simplicity:
    AUTH_CONFIG_PATH=$(mktemp)
    DELETE_AUTH_CONFIG_PATH=$AUTH_CONFIG_PATH
fi

activate_cli $CLOUDIFY_PATH $VENV_PATH

VERSION=$2
if [[ "$VERSION" == "auto" ]]; then
    VERSION=$(get_manager_version)
fi

EXPECTED_VERSION=$(get_manager_version)
if [ "$VERSION" != "$EXPECTED_VERSION" ]; then
    DECL_MSG="Declared manager version: ${VERSION}."
    REAL_MSG="Real manager version: ${EXPECTED_VERSION}."
    error "Wrong manager version supplied. $DECL_MSG $REAL_MSG" 1
fi

case $VERSION in
    3.1)
        RUNNER=run_on_manager.sh
        MANAGER_VENV=/opt/manager
        ;;
    3.2 | 3.2.1)
        RUNNER=run_on_docker.sh
        MANAGER_VENV=/opt/manager/env
        ;;
    *)
        echo "Unsupported version: $VERSION"
        usage_exit
        ;;
esac

echo "Preparing operation script"
SCRIPT_PATH=$(mktemp)
prepare_agents_script $MANAGER_VENV $OPERATION $AUTH_CONFIG_PATH $SCRIPT_PATH $MAX_ATTEMPTS $DEPLOYMENT_ID
echo "Operation script prepared, running operation $OPERATION"
supplement_credentials $2
run_operation $SCRIPT_PATH $RUNNER
echo "Operation $OPERATION completed"

