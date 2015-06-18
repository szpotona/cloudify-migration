
set -eax
if [[ $# -lt 4 ]]; then
    echo "Usage: $0 blueprint_id deployment_id manager_env operation"
    exit 1
fi

source /etc/default/celeryd-${2}_workflows

execution_id=$($3/bin/python create_execution.py $1 $2 $4)

${VIRTUALENV}/bin/python software_replacement_workflow.py $1 $2 $execution_id $4
