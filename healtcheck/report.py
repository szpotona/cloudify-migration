import argparse
import json
import os
import urllib
import uuid
import sys
import tempfile
import threading
import traceback
import time
from cloudify_cli.utils import get_rest_client

from distutils import spawn
from subprocess import call


_DIRECTORY = os.path.dirname(os.path.realpath(__file__))
_TENANTS = ''
_USER = ''
_MANAGER_KEY = ''


def _read(filename):
    with open(filename) as f:
        return json.loads(f.read())


def set_globals(config):
    conf = _read(config.config)
    global _TENANTS
    global _USER
    global _MANAGER_KEY
    _TENANTS = conf['tenants']
    _USER = conf['user']
    _MANAGER_KEY = conf['manager_key']    
    if not _TENANTS or not _USER or not _MANAGER_KEY:
        raise RuntimeError('Wrong configuration')


class Command(object):

    def prepare_parser(self, subparsers):
        subparser = subparsers.add_parser(self.name)
        self.prepare_args(subparser)
        subparser.set_defaults(func=self.perform)

    def prepare_args(self, parser):
        pass


def _get_agents_resource(resource):
    return os.path.join(_DIRECTORY, 'agents', resource)


def _get_deployment_states(client, deployments):
    res = {}
    agents_count = 0
    for deployment in deployments:
        print 'Deployment {}'.format(deployment.id)
        dep_states = set()
        dep_agents = {}
        for node in client.nodes.list(deployment_id=deployment.id):
            for node_instance in client.node_instances.list(
                    deployment_id=deployment.id, node_name=node.id):
                dep_states.add(node_instance.state)
                if 'cloudify.nodes.Compute' in node.type_hierarchy:
                    dep_agents[
                        node_instance.id] = {
                        'state': node_instance.state,
                        'ip': node_instance.runtime_properties.get(
                            'ip',
                            node.properties.get(
                                'ip',
                                '')),
                        'cloudify_agent': node.properties.get(
                            'cloudify_agent',
                            {}),
                        'is_windows': 'cloudify.openstack.nodes.WindowsServer' in node.type_hierarchy}

        if len(dep_states) > 1:
            status = 'mixed'
        elif len(dep_states) == 1:
            status = next(iter(dep_states))
        else:
            status = 'empty'
        agents_count += len(dep_agents)
        executions = [(e.created_at, e.workflow_id)
                      for e in client.executions.list(deployment_id=deployment.id)]
        res[deployment.id] = {
            'status': status,
            'agents': dep_agents,
            'ok': status in ['empty', 'started'],
            'states': list(dep_states),
            'executions': executions}
    return res, agents_count


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


def insert_blueprint_report(res, client, blueprint, deployments, config):
    res['multi_sec_nodes'] = _has_multi_sec_nodes(blueprint)
    deployments = [
        dep for dep in deployments if dep.blueprint_id == blueprint.id]
    res['deployments_count'] = len(deployments)
    res['deployments'], res[
        'agents_count'] = _get_deployment_states(client, deployments)


def _get_blueprints(client, blueprints, deployments, config):
    threads = []
    res = {}
    for blueprint in blueprints:
        res[blueprint.id] = {}
        thread = threading.Thread(target=insert_blueprint_report, args=(
            res[blueprint.id], client, blueprint, deployments, config))
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()
    agents_count = 0
    for name, blueprint_res in res.iteritems():
        agents_count = agents_count + blueprint_res.get('agents_count', 0)
    return res, agents_count


class LocalFile():

    def __init__(self, handler, remote_path):
        self.handler = handler
        self.remote_path = remote_path
        self.target_path = None

    def __enter__(self):
        _, self.target_path = tempfile.mkstemp()
        self.handler.load_file(self.remote_path, self.target_path)
        return self.target_path

    def __exit__(self, type, value, traceback):
        os.remove(self.target_path)


