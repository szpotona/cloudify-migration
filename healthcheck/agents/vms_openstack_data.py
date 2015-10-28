import sys
import json
from openstack_plugin_common import Config, NovaClient


def _get_vm_info(openstack_id, nova_client):
    try:
        server = nova_client.servers.get(openstack_id)
        ips = []
        for ip in server.networks.itervalues():
            ips.extend(ip)
        name = server.name
        return {
            'ips': ips,
            'name': name
        }
    except:
        return {}


def main(args):
    path = sys.argv[1]
    output = sys.argv[2]
    with open(path) as f:
        agents = json.loads(f.read())
    result = {}
    client = NovaClient().get(Config().get())
    for k, v in agents.iteritems():
        if v.get('resource_id'):
            result[k] = _get_vm_info(v.get('resource_id'), client)
    with open(output, 'w') as f:
        f.write(json.dumps(result))


if __name__ == '__main__':
    main(sys.argv)
