import argparse
import json
import sys

from cloudify_cli.utils import get_rest_client
from cloudify_cli.logger import configure_loggers


import os
import sys
from distutils import spawn
from cloudify_cli.utils import get_management_user
from cloudify_cli.utils import get_management_server_ip
from cloudify_cli.utils import get_management_key
from cloudify_cli.commands.ssh import ssh
from subprocess import call


_DIRECTORY = os.path.dirname(os.path.realpath(__file__))


def _get_agents_resource(resource):
    return os.path.join(_DIRECTORY, 'agents', resource)


def scp(local_path, path_on_manager, to_manager):
    scp_path = spawn.find_executable('scp')
    management_path = '{0}@{1}:{2}'.format(
        get_management_user(),
        get_management_server_ip(),
        path_on_manager
    )
    command = [scp_path, '-i', os.path.expanduser(get_management_key())]
    if to_manager:
        command += [local_path, management_path]
    else:
        command += [management_path, local_path]
    if call(command):
        raise RuntimeError('Could not scp to/from manager')


class ManagerHandler31(object):

    def put_resource(self, source, resource):
        tmp_file = '/tmp/_resource_file'
        self.send_file(source, tmp_file)
        self.execute('sudo cp {0} /opt/manager/resources/{1}'.format(
            tmp_file, resource))

    def send_file(self, source, target):
        scp(source, target, True)

    def load_file(self, source, target):
        scp(target, source, False)

    def execute(self, cmd):
        ssh(False, ('rm -f /tmp/command_succeeded && {0} && '
                    'touch /tmp/command_succeeded').format(cmd))
        try:
            self.load_file('/tmp/command_succeeded', '/tmp/command_succeeded')
        except:
            raise RuntimeError('Could not execute remote command "{0}"'.format(cmd))

    def python_call(self, cmd):
        self.execute('/opt/celery/cloudify.management__worker/env/bin/python {0}'.format(cmd))


class Command(object):
    def prepare_parser(self, subparsers):
        subparser = subparsers.add_parser(self.name)
        self.prepare_args(subparser)
        subparser.set_defaults(func=self.perform)
    def prepare_args(self, parser):
        pass


def _output(config, res):
    if config.output:
        with open(config.output, 'w') as out:
            out.write(json.dumps(res, indent=2))
    else:
        print json.dumps(res, indent=2)
     


class ListAgents(Command):

    @property 
    def name(self):
        return 'list'

    def prepare_args(self, parser):
        parser.add_argument('--output')
        parser.add_argument('--include-not-started', default=False, action='store_true')
        parser.add_argument('-d', help='Deployment id', dest='deployment_id')

    def perform(self, config):
        client = get_rest_client()
        version = client.manager.get_version()['version']
        res = {}
        if config.deployment_id:
            deployments = [client.deployments.get(deployment_id=config.deployment_id)]
        else:
            deployments = client.deployments.list()
        for deployment in deployments:
            dep_res = {}
            for node in client.nodes.list(deployment_id=deployment.id):
                if 'cloudify.nodes.Compute' in node.type_hierarchy:
                    for node_instance in client.node_instances.list(
                            deployment_id=deployment.id,
                            node_name=node.id):
                        if node_instance.state == 'started' or config.include_not_started:
                            dep_res[node_instance.id] = {
                                'state': node_instance.state,
                                'version': version
                            }
            res[deployment.id] = {'agents': dep_res}
        _output(config, res)

class CheckAgents(Command):
    
    @property
    def name(self):
        return 'check_agents'

    def prepare_args(self, parser):
        parser.add_argument('--input', required=True)
        parser.add_argument('--output')

    def perform(self, config):
        handler = ManagerHandler31()
        with open(config.input) as f:
            # Mainly for validation purposes:
            agents = json.loads(f.read())
        handler.put_resource(
            _get_agents_resource('validate_agents.py'),
            'validate_agents.py')
        target_file = '/tmp/_agents.json'
        result_file = '/tmp/_result.json'
        handler.send_file(config.input, target_file)
        handler.python_call('/opt/manager/resources/validate_agents.py '
                            '{0} {1}'.format(target_file, result_file))
        handler.load_file(result_file, result_file)
        with open(result_file) as f:
            res = json.loads(f.read())
        _output(config, res)


class CheckSSH(Command):
    
    @property
    def name(self):
        return 'check_ssh'

    def perform(self, config):
        handler = ManagerHandler31()
        handler.execute('echo "Executing test remote command"')


_COMMANDS = [
  ListAgents,
  CheckAgents,
  CheckSSH
]

def _parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    for cmd_cls in _COMMANDS:
        cmd = cmd_cls()
        cmd.prepare_parser(subparsers)
    return parser

def main(args):
    configure_loggers()
    parser = _parser()
    config = parser.parse_args(args)
    config.func(config)


if __name__ == '__main__':
    main(sys.argv[1:])
