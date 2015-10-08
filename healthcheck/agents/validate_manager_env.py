import sys
import json

from cloudify.celery import celery

path = sys.argv[1]
content = sys.argv[2]
with open(path, 'w') as f:
    f.write(content)

