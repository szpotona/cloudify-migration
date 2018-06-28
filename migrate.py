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

from setuptools import archive_util

from cloudify_rest_client.executions import Execution
from cloudify_rest_client import CloudifyClient

_DIRECTORY = os.path.dirname(os.path.realpath(__file__))

_VERBOSE = False
_ENVS = os.path.join(_DIRECTORY, 'envs')
_HEALTHCHECK_FAILED = 'healtcheck_failed'


def _json_load(path):
    with open(path) as f:
        return json.loads(f.read())


def _json_dump(path, content):
    with open(path, 'w') as f:
        f.write(json.dumps(content, indent=2))


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
        if _VERBOSE:
            print 'Changing workdir to {0}'.format(self.directory)
        try:
            cfy_path = os.path.join(self.env, 'bin/cfy')
            command = [cfy_path]
            command.extend(cmd)
            call_arr(command)
        finally:
            os.chdir(cwd)

    # Deprecated, try to use python_run_arr instead
    # It handles whitespaces in more reasonable way.
    def python_run(self, cmd):
        cwd = os.getcwd()
        os.chdir(self.directory)
        try:
            python_path = os.path.join(self.env, 'bin/python')
            call('{0} {1}'.format(python_path, cmd))
        finally:
            os.chdir(cwd)

    def python_run_arr(self, cmd):
        cwd = os.getcwd()
        os.chdir(self.directory)
        try:
            python_path = os.path.join(self.env, 'bin/python')
            command = [python_path]
            command.extend(cmd)
            call_arr(command)
        finally:
            os.chdir(cwd)


def _cfy_runner(ip):
    rest_client = report.get_rest_client(ip)
    version = rest_client.manager.get_version()['version']
    return CfyRunner(version, ip, rest_client)


def _init_runner(ip):
    runner = _cfy_runner(ip)
    # runner.mkdir()
    # runner.cfy_run(['init', '-r'])
    # runner.cfy_run(['use', '-t', ip])
    # runner.cfy_run(['status'])
    return runner


