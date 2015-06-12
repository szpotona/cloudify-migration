from manager_rest.storage_manager import instance
from manager_rest import  models
from datetime import datetime
import uuid
import sys
from subprocess import call
import os

sm = instance()

for deployment in sm.deployments_list():
    os.system('/bin/bash install_agents.sh {} {}'.format(
          deployment.blueprint_id, 
          deployment.id))
   
   
