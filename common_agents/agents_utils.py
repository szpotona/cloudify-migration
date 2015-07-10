import re


EXIT_OK = 0
EXIT_ERROR = 1
EXIT_RETRY_LIMIT_EXCEEDED = 2

_TASK_RETRIES_REGEXP = re.compile('.*\[attempt (?P<retry>\d+)(/\d+)?\]$')

_NODE_INSTANCE_STATE_STARTED = 'started'


def es_connection_from_storage_manager(sm):
    try:
        return sm._connection  # 3.2
    except AttributeError:
        return sm._get_es_conn()  # 3.1


def create_events_query_body(execution_id, last_event, batch_size):
    body = {
        'from': last_event,
        'size': batch_size,
        'sort': [{
            '@timestamp': {
                'order': 'asc',
                'ignore_unmapped': True
            }
        }],
        'query': {
            'bool': {
                'must': [
                    {'match': {'context.execution_id': execution_id}},
                    {'match': {'type': 'cloudify_event'}}
                ]
            }
        }
    }
    return body


def task_attempt_from_msg(msg, default):
    match = _TASK_RETRIES_REGEXP.match(msg)
    if match:
        return int(match.group('retry'))
    return default


def event_task_attempts(event, default=None):
    ctx = event.get('context', {})
    if 'task_current_retries' in ctx:
        return ctx.get('task_current_retries') + 1
    msg = event.get('message', {}).get('text', '')
    return task_attempt_from_msg(msg, default)


def is_deployment_installed(deployment_node_instances):
    for node_instance in deployment_node_instances:
        if node_instance.state != _NODE_INSTANCE_STATE_STARTED:
            return False
    return True
