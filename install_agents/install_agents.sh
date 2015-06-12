
set -eax
if [[ $# -lt 2 ]]; then
    echo "Usage: $0 blueprint_id deployment_id"
    exit 1
fi

. /etc/default/celeryd-${2}

execution_id=$(/opt/manager/env/bin/python create_execution.py $1 $2 migration_install)

${VIRTUALENV}/bin/python software_replacement_workflow.py $1 $2 $execution_id migration_install
