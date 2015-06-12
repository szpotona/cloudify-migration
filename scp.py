########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

import os
import sys
from distutils import spawn
from cloudify_cli.utils import get_management_user
from cloudify_cli.utils import get_management_server_ip
from cloudify_cli.utils import get_management_key
from subprocess import call


def scp(local_path, path_on_manager, to_manager):
    scp_path = spawn.find_executable('scp')
    management_path = '{0}@{1}:{2}'.format(
        get_management_user(),
        get_management_server_ip(),
        path_on_manager
    )
    command = [scp_path, '-i', os.path.expanduser(get_management_key())]
    if to_manager == 'upload':
        command += [local_path, management_path]
    else:
        command += [management_path, local_path]
    call(command)


if __name__ == "__main__":
    scp(sys.argv[1], sys.argv[2], sys.argv[3])
