import sys
from cloudify_cli import utils
from os import path


management_ip = utils.get_management_server_ip()
client = utils.get_rest_client(management_ip)

blueprints_dir = sys.argv[1]

blueprints = client.blueprints.list()
if blueprints:
    for blueprint in blueprints:
        b_id = blueprint.id
        client.blueprints.download(
            b_id,
            path.join(blueprints_dir, b_id + ".tar.gz")
        )
else:
    sys.stderr.write('No blueprints found on the Cloudify Manager.\n')
    sys.exit(1)

