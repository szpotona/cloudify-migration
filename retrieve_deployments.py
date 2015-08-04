import json
import os
import sys
from subprocess import call

from cloudify_cli import utils
from scp import scp

dump_script_path = sys.argv[1]

management_ip = utils.get_management_server_ip()
client = utils.get_rest_client(management_ip)
deployments = client.deployments.list()

magic_path = '/tmp/cloudify_migration_data_storage_3f53t9'
magic_path2 = '/tmp/cloudify_migration_data_events_3f53t9'
magic_path3 = '/tmp/cloudify_migration_script_3ho6o2'
host_magic_dir = '/tmp/cloudify_migration_data_2g25qt4/'

cmd = 'python {path} {id}'
del_files = 'rm -f {0} {1}'

if not os.path.exists(host_magic_dir):
    os.mkdir(host_magic_dir)

scp(dump_script_path, magic_path3, True)

for dep in deployments:
    dep_id = dep['id']
    call(['cfy', 'ssh', '-c', cmd.format(path=magic_path3, id=dep_id)])

scp(host_magic_dir + 'migration_deps_storage', magic_path, False)
scp(host_magic_dir + 'migration_deps_events', magic_path2, False)
call(['cfy', 'ssh', '-c', del_files.format(magic_path, magic_path2)])

# These statements have to be executed as last.
# Send the data to another script, running in a different virtenv
with os.fdopen(3, 'w') as result_f:
    result_f.write(json.dumps(deployments))
