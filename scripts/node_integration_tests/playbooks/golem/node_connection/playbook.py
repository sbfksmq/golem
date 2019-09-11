from functools import partial
import time
import typing

from scripts.node_integration_tests import helpers

from ...base import NodeTestPlaybook
from ...test_config_base import NodeId


class Playbook(NodeTestPlaybook):

    def step_wait_disconnect(self, node_id: NodeId, target_node: NodeId):
        def on_success(result):
            result_peer_keys: typing.Set[str] = \
                {peer['key_id'] for peer in result}

            if self.nodes_keys[target_node] in result_peer_keys:
                print("Waiting for nodes to disconnect...")
                time.sleep(30)
                return

            print(f"{node_id.value} disconnected with {target_node.value}.")
            self.fail()

        return self.call(node_id, 'net.peers.connected', on_success=on_success)

    steps: typing.Tuple = (
        partial(NodeTestPlaybook.step_get_key, node_id=NodeId.provider),
        partial(NodeTestPlaybook.step_get_key, node_id=NodeId.requestor),
        partial(NodeTestPlaybook.step_configure, node_id=NodeId.provider),
        partial(NodeTestPlaybook.step_configure, node_id=NodeId.requestor),
        partial(NodeTestPlaybook.step_get_network_info, node_id=NodeId.provider),
        partial(NodeTestPlaybook.step_get_network_info, node_id=NodeId.requestor),
        partial(NodeTestPlaybook.step_connect, node_id=NodeId.requestor,
                target_node=NodeId.provider),
        partial(NodeTestPlaybook.step_verify_connection, node_id=NodeId.requestor,
                target_node=NodeId.provider),
        partial(step_wait_disconnect,
                node_id=NodeId.requestor,
                target_node=NodeId.provider),
    )
