import sys
import time
import uuid
from datetime import datetime

from manager_rest import models
from manager_rest.storage_manager import instance as storage_manager_instance
from manager_rest.workflow_client import workflow_client
from celery import Celery

import agents_utils as utils


_DEFAULT_ATTEMPT_LIMIT = -1


def _events_generator(execution_id, sm):
    status = sm.get_execution(execution_id).status
    es_connection = utils.es_connection_from_storage_manager(sm)
    events_received = 0
    events_batch_size = 100
    finished = False
    while not finished:
        print 'Waiting for execution {0}'.format(execution_id)
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
        parameters=[],
        is_system_workflow=False
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

_BROKER_URL = {
    '3.1.0': 'amqp://guest:guest@127.0.0.1:5672//',
    '3.2.0': 'amqp://guest:guest@127.0.0.1:5672//',
    '3.2.1': 'amqp://cloudify:c10udify@127.0.0.1:5672//'
}

_SEPARATOR = {
    '3.1.0': '.',
    '3.2.0': '@',
    '3.2.1': '@'
}


def _check_alive(celery, worker_name):
    try:
        tasks = celery.control.inspect([worker_name]).registered() or {}
        worker_tasks = set(tasks.get(worker_name, {}))
        return 'script_runner.tasks.run' in worker_tasks
    except:
        return False


def _wait_for_workflows_worker(deployment, version):
    broker_url = _BROKER_URL[version]
    celery = Celery(broker=broker_url, backend=broker_url)
    separator = _SEPARATOR[version]
    name = 'celery{0}{1}_workflows'.format(separator, deployment)
    while not _check_alive(celery, name):
        print 'Waiting for worker {0}'.format(name)
        time.sleep(3)
    print 'Worker {0} alive'.format(name)


def main(args):
    execution_id = str(uuid.uuid4())

    blueprint_id = args[1]
    deployment_id = args[2]
    op_name = args[3]
    attempt_limit = int(args[4])
    version = args[5]
    _wait_for_workflows_worker(deployment_id, version)
    sm = storage_manager_instance()
    _start_workflow(blueprint_id, deployment_id, execution_id, op_name, sm)
    return _wait_for_execution_finish(
        execution_id,
        attempt_limit,
        sm
    )


if __name__ == '__main__':
    sys.exit(main(sys.argv))
