from datetime import datetime
import uuid
import sys

from manager_rest.storage_manager import instance
from manager_rest import models

execution_id = str(uuid.uuid4())

blueprint_id = sys.argv[1]
deployment_id = sys.argv[2]
workflow_id = sys.argv[3]

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

print new_execution.id