class ManagerHandler(object):

    def __init__(self, ip):
        self.manager_ip = ip

    def scp(self, local_path, path_on_manager, to_manager):
        scp_path = spawn.find_executable('scp')
        management_path = '{0}@{1}:{2}'.format(
            _USER,
            self.manager_ip,
            path_on_manager
        )
        command = [scp_path, '-i', os.path.expanduser(_MANAGER_KEY)]
        if to_manager:
            command += [local_path, management_path]
        else:
            command += [management_path, local_path]
        if call(command):
            raise RuntimeError(
                'Could not scp to/from manager: {0}'.format(command))

    def local_file(self, remote):
        return LocalFile(self, remote)

    def send_file(self, source, target):
        self.scp(source, target, True)

    def load_file(self, source, target):
        self.scp(target, source, False)

    def execute(self, cmd, timeout=None):
        ssh_cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', '-i',
                   os.path.expanduser(_MANAGER_KEY), '{0}@{1}'.format(
                       _USER, self.manager_ip), '-C', cmd]
        if timeout:
            cmd_list = ["timeout", str(timeout)]
            cmd_list.extend(ssh_cmd)
        else:
            cmd_list = ssh_cmd
        result = call(cmd_list)
        if result:
            raise RuntimeError(
                'Could not execute remote command "{0}"'.format(cmd))

    def files(self):
        return FileManager(self)


class ManagerHandler31(ManagerHandler):

    def python_call(self, cmd):
        self.execute(
            '/opt/celery/cloudify.management__worker/env/bin/python {0}'.format(cmd))

    def call(self, cmd):
        self.execute(cmd)

    def container_path(self, directory, filename):
        return '~/{0}/{1}'.format(directory, filename)


class ManagerHandler32(ManagerHandler):

    def docker_execute(self, cmd):
        self.execute('sudo docker exec cfy {0}'.format(cmd))

    def python_call(self, cmd):
        self.docker_execute(
            '/etc/service/celeryd-cloudify-management/env/bin/python {0}'.format(cmd))

    def call(self, cmd):
        self.docker_execute(cmd)

    def container_path(self, directory, filename):
        return '/tmp/home/{0}/{1}'.format(directory, filename)


class FileManager(object):

    def __init__(self, handler):
        self.handler = handler
        self.directory = 'migration-report-data_{0}'.format(uuid.uuid4())
        self.path = '~/{0}'.format(self.directory)

    def __enter__(self):
        self.handler.execute('mkdir {0}'.format(self.path))
        return self

    def __exit__(self, type, value, traceback):
        self.handler.execute('rm -rf {0}'.format(self.path))

    def filename(self):
        return '_tmp_file{0}'.format(uuid.uuid4())

    def send(self, path):
        filename = self.filename()
        out_path = '{0}/{1}'.format(self.path, filename)
        self.handler.send_file(path, out_path)
        return self.handler.container_path(self.directory, filename), out_path

    def get_path(self):
        filename = self.filename()
        out_path = '{0}/{1}'.format(self.path, filename)
        return self.handler.container_path(self.directory, filename), out_path


def _get_handler(version, ip):
    if version.startswith('3.1'):
        return ManagerHandler31(ip)
    else:
        return ManagerHandler32(ip)


def _add_agents_alive_info(env_result):
    if not env_result.get('manager_ssh'):
        return
    handler = _get_handler(env_result['version'], env_result['ip'])
    deployments = {}
    for blueprint in env_result.get('blueprints', {}).itervalues():
        for name, deployment in blueprint['deployments'].iteritems():
            if deployment.get('ok'):
                deployments[name] = {}
                deployments[name]['agents'] = deployment.get('agents', {})
    _, path = tempfile.mkstemp()
    with open(path, 'w') as f:
        f.write(json.dumps(deployments))
    with handler.files() as files:
        input_file, _ = files.send(path)
        script, _ = files.send(_get_agents_resource('validate_agents.py'))
        cont_result, load_result = files.get_path()
        handler.python_call('{0} {1} {2} {3}'.format(
            script, input_file, cont_result, env_result['version']))
        with handler.local_file(load_result) as local_result:
            result_deployments = _read(local_result)
    for blueprint in env_result.get('blueprints', {}).itervalues():
        for name, deployment in blueprint['deployments'].iteritems():
            if name in result_deployments:
                res_deployment = result_deployments[name]
                deployment['workflows_worker_alive'] = res_deployment[
                    'workflows_worker_alive']
                deployment['operations_worker_alive'] = res_deployment[
                    'operations_worker_alive']
                dep_alive = deployment['workflows_worker_alive'] and deployment[
                    'operations_worker_alive']
                for agent_name, alive in res_deployment[
                        'agents_alive'].iteritems():
                    deployment['agents'][agent_name]['alive'] = alive
                    dep_alive = dep_alive and alive
                deployment['alive'] = dep_alive


