# Copyright 2021 Andreas Steck (steck.andi@gmail.com)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from abc import ABC

from typing import TYPE_CHECKING

from carebt.controlNode import ControlNode
from carebt.executionContext import ExecutionContext
from carebt.nodeStatus import NodeStatus
from carebt.treeNode import TreeNode

if TYPE_CHECKING:
    from carebt.behaviorTreeRunner import BehaviorTreeRunner  # pragma: no cover


class SequenceNode(ControlNode, ABC):
    """The careBT `SequenceNode` class.

    In a `SequenceNode` the added child nodes are executed one after another until
    they all complete with `SUCCESS` or `FIXED`. The child nodes are executed in the
    order they were added to the sequence. If all children complete with `SUCCESS`
    or `FIXED` the `SequenceNode` completes with `SUCCESS`.

    If one of the children completes with `FAILURE` or `ABORTED` and the situation is
    not fixed by a contingency-handler the `SequenceNode` completes also with `FAILURE`
    or `ABORTED`.

    The `SequenceNode` forwards the ticks to the currently executing child - which can
    only be one at a time - if the status is `RUNNING`. If the status is `SUSPENDED`
    the ticks are not forwarded.

    Parameters
    ----------
    bt_runner: 'BehaviorTreeRunner'
        The behavior tree runner which started the tree.
    params: str
        The input/Output parameters of the node
        e.g. '?x ?y => ?z'

    """

    def __init__(self, bt_runner: 'BehaviorTreeRunner', params: str = None):
        """Init the `SequenceNode` with bt_runner and params."""
        super().__init__(bt_runner, params)

    # PROTECTED

    def _internal_on_tick(self) -> None:
        self.get_logger().info('ticking {}'.format(self.__class__.__name__))
        if(self.get_status() != NodeStatus.RUNNING):
            self.set_status(NodeStatus.RUNNING)

        # if child list is empty, there is nothing to do
        if(len(self._child_ec_list) == 0):
            return

        ################################################
        # if there is no current child to be ticked, create one
        if(self._child_ec_list[self._child_ptr].instance is None):
            # create node instance
            self._child_ec_list[self._child_ptr].instance = \
                self._child_ec_list[self._child_ptr].node(self._internal_get_bt_runner())
            self._internal_bind_in_params(self._child_ec_list[self._child_ptr])
            self._child_ec_list[self._child_ptr].instance.on_init()

        # tick child
        self._internal_tick_child(self._child_ec_list[self._child_ptr])
        self._internal_apply_contingencies(self._child_ec_list[self._child_ptr])

        ################################################
        # finally, check how to proceed in the sequence
        if(self.get_status() == NodeStatus.RUNNING):
            if self._child_ec_list[self._child_ptr].instance is not None:
                cur_child_state = self._child_ec_list[self._child_ptr].instance.get_status()

                # if the current child tick returned with FAILURE or ABORTED
                if(cur_child_state == NodeStatus.FAILURE
                   or cur_child_state == NodeStatus.ABORTED):
                    self.set_status(cur_child_state)
                    self.set_contingency_message(self._child_ec_list[self._child_ptr]
                                                 .instance.get_contingency_message())

                cur_child_state = self._child_ec_list[self._child_ptr].instance.get_status()
                # if the current child tick returned with SUCCESS or FIXED
                if(cur_child_state == NodeStatus.SUCCESS
                   or cur_child_state == NodeStatus.FIXED):
                    self._contingency_message = self._child_ec_list[self._child_ptr]\
                        .instance.get_contingency_message()
                    # if current child state is FIXED -> do not bind out_params
                    # as the 'fix' implementation is done in the contingency-handler
                    if(cur_child_state != NodeStatus.FIXED):
                        self._internal_bind_out_params(self._child_ec_list[self._child_ptr])
                    if(self._child_ec_list[self._child_ptr].instance is not None):
                        self._child_ec_list[self._child_ptr].instance.on_delete()
                        self._child_ec_list[self._child_ptr].instance = None
                    # check if there is at least one more node to run
                    if(self._child_ptr + 1 < len(self._child_ec_list)):
                        self._child_ptr += 1
                    else:
                        # no more nodes to run -> sequence = SUCCESS
                        self.set_status(NodeStatus.SUCCESS)
                        self.set_contingency_message(self._contingency_message)

        if(self.get_status() == NodeStatus.SUCCESS
           or self.get_status() == NodeStatus.FAILURE
           or self.get_status() == NodeStatus.ABORTED
           or self.get_status() == NodeStatus.FIXED):
            self.get_logger().info('finished {}'.format(self.__class__.__name__))
            if(self._child_ec_list[self._child_ptr].instance is not None):
                self._child_ec_list[self._child_ptr].instance.on_delete()
                self._child_ec_list[self._child_ptr].instance = None

    def _internal_on_abort(self) -> None:
        super()._internal_on_abort()
        self.get_logger().info('aborting {}'.format(self.__class__.__name__))
        # abort current child if RUNNING or SUSPENDED
        if(self._child_ec_list[self._child_ptr].instance.get_status() == NodeStatus.RUNNING or
           self._child_ec_list[self._child_ptr].instance.get_status() == NodeStatus.SUSPENDED):
            self._child_ec_list[self._child_ptr].instance._internal_on_abort()
        self.set_status(NodeStatus.ABORTED)
        self.set_contingency_message(self._child_ec_list[self._child_ptr]
                                     .instance.get_contingency_message())
        if(self._child_ec_list[self._child_ptr].instance is not None):
            self._child_ec_list[self._child_ptr].instance.on_delete()
            self._child_ec_list[self._child_ptr].instance = None
        self.on_abort()

    # PUBLIC

    def append_child(self, node: TreeNode, params: str = None) -> None:
        """Append a child node.

        Append a child node at the end of the sequence of this `SequenceNode`.

        Parameters
        ----------
        node: TreeNode
            The node to be added

        params: str (Default=None)
            The parameters of the added child node

        """
        self._child_ec_list.append(ExecutionContext(node, params))

    def insert_child_after_current(self, node: TreeNode, params: str = None) -> None:
        """Insert a child node.

        Insert a child node right after the currently executing child node. NOTE: When
        inserting more than one node, they should be inserted in reverse order. This is
        because each node will be inserted right after the currently executing!

        Parameters
        ----------
        node: TreeNode
            The node to be added

        params: str (Default=None)
            The parameters of the added child node

        """
        # if all children were removed
        if(len(self._child_ec_list) != 0
           and self._child_ec_list[self._child_ptr].instance is None
           and self._child_ptr == 0):
            self._child_ec_list.insert(0, ExecutionContext(node, params))
        else:
            self._child_ec_list.insert(self._child_ptr + 1, ExecutionContext(node, params))

    def remove_all_children(self) -> None:
        """Remove all child nodes.

        Remove all child nodes from the `SequenceNode`. This is typically done in a contingency
        handler to modify the current execution sequence and adjust it to the current situation.
        New children which should be executed afterwards can be added with `append_child` or
        `insert_child_after_current`.

        """
        self._child_ec_list[self._child_ptr].instance.on_delete()
        self._child_ec_list.clear()
        self._child_ptr = 0
