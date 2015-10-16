import argparse
import healthcheck.report as report
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid
import json
import yaml
import time
import datetime
import traceback

from cloudify_rest_client.executions import Execution

_DIRECTORY = os.path.dirname(os.path.realpath(__file__))

_VERBOSE = False
_ENVS = os.path.join(_DIRECTORY, 'envs')
_HEALTHCHECK_FAILED = 'healtcheck_failed'


def _json_load(path):
    with open(path) as f:
        return json.loads(f.read())

def _json_load_remote(runner, load_path, tmp_path):
    _, result_local = tempfile.mkstemp(dir=tmp_path)
    runner.handler.load_file(load_path, result_local)
    return _json_load(result_local) 
 

def call(command):
    if _VERBOSE:
        print 'Executing {0}'.format(command)
    shlex_split = shlex.split(command)
    if _VERBOSE:
        pipes = None
    else:
        pipes = subprocess.PIPE
    p = subprocess.Popen(shlex_split, stdout=pipes,
                         stderr=pipes)
    out, err = p.communicate()
    if p.returncode:
        raise RuntimeError('Command {0} failed.'.format(command))


def _mk_env(version):
    directory = version.replace('.', '_')
    path = os.path.join(_ENVS, directory)
    call('virtualenv {0}'.format(path))
    call('{0}/bin/pip install cloudify=={1}'.format(
        path, version
    ))

_VERSIONS = [
  '3.1.0',
  '3.2.0',
  '3.2.1'
]

def init(config):
    call('mkdir {0}'.format(_ENVS))
    for v in _VERSIONS:
        _mk_env(v)


class CfyRunner(object):
     
    def __init__(self, version, ip, rest):
        self.version = version
        self.env = os.path.join(_ENVS, version.replace('.', '_'))
        self.directory = os.path.join(_ENVS, ip.replace('.', '_'))
        self.ip = ip
        self.rest = rest
        self.handler = report.get_handler(version, ip)

    def mkdir(self):
        call('mkdir -p {0}'.format(self.directory))

    def cfy_run(self, cmd):
        cwd = os.getcwd()
        os.chdir(self.directory)
        try:
            activate_path = os.path.join(self.env, 'bin/activate')
            cfy_path = os.path.join(self.env, 'bin/cfy')
            call('bash -c ". {0} && {1} {2}"'.format(
                activate_path, cfy_path, cmd))
        finally:
            os.chdir(cwd) 

    def python_run(self, cmd):
        cwd = os.getcwd()
        os.chdir(self.directory)
        try:
            python_path = os.path.join(self.env, 'bin/python')
            call('{0} {1}'.format(python_path, cmd))
        finally:
            os.chdir(cwd) 


def _cfy_runner(ip):
    rest_client = report.get_rest_client(ip)
    version = rest_client.manager.get_version()['version']
    return CfyRunner(version, ip, rest_client)

def _init_runner(ip):
    runner = _cfy_runner(ip)
    runner.mkdir()
    runner.cfy_run('init -r')
    runner.cfy_run('use -t {0}'.format(ip))
    runner.cfy_run('status')
    return runner

def _upload_blueprint(blueprints_path, blueprint_arch, runner,
                      old_blueprints):
    blueprint = blueprint_arch[:-len('.tar.gz')]
    if blueprint in old_blueprints:
        return
    blueprint_path = os.path.join(blueprints_path, blueprint)
    call('mkdir {0}'.format(blueprint_path))
    try:
        call('tar zxf {0} -C {1} --strip-components 1'.format(
            os.path.join(blueprints_path, blueprint_arch),
            blueprint_path
        ))
        possible_blueprints = []
        for blueprint_file in os.listdir(blueprint_path):
            if blueprint_file.endswith('.yaml'):
                possible_blueprints.append(blueprint_file)
        if len(possible_blueprints) == 0:
            raise RuntimeError('No yaml file in blueprint {0}'.format(
                blueprint))
        if len(possible_blueprints) == 1:
            to_upload = possible_blueprints[0]
        else:
            print 'Migrating blueprint {0}'.format(blueprint)
            to_upload = None
            query = 'Is {0} a blueprint you want to migrate? [y/n] '
            while to_upload is None:
                for candidate in possible_blueprints:
                    answer = raw_input(query.format(candidate))
                    if answer == 'y':
                        to_upload = candidate
                        break
                if to_upload is None:
                    skip = raw_input('No file chosen, do you want to skip '
                                     'this blueprint? [y/n] ')
                    if skip == 'y':
                        return
        runner.cfy_run('blueprints upload -p {0} -b {1}'.format(
            os.path.join(blueprint_path, to_upload), blueprint
        ))
    finally:
        shutil.rmtree(blueprint_path)

