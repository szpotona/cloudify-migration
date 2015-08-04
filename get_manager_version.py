from cloudify_cli import utils


def normalize_version(ver):
    if ver.endswith('.0'):
        ver = ver[:-2]
    return ver


if __name__ == '__main__':
    management_ip = utils.get_management_server_ip()
    client = utils.get_rest_client(management_ip)

    version_info = client.manager.get_version()
    version = version_info['version']
    print normalize_version(version)
