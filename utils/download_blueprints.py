import os
import sys
from cloudify_cli import utils


management_ip = utils.get_management_server_ip()
client = utils.get_rest_client(management_ip)

blueprints_dir = sys.argv[1]

blueprints = client.blueprints.list()
if blueprints:
    os.chdir(blueprints_dir)
    for blueprint in blueprints:
        client.blueprints.download(blueprint.id)
else:
    sys.stderr.write('No blueprints found on the Cloudify Manager.\n')
    sys.exit(1)

