import argparse
import json

from cloudify_cli.utils import get_rest_client
from cloudify_cli.logger import configure_loggers


import os
import sys
import logging
from distutils import spawn
from cloudify_cli.utils import get_management_user
from cloudify_cli.utils import get_management_server_ip
from cloudify_cli.utils import get_management_key
from cloudify_cli.commands.ssh import ssh
from subprocess import call


_DIRECTORY = os.path.dirname(os.path.realpath(__file__))

def _std_err(msg):
    sys.stderr.write('{}\n'.format(msg))

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


def _read(filename):
    with open(filename) as f:
        return json.loads(f.read())


def _read_input(config):
    return _read(config.input)


def _output(config, res):
    if config.output:
        with open(config.output, 'w') as out:
            out.write(json.dumps(res, indent=2))
    else:
        print json.dumps(res, indent=2)
     

def _get_deployments(client, config):
    if config.deployment_id:
        deployments = [client.deployments.get(deployment_id=config.deployment_id)]
    else:
        deployments = client.deployments.list()
    return deployments 


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
        deployments = _get_deployments(client, config)
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


def _fill_deployments_alive(deployments):
    all_alive = True
    for deployment_id, agents in deployments.iteritems():
        alive = agents['workflows_worker_alive'] and agents['operations_worker_alive']
        for name, agent in agents['agents'].iteritems():
            alive = alive and agent['alive']
        agents['deployment_alive'] = alive
        all_alive = all_alive and alive
    return all_alive


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
        handler.send_file(
            _get_agents_resource('validate_agents.py'),
            '/tmp/validate_agents.py')
        target_file = '/tmp/_agents.json'
        result_file = '/tmp/_result.json'
        handler.send_file(config.input, target_file)
        handler.python_call('/tmp/validate_agents.py '
                            '{0} {1}'.format(target_file, result_file))
        handler.load_file(result_file, result_file)
        with open(result_file) as f:
            res = json.loads(f.read())
        all_alive = _fill_deployments_alive(res)
        _output(config, res)
        if not all_alive:
            raise RuntimeError('There are deployments that seems to be dead')



class ListDeploymentsStates(Command):
    
    @property
    def name(self):
        return 'deployments_states'

    def prepare_args(self, parser):
        parser.add_argument('--input', required=False)
        parser.add_argument('-d', help='Deployment id', dest='deployment_id')
        parser.add_argument('--output')
        parser.add_argument('--invalid-only', default=False, action='store_true')
        parser.add_argument('--valid-only', default=False, action='store_true')

    def perform(self, config):
        client = get_rest_client()
        version = client.manager.get_version()['version']
        res = {}
        if config.input:
            res = _read_input(config)
        else:
            deployments = _get_deployments(client, config)
            for deployment in deployments:
                logger.info('Checking {0}'.format(deployment.id))
                dep_states = set()
                dep_agents = {}
                for node in client.nodes.list(deployment_id=deployment.id):
                    for node_instance in client.node_instances.list(deployment_id=deployment.id,
                                                                    node_name=node.id):
                        dep_states.add(node_instance.state)
                        if 'cloudify.nodes.Compute' in node.type_hierarchy:
                            dep_agents[node_instance.id] = {
                                'state': node_instance.state,
                                'version': version,
                                'ip': node_instance.runtime_properties.get('ip', node.properties.get('ip', '')),
                                'cloudify_agent': node.properties.get('cloudify_agent', {}),
                                'is_windows': 'cloudify.openstack.nodes.WindowsServer' in node.type_hierarchy

                            }
 

                if len(dep_states) > 1:
                    status = 'mixed'
                elif len(dep_states) == 1:
                    status = next(iter(dep_states))
                else:
                    status = 'empty'
                res[deployment.id] = {
                    'status': status,
                    'agents': dep_agents,
                    'ok': status in ['empty', 'started'],
                    'states': list(dep_states)}
        if config.invalid_only:
            res = dict([ (k, v) for k, v in res.iteritems() if v['ok'] is False])
        if config.valid_only:
            res = dict([ (k, v) for k, v in res.iteritems() if v['ok'] is True])
        _output(config, res)


