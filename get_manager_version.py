from cloudify_cli import utils

management_ip = utils.get_management_server_ip()
client = utils.get_rest_client(management_ip)
version = client.manager.get_version()

print version
