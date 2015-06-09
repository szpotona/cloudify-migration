import sys
import json
from cloudify_cli import utils


management_ip = utils.get_management_server_ip()
client = utils.get_rest_client(management_ip)

deployments_json = sys.stdin.read()
deployments = json.loads(deployments_json)

if deployments:
    for dep in deployments:
        new_dep = client.deployments.create(
            dep['blueprint_id'],
            dep['id'],
            dep['inputs']
        )
        print 'Recreated deployment %s' % (new_dep['id'],)

