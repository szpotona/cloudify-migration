import sys
import time
import uuid
from datetime import datetime

from manager_rest import models
from manager_rest.storage_manager import instance as storage_manager_instance
from manager_rest.workflow_client import workflow_client

import agents_utils as utils


_DEFAULT_ATTEMPT_LIMIT = -1


def _events_generator(execution_id, sm):
    status = sm.get_execution(execution_id).status
    es_connection = utils.es_connection_from_storage_manager(sm)
    events_received = 0
    events_batch_size = 100
    finished = False
    while not finished:
        events_total = events_received + 1
        while events_received < events_total:
            response = es_connection.search(
                index='cloudify_events',
                body=utils.create_events_query_body(
                    execution_id,
                    events_received,
                    events_batch_size
                )
            )
            events = map(lambda x: x['_source'], response['hits']['hits'])
            for e in events:
                yield e
            events_received += len(events)
            events_total = response['hits']['total']
        status = sm.get_execution(execution_id).status
        finished = status in models.Execution.END_STATES
        if not finished:
            time.sleep(5)


def _start_workflow(blueprint_id, deployment_id,
                    execution_id, op_name, sm):
    workflow_id = 'hosts_software_' + op_name

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


def _wait_for_execution_finish(execution_id, attempt_limit, sm):
    canceled = False
    for event in _events_generator(execution_id, sm):
        if (not canceled and
           event.get('event_type') == 'task_failed'):
            attempt = utils.event_task_attempts(event)
            if (attempt is not None and
               attempt_limit >= 0 and
               attempt >= attempt_limit):
                # We need to cancel executions:
                msg_format = 'Retry limit exceeded, current: {0}, limit: {1}'
                msg = msg_format.format(attempt, attempt_limit)
                status = sm.get_execution(execution_id).status
                if status in (models.Execution.PENDING,
                              models.Execution.STARTED):
                    # We cancel execution only if it is still running:
                    sm.update_execution_status(
                        execution_id,
                        models.Execution.CANCELLING,
                        msg
                    )
                canceled = True
    if canceled:
        return utils.EXIT_RETRY_LIMIT_EXCEEDED
    status = sm.get_execution(execution_id).status
    if status == models.Execution.FAILED:
        return utils.EXIT_ERROR
    return utils.EXIT_OK


def main(args):
    execution_id = str(uuid.uuid4())

    blueprint_id = args[1]
    deployment_id = args[2]
    op_name = args[3]

    if len(args) > 4:
        attempt_limit = int(args[4])
    else:
        attempt_limit = _DEFAULT_ATTEMPT_LIMIT
    sm = storage_manager_instance()
    _start_workflow(blueprint_id, deployment_id, execution_id, op_name, sm)
    return _wait_for_execution_finish(
        execution_id,
        attempt_limit,
        sm
    )


if __name__ == '__main__':
    sys.exit(main(sys.argv))
