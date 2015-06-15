import sys
import json
import os
import re
from cloudify_cli import utils
from subprocess import call


management_ip = utils.get_management_server_ip()
client = utils.get_rest_client(management_ip)

deployments_json = sys.stdin.read()
deployments = json.loads(deployments_json)

host_magic_dir = "/tmp/cloudify_migration_data_2g25qt4/"

del_template =  "curl -s -XDELETE 'http://localhost:9200/cloudify_storage/node_instance/_query?q=deployment_id:{} '"
add_template = "curl -s -XPUT 'http://localhost:9200/{index}/{type}/{id}/_create' -d \'{source}\'"

if deployments:
    for dep in deployments:
        new_dep = client.deployments.create(
            dep['blueprint_id'],
            dep['id'],
            dep['inputs']
        )

        nodes = json.loads(open(host_magic_dir + dep['id'] + "_storage", 'r').read())
        events = json.loads(open(host_magic_dir + dep['id'] + "_events", 'r').read())
        
        with open(os.devnull, "w") as FNULL:
            del_command = del_template.format(dep['id'])
            call(["cfy", "ssh", "-c", del_command ], stdout=FNULL, stderr=FNULL)
            for node in nodes["hits"]["hits"]:
                source = json.dumps(node["_source"])
                if node["_type"] == "execution":
                    source = re.sub(r'/3\.1/',r'/3.2/', source) 
                add_command = add_template.format(index="cloudify_storage", type=str(node["_type"]), id=str(node["_id"]), source=source)
                call(["cfy", "ssh", "-c", add_command ], stdout=FNULL, stderr=FNULL)
            for event in events["hits"]["hits"]:
                add_command = add_template.format(index="cloudify_events", type=str(event["_type"]), id=str(event["_id"]), source=json.dumps(event["_source"]))
                call(["cfy", "ssh", "-c", add_command ], stdout=FNULL, stderr=FNULL)

 
        print 'Recreated deployment %s' % (new_dep['id'],)

