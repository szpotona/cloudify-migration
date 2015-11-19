import sys
import json
from cloudify import context
from cloudify.utils import setup_default_logger


class MockContext(object):

    def __init__(self):
        self.logger = setup_default_logger('MockContext')
        self.type = context.NODE_INSTANCE

mock_ctx = MockContext()


def _start_windows_agent(name, agent):
    from windows_agent_installer.winrm_runner import WinRMRunner
    from windows_agent_installer import tasks
    print 'Starting agent for {0}'.format(name)
    runner = WinRMRunner(agent['cloudify_agent'])
    # Not using path join because we are running on unix and creating
    # windows path..
    pid_path = '{0}\\celery.pid'.format(tasks.RUNTIME_AGENT_PATH)
    # If agent were stopped gracefully then pid file does not exist.
    runner.delete(path=pid_path, ignore_missing=True)
    # We are starting agent but this command will fail if service
    # is running. This is the case after vm restart - service
    # is running but agent is dead.
    runner.run('sc start {0}'.format(tasks.AGENT_SERVICE_NAME),
               raise_on_failure=False)


def _start_unix_agent(name, agent):
    from worker_installer.utils import FabricRunner
    runner = FabricRunner(mock_ctx, agent['cloudify_agent'])
    runner.ping()
    runner.run("sudo service celeryd-{0} start".format(name))


def main(args):
    input_path = sys.argv[1]
    with open(input_path) as f:
        deployment = json.loads(f.read())
    for agent_name, agent in deployment.get('agents', {}).iteritems():
        if not agent['alive']:
            if agent['is_windows']:
                _start_windows_agent(agent_name, agent)
            else:
                _start_unix_agent(agent_name, agent)


if __name__ == '__main__':
    main(sys.argv)
