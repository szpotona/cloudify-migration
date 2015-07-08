import sys
import time

import manager_rest.es_storage_manager as es

from manager_rest import models
from manager_rest.storage_manager import instance as storage_manager_instance


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
    while status not in models.Execution.END_STATES:
        # first, lets retrieve all events:
        while events_received < events_total:
            response = es_connection.search(
                index='cloudify_events',
                body=_create_events_query_body(
                    execution_id,
                    last_event,
                    events_batch_size
                )
            )
            events = map(lambda x: x['_source'], response['hits']['hits'])
            for e in events:
                yield e
            events_received += len(events)
            events_total = response['hits']['total']
        time.sleep(5)
        status = sm.get_execution(execution_id).status


def main(args):
    sm = storage_manager_instance()
    execution_id = args[0]
    for e in events_generator(execution_id, sm):
        print e


if __name__ == '__main__':
    main(sys.argv)
