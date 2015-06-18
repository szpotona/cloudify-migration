#!/bin/bash

set -e

. common.sh

SCRIPT_NAME=$0

function usage {
    echo "Usage: $SCRIPT_NAME [-bh] old_cli_venv old_cli_dir new_cli_venv new_cli_dir"
}

MODIFY_BLUEPRINTS=false
while getopts bh opt; do
    case $opt in
        b)
            MODIFY_BLUEPRINTS=true
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

OLD_CLI_PYTHON_VIRTENV=$(absolute_path $1)  # Directory of the virtualenv which is utilized by Cloudify CLI to manage the old manager
OLD_CLI_DIR=$(absolute_path $2)             # Location of the .cloudify directory initialized by Cloudify CLI to manage the old manager
NEW_CLI_PYTHON_VIRTENV=$(absolute_path $3)  # Directory of the virtualenv which is utilized by Cloudify CLI to manage the new manager
NEW_CLI_DIR=$(absolute_path $4)             # Location of the .cloudify directory initialized by Cloudify CLI to manage the new manager

BLUEPRINTS_DIR=$(mktemp -d /tmp/migr_blueprints_XXXX)
BASE_DIR=$PWD
USER_YES_RESP_REGEXP="^([yY][eE][sS]|[yY])$"


function download_all_blueprints {
    activate_old_cli
    if python $BASE_DIR/download_blueprints.py $BLUEPRINTS_DIR; then
        echo "All blueprints that are to be migrated have been stored in $BLUEPRINTS_DIR"
    else
        error "Downloading blueprints from the old Cloudify Manager failed.." 1
    fi
    for blueprint_tar_gz in $BLUEPRINTS_DIR/*.tar.gz; do
        extracted_dir="${blueprint_tar_gz%%.*}"
        mkdir $extracted_dir
        tar xzf $blueprint_tar_gz -C $extracted_dir --strip-components 1
        rm $blueprint_tar_gz
    done
}

function update_blueprint {
    if $MODIFY_BLUEPRINTS; then
        changed_blueprint=$1'.chg'
        sed 's/1.1/1.2/g;s/3.1/3.2/g' $1 > $changed_blueprint
        if ! diff --old-group-format=$'\e[0;31m%<\e[0m' \
                  --new-group-format=$'\e[0;32m%>\e[0m' \
                  --unchanged-group-format='' $1 $changed_blueprint; then
            read -p "Do you accept these modifications for $1? [y/n] " user_resp
            if [[ $user_resp =~ $USER_YES_RESP_REGEXP ]]; then
                mv $changed_blueprint $1
            else
                rm $changed_blueprint
                read -p "Please make $1 compliant with Cloudify 3.2 on your own and press enter."
            fi
        fi
    fi
}

function update_and_upload_all_blueprints {
    activate_new_cli
    for blueprint_dir in $BLUEPRINTS_DIR/*; do
        potential_bpnts=( $blueprint_dir/*.yaml )
        if [ ${#potential_bpnts[@]} -eq 1 ]; then # There is only one yaml file - our blueprint
            blueprint=${potential_bpnts[0]}
        else                                     # There are more files than can possibly be a blueprint
            for potential_bpnt in "${potential_bpnts[@]}"; do
                read -p "Is $potential_bpnt a blueprint you want to migrate? [y/n] " user_resp
                if [[ $user_resp =~ $USER_YES_RESP_REGEXP ]]; then
                    blueprint=$potential_bpnt
                    break # We assume there should be only one proper blueprint in $blueprint_dir directory
                fi
            done
        fi
        update_blueprint $blueprint
        cfy blueprints upload -p $blueprint -b $(basename $blueprint_dir)
    done
}

function create_deployments {
    (activate_old_cli; python $BASE_DIR/retrieve_deployments.py 3>&1 1>&4 | \
        (activate_new_cli; python $BASE_DIR/create_deployments.py)
    ) 4>&1
}

download_all_blueprints
update_and_upload_all_blueprints
create_deployments

#rm -fr $BLUEPRINTS_DIR