def prepare_report(result, env, config):
    ip = env['config']['MANAGER_IP_ADDRESS']
    result['ip'] = ip
    if env.get('inactive'):
        result['inactive'] = True
        return
    _, temp = tempfile.mkstemp()
    print temp
    status = call(['timeout', '2', 'wget', ip, '-O', temp])
    if status:
        result['msg'] = 'Cant connect to manager'
        return
    os.remove(temp)
    client = get_rest_client(manager_ip=ip)
    result['version'] = client.manager.get_version()['version']
    if config.test_manager_ssh:
        handler = _get_handler(result['version'], ip)
        try:
            handler.execute('echo test > /dev/null', timeout=4)
            content = str(uuid.uuid4())
            with handler.files() as files:
                tmp_file, _ = files.send(
                    _get_agents_resource('validate_manager_env.py'))
                cont_res, load_res = files.get_path()
                handler.python_call('{0} {1} {2}'.format(
                    tmp_file, cont_res, content))
                with handler.local_file(load_res) as local_path:
                    with open(local_path) as f:
                        res = f.read()
                        if res != content:
                            raise RuntimeError(
                                'Invalid result retrieved, expected {0}, got {1}'.format(
                                    content, res))
            result['manager_ssh'] = True
        except Exception as e:
            traceback.print_exc()
            result['manager_ssh'] = False
            result['manager_ssh_error'] = str(e)
    if config.blueprints_states:
        deployments = client.deployments.list()
        if config.blueprint:
            blueprints = [client.blueprints.get(blueprint_id=config.blueprint)]
        else:
            blueprints = client.blueprints.list()
        result['blueprints'], result['agents_count'] = _get_blueprints(
            client, blueprints, deployments, config)
        result['deployments_count'] = len(deployments)
        result['blueprints_count'] = len(blueprints)
    if config.test_agents_alive:
        _add_agents_alive_info(result)
    return result


def insert_env_report(env_result, env, config):
    try:
        prepare_report(env_result, env, config)
    except Exception as e:
        traceback.print_exc()
        env_result[
            'error'] = 'Could not create report, cause: {0}'.format(str(e))


def _output(config, res):
    if config.output:
        with open(config.output, 'w') as out:
            out.write(json.dumps(res, indent=2))
    else:
        print json.dumps(res, indent=2)


