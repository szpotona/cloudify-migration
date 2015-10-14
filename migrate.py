import argparse
import healthcheck.report as report
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
import json
import yaml
_DIRECTORY = os.path.dirname(os.path.realpath(__file__))
_VERBOSE = False
_ENVS = os.path.join(_DIRECTORY, 'envs')

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
        arch_path = os.path.join(path, 'arch.tar.gz')
        call('cp -rf {0}/healthcheck {0}/remote'.format(_DIRECTORY))
        call('bash -c "cd {1}/remote ; tar -cf {0} *;"'.format(arch_path, _DIRECTORY))
        call('rm -rf {0}/remote/healthcheck'.format(_DIRECTORY))
        handler.execute('mkdir -p {0}'.format(directory))
        handler.send_file(arch_path, directory)
        handler.execute('tar xf {0} -C {1} && cd {1} && mkdir -p tmp'.format(
            os.path.join(directory, 'arch.tar.gz'), directory))
    finally:
        shutil.rmtree(path)

_REMOTE_PATH = 'migration'
_REMOTE_TMP = os.path.join(_REMOTE_PATH, 'tmp')

def _migrate_deployment(deployment, existing_deployments,
                        source_runner, target_runner):
    if deployment.id in existing_deployments:
        return
    deployment_path = tempfile.mkdtemp(
        prefix='deployment_dir_{0}'.format(deployment.id))
    try:
        print 'Deployment {0}'.format(deployment.id)
        filename = str(uuid.uuid4())
        script_path = source_runner.handler.container_path(_REMOTE_TMP, filename)
        print 'Healthcheck and data dump...'        
        source_runner.handler.python_call('{0} healthcheck_and_dump --deployment {1} --output {2}'.format(
            source_runner.handler.container_path(_REMOTE_PATH, 'main.py'),
            deployment.id,
            script_path
        ))
        res_path = os.path.join(deployment_path, 'arch.tar.gz')
        print 'Downloading data dump...'        
        source_runner.handler.load_file('~/{0}/{1}'.format(_REMOTE_TMP, filename),
                                        res_path)
        _, inputs = tempfile.mkstemp(dir=deployment_path)
        with open(inputs, 'w') as f:
            f.write(yaml.dump(deployment['inputs']))
        print 'Creating deployment...'        
        target_runner.cfy_run('deployments create -d {0} -b {1} -i {2}'.format(
            deployment.id,
            deployment.blueprint_id,
            inputs
        ))
        archname = str(uuid.uuid4())
        script_arch = target_runner.handler.container_path(_REMOTE_TMP, archname)
        print 'Sending data dump...'        
        target_runner.handler.send_file(res_path, os.path.join(_REMOTE_TMP, archname))
        print 'Recreating deployment...'        
        target_runner.handler.python_call('{0} recreate_deployment --deployment {1} --input {2}'.format(
            target_runner.handler.container_path(_REMOTE_PATH, 'main.py'),
            deployment.id,
            script_arch
        )) 
        print 'Uninstalling old agents...'        
        _modify_agents(source_runner, 'uninstall', deployment.id)
        print 'Installing new agents...'        
        _modify_agents(target_runner, 'install', deployment.id)
        print 'Deployment {0} migrated.'.format(deployment.id)        
    finally:
        print deployment_path

def migrate_deployments(source_runner, target_runner, config):
    print 'Installing code on source manager'
    install_code(source_runner.handler, _REMOTE_PATH, config)
    print 'Installing code on target manager'
    install_code(target_runner.handler, _REMOTE_PATH, config)
    deployments = source_runner.rest.deployments.list()
    existing_deployments = [d.id for d in 
        target_runner.rest.deployments.list()]
    for deployment in deployments:
        _migrate_deployment(deployment, existing_deployments,
                            source_runner, target_runner)
 
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

def _parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    init_p = subparsers.add_parser('init')
    init_p.set_defaults(func=init)

    migrate_p = subparsers.add_parser('migrate')
    migrate_p.add_argument('--source', required=True)
    migrate_p.add_argument('--target', required=True)
    migrate_p.add_argument('--config', required=True)
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
    return parser

def main(args):
    parser = _parser()
    config = parser.parse_args(args)
    print str(config)
    config.func(config)
    


if __name__ == '__main__':
    main(sys.argv[1:])
