import re
import sys
import time

import manager_rest.es_storage_manager as es

from manager_rest import models
from manager_rest.storage_manager import instance as storage_manager_instance


_TASK_RETRIES_REGEXP = re.compile('.*\[attempt (?P<retry>\d+)(/\d+)?\]$')

def es_connection_from_storage_manager(sm):
    try:
        return sm._connection  # 3.2
    except AttributeError:
        return sm._get_es_conn()  # 3.1


def _create_events_query_body(execution_id, last_event, batch_size):
    body = {
        'from': last_event,
        'size': batch_size,
        'sort': [{
            '@timestamp': {
                'order': 'asc',
                'ignore_unmapped': True
            }}],
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


def events_generator(execution_id, sm):
    status = sm.get_execution(execution_id).status
    es_connection = es_connection_from_storage_manager(sm)
    events_received = 0
    events_batch_size = 100
    events_total = 1  # dummy value, can be anything > 0
    finished = False
    while not finished:
        # first, lets retrieve all events:
        while events_received < events_total:
            response = es_connection.search(
                index='cloudify_events',
                body=_create_events_query_body(
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

def task_retries_from_msg(msg, default):
    match = _TASK_RETRIES_REGEXP.match(msg)
    if match:
        return int(match.group('retry'))
    return int(default)


def event_task_retries(event, default):
    ctx = event.get('context', {})
    if 'task_current_retries' in ctx:
        return ctx.get('task_current_retries')
    msg = event.get('message', {}).get('text', '')
    return task_retries_from_msg(msg, default)

    
def _task_retries_from_msg_test():
    print 'Testing _task_retries_from_msg_test'
    inputs = [
        'random message [attempt 4/19]',
        'random message with infinite attempts [attempt 5]',
        'random message with infinite attempts [attempt 6][attempt 7]',
        'random message with no attempts'
    ]
    default_value = 143
    results = [4, 5, 7, default_value]
    for question, answer in zip(inputs, results):
        res = task_retries_from_msg(question, default_value)
        if res != answer:
            raise Exception(
                'Wrong result for "{}": expected {}, received {}'.format(
                    question,
                    answer,
                    res
                )
            )
    print 'Test succeeded'


def main(args):
    if len(args) > 1:
        sm = storage_manager_instance()
        execution_id = args[1]
        retries = map(lambda e: event_task_retries(e, 0), events_generator(execution_id, sm))
        print retries
        pass
    else:
        _task_retries_from_msg_test() 


if __name__ == '__main__':
    main(sys.argv)
