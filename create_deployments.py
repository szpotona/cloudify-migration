import json
import os
import sys
from subprocess import call

from cloudify_cli import utils
from scp import scp


management_ip = utils.get_management_server_ip()
client = utils.get_rest_client(management_ip)

deployments_json = sys.stdin.read()
deployments = json.loads(deployments_json)

host_magic_dir = '/tmp/cloudify_migration_data_2g25qt4/'
magic_file = '/tmp/cloudify_migration_data_5ovg6bht'

del_template = ("curl -s -XDELETE 'http://localhost:9200/"
                "cloudify_storage/node_instance/_query?q=deployment_id:{} '")
bulk_template = ("curl -s XPOST 'http://localhost:9200/"
                 "{index}/_bulk' --data-binary @{file}")
update_exec_workflow_id_template = (
    "curl -s XPOST 'http://localhost:9200/cloudify_storage/execution/"
    "{execution_id}/_update' -d '{{\"doc\":{{\"workflow_id\":\"{w_id}\"}}}}'"
)


with open(os.devnull, 'w') as FNULL:
    if deployments:
        for dep in deployments:
            new_dep = client.deployments.create(
                dep['blueprint_id'],
                dep['id'],
                dep['inputs']
            )

            del_command = del_template.format(dep['id'])
            call(['cfy', 'ssh', '-c', del_command],
                 stdout=FNULL, stderr=FNULL)

            create_dep_execution = client.executions.list(
                deployment_id=new_dep.id
            )[0]
            call(['cfy', 'ssh', '-c', update_exec_workflow_id_template.format(
                execution_id=create_dep_execution.id,
                w_id='create_deployment_environment_' + os.environ['NEW_MANAGER_VER']
            )], stdout=FNULL, stderr=FNULL)

            print 'Recreated deployment %s' % (new_dep['id'],)

    scp(host_magic_dir + 'migration_deps_storage', magic_file, True)
    call(['cfy', 'ssh', '-c',  bulk_template.format(
        file=magic_file,
        index='cloudify_storage'
        )], stdout=FNULL, stderr=FNULL)

    scp(host_magic_dir + 'migration_deps_events', magic_file, True)
    call(['cfy', 'ssh', '-c',  bulk_template.format(
        file=magic_file,
        index='cloudify_events'
        )], stdout=FNULL, stderr=FNULL)

print 'Deployments migrated.'
