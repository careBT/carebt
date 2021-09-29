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

import re

from typing import Callable
from typing import final
from typing import TYPE_CHECKING

from carebt.executionContext import ExecutionContext
from carebt.nodeStatus import NodeStatus
from carebt.treeNode import TreeNode

if TYPE_CHECKING:
    from carebt.behaviorTreeRunner import BehaviorTreeRunner  # pragma: no cover


class ControlNode(TreeNode):  # abstract

    def __init__(self, bt_runner: 'BehaviorTreeRunner', params: str = None):
        super().__init__(bt_runner, params)

        # list for the child nodes
        self._child_ec_list = []

        # the current child pointer
        self._child_ptr = 0

        self._contingency_handler_list = []

        self.set_status(NodeStatus.IDLE)

    # PRIVATE

    """ allowed wildcards:
        ? one character
        * one or many charactres"""
    def __wildcard_to_regex(self, wildcard: str) -> re:
        # replace wildcards
        wildcard = wildcard.replace('?', '.')
        wildcard = wildcard.replace('*', '.*')

        return re.compile(wildcard)

    def _bind_in_params(self, child_ec: ExecutionContext) -> None:
        if(len(child_ec.call_in_params) != len(child_ec.instance.get_in_params())):
            self.get_logger().warn('{} takes {} argument(s), but {} was/were provided'
                                   .format(child_ec.node_as_class.__name__,
                                           len(child_ec.instance.get_in_params()),
                                           len(child_ec.call_in_params)))
        for i, var in enumerate(child_ec.call_in_params):
            if(isinstance(var, str) and var[0] == '?'):
                var = var.replace('?', '_', 1)
                var = getattr(self, var)
            setattr(child_ec.instance,
                    child_ec.instance.get_in_params()[i].replace('?', '_', 1), var)

    def _bind_out_params(self, child_ec: ExecutionContext) -> None:
        for i, var in enumerate(child_ec.instance.get_out_params()):
            var = var.replace('?', '_', 1)
            if(getattr(child_ec.instance, var) is None):
                self.get_logger().warn('{} output {} is not set'
                                       .format(child_ec.node_as_class.__name__,
                                               var.replace('_', '?', 1)))
            else:
                if(len(child_ec.call_out_params) <= i):
                    self.get_logger().warn('{} output {} not provided'
                                           .format(child_ec.node_as_class.__name__,
                                                   i))
                else:
                    setattr(self, child_ec.call_out_params[i].replace('?', '_', 1),
                            getattr(child_ec.instance, var))

    # PROTECTED

    @final
    def _tick_child(self, child_ec: ExecutionContext):

        # if child status is IDLE or RUNNING -> tick it
        if(child_ec.instance.get_status() == NodeStatus.IDLE or
           child_ec.instance.get_status() == NodeStatus.RUNNING):
            # tick child
            child_ec.instance._on_tick()

    @final
    def _apply_contingencies(self, child_ec: ExecutionContext):
        self.get_logger().debug('searching contingency-handler for: {} - {} - {}'
                                .format(child_ec.instance.__class__.__name__,
                                        child_ec.instance.get_status(),
                                        child_ec.instance.get_message()))

        # iterate over contingency_handler_list
        for contingency_handler in self._contingency_handler_list:

            # handle wildcards
            if(isinstance(contingency_handler[0], str)):
                regexClassName = self.__wildcard_to_regex(
                    contingency_handler[0])
            else:
                regexClassName = self.__wildcard_to_regex(
                    contingency_handler[0].__name__)
            regexMessage = self.__wildcard_to_regex(contingency_handler[2])

            self.get_logger().debug('checking contingency_handler: {} -{} - {}'
                                    .format(regexClassName.pattern,
                                            contingency_handler[1],
                                            regexMessage.pattern))
            # check if contingency-handler matches
            if(bool(re.match(regexClassName,
                             child_ec.instance.__class__.__name__))
                    and child_ec.instance.get_status() in contingency_handler[1]
                    and bool(re.match(regexMessage,
                                      child_ec.instance.get_message()))):
                self.get_logger().info('{} -> run contingency_handler {}'
                                       .format(child_ec.instance.__class__.__name__,
                                               contingency_handler[3]))
                # execute function attached to the contingency-handler
                exec('self.{}()'.format(contingency_handler[3]))
                self.get_logger().debug('after contingency_handler {} - {} - {}'
                                        .format(child_ec.instance.__class__.__name__,
                                                child_ec.instance.get_status(),
                                                child_ec.instance.get_message()))
                break

    # PUBLIC

    @final
    def attach_contingency_handler(self, node_as_class: TreeNode, node_status_list: NodeStatus,
                                   message: str, function: Callable) -> None:
        # for the function only store the name, thus there is no 'bound method' to self
        # which increases the ref count and prevents the gc to delete the object
        self._contingency_handler_list.append((node_as_class,
                                               node_status_list,
                                               message,
                                               function.__name__))

    def fix_current_child(self) -> None:
        self._child_ec_list[self._child_ptr].instance.set_status(NodeStatus.FIXED)
        self._child_ec_list[self._child_ptr].instance.set_message('')
