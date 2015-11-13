#!/bin/bash

set -e
if [[ $# -lt 2 ]]; then
    echo "Usage: $0 deployment_id output"
    exit 1
fi

OUTPUT=$2
source /etc/default/celeryd-${1}_workflows

echo ${VIRTUALENV} > ${OUTPUT}
echo ${CELERY_WORK_DIR} >> ${OUTPUT}
echo ${INCLUDES} >> ${OUTPUT}

