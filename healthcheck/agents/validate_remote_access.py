import sys
import json

from cloudify import context
from cloudify.utils import setup_default_logger


path = sys.argv[1]
output = sys.argv[2]


class MockContext(object):

    def __init__(self):
        self.logger = setup_default_logger('MockContext')
        self.type = context.NODE_INSTANCE 

with open(path) as f:
    agents = json.loads(f.read())


mock_ctx = MockContext()
access = {}
for name, agent in agents.iteritems():
    access[name] = {}
    try:
        if agent['is_windows']:
            from windows_agent_installer.winrm_runner import WinRMRunner
            runner = WinRMRunner(agent['cloudify_agent'])
        else:
            from worker_installer.utils import FabricRunner
            runner = FabricRunner(mock_ctx, agent['cloudify_agent'])
            runner.ping()
        access[name]['can_connect'] = True
    except Exception as e:
        access[name]['can_connect'] = False
        access[name]['error'] = str(e)

with open(output, 'w') as f:
    f.write(json.dumps(access))
