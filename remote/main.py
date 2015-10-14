import argparse
import os
import sys
import json
from subprocess import check_output
import subprocess
import tarfile
import tempfile
import time
import shutil
import shlex
from cloudify_rest_client.client import CloudifyClient
from cloudify_rest_client.executions import Execution


_DIRECTORY = os.path.dirname(os.path.realpath(__file__))
_VERBOSE = True


def _tempfile():
    _, res = tempfile.mkstemp(dir=os.path.join(_DIRECTORY, 'tmp'))
    return res

def _tempdir():
    return tempfile.mkdtemp(dir=os.path.join(_DIRECTORY, 'tmp'))

def health_check_and_dump(config):
    CHUNK_SIZE = 100
    dep_id = config.deployment
    data_path = _tempfile()
    events_path = _tempfile()
    
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
    with open(data_path, 'a') as f:
        # Storage dumping
        dump_chunks(f, dump_storage_template)
    res.add(data_path, arcname='data.json') 
    with open(events_path, 'a') as f:
        # Events dumping
        dump_chunks(f, dump_events_template)
    res.add(events_path, arcname='events.json')

def call(command):
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



DEL_TEMPLATE = ("curl -s -XDELETE 'http://localhost:9200/"
                "cloudify_storage/node_instance/_query?q=deployment_id:{} '")
BULK_TEMPLATE = ("curl -s XPOST 'http://localhost:9200/"
                 "{index}/_bulk' --data-binary @{file}")
UPDATE_EXEC_WORKFLOW_ID_TEMPLATE = (
    "curl -s XPOST 'http://localhost:9200/cloudify_storage/execution/"
    "{execution_id}/_update' -d '{{\"doc\":{{\"workflow_id\":\"{w_id}\"}}}}'"
)


def recreate_deployment(config):
    archive = tarfile.TarFile(config.input)
    dep_dir = _tempdir()
    archive.extractall(dep_dir)
    call(DEL_TEMPLATE.format(config.deployment))
    client = CloudifyClient()
    create_dep_execution = client.executions.list(
        deployment_id=config.deployment
    )[0]
    call(UPDATE_EXEC_WORKFLOW_ID_TEMPLATE.format(
        execution_id=create_dep_execution.id,
        w_id='create_deployment_environment_3_2_1'
    ))
    call(BULK_TEMPLATE.format(
        file=os.path.join(dep_dir, 'data.json'),
        index='cloudify_storage'
    ))
    call(BULK_TEMPLATE.format(
        file=os.path.join(dep_dir, 'events.json'),
        index='cloudify_events'
    ))
    execution = client.executions.get(create_dep_execution.id)
    while execution.status not in Execution.END_STATES:
        time.sleep(2)
        print 'Waiting for execution {0}'.format(create_dep_execution.id)
        execution = client.executions.get(create_dep_execution.id)

_ENVS = {
  '3.1.0': '/opt/manager',
  '3.2.0': '/opt/manager/env',
  '3.2.1': '/opt/manager/env'
}


def _perform_agent_operation(config):
    env = _ENVS[config.version]
    auth_path = _tempfile()
    call('{0}/bin/python {1}/modify_agents.py {0} {4} 5 {2} {3}'.format(
        env, _DIRECTORY, config.deployment, auth_path, config.operation
    )) 


def modify_agents(config):
    _perform_agent_operation(config)


def _parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    health = subparsers.add_parser('healthcheck_and_dump')
    health.add_argument('--deployment', required=True)
    health.add_argument('--output', required=True)
    health.set_defaults(func=health_check_and_dump)

    create = subparsers.add_parser('recreate_deployment')
    create.add_argument('--deployment', required=True)
    create.add_argument('--input', required=True)
    create.set_defaults(func=recreate_deployment)

    modify = subparsers.add_parser('modify_agents')
    modify.add_argument('--deployment', required=True)
    modify.add_argument('--version', required=True)
    modify.add_argument('--operation', required=True)
    modify.set_defaults(func=modify_agents)

    return parser


def main(args):
    parser = _parser()
    config = parser.parse_args(args)
    config.func(config)

if __name__ == '__main__':
    main(sys.argv[1:])
