#!/bin/bash

OLD_MAGIC_PATH="/tmp/cloudify_migration_data_metrics_53hot.tar.gz"
HOST_FILE="cloudify_migration_data_metrics_gf35.tar.gz"
HOST_MAGIC_PATH="/tmp/$HOST_FILE"

BASE_DIR=$(dirname $(readlink -e $0))
. $BASE_DIR/common.sh

function usage {
    echo "Usage: $SCRIPT_NAME old_cli_venv old_cli_dir new_cli_venv new_cli_dir"
}

if [[ $# != 4 ]]; then
    usage
    error "Wrong number of parameters" 2
fi

put_common_args_to_variables $1 $2 $3 $4

function export_metrics {
     activate_old_cli
     cfy ssh -c "sudo tar -czf $OLD_MAGIC_PATH  /opt/influxdb/shared/data"
     download_from_manager $HOST_MAGIC_PATH $OLD_MAGIC_PATH  
     cfy ssh -c "rm -f $OLD_MAGIC_PATH &> /dev/null"
}

function import_metrics {
    activate_new_cli
    mv $HOST_MAGIC_PATH $BASE_DIR/common_metrics/$HOST_FILE
    cd $BASE_DIR/common_metrics
    tar -czf package.tar.gz  run.sh $HOST_FILE    
    cd -
    run_operation $BASE_DIR/common_metrics/package.tar.gz run_on_docker.sh
    rm -f $HOST_MAGIC_PATH
    rm -f $BASE_DIR/common_metrics/$HOST_FILE $BASE_DIR/common_metrics/package.tar.gz
}

export_metrics
import_metrics

