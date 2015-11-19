import argparse
import os
import sys
import json
from subprocess import check_output
import subprocess
import tarfile
import tempfile
import threading
import time
import traceback
import shutil
import shlex
from cloudify_rest_client.client import CloudifyClient
from cloudify_rest_client.executions import Execution
from healthcheck import report
from healthcheck.agents import validate_agents

_DIRECTORY = os.path.dirname(os.path.realpath(__file__))
_VERBOSE = True
_HEALTHCHECK_FAILED = 'healtcheck_failed'


def _tempfile():
    _, res = tempfile.mkstemp(dir=os.path.join(_DIRECTORY, 'tmp'))
    return res


def _tempdir():
    return tempfile.mkdtemp(dir=os.path.join(_DIRECTORY, 'tmp'))


def _json_load(path):
    with open(path) as f:
        return json.loads(f.read())


def _json_dump(path, content):
    with open(path, 'w') as f:
        f.write(json.dumps(content, indent=2))


def _mk_public(path):
    os.chmod(path, 0o666)


def get_override_credentials_rules(deployment_id):
    auth = _json_load(os.path.join(_DIRECTORY, 'auth.json'))
    deployment_specific = auth.get(deployment_id, {})
    res = report.get_override_credentials_rules_from_path(
        os.path.join(_DIRECTORY, 'config.json'))
    res['deployment'] = deployment_specific
    return res


def get_deployment_state(deployment_id, client=None):
    if client is None:
        client = CloudifyClient()
    override = get_override_credentials_rules(deployment_id)
    dep_overrides = {}
    dep_overrides[deployment_id] = override['deployment']
    deployment = client.deployments.get(deployment_id)
    state, _ = report.get_deployment_states(
        client, [deployment], report.get_default_agent(client), override, dep_overrides)
    return state[deployment_id]


def healthcheck(deployment_id, version, assert_vms_agents_alive=True, check_vms_access=True):
    client = CloudifyClient()
    result = get_deployment_state(deployment_id, client)
    if not result['ok']:
        result[_HEALTHCHECK_FAILED] = 'wrong_state'
        return result
    agents_alive, dep_alive = validate_agents.check_agents_alive(
        deployment_id, result, version)
    report.add_agents_alive_to_deployment(result, agents_alive)
    if not dep_alive and assert_vms_agents_alive:
        result[_HEALTHCHECK_FAILED] = 'agent_dead'
        return result
    if not check_vms_access:
        return result
    vm_access = validate_agents.check_vm_access(
        deployment_id,
        result,
        report.get_agents_resource('validate_remote_access.py')
    )
    report.add_vm_access_to_deployment(result, vm_access)
    vms_accessible = report.all_vms_accessible(result)
    if not vms_accessible:
        result[_HEALTHCHECK_FAILED] = 'vm_not_accessible'
    return result


def healthcheck_command(config):
    res = healthcheck(config.deployment, config.version)
    with open(config.output, 'w') as f:
        f.write(json.dumps(res, indent=2))
    _mk_public(config.output)


def health_check_and_dump(config):

    CHUNK_SIZE = 100
    dep_id = config.deployment
    data_path = _tempfile()
    events_path = _tempfile()
    state_path = _tempfile()

    dump_storage_template = (
        'http://localhost:9200/'
        'cloudify_storage/node_instance,execution/'
        '_search?from={start}&size={size}&q=deployment_id:{id}')
    dump_events_template = (
        'http://localhost:9200/'
        'cloudify_events/_search?from={start}&size={size}&'
        'q=deployment_id:{id}')

    bulk_entry_template = ('{{ create: {{ "_id": "{id}",'
                           '"_type": "{type}"  }} }}\n{source}\n')

    def get_chunk(cmd):
        return check_output(['curl', '-s', '-XGET', cmd], universal_newlines=True)

    def remove_newlines(s):
        return s.replace('\n', '').replace('\r', '')

    def convert_to_bulk(chunk):
        def get_source(n):
            source = n['_source']
            if n['_type'] == 'execution' and 'is_system_workflow' not in source:
                source['is_system_workflow'] = False
            return json.dumps(source)

        return ''.join([bulk_entry_template.format(
            id=str(n['_id']),
            type=str(n['_type']),
            source=remove_newlines(get_source(n))
        ) for n in chunk])

    def append_to_file(f, js):
        f.write(convert_to_bulk(js['hits']['hits']))

    def dump_chunks(f, template):
        cmd = template.format(id=dep_id, start='0', size=str(CHUNK_SIZE))
        js = json.loads(get_chunk(cmd))
        append_to_file(f, js)
        total = int(js['hits']['total'])
        if total > CHUNK_SIZE:
            for i in xrange(CHUNK_SIZE, total, CHUNK_SIZE):
                cmd = template.format(
                    id=dep_id,
                    start=str(i),
                    size=str(CHUNK_SIZE))
                js = json.loads(get_chunk(cmd))
                append_to_file(f, js)

    res = tarfile.TarFile(config.output, mode='w')
    state = healthcheck(config.deployment, config.version)
    _json_dump(state_path, state)
    res.add(state_path, arcname='state.json')
    if _HEALTHCHECK_FAILED in state:
        res.close()
        _mk_public(config.output)
        return

    with open(data_path, 'w') as f:
        # Storage dumping
        dump_chunks(f, dump_storage_template)
    res.add(data_path, arcname='data.json')
    with open(events_path, 'w') as f:
        # Events dumping
        dump_chunks(f, dump_events_template)
    res.add(events_path, arcname='events.json')
    res.close()
    _mk_public(config.output)


