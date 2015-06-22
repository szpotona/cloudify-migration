import json
import re
import sys
from subprocess import check_output

dep_id = sys.argv[1]
chunk_size = '100'
if len(sys.argv) > 2:
    chunk = sys.argv[2]

ichunk_size = int(chunk_size)
magic_path = '/tmp/cloudify_migration_data_storage_3f53t9'
magic_path2 = '/tmp/cloudify_migration_data_events_3f53t9'

dump_storage_template = (
    'http://localhost:9200/'
    'cloudify_storage/node_instance,execution/'
    '_search?from={start}&size={size}&q=deployment_id:{id}')
dump_events_template = (
    'http://localhost:9200/'
    'cloudify_events/_search?from={start}&size={size}&'
    'q=deployment_id:{id}')

bulk_entry_template = ('{{ create: {{ "_id": "{id}",'
                       '"_type": "{type}"  }} }}\n{source}\n')


def get_chunk(cmd):
    return check_output(['curl', '-s', '-XGET', cmd], universal_newlines=True)


def remove_newlines(s):
    return s.replace('\n', ' ').replace('\r', '')


def convert_to_bulk(chunk):
    def get_source(n):
        source = json.dumps(n['_source'])
        if n['_type'] == 'execution':
            source = re.sub(r'/3\.1/', r'/3.2/', source)
        return source

    return ''.join([bulk_entry_template.format(
        id=str(n['_id']),
        type=str(n['_type']),
        source=remove_newlines(get_source(n))
        ) for n in chunk])


def append_to_file(f, js):
    f.write(convert_to_bulk(js['hits']['hits']))


def dump_chunks(f, template):
    cmd = template.format(id=dep_id, start='0', size=chunk_size)
    js = json.loads(get_chunk(cmd))
    append_to_file(f, js)
    total = int(js['hits']['total'])
    if total > ichunk_size:
        for i in xrange(ichunk_size, total, ichunk_size):
            cmd = dump_storage_template.format(
                    id=dep_id,
                    start=str(i),
                    size=chunk_size)
            js = json.loads(get_chunk(cmd))
            append_to_file(f, js)

with open(magic_path, 'a') as f:
    # Storage dumping
    dump_chunks(f, dump_storage_template)

with open(magic_path2, 'a') as f:
    # Events dumping
    dump_chunks(f, dump_events_template)
