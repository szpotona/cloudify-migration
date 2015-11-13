import os
import os.path
import sys

import json

import manager_rest.es_storage_manager as es
from manager_rest.storage_manager import instance as storage_manager_instance

import agents_utils
import execute

_DIRECTORY = os.path.dirname(os.path.realpath(__file__))

def _prepare_auth_updates(deployment_id, auth_dict, sm):
    # will throw an exception if there is no such deployment
    sm.get_deployment(deployment_id)
    update_actions = []
    revert_actions = []
    for node_id, agent_config in auth_dict.iteritems():
        node = sm.get_node(deployment_id, node_id)
        agent_properties = node.properties['cloudify_agent']
        revert_actions.append((node, agent_properties))
        agent_properties = agent_properties.copy()
        for key in agent_config.keys():
            if key not in ['user', 'password', 'key']:
                raise Exception(
                    'Key {0} not allowed in auth config'.format(key))
            new_value = agent_config.get(key)
            if new_value is not None:
                agent_properties[key] = new_value
        update_actions.append((node, agent_properties))
    return {
        'update': update_actions,
        'revert': revert_actions
    }


def _perform_node_update(update_spec, deployment_id, sm):
    node, agent_properties = update_spec
    storage_node_id = sm._storage_node_id(deployment_id, node.id)
    node.properties['cloudify_agent'] = agent_properties
    update_doc = {'doc': {'properties': node.properties}}
    connection = agents_utils.es_connection_from_storage_manager(sm)
    connection.update(index=es.STORAGE_INDEX_NAME,
                      doc_type=es.NODE_TYPE,
                      id=storage_node_id,
                      body=update_doc,
                      refresh=True)


def _perform_deployment_updates(deployment_id, updates, update_key, sm):
    updates_list = updates.get(update_key, [])
    map(lambda u: _perform_node_update(u, deployment_id, sm), updates_list)


def main(args):
    sm = storage_manager_instance()

    manager_venv = args[1]
    operation = args[2]
    max_attempts = args[3]
    deployment_id = args[4]
    auth_override = args[5]
    version = args[6]
    with open(auth_override, 'r') as auth_stream:
        custom_auth = json.load(auth_stream) or {}

    actions = _prepare_auth_updates(deployment_id, custom_auth, sm)

    deployment = sm.get_deployment(deployment_id)
    node_instances = sm.get_node_instances(deployment.id)
    try:
        _perform_deployment_updates(
            deployment.id,
            actions,
            'update',
            sm
        )
        ret = execute.main([
            '', 
            deployment.blueprint_id,
            deployment.id,
            operation,
            max_attempts,
            version])
    finally:
        _perform_deployment_updates(
            deployment.id,
            actions,
            'revert',
            sm
        )
    sys.exit(ret)

if __name__ == '__main__':
    main(sys.argv)
