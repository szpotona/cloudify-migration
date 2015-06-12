from cloudify_cli import utils
import json
import os
from subprocess import call


management_ip = utils.get_management_server_ip()
client = utils.get_rest_client(management_ip)
deployments = client.deployments.list()

# Send the data to another script, running in a different virtenv
result_f = os.fdopen(3, 'w')
result_f.write(json.dumps(deployments))
result_f.close()

magic_file = "cloudify_migration_data_file_3f53t9"
magic_path = "/tmp/" + magic_file
host_magic_dir = "/tmp/cloudify_migration_data_2g25qt4/"

dump_template = "curl -s -XGET 'http://localhost:9200/cloudify_storage/node_instance/_search?size=10000&q=deployment_id:{id}' > {tempfile}"

if not os.path.exists(host_magic_dir):
    os.makedir(host_magic_dir)

with open(os.devnull, "w") as FNULL:
    for dep in deployments:
        dep_id = dep["id"]
        call(["cfy", "ssh", "-c", dump_template.format(id=dep_id, tempfile=magic_path)], stdout=FNULL, stderr=FNULL)
        scp(magic_path, host_magic_dir + dep_id)


