#!/bin/bash

set -e
if [[ $# -lt 5 ]]; then
    echo "Usage: $0 blueprint_id deployment_id manager_env operation max_attempts"
    exit 1
fi

echo "Running operation $4 for deployment $2"
source /etc/default/celeryd-${2}_workflows
cp software_replacement_workflow.py ${VIRTUALENV}/lib/python2.7/site-packages
cp ${CELERY_WORK_DIR}/celeryd-includes ${CELERY_WORK_DIR}/celeryd-includes.backup
echo "INCLUDES=$INCLUDES,software_replacement_workflow" > ${CELERY_WORK_DIR}/celeryd-includes

service celeryd-${WORKER_MODIFIER} restart
echo "Celery worker restarted, executing operation"

set +e
$3/bin/python execute.py $1 $2 $4 $5
CODE=$?
set -e

echo "Operation finished, code $CODE"
echo "Cleaning up environment"

mv ${CELERY_WORK_DIR}/celeryd-includes.backup  ${CELERY_WORK_DIR}/celeryd-includes
rm -f ${VIRTUALENV}/lib/python2.7/site-packages/software_replacement_workflow.py*

service celeryd-${WORKER_MODIFIER} restart

echo "Updating agents for deployment $2 finished with code $CODE"
exit $CODE