def _upload_blueprint(blueprints_path, blueprint_arch, runner,
                      old_blueprints, config, source_runner):
    blueprint = _get_blueprint_name_from_file(blueprint_arch)
    if blueprint in old_blueprints:
        return
    blueprint_path = os.path.join(blueprints_path, blueprint)

    tf = tempfile.mkdtemp()
    try:
        archive_util.unpack_archive(
            os.path.join(blueprints_path, blueprint_arch),
            tf
        )
        # blueprint archive has exactly one directory inside
        shutil.move(os.path.join(tf, os.listdir(tf)[0]), blueprint_path)

        possible_blueprints = []
        for blueprint_file in os.listdir(blueprint_path):
            if blueprint_file.endswith('.yaml'):
                possible_blueprints.append(blueprint_file)
        if config.autofilter_blueprints:
            possible_blueprints = _filter_possible_blueprint_files(
                blueprint,
                possible_blueprints,
                blueprint_path,
                source_runner
            )
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
        runner.cfy_run(['blueprints', 'publish-archive',
                        '-l', os.path.join(blueprints_path, blueprint_arch),
                        '-b', blueprint,
                        '-n', to_upload])
    finally:
        shutil.rmtree(blueprint_path)
        shutil.rmtree(tf)


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
        call('bash -c "chmod +x {0}/remote/*.sh"'.format(_DIRECTORY))
        call(
            'bash -c "cd {1}/remote ; tar -cf {0} *;"'.format(arch_path, _DIRECTORY))
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
                       source_runner, target_runner, logpath, config):
    done = False
    retry = False
    result = {}
    _log_msg(deployment.id, 'starting migration', logpath)
    while not done:
        internal_error = False
        try:
            _migrate_deployment(deployment, existing_deployments,
                                source_runner, target_runner, result, config)
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
                        source_runner, target_runner, result, config):
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
        source_output_parameter_path = source_runner.handler.container_path(
            _REMOTE_TMP, filename)
        source_output_load_path = '~/{0}/{1}'.format(_REMOTE_TMP, filename)
        filename = str(uuid.uuid4())
        target_output_parameter_path = target_runner.handler.container_path(
            _REMOTE_TMP, filename)
        target_output_load_path = '~/{0}/{1}'.format(_REMOTE_TMP, filename)

        print 'Healthcheck and data dump...'
        source_runner.handler.python_call(
            ('{0} healthcheck_and_dump --deployment {1} --output {2} '
             '--version {3} {4}').format(
                source_runner.handler.container_path(_REMOTE_PATH, 'main.py'),
                deployment.id,
                source_output_parameter_path,
                source_runner.version,
                '--skip-env-healthchecks' if config.skip_agents else ''
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
        target_runner.cfy_run(['deployments', 'create', '-d', deployment.id, '-b', deployment.blueprint_id, '-i', inputs])
        phase = 'creating_deployment'
        create_dep_execution = target_runner.rest.executions.list(
            deployment_id=deployment.id
        )[0]
        print 'Waiting for create_deployment_environment workflow'
        _wait_for_execution(create_dep_execution.id, target_runner.rest)
        archname = str(uuid.uuid4())
        script_arch = target_runner.handler.container_path(
            _REMOTE_TMP, archname)
        print 'Sending data dump...'
        target_runner.handler.send_file(
            res_path, os.path.join(_REMOTE_TMP, archname))
        recreate_result = str(uuid.uuid4())
        script_recreate_result = target_runner.handler.container_path(
            _REMOTE_TMP, recreate_result)
        print 'Restoring deployment runtime data...'
        target_runner.handler.python_call(('{0} recreate_deployment --deployment {1} --input {2}'
                                           ' --version {3} --output {4} {5}').format(
            target_runner.handler.container_path(_REMOTE_PATH, 'main.py'),
            deployment.id,
            script_arch,
            target_runner.version,
            target_output_parameter_path,
            '--skip-healthchecks' if config.skip_agents else ''
        ))
        # No need to perform healthchecks on restored deployment
        if config.skip_agents:
            phase = 'deployment_migrated'
            return
        print 'Loading result of recreate deployment...'
        recreate_result = _json_load_remote(
            target_runner, target_output_load_path, deployment_path)
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
        uninstall_result = _json_load_remote(
            source_runner, source_output_load_path, deployment_path)
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
        install_result = _json_load_remote(
            target_runner, target_output_load_path, deployment_path)
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


def migrate_deployments(source_runner, target_runner, blueprints_to_skip,
                        config):
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
        if deployment.blueprint_id in blueprints_to_skip:
            _log_msg(
                deployment.id,
                "Skipping deployment because of skipped blueprint '{0}'"
                .format(deployment.blueprint_id),
                config.logfile)
            continue
        _perform_migration(deployment, existing_deployments,
                           source_runner, target_runner, config.logfile,
                           config)


def migrate(config):
    source_runner = _init_runner(config.source)
    target_runner = _init_runner(config.target)
    blueprints_to_skip = _get_blueprints_to_skip(config.blueprints_to_skip)
    if not config.skip_blueprints:
        migrate_blueprints(source_runner, target_runner,
                           blueprints_to_skip, config)
    report.set_credentials(config)
    if not config.skip_deployments:
        migrate_deployments(source_runner, target_runner,
                            blueprints_to_skip, config)
    else:
        print 'Skipping deployment migration'


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
    conf = _json_load(config.config)
    manager_ip = config.manager_ip
    runner = _init_runner(manager_ip)
    print 'Installing required code'
    remote_path = os.path.join(conf['manager_home'], _REMOTE_PATH)
    remote_tmp = os.path.join(remote_path, 'tmp')
    install_code(runner.handler, remote_path, config)
    filename = str(uuid.uuid4())
    print 'Running healtcheck'
    report_path = runner.handler.container_path(os.path.join(_REMOTE_PATH, 'tmp'),
                                                filename)

    deployments = [config.deployment]
    if config.all:
        mgr = CloudifyClient(manager_ip)
        ds = mgr.deployments.list()
        deployments = [d['id'] for d in ds]

    results = {}
    try:
        for deployment in deployments:
            try:
                runner.handler.python_call('{0} healthcheck --deployment {1} --version {2} --output {3}'.format(
                    runner.handler.container_path(_REMOTE_PATH, 'main.py'),
                    deployment,
                    runner.version,
                    report_path
                ))
                _, res_path = tempfile.mkstemp()
                print 'Loading results'
                runner.handler.load_file('{0}/{1}'.format(remote_tmp, filename),
                                         res_path)
                with open(res_path) as f:
                    rep = json.loads(f.read())
                    results[rep['id']] = rep
                os.remove(res_path)
            except RuntimeError:
                print "Error happened on deployment: %s" % deployment
                results[deployment] = {"status": "failure"}
    finally:
        print "Done %d out of %d" % (len(results.keys()), len(deployments))
        report_path = 'manager_{}.json'.format(manager_ip)
        print 'Results: {}'.format(report_path)
        with open(report_path, 'w') as f:
            f.write(json.dumps(results))


def start_agents(config):
    runner = _init_runner(config.manager_ip)
    report.set_credentials(config)
    install_code(runner.handler, _REMOTE_PATH, config)
    runner.handler.python_call('{0} start_agents --version {1}'.format(
        runner.handler.container_path(_REMOTE_PATH, 'main.py'),
        runner.version
    ))


def _get_blueprints_to_skip(bts_path):
    if not bts_path:
        return []

    if not os.path.exists(bts_path):
        raise RuntimeError("--blueprints-to-skip path '{0}' doesn't exist"
                           .format(bts_path))

    with open(bts_path, 'r') as f:
        lines = f.readlines()
        return map(str.strip, lines)


def _get_blueprint_name_from_file(filename):
    """
    We support blueprints archive types: .tar, .tar.gz, .tar.bz2, .zip.

    :param filename: blueprint archive file name
    :return: blueprint name
    """
    name, _ = os.path.splitext(filename)
    if name.endswith('.tar'):
        name, _ = os.path.splitext(name)
    return name


def migrate_blueprints(source_runner, target_runner, blueprints_to_skip,
                       config):
    blueprints_path = tempfile.mkdtemp(prefix='blueprints_dir')
    try:
        source_runner.python_run('{0} {1}'.format(
            os.path.join(_DIRECTORY, 'utils', 'download_blueprints.py'),
            blueprints_path))
        blueprints = [b.id for b in target_runner.rest.blueprints.list()]
        for blueprint in os.listdir(blueprints_path):
            blueprint_name = _get_blueprint_name_from_file(blueprint)
            if blueprint_name in blueprints_to_skip:
                print "Skipping blueprint '{0}' (on list to skip)"\
                    .format(blueprint_name)
                continue
            _upload_blueprint(blueprints_path, blueprint, target_runner,
                              blueprints, config, source_runner)
    finally:
        shutil.rmtree(blueprints_path)


def _filter_possible_blueprint_files(blueprint_name, possible_blueprints,
                                     blueprint_path, runner):
    print 'Filtering blueprint files for blueprint {0}'.format(blueprint_name)
    original_blueprint = runner.rest.blueprints.get(blueprint_name)
    expected_nodes = {n['name'] for n in original_blueprint['plan']['nodes']}
    result = []
    for blueprint in possible_blueprints:
        print 'Checking candidate {0}'.format(blueprint)
        _, path = tempfile.mkstemp()
        try:
            runner.python_run_arr([
                os.path.join(_DIRECTORY, 'utils', 'list_node_names.py'),
                os.path.join(blueprint_path, blueprint),
                path
            ])
            nodes = _json_load(path)
            if nodes['ok'] and set(nodes['nodes']) == expected_nodes:
                result.append(blueprint)
        finally:
            os.remove(path)
    return result


def _insert_blueprint_result(blueprint_arch, blueprints_path, results,
                             runner, config):
    blueprint = _get_blueprint_name_from_file(blueprint_arch)
    blueprint_path = os.path.join(blueprints_path, blueprint)

    tf = tempfile.mkdtemp()
    try:
        archive_util.unpack_archive(
            os.path.join(blueprints_path, blueprint_arch),
            tf
        )
        # blueprint archive has exactly one directory inside
        shutil.move(os.path.join(tf, os.listdir(tf)[0]), blueprint_path)

        possible_blueprints = []
        for blueprint_file in os.listdir(blueprint_path):
            if blueprint_file.endswith('.yaml'):
                possible_blueprints.append(blueprint_file)
        if config.autofilter_blueprints:
            possible_blueprints = _filter_possible_blueprint_files(
                blueprint,
                possible_blueprints,
                blueprint_path,
                runner
            )
        results[blueprint] = {
            'possible_files': possible_blueprints
        }
    finally:
        shutil.rmtree(blueprint_path)
        shutil.rmtree(tf)


def analyze_blueprints(config):
    runner = _init_runner(config.manager_ip)
    report.set_credentials(config)
    blueprints_path = tempfile.mkdtemp(prefix='blueprints_dir')
    try:
        runner.python_run('{0} {1}'.format(
            os.path.join(_DIRECTORY, 'utils', 'download_blueprints.py'),
            blueprints_path))
        blueprints_results = {}
        for blueprint in os.listdir(blueprints_path):
            _insert_blueprint_result(blueprint, blueprints_path,
                                     blueprints_results, runner, config)
        multi_yaml = 0
        single_yaml = 0
        for k, vals in blueprints_results.iteritems():
            if len(vals['possible_files']) > 1:
                multi_yaml += 1
            elif len(vals['possible_files']) == 1:
                single_yaml += 1
            else:
                raise RuntimeError(
                    'Blueprint {0} does not contain yaml file'.format(k))
        res = {
            'single_yaml': single_yaml,
            'multi_yaml': multi_yaml,
            'blueprints': blueprints_results
        }
        _json_dump(config.output, res)
        with open(config.csv_output, 'w') as f:
            f.write('blueprint,files\n')
            for k, vals in blueprints_results.iteritems():
                if len(vals['possible_files']) > 1:
                    files = [k] + vals['possible_files']
                    f.write('{0}\n'.format(','.join(files)))
        print 'Summary:'
        print 'Blueprints with multiple yaml files: {0}'.format(multi_yaml)
        print 'Blueprints with single yaml file: {0}'.format(single_yaml)
    finally:
        shutil.rmtree(blueprints_path)


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
                           default=False, action='store_true',
                           help='Skip migration of blueprints')
    migrate_p.add_argument('--skip-deployments',
                           default=False, action='store_true',
                           help='Skip migration of deployments')
    migrate_p.add_argument('--skip-agents',
                           default=False, action='store_true',
                           help='Skip migration of agents')
    migrate_p.add_argument('--autofilter-blueprints',
                           default=False, action='store_true')
    migrate_p.add_argument('--blueprints-to-skip', metavar='FILE_PATH',
                           help='Path to file providing in each line name of '
                                'the blueprint to skip. Flag also skips '
                                'deployments that are based on skipped '
                                'blueprints')
    migrate_p.set_defaults(func=migrate)

    cleanup = subparsers.add_parser('cleanup')
    cleanup.add_argument('--manager_ip', required=True)
    cleanup.add_argument('--config', required=True)
    cleanup.set_defaults(func=perform_cleanup)

    healthcheck_p = subparsers.add_parser('healthcheck')
    healthcheck_p.add_argument('--deployment')
    healthcheck_p.add_argument('--all', action='store_true')
    healthcheck_p.add_argument('--manager_ip')
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
