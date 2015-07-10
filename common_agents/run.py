import os
import os.path
import sys

import yaml

import manager_rest.es_storage_manager as es
from manager_rest.storage_manager import instance as storage_manager_instance

import agents_utils


def _prepare_auth_updates(auth_dict, sm):
    result = {}
    for deployment_id, config in auth_dict.iteritems():
        # will throw an exception if there is no such deployment
        sm.get_deployment(deployment_id)
        update_actions = []
        revert_actions = []
        for node_id, agent_config in config.iteritems():
            node = sm.get_node(deployment_id, node_id)
            agent_properties = node.properties['cloudify_agent']
            revert_actions.append((node, agent_properties))
            agent_properties = agent_properties.copy()
            for key in agent_config.keys():
                if key not in ['user', 'password']:
                    raise Exception(
                        'Key {0} not allowed in auth config'.format(key))
                new_value = agent_config.get(key)
                if new_value is not None:
                    agent_properties[key] = new_value
            update_actions.append((node, agent_properties))
        result[deployment_id] = {
            'update': update_actions,
            'revert': revert_actions
        }
    return result


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
    updates_list = updates.get(deployment_id, {}).get(update_key, [])
    map(lambda u: _perform_node_update(u, deployment_id, sm), updates_list)


def main(args):
    sm = storage_manager_instance()

    manager_venv = args[1]
    operation = args[2]
    max_attempts = args[3]

    with open('auth_config.yaml', 'r') as auth_stream:
        custom_auth = yaml.load(auth_stream) or {}

    actions = _prepare_auth_updates(custom_auth, sm)

    if os.path.isfile('deployment_id'):
        with open('deployment_id', 'r') as deployment_file:
            deployment_id = deployment_file.read()
            deployments = [sm.get_deployment(deployment_id)]
    else:
        deployments = sm.deployments_list()

    for deployment in deployments:
        try:
            _perform_deployment_updates(deployment.id, actions, 'update', sm)
            ret = os.system('/bin/bash modify_agents.sh {} {} {} {} {}'.format(
                deployment.blueprint_id,
                deployment.id,
                manager_venv,
                operation,
                max_attempts
            ))
        finally:
            _perform_deployment_updates(deployment.id, actions, 'revert', sm)
        if ret:
            sys.exit(ret)


if __name__ == '__main__':
    main(sys.argv)
