import sys
import json

from cloudify.celery import celery


path = sys.argv[1]
output = sys.argv[2]

with open(path) as f:
    deployments = json.loads(f.read())


def _check_alive(name):
    try:
        worker_name = 'celery.{0}'.format(name)
        tasks = celery.control.inspect([worker_name]).registered() or {}
        worker_tasks = set(tasks.get(worker_name, {}))
        return 'script_runner.tasks.run' in worker_tasks
    except:
        return False


for deployment_id, agents in deployments.iteritems():
    agents['workflows_worker_alive'] = _check_alive(
        '{0}_workflows'.format(deployment_id))
    agents['operations_worker_alive'] = _check_alive(deployment_id)
    for name, agent in agents.get('agents', {}).iteritems():
       agent['alive'] = _check_alive(name)


with open(output, 'w') as f:
    f.write(json.dumps(deployments))    
