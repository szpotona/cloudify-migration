# Cloudify Migration

This repository contains `migrate.sh` script and some utilities/tools that ease the process of Cloudify's live migration upgrades among versions 3.1, 3.2 and 3.2.1.

# Usage

Install packages specified in requirements.txt

Run python migrate.py init

Run python migrate.py migrate with proper arguments

Run python migrate.py cleanup for both managers


# Commands
init - initializes environment for this script. It should be run before any other commands.

migrate - migration itself

cleanup - cleanup after migration

agents - it can be used for agent installation/uninstallation for specific deployment

healthcheck - runs healthcheck for specific deployment

start_agents - starts agents on host vms in all valid deployments on manager. It skips those deployments where agents are responding and those where there is a vm that can't be accessed remotely.

analyze_blueprints - subcommand that downloads all blueprints from manager and checks if it is possible to autmatically pick correct yaml file. Generates two outputs files:
full report - json file, path should be specified with --output flag
list of problematic blueprints - csv file, path should specified with --csv_output file. First column in csv file is a name of the blueprint, all following columns are filled with names of blueprint file candidates. Only those blueprints that have multiple blueprint file candidates are listed here.

# Testing environment
All testing is performed in openstack cloud.

Machine where script is run: Ubuntu 14.04

Cloudify machines:

Manager 3.1: Ubuntu 12.04

Manager 3.2: Ubuntu 14.04

Manager 3.2.1: Ubuntu 14.04

Unix deployments: Ubuntu 14.04

Windows deployments: Windows Server 2008, Service Pack 2 (custom image with preconfigured WinRM and predefined username/password)
