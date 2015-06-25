from datetime import datetime
import uuid
import sys
import time

from manager_rest.storage_manager import instance
from manager_rest import models
from manager_rest.workflow_client import workflow_client


execution_id = str(uuid.uuid4())

blueprint_id = sys.argv[1]
deployment_id = sys.argv[2]
op_name = sys.argv[3]

workflow_id = "hosts_software_" + op_name

new_execution = models.Execution(
    id=execution_id,
    status=models.Execution.PENDING,
    created_at=str(datetime.now()),
    blueprint_id=blueprint_id,
    workflow_id=workflow_id,
    deployment_id=deployment_id,
    error='',
    parameters=[]
)
sm = instance()
sm.put_execution(new_execution.id, new_execution)

workflow = {
    'operation': 'software_replacement_workflow.replace_host_software'
}

workflow_client().execute_workflow(
    workflow_id,
    workflow,
    blueprint_id=blueprint_id,
    deployment_id=deployment_id,
    execution_id=execution_id,
    execution_parameters={'op_name': op_name})

status = sm.get_execution(execution_id).status
while status not in models.Execution.END_STATES:
    time.sleep(5)
    status = sm.get_execution(execution_id).status

print '{} finished with status "{}"'.format(workflow_id, status)

if status == models.Execution.FAILED:
    sys.exit(1)
