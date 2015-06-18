from manager_rest.storage_manager import instance
from manager_rest import  models
from datetime import datetime
import uuid
import sys
from subprocess import call
import os
import sys

sm = instance()

manager_venv = sys.argv[1]
operation = sys.argv[2]

for deployment in sm.deployments_list():
    os.system('/bin/bash modify_agents.sh {} {} {} {}'.format(
          deployment.blueprint_id, 
          deployment.id,
          manager_venv,
          operation
          ))
   
   
