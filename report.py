import argparse
import json
import urllib
import sys
import threading
from cloudify_cli.utils import get_rest_client
from subprocess import call


_DIRECTORY = os.path.dirname(os.path.realpath(__file__))
_TENNANTS = "http://git.cloud.td.com/its-cloud/management-cluster/raw/master/bootstrap/tenants.json"
_USER = 'cloudify'


class Command(object):

    def prepare_parser(self, subparsers):
        subparser = subparsers.add_parser(self.name)
        self.prepare_args(subparser)
        subparser.set_defaults(func=self.perform)

    def prepare_args(self, parser):
        pass


def _ret_msg(msg):
    return {
        'msg': msg
    }


def _get_deployment_states(client, deployments):
    res = {}
    agents_count = 0
    for deployment in deployments:
        print 'Deployment {}'.format(deployment.id)
        dep_states = set()
        dep_agents = {}
        for node in client.nodes.list(deployment_id=deployment.id):
            for node_instance in client.node_instances.list(deployment_id=deployment.id,
                                                            node_name=node.id):
                dep_states.add(node_instance.state)
                if 'cloudify.nodes.Compute' in node.type_hierarchy:
                    dep_agents[node_instance.id] = {
                        'state': node_instance.state,
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
        agents_count += len(dep_agents)
        res[deployment.id] = {
            'status': status,
            'agents': dep_agents,
            'ok': status in ['empty', 'started'],
            'states': list(dep_states)}
    return res, agents_count


def prepare_report(env, config):
    if env.get('inactive'):
        return {
            'inactive': True
        }
    ip = env['config']['MANAGER_IP_ADDRESS']
    status = call(['timeout', '2', 'wget', ip, '-o', '/tmp/index.html'])
    if status:
        return _ret_msg('Cant connect to manager')
    client = get_rest_client(manager_ip=ip)
    result = {}
    result['ip'] = ip
    result['version'] = client.manager.get_version()['version']
    if config.deployment_states:
        if config.deployment:
            deployments = [client.deployments.get(deployment_id=config.deployment)]
        else:
            deployments = client.deployments.list()
        result['deployments'], result['agents_count'] = _get_deployment_states(client, deployments)
    return result 


def insert_env_report(env_result, env, config):
    try:
        report = prepare_report(env, config)
    except Exception as e:
        report = {
            'error': 'Could not create report, cause: {0}'.format(str(e))
        }
    env_result['report'] = report
 


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
        parser.add_argument('--manager')
        parser.add_argument('--env')
        parser.add_argument('--output')
        parser.add_argument('--deployment')
        parser.add_argument('--deployment-states', default=False, action='store_true')

    def perform(self, config):
        tennants, _ = urllib.urlretrieve(_TENNANTS)
        with open(tennants) as f:
            managers = json.loads(f.read()) 
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
        _output(config, result)


_COMMANDS = [
    Generate
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
