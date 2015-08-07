import os, sys
from cloudify_cli.utils import (get_management_user,
                                get_management_server_ip,
                                get_management_key)


command = 'ssh -n -o BatchMode=yes -i %s %s@%s true 2> /dev/null' % (
    get_management_key(),
    get_management_user(),
    get_management_server_ip()
)

command_result = os.system(command)
sys.exit(os.WEXITSTATUS(command_result))
