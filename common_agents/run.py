import os
import sys

import yaml

import manager_rest.es_storage_manager as es
from manager_rest.storage_manager import instance as storage_manager_instance


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
            updated_keys = ['user', 'password']
            for key in agent_config.keys():
                if key not in updated_keys:
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
    try:
        connection = sm._connection  # 3.2
    except AttributeError:
        connection = sm._get_es_conn()  # 3.1
    connection.update(index=es.STORAGE_INDEX_NAME,
                      doc_type=es.NODE_TYPE,
                      id=storage_node_id,
                      body=update_doc,
                      refresh=True)


def _perform_deployment_updates(deployment_id, updates, update_key, sm):
    updates_list = updates.get(deployment_id, {}).get(update_key, [])
    map(lambda u: _perform_node_update(u, deployment_id, sm), updates_list)


sm = storage_manager_instance()

manager_venv = sys.argv[1]
operation = sys.argv[2]

with open('auth_config.yaml', 'r') as auth_stream:
    custom_auth = yaml.load(auth_stream) or {}

actions = _prepare_auth_updates(custom_auth, sm)

for deployment in sm.deployments_list():
    try:
        _perform_deployment_updates(deployment.id, actions, 'update', sm)
        ret = os.system('/bin/bash modify_agents.sh {} {} {} {}'.format(
            deployment.blueprint_id,
            deployment.id,
            manager_venv,
            operation
        ))
    finally:
        _perform_deployment_updates(deployment.id, actions, 'revert', sm)
    if ret:
        sys.exit(ret)
