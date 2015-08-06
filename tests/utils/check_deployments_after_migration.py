import sys, os
from cloudify_cli import utils


def find_execution(executions, wf_id):
    return next((e for e in executions if e.workflow_id == wf_id), None)


def main(blueprint_id, deployment_id):
    management_ip = utils.get_management_server_ip()
    client = utils.get_rest_client(management_ip)

    blueprints = client.blueprints.list()
    blueprint = next(b for b in blueprints if b.id == blueprint_id)
    assert blueprint, "Blueprint %s hasn't been migrated" % (blueprint_id,)

    deployments = client.deployments.list()
    deployment = next(d for d in deployments if d.id == deployment_id)
    assert blueprint, "Deployment %s hasn't been migrated" % (deployment_id,)

    executions = client.executions.list(deployment_id=deployment_id)
    assert find_execution(executions, 'create_deployment_environment'), \
           "create_deployment_environment has not been migrated"
    new_create_env_name = \
        'create_deployment_environment_' + os.environ['NEW_MANAGER_VER']
    assert find_execution(executions, new_create_env_name), \
        "create_deployment_environment has not been launched on the new manager"


if __name__ == '__main__':
    main(*sys.argv[1:])

