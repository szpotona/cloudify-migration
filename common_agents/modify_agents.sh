
set -e
if [[ $# -lt 4 ]]; then
    echo "Usage: $0 blueprint_id deployment_id manager_env operation"
    exit 1
fi

source /etc/default/celeryd-${2}_workflows
cp software_replacement_workflow.py ${VIRTUALENV}/lib/python2.7/site-packages
cp ${CELERY_WORK_DIR}/celeryd-includes ${CELERY_WORK_DIR}/celeryd-includes.backup
source ${CELERY_WORK_DIR}/celeryd-includes
echo "INCLUDES=$INCLUDES,software_replacement_workflow" > ${CELERY_WORK_DIR}/celeryd-includes

service celeryd-${WORKER_MODIFIER} restart

mv ${CELERY_WORK_DIR}/celeryd-includes.backup  ${CELERY_WORK_DIR}/celeryd-includes
rm -f ${VIRTUALENV}/lib/python2.7/site-packages/software_replacement_workflow.py*
echo "done"

#execution_id=$($3/bin/python create_execution.py $1 $2 $4)

#${VIRTUALENV}/bin/python software_replacement_workflow.py $1 $2 $execution_id $4
