# Cloudify Migration

A migrate.sh and `migrate_agents.sh` scripts and their helper subscripts/tools easing live migration of Cloudify from version 3.1 to version 3.2.
Migrations between other versions might be supported in the future.

Migration consists of two parts -  First is migration of blueprints and deployments.
The second is migration of agents, metrics and ElasticSearch data.

To launch migration simply run migrate.sh script:

`./migrate.sh -a -b old_cli_virtenv_dir   old_cli_dir    new_cli_virtenv_dir   new_cli_dir`


Parameters and options:

    -a
        Perform full migration.
        Without this flag the hosts software will not be updated and
        will have to be migrated later by using the migrate_agents script.

    -b
        With this flag the script will ask the user whether or not to automatically
        update the versions  in the blueprints.

    old_cli_virtenv_dir
                Python virtualenv dir used by 3.1 cli.

    old_cli_dir
                A directory, where the cfy for the 3.1 manager has been initialized.
                It should contain the .cloudify directory.

    new_cli_virtenv_dir
                Python virtualenv dir used by 3.2 cli.

    new_cli_dir
                A directory, where the cfy for the 3.2 manager has been initialized.
                It should contain the .cloudify directory.


We assume that the new 3.2 manager is operational and that we have two environments that can be used to manage our Cloudify managers (3.1 and 3.2).

As soon as all blueprints are reuploaded, there comes the next step - recreating deployments. It involves creating them and migrating crucial ElasticSearch data - node instances and executions from the cloudify\_storage index and the whole cloudify\_events index.

The last stage is updating software on agent machines and transferring metrics stored in InfluxDB.


Run `migrate_agent.sh` script to perform agents recovery for cloudify 3.1

`./migrate_agents.sh install 3.1 old_cli_virtenv_dir old_cli_dir`
