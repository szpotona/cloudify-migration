import os
import sys

from manager_rest.storage_manager import instance

sm = instance()

manager_venv = sys.argv[1]
operation = sys.argv[2]

for deployment in sm.deployments_list():
    ret = os.system('/bin/bash modify_agents.sh {} {} {} {}'.format(
        deployment.blueprint_id,
        deployment.id,
        manager_venv,
        operation
    ))
    if ret:
        sys.exit(ret)
