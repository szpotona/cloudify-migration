#!/bin/bash

OLD_MAGIC_PATH="/tmp/cloudify_migration_data_metrics_53hot.tar.gz"
HOST_FILE="cloudify_migration_data_metrics_gf35.tar.gz"
HOST_MAGIC_PATH="/tmp/$HOST_FILE"

BASE_DIR=$(dirname $(readlink -e $0))
. $BASE_DIR/common.sh

function usage {
    echo "Usage: $SCRIPT_NAME old_cli_venv old_cli_dir new_cli_venv new_cli_dir docker/nodocker"
}

if [[ $# != 5 ]]; then
    usage
    error "Wrong number of parameters" 2
fi

perform_setup $1 $2 $3 $4

function export_metrics {
    activate_old_cli
    if [[ '$5' != 'docker' ]]; then
        cfy ssh -c "sudo tar -czf $OLD_MAGIC_PATH  /opt/influxdb/shared/data"
    else
        cd $BASE_DIR/common_metrics/export
        tar -czf package.tar.gz run.sh
        cd -
        run_operation $BASE_DIR/common_metrics/export/package.tar.gz run_on_docker.sh
        cfy ssh -c "sudo docker cp cfy:$OLD_MAGIC_PATH /tmp"
        rm -f $BASE_DIR/common_metrics/export/package.tar.gz
    fi

    download_from_manager $HOST_MAGIC_PATH $OLD_MAGIC_PATH
    cfy ssh -c "rm -f $OLD_MAGIC_PATH &> /dev/null"
}

function import_metrics {
    activate_new_cli
    mv $HOST_MAGIC_PATH $BASE_DIR/common_metrics/import/$HOST_FILE
    cd $BASE_DIR/common_metrics/import
    tar -czf package.tar.gz  run.sh $HOST_FILE
    cd -
    run_operation $BASE_DIR/common_metrics/import/package.tar.gz run_on_docker.sh
    rm -f $BASE_DIR/common_metrics/import/$HOST_FILE $BASE_DIR/common_metrics/import/package.tar.gz
}

export_metrics
import_metrics