def call(command, quiet=False):
    shlex_split = shlex.split(command)
    if _VERBOSE and not quiet:
        pipes = None
    else:
        pipes = subprocess.PIPE
    p = subprocess.Popen(shlex_split, stdout=pipes,
                         stderr=pipes)
    out, err = p.communicate()
    if p.returncode:
        raise RuntimeError('Command {0} failed.'.format(command))


def call_arr(command, quiet=False):
    if _VERBOSE and not quiet:
        pipes = None
    else:
        pipes = subprocess.PIPE
    p = subprocess.Popen(command, stdout=pipes,
                         stderr=pipes)
    out, err = p.communicate()
    if p.returncode:
        raise RuntimeError('Command {0} failed.'.format(command))


DEL_TEMPLATE = ("curl -s -XDELETE 'http://localhost:9200/"
                "cloudify_storage/node_instance/_query?q=deployment_id:{} '")
BULK_TEMPLATE = ("curl -s XPOST 'http://localhost:9200/"
                 "{index}/_bulk?refresh=1' --data-binary @{file}")
UPDATE_EXEC_WORKFLOW_ID_TEMPLATE = (
    "curl -s XPOST 'http://localhost:9200/cloudify_storage/execution/"
    "{execution_id}/_update' -d '{{\"doc\":{{\"workflow_id\":\"{w_id}\"}}}}'"
)


def recreate_deployment(config):
    archive = tarfile.TarFile(config.input)
    dep_dir = _tempdir()
    archive.extractall(dep_dir)
    call(DEL_TEMPLATE.format(config.deployment), quiet=True)
    client = CloudifyClient()
    create_dep_execution = client.executions.list(
        deployment_id=config.deployment
    )[0]
    call(UPDATE_EXEC_WORKFLOW_ID_TEMPLATE.format(
        execution_id=create_dep_execution.id,
        w_id='create_deployment_environment_3_2_1'
    ), quiet=True)
    call(BULK_TEMPLATE.format(
        file=os.path.join(dep_dir, 'data.json'),
        index='cloudify_storage'
    ), quiet=True)
    call(BULK_TEMPLATE.format(
        file=os.path.join(dep_dir, 'events.json'),
        index='cloudify_events'
    ), quiet=True)
    state = healthcheck(config.deployment, config.version,
                        assert_vms_agents_alive=False)
    if _HEALTHCHECK_FAILED not in state:
        mgmt_workers_alive = state['workflows_worker_alive'] and state[
            'operations_worker_alive']
        if not mgmt_workers_alive:
            state[_HEALTHCHECK_FAILED] = 'management_worker_dead'
    _json_dump(config.output, state)
    _mk_public(config.output)


_ENVS = {
    '3.1.0': '/opt/manager',
    '3.2.0': '/opt/manager/env',
    '3.2.1': '/opt/manager/env'
}


class WorkflowInjector(object):

    def __init__(self, venv, work_dir, includes):
        self.venv = venv
        self.work_dir = work_dir
        self.includes = includes

    def inject(self):
        shutil.copyfile(
            os.path.join(_DIRECTORY, 'software_replacement_workflow.py'),
            os.path.join(self.venv, 'lib', 'python2.7', 'site-packages',
                         'software_replacement_workflow.py'))
        shutil.copyfile(
            os.path.join(self.work_dir, 'celeryd-includes'),
            os.path.join(self.work_dir, 'celeryd-includes.backup'))
        with open(os.path.join(self.work_dir, 'celeryd-includes'), 'w') as f:
            f.write('INCLUDES={0},software_replacement_workflow'.format(
                self.includes))

    def cleanup(self):
        os.rename(
            os.path.join(self.work_dir, 'celeryd-includes.backup'),
            os.path.join(self.work_dir, 'celeryd-includes'))
        try:
            code_path = os.path.join(
                self.venv, 'lib', 'python2.7', 'site-packages')
            os.remove(os.path.join(
                code_path, 'software_replacement_workflow.py'))
            os.remove(os.path.join(
                code_path, 'software_replacement_workflow.pyc'))
        except:
            # Not really an issue
            pass


