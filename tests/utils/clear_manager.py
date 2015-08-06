import time
from cloudify_cli import utils
from cloudify_rest_client.executions import Execution


management_ip = utils.get_management_server_ip()
client = utils.get_rest_client(management_ip)
deployments = client.deployments.list()


uninstall_executions = []
for deployment in deployments:
    ex = client.executions.start(deployment.id, 'uninstall')
    uninstall_executions.append(ex)

for uninstall_ex in uninstall_executions:
    execution = client.executions.get(uninstall_ex.id)
    while execution.status not in Execution.END_STATES:
        time.sleep(5)
        execution = client.executions.get(execution.id)


for deployment in deployments:
    client.deployments.delete(deployment.id)


# There is some kind of problem to investigate,
# sometimes rest still sees deployments ..
time.sleep(1)
for blueprint in client.blueprints.list():
    client.blueprints.delete(blueprint.id)

