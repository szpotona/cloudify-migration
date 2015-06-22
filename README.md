# Cloudify Migration

This repository contains `migrate.sh` script and some utilities/tools that ease the process of Cloudify's live migration from version 3.1 to version 3.2. Migrations between other versions might be supported in the future.

###Prerequisites:###
The script's assumptions are that the new 3.2 manager is operational and that we have two CLI environments that can be used to manage our Cloudify managers (3.1 and 3.2).

Moreover, the 3.2 manager should be able to access all applications' machines, for example by using the same ssh keys and being in the same network as the 3.1 manager.


###Migration consists of two phases:###

- The first one involves reuploading blueprints and recreating deployments on the new manager. Additionally, the ElasticSearch data is transferred as well.
- The second one handles updating the Cloudify related software on host-agents machines (Celery workers, Diamond daemon, plugins) and migrating metrics stored in the InfluxDB database (Cloudify UI's charts are based on them).

To launch migration, simply run the migrate.sh script:

`./migrate.sh -a -b  old_cli_virtenv_dir  old_cli_dir  new_cli_virtenv_dir  new_cli_dir`


Parameters and flags:

    -a
        i.e. "migrate all" - perform full migration.
        Without this flag the second phase will not be performed. The process may be
        completed later by using `migrate_agents.sh` and `migrate_metrics.sh` scripts.

    -b
        With this flag set the script suggests updating versions (1.1 -> 1.2 and 3.1 -> 3.2) in each blueprint's imports by displaying a colored diff. The proposed modifications are applied upon user's permission. This option is highly recommended.

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

Parameters:

    operation
        install or uninstall

    manager
        3.1 or 3.2

    managers_cli_venv
        Python virtualenv directory used by the CLI initialized to operate the manager specified by the `manager` parameter

    managers_cli_dir
        A directory where the cfy for the manager specified by the `manager` parameter has been initialized.
        It should contain the .cloudify directory.

- `migrate_metrics.sh`

The mandatory parameters are the same as for the `migrate.sh` script. No optional flags are specified for this script for the time being.


###Tips:###

Should the migration process fail, you can always recover the 3.1 manager by restoring the Cloudify software on all host-agents machines. It can be achieved by running the following command:

`./migrate_agents.sh install 3.1 old_cli_virtenv_dir old_cli_dir`

Doing so is reasonable only if the Cloudify components have been effectively uninstalled on host-agents machines.
Otherwise the 3.1 manager should be consistent and ready to work with without performing any recovery actions.
