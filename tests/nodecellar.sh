#!/bin/bash

set -e

function cleanup {
    rm -fr $REPO_DIR
    rm -f $INPUTS_FILE
}
trap cleanup EXIT

BASE_DIR=$(dirname $(dirname $(readlink -e $0)))
. $BASE_DIR/common.sh
. $BASE_DIR/tests/utils/tests-common.sh

perform_setup $1 $2 $3 $4

REPO_DIR=$(mktemp -d /tmp/nodecellar_XXXX)
chmod 775 $REPO_DIR # For the cfy upload to succeed
INPUTS_FILE=$(mktemp /tmp/inputs_XXXX)
create_inputs $INPUTS_FILE
BLUEPRINT=$REPO_DIR/openstack-blueprint.yaml
BLUEPRINT_ID=nodecellar-migration
DEPLOYMENT_ID=nodecellard

function verify_nodecellar_is_up {
    echo "Verifying that Nodecellar is launched"
    python $BASE_DIR/tests/utils/verify_nodecellar_is_up.py $DEPLOYMENT_ID
}

git clone https://github.com/cloudify-cosmo/cloudify-nodecellar-example $REPO_DIR
(cd $REPO_DIR; git checkout $OLD_MANAGER_VER)
find $REPO_DIR -name "*blueprint*yaml" | grep -v openstack-blueprint | while read unnecessary_bp; do rm $unnecessary_bp; done

activate_old_cli
cfy blueprints upload -b $BLUEPRINT_ID -p $BLUEPRINT
cfy deployments create -b $BLUEPRINT_ID -d $DEPLOYMENT_ID -i $INPUTS_FILE
sleep 1 # Sometimes a strange bug pops up, it needs investigation (create_dep_env not found)
cfy executions start -d $DEPLOYMENT_ID -w install

verify_nodecellar_is_up

# TODO: get rid of "yes" by adding some customization options
yes | $BASE_DIR/migrate.sh -a -b -m $OLD_CLI_PYTHON_VIRTENV $OLD_CLI_DIR $NEW_CLI_PYTHON_VIRTENV $NEW_CLI_DIR

activate_new_cli
python $BASE_DIR/tests/utils/verify_state_after_migration.py $BLUEPRINT_ID $DEPLOYMENT_ID
verify_nodecellar_is_up

echo Clearing both managers
(activate_old_cli; clear_manager) &
clear_manager
$BASE_DIR/print_failed_tasks.sh -w uninstall $NEW_CLI_PYTHON_VIRTENV $NEW_CLI_DIR
wait
echo "Test passed"

