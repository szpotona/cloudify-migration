import sys

from cloudify_cli import utils
from cloudify_cli.bootstrap import bootstrap as bs
from cloudify_cli.bootstrap import tasks as bstasks


manager_version = sys.argv[1]

with utils.update_wd_settings() as settings:
    if settings.get_management_key() is None and settings.get_management_user() is None:
        provider_context = settings.get_provider_context()
        bs.read_manager_deployment_dump_if_needed(
            provider_context.get('cloudify', {}).get('manager_deployment')
        )
        env = bs.load_env('manager') # literal string here ..
        storage = env.storage
        for instance in storage.get_node_instances():
            manager_key = instance.runtime_properties.get(bstasks.MANAGER_KEY_PATH_RUNTIME_PROPERTY)
            if manager_key:
                settings.set_management_key(manager_key)
            manager_user = instance.runtime_properties.get(bstasks.MANAGER_USER_RUNTIME_PROPERTY)
            if manager_user:
                settings.set_management_user(manager_user)
            if manager_user or manager_key:
                break
    else:
        print 'The script is not able to perform "cfy ssh" and is not able to fix it automatically..'
        manager_key = raw_input("Please provide a path to the %s manager's key: " % manager_version)
        settings.set_management_key(manager_key)
        manager_user = raw_input("Please provide the %s manager's user name: " % manager_version)
        settings.set_management_user(manager_user)

