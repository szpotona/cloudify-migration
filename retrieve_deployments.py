from cloudify_cli import utils
import json
import os


management_ip = utils.get_management_server_ip()
client = utils.get_rest_client(management_ip)
deployments = client.deployments.list()

# Send the data to another script, running in a different virtenv
result_f = os.fdopen(3, 'w')
result_f.write(json.dumps(deployments))
result_f.close()
