import sys
import threading
import json

from cloudify.celery import celery

_THREAD_COUNT = 10

path = sys.argv[1]
output = sys.argv[2]
version = sys.argv[3]

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
    if not dep_alive:
        return



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
