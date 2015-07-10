import unittest

import agents_utils as utils


class TestTaskAtteptsParser(unittest.TestCase):
    def test_task_attempts_from_event(self):
        event = {
            u'event_type': u'task_failed',
            u'timestamp': u'2015-07-09 13:10:11.885+0000',
            u'@timestamp': u'2015-07-09T13:10:11.889Z',
            u'message_code': None,
            u'@version': u'1',
            u'context': {
                u'deployment_id': u'nc2',
                u'task_current_retries': 3,
                u'task_id': u'9cabd4fc-0608-4c29-870c-dec054103fe9',
                u'blueprint_id': u'nc',
                u'plugin': u'diamond',
                u'task_target': u'nodejs_host_6afd6',
                u'node_name': u'nodejs_host',
                u'workflow_id': u'hosts_software_install',
                u'node_id': u'nodejs_host_6afd6',
                u'task_name': u'diamond_agent.tasks.install',
                u'operation': u'cloudify.interfaces.monitoring_agent.install',
                u'task_total_retries': -1,
                u'execution_id': u'5a557b53-c2f3-4b36-96b6-e6587e972422',
                },
            u'message': {u'text':
                         u'Task failed \'diamond_agent.tasks.install\' -> '
                         'RecoverableError("OSError: [Errno 17] File exists: '
                         '\'/home/ubuntu/cloudify.nodejs_host_6afd6/diamond/'
                         'collectors/sockstat\'",) [attempt 4]',
                         u'arguments': None},
            u'type': u'cloudify_event',
        }
        expected = 4
        res = utils.event_task_attempts(event)
        self.assertEquals(res, expected)

    def test_task_retries_from_msg(self):
        inputs = [
            'random message [attempt 4/19]',
            'random message with infinite attempts [attempt 5]',
            'random message with infinite attempts [attempt 6][attempt 7]',
            'random message with no attempts'
        ]
        default_value = 143
        results = [4, 5, 7, default_value]
        for question, answer in zip(inputs, results):
            res = utils.task_attempt_from_msg(question, default_value)
            self.assertEquals(res, answer)