def _perform_agent_operation(deployment, operation, version):
    variables = _tempfile()
    call_arr([os.path.join(_DIRECTORY, 'dump_deployment_vars.sh'),
              deployment, variables])
    with open(variables) as f:
        content = [line.rstrip('\n') for line in f]
    virtualenv = content[0]
    work_dir = content[1]
    includes = content[2]
    injector = WorkflowInjector(virtualenv, work_dir, includes)
    env = _ENVS[version]
    auth_path = _tempfile()
    state = get_deployment_state(deployment)
    override = get_override_credentials_rules(deployment)
    actions = report.prepare_credentials_override_actions(
        state['agents'], override)
    _json_dump(auth_path, actions)
    with validate_agents.with_deployment_env(
            deployment, version, force_restart=True, restart_init=injector.inject,
            restart_cleanup=injector.cleanup):
        call('{0}/bin/python {1}/modify_agents.py {0} {4} 5 {2} {3} {5}'.format(
            env, _DIRECTORY, deployment, auth_path, operation, version
        ))


def modify_agents(config):
    _perform_agent_operation(
        config.deployment, config.operation, config.version)


def uninstall_agents(config):
    _perform_agent_operation(config.deployment, 'uninstall', config.version)
    state = healthcheck(config.deployment, config.version,
                        assert_vms_agents_alive=False, check_vms_access=False)
    if _HEALTHCHECK_FAILED not in state:
        agent_alive = False
        for agent in state['agents'].itervalues():
            agent_alive = agent_alive or agent['alive']
        if agent_alive:
            state[_HEALTHCHECK_FAILED] = 'agent_alive'
    _json_dump(config.output, state)
    _mk_public(config.output)


def install_agents(config):
    _perform_agent_operation(config.deployment, 'install', config.version)
    state = healthcheck(config.deployment, config.version)
    i = 1
    while i < 5 and _HEALTHCHECK_FAILED in state:
        print 'Post install healtcheck failed - attempt {0}'.format(i)
        time.sleep(4)
        state = healthcheck(config.deployment, config.version)
        i = i + 1
    _json_dump(config.output, state)
    _mk_public(config.output)


def _start_deployment_agents(config, results, deployment):
    print 'Starting agents for deployment {0}'.format(deployment.id)
    dep = {}
    results[deployment.id] = dep
    try:
        state = healthcheck(deployment.id, config.version,
                            assert_vms_agents_alive=False)
        dep['pre_check'] = state
        if _HEALTHCHECK_FAILED in state:
            dep['ok'] = False
            dep['error'] = state[_HEALTHCHECK_FAILED]
            return
        dep_python = '~/cloudify.{0}/env/bin/python'.format(deployment.id)
        dep_path = _tempfile()
        _json_dump(dep_path, state)
        call_arr(['timeout', '200', os.path.expanduser(dep_python),
                  os.path.join(_DIRECTORY, 'start_agents.py'), dep_path])
        dep['ok'] = True
    except Exception as e:
        traceback.print_exc()
        dep['ok'] = False
        dep['error'] = str(e)


def perform_start_agents(config):
    client = CloudifyClient()
    results = {}
    threads = []
    for dep in client.deployments.list():
        thread = threading.Thread(
            target=_start_deployment_agents, args=(config, results, dep))
        thread.start()
        threads.append(thread)
    for t in threads:
        t.join()
    for k, v in results.iteritems():
        print '{0}: {1}, {2}'.format(k, v['ok'], v.get('error', ''))


def _parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    health = subparsers.add_parser('healthcheck_and_dump')
    health.add_argument('--deployment', required=True)
    health.add_argument('--output', required=True)
    health.add_argument('--version', required=True)
    health.set_defaults(func=health_check_and_dump)

    create = subparsers.add_parser('recreate_deployment')
    create.add_argument('--deployment', required=True)
    create.add_argument('--input', required=True)
    create.add_argument('--output', required=True)
    create.add_argument('--version', required=True)
    create.set_defaults(func=recreate_deployment)

    modify = subparsers.add_parser('modify_agents')
    modify.add_argument('--deployment', required=True)
    modify.add_argument('--version', required=True)
    modify.add_argument('--operation', required=True)
    modify.set_defaults(func=modify_agents)

    uninstall_p = subparsers.add_parser('uninstall_agents')
    uninstall_p.add_argument('--deployment', required=True)
    uninstall_p.add_argument('--version', required=True)
    uninstall_p.add_argument('--output', required=True)
    uninstall_p.set_defaults(func=uninstall_agents)

    install_p = subparsers.add_parser('install_agents')
    install_p.add_argument('--deployment', required=True)
    install_p.add_argument('--version', required=True)
    install_p.add_argument('--output', required=True)
    install_p.set_defaults(func=install_agents)

    healthcheck_p = subparsers.add_parser('healthcheck')
    healthcheck_p.add_argument('--deployment', required=True)
    healthcheck_p.add_argument('--version', required=True)
    healthcheck_p.add_argument('--output', required=True)
    healthcheck_p.set_defaults(func=healthcheck_command)

    start_agents = subparsers.add_parser('start_agents')
    start_agents.add_argument('--version', required=True)
    start_agents.set_defaults(func=perform_start_agents)
    return parser


def main(args):
    parser = _parser()
    config = parser.parse_args(args)
    config.func(config)

if __name__ == '__main__':
    main(sys.argv[1:])
