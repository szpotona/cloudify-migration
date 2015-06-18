 #!/bin/bash

set -e

. common.sh

SCRIPT_NAME=$0

function usage {
    echo "Usage: $SCRIPT_NAME old_cli_venv old_cli_dir new_cli_venv new_cli_dir"
}

if [[ $# != 4 ]]; then
    usage
    error "Wrong number of parameters" 2
fi

OLD_CLI_PYTHON_VIRTENV=$(absolute_path $1)  # Directory of the virtualenv which is utilized by Cloudify CLI to manage the old manager
OLD_CLI_DIR=$(absolute_path $2)             # Location of the .cloudify directory initialized by Cloudify CLI to manage the old manager
NEW_CLI_PYTHON_VIRTENV=$(absolute_path $3)  # Directory of the virtualenv which is utilized by Cloudify CLI to manage the new manager
NEW_CLI_DIR=$(absolute_path $4)             # Location of the .cloudify directory initialized by Cloudify CLI to manage the new manager

BASE_DIR=$PWD

#  Usage:
#  upload_to_manager what where
# To choose the manager, activate the appropriate CLI
function upload_to_manager {
    python $BASE_DIR/scp.py $1 $2 upload
}
 
#  $1 - either install_agents or uninstall_agents
function prepare_agents_script {
    mkdir -p /tmp/agents_installer
    cp $BASE_DIR/$1/* /tmp/agents_installer
    cp $BASE_DIR/common_agents/* /tmp/agents_installer
    cd /tmp/agents_installer
    tar -cvf /tmp/script.tar.gz *
    cd /tmp
    rm -rf /tmp/agents_installer
}

function install_agents {
    prepare_agents_script install_agents
    activate_new_cli
    upload_to_manager /tmp/script.tar.gz /tmp
    upload_to_manager $BASE_DIR/install_agents/run_on_docker.sh /tmp
    cfy ssh -c '/tmp/run_on_docker.sh /tmp/script.tar.gz'
}


function uninstall_agents {
    prepare_agents_script uninstall_agents
    activate_old_cli
    upload_to_manager /tmp/script.tar.gz /tmp
    upload_to_manager $BASE_DIR/uninstall_agents/run_on_manager.sh /tmp
    cfy ssh -c '/tmp/run_on_manager.sh /tmp/script.tar.gz'
}
 
uninstall_agents
install_agents