def migrate_blueprints(source_runner, target_runner):
    blueprints_path = tempfile.mkdtemp(prefix='blueprints_dir')
    try:
        source_runner.python_run('{0} {1}'.format(
            os.path.join(_DIRECTORY, 'utils', 'download_blueprints.py'),
            blueprints_path))
        blueprints = [b.id for b in target_runner.rest.blueprints.list()]
        for blueprint in os.listdir(blueprints_path):
            _upload_blueprint(blueprints_path, blueprint, target_runner,
                              blueprints)
    finally:
        shutil.rmtree(blueprints_path) 


def install_code(handler, directory, config):
    path = tempfile.mkdtemp()
    try:
        conf = _json_load(config.config)
        auth_path = conf.get('deployments_auth_override_path')
        if auth_path:
            auth = _json_load(auth_path)
        else:
            auth = {}
        with open(os.path.join(_DIRECTORY, 'remote', 'auth.json'), 'w') as f:
            f.write(json.dumps(auth))
        arch_path = os.path.join(path, 'arch.tar.gz')
        call('cp -rf {0}/healthcheck {0}/remote'.format(_DIRECTORY))
        call('cp {0} {1}/remote/config.json'.format(config.config, _DIRECTORY))
        call('bash -c "cd {1}/remote ; tar -cf {0} *;"'.format(arch_path, _DIRECTORY))
        call('rm -rf {0}/remote/healthcheck'.format(_DIRECTORY))
        call('rm {0}/remote/config.json {0}/remote/auth.json'.format(_DIRECTORY))
        handler.execute('mkdir -p {0}'.format(directory))
        handler.send_file(arch_path, directory)
        handler.execute('tar xf {0} -C {1} && cd {1} && mkdir -p tmp'.format(
            os.path.join(directory, 'arch.tar.gz'), directory))
    finally:
        shutil.rmtree(path)

_REMOTE_PATH = 'migration'
_REMOTE_TMP = os.path.join(_REMOTE_PATH, 'tmp')


def _wait_for_execution(execution_id, client):
    execution = client.executions.get(execution_id)
    while execution.status not in Execution.END_STATES:
        time.sleep(2)
        print 'Waiting for execution {0}'.format(execution_id)
        execution = client.executions.get(execution_id)

def _log_msg(deployment_id, msg, logpath):
    message = '{0}: <{1}> {2}\n'.format(
        datetime.datetime.now(),
        deployment_id,
        msg
    )
    print message
    with open(logpath, 'a') as f:
        f.write(message)
 
def _perform_migration(deployment, existing_deployments,
                       source_runner, target_runner, logpath):
    done = False
    retry = False
    result = {}
    _log_msg(deployment.id, 'starting migration', logpath)
    while not done:
        internal_error = False
        try:
            _migrate_deployment(deployment, existing_deployments, source_runner, target_runner, result)
        except Exception as e:
            traceback.print_exc()
            internal_error = True
            result['error'] = str(e)
        phase = result['phase']
        error = result['error']
        if internal_error:
            print 'Phase {0}: internal error: "{1}"'.format(phase, error)
        else:
            if phase == 'deployment_migrated':
                migration_state = 'migrated'
                done = True
            elif phase == 'starting':
                if not retry:
                    migration_state = 'skipped_automatically'
                    done = True
        if not done and not internal_error:
            print 'Phase {0}: healthcheck error: "{1}"'.format(phase, error)
        if not done:
            print 'Failure during migration of deployment {0} detected'.format(deployment.id)
            answer = ''
            while answer not in ['skip', 'retry', 'abort']:
                print 'Choose action [skip,retry,abort]'
                answer = raw_input('--> ')
            if answer == 'skip':
                migration_state = 'skipped_manually'
                done = True
            elif answer == 'retry':
                retry = True
            else:
                msg = '{0}, phase {1}, error: {2}'.format(
                    'aborted', phase, error
                )
                _log_msg(deployment.id, msg, logpath) 
                raise RuntimeError('Migration aborted')


    if migration_state == 'migrated':
        msg = 'migrated'
    else:
        msg = '{0}, phase {1}, error: {2}'.format(
            migration_state, phase, error
        )
    _log_msg(deployment.id, msg, logpath)


