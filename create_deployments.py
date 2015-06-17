import sys
import json
import os
import re
from cloudify_cli import utils
from subprocess import call
from scp import scp


management_ip = utils.get_management_server_ip()
client = utils.get_rest_client(management_ip)

deployments_json = sys.stdin.read()
deployments = json.loads(deployments_json)

host_magic_dir = "/tmp/cloudify_migration_data_2g25qt4/"
magic_file = "/tmp/cloudify_migration_data_5ovg6bht"
host_magic_file = "/tmp/cloudify_migration_data_646mo325h"

del_template = ("curl -s -XDELETE 'http://localhost:9200/"
                "cloudify_storage/node_instance/_query?q=deployment_id:{} '")
add_template = ("curl -s -XPUT 'http://localhost:9200/"
                "{index}/{type}/{id}/_create' -d \'{source}\'")
bulk_template = ("curl -s XPOST 'http://localhost:9200/"
                 "cloudify_events/_bulk' --data-binary @{file}")
bulk_entry_template = ('{{ create: {{ "_id": "{id}",'
                       '"_type": "{type}"  }} }}\n{source}\n')

if deployments:
    for dep in deployments:
        new_dep = client.deployments.create(
            dep['blueprint_id'],
            dep['id'],
            dep['inputs']
        )

        nodes = json.loads(open(
            host_magic_dir + dep['id'] + "_storage",
            'r'
        ).read())

        events = json.loads(open(
            host_magic_dir + dep['id'] + "_events",
            'r').read()
        )

        with open(os.devnull, "w") as FNULL:
            del_command = del_template.format(dep['id'])
            call(["cfy", "ssh", "-c", del_command],
                 stdout=FNULL, stderr=FNULL)
            for node in nodes["hits"]["hits"]:
                source = json.dumps(node["_source"])
                if node["_type"] == "execution":
                    source = re.sub(r'/3\.1/', r'/3.2/', source)
                add_command = add_template.format(
                        index="cloudify_storage",
                        type=str(node["_type"]),
                        id=str(node["_id"]),
                        source=source)
                call(["cfy", "ssh", "-c", add_command],
                     stdout=FNULL, stderr=FNULL)

            def remove_newlines(s):
                return s.replace('\n', ' ').replace('\r', '')

            bulk = "".join([bulk_entry_template.format(
                id=str(event["_id"]),
                type=str(event["_type"]),
                source=remove_newlines(json.dumps(event["_source"]))
                ) for event in events["hits"]["hits"]])

            with open(host_magic_file, "w") as f:
                f.write(bulk)
            scp(host_magic_file, magic_file, True)
            call(["cfy", "ssh", "-c",  bulk_template.format(file=magic_file)],
                 stdout=FNULL, stderr=FNULL)

        print 'Recreated deployment %s' % (new_dep['id'],)