class Generate(Command):

    @property
    def name(self):
        return 'generate'

    def prepare_args(self, parser):
        parser.add_argument('--config', default='config.json')
        parser.add_argument('--manager')
        parser.add_argument('--env')
        parser.add_argument('--output')
        parser.add_argument('--deployment')
        parser.add_argument('--blueprints-states',
                            default=False, action='store_true')
        parser.add_argument('--blueprint')
        parser.add_argument('--test-manager-ssh',
                            default=False, action='store_true')
        parser.add_argument('--test-agents-alive',
                            default=False, action='store_true')

    def perform(self, config):
        set_globals(config)
        res = {}
        try:
            print _TENANTS
            tenants, _ = urllib.urlretrieve(_TENANTS)
            managers = _read(tenants)
            if config.manager:
                managers = {
                    config.manager: managers[config.manager]
                }
            if config.env:
                new_managers = {}
                for name, manager in managers.iteritems():
                    envs = {}
                    for env_name, env in manager['environments'].iteritems():
                        if env_name == config.env:
                            envs[env_name] = env
                    if envs:
                        manager['environments'] = envs
                        new_managers[name] = manager
                managers = new_managers
            result = {}
            res['managers'] = result
            threads = []
            for mgr_name, manager in managers.iteritems():
                print 'Manager {0}'.format(mgr_name)
                mgr_result = {}
                for env_name, env in manager['environments'].iteritems():
                    env_result = {}
                    thread = threading.Thread(target=insert_env_report,
                                              args=(env_result, env, config))
                    thread.start()
                    threads.append(thread)
                    mgr_result[env_name] = env_result
                result[mgr_name] = mgr_result
            for thread in threads:
                thread.join()
            for key in [
                    'agents_count',
                    'deployments_count',
                    'blueprints_count']:
                val = 0
                for manager in res['managers'].itervalues():
                    for env in manager.itervalues():
                        val = val + env.get(key, 0)
                res[key] = val
        finally:
            _output(config, res)


class ToCsv(Command):

    @property
    def name(self):
        return 'to_csv'

    def prepare_args(self, parser):
        parser.add_argument('--input', required=True)
        parser.add_argument('--output', required=True)
        parser.add_argument('--summary', required=True)

    def perform(self, config):
        raport = _read(config.input)
        with open(config.output, 'w') as f, open(config.summary, 'w') as summary:
            f.write('{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10}\n'.format(
                'manager',
                'env',
                'ip',
                'blueprint',
                'multi_sec_group',
                'deployment',
                'version',
                'nodes status',
                'are agents on both manager and hosts responding?',
                'last_execution_start_date',
                'last_execution_start_time',
            ))
            summary.write('{0},{1},{2},{3},{4},{5}\n'.format(
                'manager',
                'env',
                'version',
                'all_deployments',
                'valid_deployments',
                'checked'
            ))

            for mgr_name, manager in raport['managers'].iteritems():
                for env_name, env in manager.iteritems():
                    checked = 'inactive' not in env and 'msg' not in env and 'error' not in env and env.get(
                        'manager_ssh')
                    version = env.get('version', '')
                    ip = env['ip']
                    deployments_count = 0
                    valid_deployments_count = 0
                    for bpt_name, bpt in env.get('blueprints', {}).iteritems():
                        multi_sec_group = bpt.get('multi_sec_nodes', '')
                        for dp_name, dp in bpt['deployments'].iteritems():
                            state = dp['status']
                            alive = dp.get('alive', 'skipped')
                            valid = state in ['started',
                                              'empty'] and alive is True
                            deployments_count = deployments_count + 1
                            if valid:
                                valid_deployments_count = valid_deployments_count + 1
                            timestamps = sorted(
                                [t for t, _ in dp.get('executions', [''])])
                            if not timestamps:
                                timestamps = ['']
                            last = timestamps[-1]
                            times = last.split()
                            times.append('')
                            times.append('')
                            date = times[0]
                            time = times[1]
                            f.write(
                                '{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10}\n'.format(
                                    mgr_name,
                                    env_name,
                                    ip,
                                    bpt_name,
                                    multi_sec_group,
                                    dp_name,
                                    version,
                                    state,
                                    alive,
                                    date,
                                    time))
                    summary.write(
                        '{0},{1},{2},{3},{4},{5}\n'.format(
                            mgr_name,
                            env_name,
                            version,
                            deployments_count,
                            valid_deployments_count,
                            checked))

_COMMANDS = [
    Generate,
    ToCsv
]


def _parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    for cmd_cls in _COMMANDS:
        cmd = cmd_cls()
        cmd.prepare_parser(subparsers)
    return parser


def main(args):
    parser = _parser()
    config = parser.parse_args(args)
    config.func(config)


if __name__ == '__main__':
    main(sys.argv[1:])
