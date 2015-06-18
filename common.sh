
# Common utility functions for migration scripts.
# Script requires four variables to be set to work properly:
#   OLD_CLI_PYTHON_VIRTENV
#   OLD_CLI_DIR
#   NEW_CLI_PYTHON_VIRTENV
#   NEW_CLI_DIR

function error {
    echo "$1" 1>&2
    exit $2
}

function absolute_path {
    echo $(dirname $(readlink -e $1))/$(basename $1)
}

function activate_cli {
    # Deactivate any virtual env that is potentially activated
    if [[ $(type -t deactivate) == 'function' ]]; then
        deactivate
    fi
    # Change dir to a directory containing an appropriate .cloudify directory
    cd $1
    # Activate the desired virtual env
    . $2/bin/activate
}

function activate_old_cli {
    activate_cli $OLD_CLI_DIR $OLD_CLI_PYTHON_VIRTENV
}

function activate_new_cli {
    activate_cli $NEW_CLI_DIR $NEW_CLI_PYTHON_VIRTENV
}
 