class FilterDeployments(Command):
    
    @property
    def name(self):
        return 'filter_deployments'

    def prepare_args(self, parser):
        parser.add_argument('--input', required=True)
        parser.add_argument('--output')
        parser.add_argument('--field', required=True)

    def perform(self, config):
        deps = _read_input(config)
        _output(config, dict([(k, v) for k, v in deps.iteritems() if v[config.field] is True]))

       
class CheckSSH(Command):
    
    @property
    def name(self):
        return 'check_ssh'

    def perform(self, config):
        handler = ManagerHandler31()
        handler.execute('echo "Executing test remote command"')


def _has_multi_sec_nodes(blueprint):
    types = {}
    for node in blueprint.plan['nodes']:
        types[node['name']] = node['type_hierarchy']
    for node in blueprint.plan['nodes']:
        name = node['name']
        if 'cloudify.nodes.Compute' in types[name]:
            connected_sec_groups = []
            for relationship in node['relationships']:
                target = relationship['target_id']
                if 'cloudify.nodes.SecurityGroup' in types[target]:
                    connected_sec_groups.append(target)
            if len(connected_sec_groups) > 1:
                return True
    return False


def _blueprints_with_multi_sec_group_nodes(client, blueprint_id):
    if blueprint_id:
        blueprints = [client.blueprints.get(blueprint_id=blueprint_id)]
    else:
        blueprints = client.blueprints.list()
    result = []
    for blueprint in blueprints:
        if _has_multi_sec_nodes(blueprint):
            result.append(blueprint.id)
    return result 

class Managers(Command):
 
    @property
    def name(self):
        return 'managers'

    def prepare_args(self, parser):
        parser.add_argument('--input', required=True)
        parser.add_argument('--skip-ips')
        parser.add_argument('--name')
        parser.add_argument('--output')
        parser.add_argument('--multi_sec_blueprints', default=False, action='store_true')
        parser.add_argument('--blueprint')

    def perform(self, config):
        managers = _read_input(config)
        if config.skip_ips:
            ips_to_skip = _read(config.skip_ips)
        else:
            ips_to_skip = []
        result = {}
        for name, value in managers.iteritems():
            _std_err('Manager {}'.format(name))
            manager_result = {}
            for env_name, env in value['environments'].iteritems():
                ip = env['config']['MANAGER_IP_ADDRESS']
                _std_err('  Environment {} {}'.format(env_name, ip))
                if ip in ips_to_skip:
                    manager_result[env_name] = {
                        'ip': ip,
                        'deployments_count': '',
                        'msg': 'skipped'
                    }
                else:
                    client = get_rest_client(
                        manager_ip=env['config']['MANAGER_IP_ADDRESS'])
                    manager_result[env_name] = {
                        'ip': ip,
                        'deployments_count': len(client.deployments.list()),
                        'blueprints_count': len(client.blueprints.list())
                    }
                    if config.multi_sec_blueprints:
                        manager_result[env_name][
                            'multi_sec_blueprints'] =_blueprints_with_multi_sec_group_nodes(client, config.blueprint)
                result[name] = manager_result
        _output(config, result)
     
class MultiSecBlueprintsToCsv(Command):

    @property
    def name(self):
        return 'multi_sec_blueprints_to_csv'

    def prepare_args(self, parser):
        parser.add_argument('--input', required=True)
        parser.add_argument('--output', required=True)

    def perform(self, config):
        managers = _read_input(config)
        with open(config.output, 'w') as f:
            for mngr_name, mngr in managers.iteritems():
                for env_name, env in mngr.iteritems():
                    for blueprint in env.get('multi_sec_blueprints', []):
                        f.write('{0},{1},{2}\n'.format(
                            mngr_name,
                            env_name,
                            blueprint))


_COMMANDS = [
  ListAgents,
  CheckAgents,
  CheckSSH,
  ListDeploymentsStates,
  FilterDeployments,
  Managers,
  MultiSecBlueprintsToCsv
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
