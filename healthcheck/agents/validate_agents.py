import json
import os
import sys
import tempfile
import threading

from subprocess import call
from cloudify.celery import celery


_DIRECTORY = os.path.dirname(os.path.realpath(__file__))
_THREAD_COUNT = 10


def _check_alive(name, version):
    if version.startswith('3.1'):
        sep = '.'
    else:
        sep = '@'
    try:
        worker_name = 'celery{0}{1}'.format(sep, name)
        tasks = celery.control.inspect([worker_name]).registered() or {}
        worker_tasks = set(tasks.get(worker_name, {}))
        return 'script_runner.tasks.run' in worker_tasks
    except:
        return False


def check_agents_alive(deployment_id, deployment, version):
    dep_res= {}
    dep_res['workflows_worker_alive'] = _check_alive(
        '{0}_workflows'.format(deployment_id), version)
    dep_res['operations_worker_alive'] = _check_alive(deployment_id, version)
    dep_res['agents_alive'] = {}
    dep_alive = dep_res['workflows_worker_alive'] and dep_res[
        'operations_worker_alive']
    agents = deployment['agents'].keys()
    for agent in agents:
        agent_alive = _check_alive(agent, version)
        dep_res['agents_alive'][agent] = agent_alive
        dep_alive = dep_alive and agent_alive
    return dep_res, dep_alive 


def check_vm_access(deployment_id, deployment, test_vm_script):
    dep_res = {}
    dep_python = '~/cloudify.{0}/env/bin/python'.format(deployment_id)
    _, input_path = tempfile.mkstemp()
    _, output_path = tempfile.mkstemp()
    try:
        with open(input_path, 'w') as f:
            f.write(json.dumps(deployment['agents']))
        status = call(['timeout', '20', os.path.expanduser(dep_python),
                      test_vm_script, input_path, output_path])
        if status:
            dep_res['agents_remote_access_error'] = True
        else:
            with open(output_path) as f:
                dep_res['agents_remote_access'] = json.loads(f.read())
        return dep_res 
    finally:
        os.remove(input_path)
        os.remove(output_path)
 

def _insert_deployment_result(dep_res, deployment_id, deployment, version, test_vm_access, test_vm_script):
    result, dep_alive = check_agents_alive(deployment_id, deployment, version)
    dep_res.update(result)
    if not dep_alive or not test_vm_access:
        return
    vm_access = check_vm_access(deployment_id, deployment, test_vm_script)
    dep_res.update(vm_access)


def _prepare_deployment_results(queue):
    for res, dep_id, agents, version, test_vm_access, test_vm_script in  queue:
        _insert_deployment_result(res, dep_id, agents, version, test_vm_access, test_vm_script)


def main(args):
    path = sys.argv[1]
    output = sys.argv[2]
    version = sys.argv[3]
    test_vm_access = len(sys.argv) > 4
    if test_vm_access:
        test_vm_script = sys.argv[4]
    else:
        test_vm_script = None
   
    with open(path) as f:
        deployments = json.loads(f.read())
    
    
    res = {}
    threads = []
    queues = [[] for _ in range(_THREAD_COUNT)]
    i = 0
    for deployment_id, agents in deployments.iteritems():
        dep_res = {}
        res[deployment_id] = dep_res
        thread_id = i % _THREAD_COUNT
        queues[thread_id].append((dep_res, deployment_id, agents, version, test_vm_access, test_vm_script))
        i = i + 1
    
    for queue in queues:
        thread = threading.Thread(target=_prepare_deployment_results,
                                  kwargs={'queue': queue})
        thread.start()
        threads.append(thread)
    
    for thread in threads:
        thread.join()

    with open(output, 'w') as f:
        f.write(json.dumps(res))


if __name__ == '__main__':
    main(sys.argv)
