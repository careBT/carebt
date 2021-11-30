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
from abc import abstractmethod

from threading import Timer

from typing import final
from typing import TYPE_CHECKING

from carebt.nodeStatus import NodeStatus

if TYPE_CHECKING:
    from carebt.behaviorTreeRunner import BehaviorTreeRunner  # pragma: no cover
    from carebt.abstractLogger import AbstractLogger  # pragma: no cover


class TreeNode(ABC):
    """
    `TreeNode` is the basic class which provides the common implementation
    for all careBT nodes.

    """

    def __init__(self, bt_runner: 'BehaviorTreeRunner', params: str = None):
        self.bt_runner = bt_runner
        self.__node_status = NodeStatus.IDLE
        self.__contingency_message = ''
        self.__params = params
        self.__in_params = []
        self.__out_params = []
        self.__timeout_timer = None

        # create local variables
        if(self.__params is not None):
            _params = self.__params.split('=>')
            if(len(_params[0]) > 0):
                self.__in_params = _params[0].strip().split(' ')
            if len(_params) == 2:
                self.__out_params = _params[1].strip().split(' ')

            self.get_logger().trace('{} in_params:  {}'
                                    .format(self.__class__.__name__,
                                            self.__in_params))
            self.get_logger().trace('{} out_params: {}'
                                    .format(self.__class__.__name__,
                                            self.__out_params))

            # create in params
            for p in filter(None, self.__in_params):
                p = p.replace('?', '_', 1)
                self.get_logger().trace('in: {}'.format(p))
                exec('self.{} = None'.format(p))

            # create out params
            for p in filter(None, self.__out_params):
                p = p.replace('?', '_', 1)
                self.get_logger().trace('out: {}'.format(p))
                exec('self.{} = None'.format(p))

    # PRIVATE

    @final
    def __internal_on_timeout(self):
        # timeout can only occure when state is RUNNING OR SUSPENDED
        if(self.get_status() == NodeStatus.RUNNING
           or self.get_status() == NodeStatus.SUSPENDED):
            self.on_timeout()

        self.cancel_timeout_timer()

    # PROTECTED

    @abstractmethod
    def _internal_on_tick(self) -> None:
        raise NotImplementedError

    def _internal_on_abort(self) -> None:
        self.cancel_timeout_timer()

    @final
    def _internal_get_bt_runner(self) -> 'BehaviorTreeRunner':
        return self.bt_runner

    @final
    def _internal_get_in_params(self) -> list:
        return self.__in_params

    @final
    def _internal_get_out_params(self) -> list:
        return self.__out_params

    # PUBLIC

    def on_init(self) -> None:
        """
        The `on_init` callback is called right after the node is instantiated.

        """

        pass

    def on_abort(self) -> None:
        """
        The `on_abort` callback is called in case the node is aborted.

        """

        pass

    def on_timeout(self) -> None:
        """
        The `on_timeout` callback is called in case the node timed out. To set the
        timer use `set_timeout`.

        """

        self.get_logger().warn('{}.on_timeout is not overridden, thus the default '
                               'is called (abort).'
                               .format(self.__class__.__name__))
        self.abort()
        self.set_contingency_message('TIMEOUT')

    def on_delete(self) -> None:
        """
        The `on_delete` callback is called if the node has completed execution. This
        allows to free blocked or allocated resources, especially when working with
        asynchronous actions.

        """

        pass

    @final
    def get_logger(self) -> 'AbstractLogger':
        """
        Returns the current logger, which is an implementation of
        `AbstractLogger`.

        Returns
        -------
        `AbstractLogger`
            The current logger

        """

        return self.bt_runner.get_logger()

    @final
    def get_status(self) -> NodeStatus:
        """
        Returns the current status of the node.

        Returns
        -------
        `NodeStatus`
            Current status of the node

        """

        return self.__node_status

    @final
    def set_timeout(self, timeout_ms: int) -> None:
        """
        Sets a timeout and starts the timer. In case a timeout occures,
        the `on_timeout` callback is called.

        Parameters
        ----------
        timeout_ms: int
            The timeout in milliseconds

        """

        self.__timeout_timer = Timer(timeout_ms/1000, self.__internal_on_timeout)
        self.__timeout_timer.start()

    @final
    def cancel_timeout_timer(self) -> None:
        """
        Cancels the timeout timer of the node.

        """

        if(self.__timeout_timer is not None):
            self.get_logger().trace('{} -> cancel timeout timer'
                                    .format(self.__class__.__name__))
            self.__timeout_timer.cancel()
            # set the timer to None to make sure that all references (bound method)
            # are released and the object gets destroyed by gc
            self.__timeout_timer = None

    @final
    def set_status(self, node_status: NodeStatus) -> None:
        """
        Sets the current status of the node.

        Parameters
        ----------
        node_status: `NodeStatus`
            Current status of the node

        """

        self.__node_status = node_status
        # If the status of the node is set to one of the following,
        # make sure that the timeout timer is canceled.
        if(node_status == NodeStatus.SUCCESS
           or node_status == NodeStatus.FAILURE
           or node_status == NodeStatus.FIXED
           or node_status == NodeStatus.ABORTED):
            self.cancel_timeout_timer()

    @final
    def get_contingency_message(self) -> str:
        """
        Returns the contincency message of the node. Typically this
        message is set in case the node completes with `FAILURE` to
        provide more details what went wrong.

        Returns
        -------
        str
            The contingency message

        """

        return self.__contingency_message

    @final
    def set_contingency_message(self, contingency_message: str) -> None:
        """
        Sets the contincency message of the node. Typically this
        message is set in case the node completes with `FAILURE` to
        provide more details what went wrong.

        Parameters
        ----------
        contingency_message: str
            The contingency message

        """

        self.__contingency_message = contingency_message

    @final
    def abort(self) -> None:
        """
        Abort the current node.

        """

        self._internal_on_abort()
