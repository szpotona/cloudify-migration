#!/bin/bash

set -e

BASE_DIR=$(dirname $(readlink -e $0))
. $BASE_DIR/common.sh

function usage {
    echo "Usage: $SCRIPT_NAME [-bamh] [-p auth_path] [-n attempts_limit] old_cli_venv old_cli_dir new_cli_venv new_cli_dir"
}

MODIFY_BLUEPRINTS=false
UPDATE_HOSTS_SOFTWARE=false
MIGRATE_INFLUXDB_DATA=false # Migrate metrics (used by graphs in the UI for example)
MAX_ATTEMPTS=-1
unset AUTHENTICATION_DATA_OVERRIDE_PATH
while getopts bamhp:n: opt; do
    case $opt in
        b)
            MODIFY_BLUEPRINTS=true
            ;;
        a)
            UPDATE_HOSTS_SOFTWARE=true
            ;;
        m)
            MIGRATE_INFLUXDB_DATA=true
            ;;
        p)
            AUTHENTICATION_DATA_OVERRIDE_PATH=$(absolute_path $OPTARG)
            ;;
        n)
            MAX_ATTEMPTS=$OPTARG
            ;;
        h)
            usage
            exit 0
            ;;
        \?)
            usage
            error "Invalid option supplied" 2
            ;;
    esac
done
shift $((OPTIND - 1))

if [[ $# != 4 ]]; then
    usage
    error "Wrong number of parameters" 2
fi

perform_setup $1 $2 $3 $4

BLUEPRINTS_DIR=$(mktemp -d /tmp/migr_blueprints_XXXX)
USER_YES_RESP_REGEXP="^([yY][eE][sS]|[yY])$"

function cleanup {
    rm -fr $BLUEPRINTS_DIR
}
trap cleanup EXIT

function download_all_blueprints {
    activate_old_cli
    if ! python $BASE_DIR/download_blueprints.py $BLUEPRINTS_DIR; then
        error "Downloading blueprints from the old Cloudify Manager failed.." 1
    fi
    for blueprint_tar_gz in $BLUEPRINTS_DIR/*.tar.gz; do
        local extracted_dir="${blueprint_tar_gz%%.tar.gz}"
        local untar_options="xf $blueprint_tar_gz -C $extracted_dir --strip-components 1"
        mkdir $extracted_dir
        if ! (tar $untar_options) 2> /dev/null; then
            tar z$untar_options
        fi
        rm $blueprint_tar_gz
    done
}

function update_blueprint {
    if $MODIFY_BLUEPRINTS; then
        local changed_blueprint=$1'.chg'
        python $BASE_DIR/update_blueprint.py $1 $changed_blueprint $OLD_MANAGER_VER $NEW_MANAGER_VER
        if ! diff --old-group-format=$'\e[0;31m%<\e[0m' \
                  --new-group-format=$'\e[0;32m%>\e[0m' \
                  --unchanged-group-format='' $1 $changed_blueprint; then
            read -p "Do you accept these modifications for $1? [y/n] " user_resp
            if [[ $user_resp =~ $USER_YES_RESP_REGEXP ]]; then
                mv $changed_blueprint $1
            else
                rm $changed_blueprint
                read -p "Please make $1 compliant with Cloudify $NEW_MANAGER_VER on your own and press enter."
            fi
        fi
    fi
}

function update_and_upload_all_blueprints {
    activate_new_cli
    for blueprint_dir in $BLUEPRINTS_DIR/*; do
        local potential_bpnts=( $blueprint_dir/*.yaml )
        if [ ${#potential_bpnts[@]} -eq 1 ]; then # There is only one yaml file - our blueprint
            local blueprint=${potential_bpnts[0]}
        else                                      # There are more files than can possibly be a blueprint
            for potential_bpnt in "${potential_bpnts[@]}"; do
                read -p "Is $potential_bpnt a blueprint you want to migrate? [y/n] " user_resp
                if [[ $user_resp =~ $USER_YES_RESP_REGEXP ]]; then
                    local blueprint=$potential_bpnt
                    break # We assume there should be only one proper blueprint in $blueprint_dir directory
                fi
            done
        fi
        update_blueprint $blueprint
        while ! cfy blueprints upload -p $blueprint -b $(basename $blueprint_dir); do
            read -p "Please make sure that blueprint $blueprint is valid and press enter."
        done
    done
}

function create_deployments {
    (activate_old_cli; python $BASE_DIR/retrieve_deployments.py $BASE_DIR/common_elasticsearch/dump_elasticsearch.py 3>&1 1>&4 | \
        (activate_new_cli; python $BASE_DIR/create_deployments.py)
    ) 4>&1
}

read -p "Press enter to proceed with the <$OLD_MANAGER_VER --> $NEW_MANAGER_VER> migration."
download_all_blueprints
update_and_upload_all_blueprints
create_deployments
if $UPDATE_HOSTS_SOFTWARE; then
    $BASE_DIR/migrate_agents.sh -n $MAX_ATTEMPTS uninstall $OLD_MANAGER_VER $OLD_CLI_PYTHON_VIRTENV $OLD_CLI_DIR $AUTHENTICATION_DATA_OVERRIDE_PATH
    if ! $BASE_DIR/print_failed_tasks.sh -w hosts_software_uninstall $OLD_CLI_PYTHON_VIRTENV $OLD_CLI_DIR; then
        echo 'Failure during agent uninstallation process detected.'
        echo -n 'Make sure that agents were uninstalled properly and '
        echo 'continue migration process manually.'
        exit 1
    fi
    if $MIGRATE_INFLUXDB_DATA; then
        $BASE_DIR/migrate_metrics.sh $OLD_CLI_PYTHON_VIRTENV $OLD_CLI_DIR $NEW_CLI_PYTHON_VIRTENV $NEW_CLI_DIR
    fi
    $BASE_DIR/migrate_agents.sh -n $MAX_ATTEMPTS install $NEW_MANAGER_VER $NEW_CLI_PYTHON_VIRTENV $NEW_CLI_DIR $AUTHENTICATION_DATA_OVERRIDE_PATH
    if ! $BASE_DIR/print_failed_tasks.sh -w hosts_software_install $NEW_CLI_PYTHON_VIRTENV $NEW_CLI_DIR; then
        echo 'Failure during agent installation process detected.'
        exit 1
    fi
fi
