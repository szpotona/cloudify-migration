import json
import os
import sys
import tempfile
import threading

from subprocess import call
from cloudify.celery import celery


_DIRECTORY = os.path.dirname(os.path.realpath(__file__))


_THREAD_COUNT = 10

path = sys.argv[1]
output = sys.argv[2]
version = sys.argv[3]
test_vm_access = len(sys.argv) > 4
if test_vm_access:
    test_vm_script = sys.argv[4]

if version.startswith('3.1'):
    sep = '.'
else:
    sep = '@'

with open(path) as f:
    deployments = json.loads(f.read())


def _check_alive(name):
    try:
        worker_name = 'celery{0}{1}'.format(sep, name)
        tasks = celery.control.inspect([worker_name]).registered() or {}
        worker_tasks = set(tasks.get(worker_name, {}))
        return 'script_runner.tasks.run' in worker_tasks
    except:
        return False


def _insert_deployment_result(dep_res, deployment_id, deployment):
    dep_res['workflows_worker_alive'] = _check_alive(
        '{0}_workflows'.format(deployment_id))
    dep_res['operations_worker_alive'] = _check_alive(deployment_id)
    dep_res['agents_alive'] = {}
    dep_alive = dep_res['workflows_worker_alive'] and dep_res[
        'operations_worker_alive']
    agents = deployment['agents'].keys()
    for agent in agents:
        agent_alive = _check_alive(agent)
        dep_res['agents_alive'][agent] = agent_alive
        dep_alive = dep_alive and agent_alive
    if not dep_alive or not test_vm_access:
        return
    dep_python = '~/cloudify.{0}/env/bin/python'.format(deployment_id)
    _, input_path = tempfile.mkstemp(dir=_DIRECTORY)
    _, output_path = tempfile.mkstemp(dir=_DIRECTORY)
    with open(input_path, 'w') as f:
        f.write(json.dumps(deployment['agents']))
    status = call(['timeout', '10', os.path.expanduser(dep_python),
                   test_vm_script, input_path, output_path])
    if status:
        dep_res['agents_remote_access_error'] = True
        return
    with open(output_path) as f:
        dep_res['agents_remote_access'] = json.loads(f.read())


def _prepare_deployment_results(queue):
    for res, dep_id, agents in queue:
        _insert_deployment_result(res, dep_id, agents)


res = {}
threads = []
queues = [[] for _ in range(_THREAD_COUNT)]
i = 0
for deployment_id, agents in deployments.iteritems():
    dep_res = {}
    res[deployment_id] = dep_res
    thread_id = i % _THREAD_COUNT
    queues[thread_id].append((dep_res, deployment_id, agents))
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
