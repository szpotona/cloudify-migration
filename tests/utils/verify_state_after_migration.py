import sys, os
from cloudify_cli import utils


def execution_by_wf_id(executions, wf_id):
    return next((e for e in executions if e.workflow_id == wf_id), None)


def main(blueprint_id, deployment_id):
    management_ip = utils.get_management_server_ip()
    client = utils.get_rest_client(management_ip)

    print 'Verifying that blueprint and deployment got migrated'
    client.blueprints.get(blueprint_id=blueprint_id)    # exceptions are raised
    client.deployments.get(deployment_id=deployment_id) # if no objects found

    print 'Verifying that "old" and "new" '\
          'create_deployment_environment executions exist'
    executions = client.executions.list(deployment_id=deployment_id)
    assert execution_by_wf_id(executions, 'create_deployment_environment'), \
           "create_deployment_environment has not been migrated"
    new_create_env_name = \
        'create_deployment_environment_' + os.environ['NEW_MANAGER_VER']
    assert execution_by_wf_id(executions, new_create_env_name), \
        "create_deployment_environment has not been launched on the new manager"


if __name__ == '__main__':
    main(*sys.argv[1:])

