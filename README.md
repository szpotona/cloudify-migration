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

