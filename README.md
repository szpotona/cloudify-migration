# Cloudify Migration

This repository contains `migrate.sh` script and some utilities/tools that ease the process of Cloudify's live migration from version 3.1 to version 3.2. Migrations between other versions might be supported in the future.

###Prerequisites:###
The script's assumptions are that the new 3.2 manager is operational and that we have two CLI environments that can be used to manage our Cloudify managers (3.1 and 3.2).

Moreover, the 3.2 manager should be able to access all applications' machines, for example by using the same ssh keys and being in the same network as the 3.1 manager.


###Migration consists of two phases:###

- The first one involves reuploading blueprints and recreating deployments on the new manager. Additionally, the ElasticSearch data is transferred as well.
- The second one handles updating the Cloudify related software on host-agents machines (Celery workers, Diamond daemon, plugins) and optionally migrating metrics stored in the InfluxDB database (Cloudify UI's charts are based on them).

To launch migration, simply run the migrate.sh script:

`./migrate.sh -b -a -m  old_cli_virtenv_dir  old_cli_dir  new_cli_virtenv_dir  new_cli_dir`


Parameters and flags:

    -a
        i.e. "agents hosts software update"
        Without this flag the second phase will not be performed. The process may be
        accomplished later by using `migrate_agents.sh` and `migrate_metrics.sh` scripts.

    -b
        With this flag set the script suggests replacing strings 1.1 and 3.1 by 1.2 and 3.2
        in the whole blueprint - a colored diff is displayed. The proposed modifications
        are applied upon user's acceptance.

    -m
        Migrate InfluxDB metrics. For this flag to work, flag `-a` must be set as well.
        This option is implemented by the `migrate_metrics.sh` script.

    -p
        Usage: -p path_to_file.
        This flag is used to specify authentication override rules.
        Value of this flag will be passed directly to the `migrate_agents.sh` script
        as the last parameter. Check `migrate_agents.sh` description for more details.

    -n
        Usage: -n max_number_of_attempts
        This flag is used to specify the maximum number of attempts of a single task
        during agent migration. Check `migrate_agents.sh` description for more details.

    old_cli_virtenv_dir
        Python virtualenv directory used by the CLI initialized to operate the 3.1 manager.

    old_cli_dir
        A directory where the CLI for the 3.1 manager has been initialized.
        It should contain the .cloudify directory.

    new_cli_virtenv_dir
        Python virtualenv directory used by the CLI initialized to operate the 3.1 manager.

    new_cli_dir
        A directory where the cfy for the 3.2 manager has been initialized.
        It should contain the .cloudify directory.


Utility scripts:

- `migrate_agents.sh`

This script is responsible for updating Cloudify components on host-agents machines. These components are Celery workers, plugins code and the monitoring tool - Diamond.

Parameters and flags:

    -d
        Usage: -d deployment_id
        Optional flag. If specified, migrate_agents will perform operation only on hosts
        that are part of a deployment identified by id 'deployment_id'.
        Otherwise, operation will be performed on all hosts.

    -n
        Usage: -n max_number_of_attempts
        Optional flag. This flag is used to specify the maximum number of attempts 
        of a single task during agent migration. If this value is exceeded agent
        migration workflow will be cancelled. Its default value is -1, which
        means that there is no limit.

    operation
        install or uninstall

    manager
        3.1 or 3.2

    managers_cli_venv
        Python virtualenv directory used by the CLI initialized to operate the manager
        specified by the `manager` parameter

    managers_cli_dir
        A directory where the cfy for the manager specified by the `manager` parameter
        has been initialized. It should contain the .cloudify directory.

    passwords_path
        An optional path to a file that contains usernames/passwords that will be used
        during agent installation/uninstallation process. By default, script will use
        usernames/passwords that are contained in elastic search database of manager.
        You can use this parameter to override this behaviour. The file's format is YAML,
        for example:

        deployment_1:
          host_1:
            password: new_password
        deployment_2:
          host_2:
            user: new_user

        This file will force migrate_agents to use password `new_password` during agent
        modification on host with host id host_1 in deployment deployment_1 and username
        `new_user` for host_2 in deployment_2. All other agents will be installed/uninstalled
        using usernames/passwords stored on manager.


- `migrate_metrics.sh`

The mandatory parameters are the same as for the `migrate.sh` script. No optional flags are specified for this script for the time being.

- `print_failed_tasks.sh`

This scripts can be used in order to check if workflows run by migrate_agents.sh succeeded.

Parameters and flags:

    -w
        Usage: -w workflow_id
        Default value: `hosts_software_uninstall`.
        This flag lets user specify what workflows should be checked.

    managers_cli_venv
        Python virtualenv directory used by the CLI initialized to operate the manager
        specified by the `manager` parameter

    managers_cli_dir
        A directory where the cfy for the manager specified by the `manager` parameter
        has been initialized. It should contain the .cloudify directory.



###Tips:###

Should the migration process fail, you can always recover the 3.1 manager by restoring the Cloudify software on all host-agents machines. It can be achieved by running the following command:

`./migrate_agents.sh install 3.1 old_cli_virtenv_dir old_cli_dir`

Doing so is reasonable only if the Cloudify components have been effectively uninstalled on host-agents machines.
Otherwise the 3.1 manager should be consistent and ready to work with without performing any recovery actions.
