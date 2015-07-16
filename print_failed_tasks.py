import datetime
import sys
import time

from cloudify_cli import utils
from cloudify_cli.execution_events_fetcher import ExecutionEventsFetcher
from cloudify_cli.logger import (
    get_logger,
    get_events_logger,
    configure_loggers
)

import common_agents.agents_utils as agents_utils


TIME_FORMAT = '%Y-%m-%d %H:%M:%S.%f'
FAILED_TASK_TYPE = 'task_failed'
FAILURE_MSG_FORMAT = ('Deployment {0}: failure detected '
                      'in workflow {1}, execution id {2}:')
NO_EXECUTION_MSG_FORMAT = 'Deployment {0}: workflow {1} hasn\'t been executed.'
OK_MSG_FORMAT = 'Deployment {0}: workflow {1} succeeded, execution id {2}.'
NOT_INSTALLED_MSG_FORMAT = ('Deployment {0}: deployment not installed,'
                            ' skipping.')

RESULT_TASKS = 'tasks'
RESULT_NO_EXECUTION = 'no_execution'
RESULT_NOT_INSTALLED = 'deployment_not_installed'


def execution_timestamp(execution):
    return time.mktime(datetime.datetime.strptime(execution.created_at,
                                                  TIME_FORMAT).timetuple())


def deployment_failed_tasks(client, workflow_id, deployment):
    node_instances = client.node_instances.list(deployment_id=deployment.id)
    if not agents_utils.is_deployment_installed(node_instances):
        return {'type': RESULT_NOT_INSTALLED, 'deployment': deployment}
    executions = client.executions.list(deployment_id=deployment.id)
    executions = [e for e in executions
                  if e.workflow_id == workflow_id]
    if not executions:
        return {'type': RESULT_NO_EXECUTION, 'deployment': deployment}
    executions.sort(key=execution_timestamp)
    last = executions[-1]
    execution_events = ExecutionEventsFetcher(
        client,
        last.id,
        include_logs=False)
    events = []
    execution_events.fetch_and_process_events(
        events_handler=lambda e: events.extend(e))
    events = [e for e in events if e.get('event_type') == FAILED_TASK_TYPE]
    return {'type': RESULT_TASKS, 'failed_tasks': events, 'execution': last}


def main(args):
    workflow_id = args[1]
    configure_loggers()
    logger = get_logger()
    manager_ip = utils.get_management_server_ip()
    client = utils.get_rest_client(manager_ip)
    deployments = client.deployments.list()
    results = map(lambda d: deployment_failed_tasks(client, workflow_id, d),
                  deployments)
    failure_detected = False
    for res in results:
        if res.get('type') == RESULT_TASKS:
            tasks = res.get('failed_tasks')
            exc = res.get('execution')
            if tasks:
                failure_detected = True
                msg = FAILURE_MSG_FORMAT.format(exc.deployment_id,
                                                workflow_id,
                                                exc.id)
                logger.info(msg)
                get_events_logger()(tasks)
                logger.info('Total tasks failed: {0}\n'.format(len(tasks)))
            else:
                msg = OK_MSG_FORMAT.format(exc.deployment_id,
                                           workflow_id,
                                           exc.id)
                logger.info(msg)
        elif res.get('type') == RESULT_NOT_INSTALLED:
            deployment = res.get('deployment')
            logger.info(NOT_INSTALLED_MSG_FORMAT.format(deployment.id))
        else:
            deployment = res.get('deployment')
            failure_detected = True
            logger.info(NO_EXECUTION_MSG_FORMAT.format(deployment.id,
                                                       workflow_id))
    if failure_detected:
        logger.info('Failure detected.')
    return int(failure_detected)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
