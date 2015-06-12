import sys
import json
import os
from cloudify_cli import utils
from subprocess import call


management_ip = utils.get_management_server_ip()
client = utils.get_rest_client(management_ip)

deployments_json = sys.stdin.read()
deployments = json.loads(deployments_json)

host_magic_dir = "/tmp/cloudify_migration_data_2g25qt4/"

del_template =  "curl -s -XDELETE 'http://localhost:9200/cloudify_storage/node_instance/_query?q=deployment_id:{} '"
add_template = "curl -s -XPUT 'http://localhost:9200/cloudify_storage/node_instance/{id}/_create' -d \'{source}\'"

if deployments:
    for dep in deployments:
        #new_dep = client.deployments.create(
        #    dep['blueprint_id'],
        #    dep['id'],
        #    dep['inputs']
        #)

        nodes = json.loads(open(host_magic_dir + dep['id'], 'r').read())
        
        with open(os.devnull, "w") as fnull:
            del_command = del_template.format(dep['id'])
            call(["cfy", "ssh", "-c", del_command ], stdout=fnull, stderr=fnull)
            for node in nodes["hits"]["hits"]:
                add_command = add_template.format(id = str(node["_id"]), source=json.dumps(node["_source"]) )
                call(["cfy", "ssh", "-c", add_command ], stdout=fnull, stderr=fnull)
 
        print 'Recreated deployment %s' % (new_dep['id'],)