def _migrate_deployment(deployment, existing_deployments,
                        source_runner, target_runner, result):
    phase = 'starting'
    error = ''
    deployment_path = tempfile.mkdtemp(
        prefix='deployment_dir_{0}'.format(deployment.id))
    try:
        print 'Deployment {0}:'.format(deployment.id)
        if deployment.id in existing_deployments:
            print 'Deployment already exists, skipping'
            error = 'Deployment exists'
            return
        filename = str(uuid.uuid4())
        source_output_parameter_path = source_runner.handler.container_path(_REMOTE_TMP, filename)
        source_output_load_path = '~/{0}/{1}'.format(_REMOTE_TMP, filename)
        filename = str(uuid.uuid4())
        target_output_parameter_path = target_runner.handler.container_path(_REMOTE_TMP, filename)
        target_output_load_path = '~/{0}/{1}'.format(_REMOTE_TMP, filename)
 
        print 'Healthcheck and data dump...'        
        source_runner.handler.python_call('{0} healthcheck_and_dump --deployment {1} --output {2} --version {3}'.format(
            source_runner.handler.container_path(_REMOTE_PATH, 'main.py'),
            deployment.id,
            source_output_parameter_path,
            source_runner.version
        ))
        res_path = os.path.join(deployment_path, 'arch.tar.gz')
        print 'Downloading data dump...'        
        source_runner.handler.load_file(source_output_load_path, res_path)
        with tarfile.TarFile(res_path) as tar:
            state_file = tar.extractfile('state.json')
            state = json.loads(state_file.read())
        
        if _HEALTHCHECK_FAILED in state:
            error = 'Initial healtcheck for deployment {0} failed, reason: {1}'.format(
                deployment.id, state[_HEALTHCHECK_FAILED]
            )
            return
        else:
            print 'Initial healtcheck for deployment {0} succeeded'.format(deployment.id)

        _, inputs = tempfile.mkstemp(dir=deployment_path)
        with open(inputs, 'w') as f:
            f.write(yaml.dump(deployment['inputs']))
        print 'Creating deployment...'        
        target_runner.cfy_run('deployments create -d {0} -b {1} -i {2}'.format(
            deployment.id,
            deployment.blueprint_id,
            inputs
        ))
        phase = 'creating_deployment'
        create_dep_execution = target_runner.rest.executions.list(
            deployment_id=deployment.id
        )[0]
        print 'Waiting for create_deployment_environment workflow'
        _wait_for_execution(create_dep_execution.id, target_runner.rest)
        archname = str(uuid.uuid4())
        script_arch = target_runner.handler.container_path(_REMOTE_TMP, archname)
        print 'Sending data dump...'        
        target_runner.handler.send_file(res_path, os.path.join(_REMOTE_TMP, archname))
        recreate_result = str(uuid.uuid4())
        script_recreate_result = target_runner.handler.container_path(_REMOTE_TMP, recreate_result)
        print 'Restoring deployment runtime data...'        
        target_runner.handler.python_call(('{0} recreate_deployment --deployment {1} --input {2}'
                                           ' --version {3} --output {4}').format(
            target_runner.handler.container_path(_REMOTE_PATH, 'main.py'),
            deployment.id,
            script_arch,
            target_runner.version,
            target_output_parameter_path
        )) 
        print 'Loading result of recreate deployment...'        
        recreate_result = _json_load_remote(target_runner, target_output_load_path, deployment_path)
        if _HEALTHCHECK_FAILED in recreate_result:
            error = 'Post recreate deployment healtcheck for deployment {0} failed, reason: {1}'.format(
                deployment.id, recreate_result[_HEALTHCHECK_FAILED]
            )
            return
        else:
            print 'Post recreate deployment healtcheck for deployment {0} succeeded'.format(deployment.id)
        print 'Uninstalling old agents...'        
        phase = 'uninstalling_agents'
        source_runner.handler.python_call(('{0} uninstall_agents --deployment {1}'
                                           ' --version {2} --output {3}').format(
            source_runner.handler.container_path(_REMOTE_PATH, 'main.py'),
            deployment.id,
            source_runner.version,
            source_output_parameter_path
        ))
        uninstall_result = _json_load_remote(source_runner, source_output_load_path, deployment_path)
        if _HEALTHCHECK_FAILED in uninstall_result:
            error = 'Post agent uninstall healtcheck for deployment {0} failed, reason: {1}'.format(
                deployment.id, uninstall_result[_HEALTHCHECK_FAILED]
            )
            return
        else:
            print 'Post agent uninstall healtcheck for deployment {0} succeeded'.format(deployment.id)
        print 'Installing new agents...' 
        phase = 'installing_agents'
        target_runner.handler.python_call(('{0} install_agents --deployment {1}'
                                           ' --version {2} --output {3}').format(
            target_runner.handler.container_path(_REMOTE_PATH, 'main.py'),
            deployment.id,
            target_runner.version,
            target_output_parameter_path
        ))
        install_result = _json_load_remote(target_runner, target_output_load_path, deployment_path)
        if _HEALTHCHECK_FAILED in install_result:
            error = 'Post agent install healtcheck for deployment {0} failed, reason: {1}'.format(
                deployment.id, install_result[_HEALTHCHECK_FAILED]
            )
            return
        else:
            print 'Post agent install healtcheck for deployment {0} succeeded'.format(deployment.id)
        print 'Deployment {0} migrated.'.format(deployment.id)        
        phase = 'deployment_migrated'
    finally:
        result['phase'] = phase
        result['error'] = error
        shutil.rmtree(deployment_path)


