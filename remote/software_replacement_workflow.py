import sys
import time

from cloudify.exceptions import NonRecoverableError
from cloudify.decorators import workflow
from cloudify.plugins.workflows import (
    _is_host_node,
    _host_post_start,
    _host_pre_stop
)


@workflow
# op_name should be either install or uninstall
def replace_host_software(ctx, op_name, **kwargs):
    graph = ctx.graph_mode()
    for node in ctx.nodes:
        for instance in node.instances:
            if _is_host_node(instance) \
                    and instance._node_instance.state == 'started' \
                    and node.properties['install_agent'] is True:
                if op_name == "uninstall":
                    generate_tasks_fun = _host_pre_stop
                elif op_name == "install":
                    def generate_tasks_fun(instance):
                        tasks = _host_post_start(instance)
                        for subnode in instance.get_contained_subgraph():
                            tasks.append(
                                subnode.execute_operation(
                                    'cloudify.interfaces.monitoring.start')
                            )
                        return tasks
                else:
                    raise NonRecoverableError(
                        'Unrecognized operation %s' % op_name)
                sequence = graph.sequence()
                sequence.add(*generate_tasks_fun(instance))
    graph.execute()