def migrate_deployments(source_runner, target_runner, config):
    print 'Installing code on source manager'
    install_code(source_runner.handler, _REMOTE_PATH, config)
    print 'Installing code on target manager'
    install_code(target_runner.handler, _REMOTE_PATH, config)
    existing_deployments = [d.id for d in 
        target_runner.rest.deployments.list()]
    if config.deployment:
        deployments = [
            source_runner.rest.deployments.get(config.deployment)]
    else:
        deployments = source_runner.rest.deployments.list()
    for deployment in deployments:
        _perform_migration(deployment, existing_deployments,
                           source_runner, target_runner, config.logfile)
 
def migrate(config):
    source_runner = _init_runner(config.source)
    target_runner = _init_runner(config.target)
    if not config.skip_blueprints:
        migrate_blueprints(source_runner, target_runner)
    report.set_credentials(config)
    migrate_deployments(source_runner, target_runner, config)
    pass


def _modify_agents(runner, operation, deployment):
    print 'Performing agent modification {0} for deployment {1}'.format(operation, deployment)
    runner.handler.python_call('{0} modify_agents --operation {1} --deployment {2} --version {3}'.format(
        runner.handler.container_path(_REMOTE_PATH, 'main.py'),
        operation,
        deployment,
        runner.version
    ))


def modify_agents(config):
    runner = _init_runner(config.manager_ip)
    report.set_credentials(config)
    install_code(runner.handler, _REMOTE_PATH, config)
    _modify_agents(runner, config.operation, config.deployment)


def perform_cleanup(config):
    report.set_credentials(config)
    runner = _init_runner(config.manager_ip)
    runner.handler.execute('sudo rm -rf ~/{0}'.format(_REMOTE_PATH))


def perform_healthcheck(config):
    report.set_credentials(config)
    runner = _init_runner(config.manager_ip)
    print 'Installing required code'
    install_code(runner.handler, _REMOTE_PATH, config)
    filename = str(uuid.uuid4())
    print 'Running healtcheck'
    report_path = runner.handler.container_path(_REMOTE_TMP, filename)
    runner.handler.python_call('{0} healthcheck --deployment {1} --version {2} --output {3}'.format(
        runner.handler.container_path(_REMOTE_PATH, 'main.py'),
        config.deployment,
        runner.version,
        report_path
    ))
    _, res_path = tempfile.mkstemp()
    print 'Loading results'
    runner.handler.load_file('~/{0}/{1}'.format(_REMOTE_TMP, filename),
                              res_path)
    print 'Results:'
    with open(res_path) as f:
        print f.read()
    os.remove(res_path)
 

def _parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    init_p = subparsers.add_parser('init')
    init_p.set_defaults(func=init)

    migrate_p = subparsers.add_parser('migrate')
    migrate_p.add_argument('--source', required=True)
    migrate_p.add_argument('--target', required=True)
    migrate_p.add_argument('--config', required=True)
    migrate_p.add_argument('--logfile', required=True)
    migrate_p.add_argument('--deployment')
    migrate_p.add_argument('--skip-blueprints',
                            default=False, action='store_true')
 
    migrate_p.set_defaults(func=migrate)

    agent = subparsers.add_parser('agents')
    agent.add_argument('--deployment', required=True)
    agent.add_argument('--manager_ip', required=True)
    agent.add_argument('--operation', required=True)
    agent.add_argument('--config', required=True)
    agent.set_defaults(func=modify_agents)

    cleanup = subparsers.add_parser('cleanup')
    cleanup.add_argument('--manager_ip', required=True)
    cleanup.add_argument('--config', required=True)
    cleanup.set_defaults(func=perform_cleanup)

    healthcheck_p = subparsers.add_parser('healthcheck')
    healthcheck_p.add_argument('--deployment', required=True)
    healthcheck_p.add_argument('--manager_ip', required=True)
    healthcheck_p.add_argument('--config', required=True)
    healthcheck_p.set_defaults(func=perform_healthcheck) 
    return parser

def main(args):
    parser = _parser()
    config = parser.parse_args(args)
    print str(config)
    config.func(config)
    


if __name__ == '__main__':
    main(sys.argv[1:])
