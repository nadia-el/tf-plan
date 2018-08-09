# This file is part of tf-plan.

# tf-plan is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# tf-plan is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with tf-plan. If not, see <http://www.gnu.org/licenses/>.


from tfrddlsim.compiler import Compiler
from tfrddlsim.policy import Policy
from tfrddlsim.fluent import TensorFluent

import tensorflow as tf

from typing import Optional, Sequence, Tuple

Bounds = Tuple[Optional[TensorFluent], Optional[TensorFluent]]


class OpenLoopPolicy(Policy):
    '''OpenLoopPolicy returns an action independently of the current state.

    Note:
        It uses the current state only for constraining the bounds of each action fluent.

    Args:
        compiler (:obj:`tfrddlsim.compiler.Compiler`): A RDDL2TensorFlow compiler.
        batch_size (int): The batch size.
        horizon(int): The number of timesteps.
    '''

    def __init__(self, compiler: Compiler, batch_size: int, horizon: int) -> None:
        self._compiler = compiler
        self._batch_size = batch_size
        self._horizon = horizon

        self._build_policy_variables()

    def _build_policy_variables(self) -> None:
        '''Builds the policy variables for each action fluent.'''
        action_fluents = self._compiler.action_fluent_ordering
        action_size = self._compiler.action_size
        with self._compiler.graph.as_default():
            self._policy_variables = []
            for fluent, shape in zip(action_fluents, action_size):
                var = self._get_policy_variable(fluent, shape)
                self._policy_variables.append(var)
            self._policy_variables = tuple(self._policy_variables)

    def __call__(self,
            state: Sequence[tf.Tensor],
            timestep: tf.Tensor) -> Sequence[tf.Tensor]:
        '''Returns action fluents for the current `state` and `timestep`.

        Args:
            state (Sequence[tf.Tensor]): The current state fluents.
            timestep (tf.Tensor): The current timestep.

        Returns:
            Sequence[tf.Tensor]: A tuple of action fluents.
        '''
        action_fluents = self._compiler.action_fluent_ordering
        bounds = self._compiler.compile_action_bound_constraints(state)
        action = []
        with self._compiler.graph.as_default():
            t = tf.cast(timestep[0][0], tf.int32) # TODO change timestep dtype in tfrddlsim
            for fluent, var in zip(action_fluents, self._policy_variables):
                tensor = self._get_action_tensor(var[:,t,:], bounds[fluent])
                action.append(tensor)
        return tuple(action)

    def _get_policy_variable(self, fluent: str, fluent_shape: Sequence[int]) -> tf.Tensor:
        '''Returns the correspondig policy variable for `fluent` with `fluent_shape`.

        Args:
            fluent (str): The fluent name.
            fluent_shape (Sequence[int]): The fluent shape.

        Returns:
            tf.Tensor: The policy variable for the action fluent.
        '''
        shape = [self._batch_size, self._horizon] + list(fluent_shape)
        name = fluent.replace('/', '-') # TODO change canonical fluent name in tfrddlsim
        return tf.get_variable(name, dtype=tf.float32, shape=shape)

    def _get_action_tensor(self, policy_variable: tf.Tensor, bounds: Bounds) -> tf.Tensor:
        '''Returns the action tensor for `policy_variable` with domain
        constrainted by the action fluent precondition `bounds`

        Args:
            policy_variable (tf.Tensor): The policy variable.
            bounds (Tuple[Optional[tfrddlsim.fluent.TensorFluent],
            Optional[tfrddlsim.fluent.TensorFluent]]): The (lower, upper) bounds.

        Returns:
            tf.Tensor: The action fluent tensor.
        '''
        lower, upper = bounds
        lower = lower.tensor if lower is not None else None
        upper = upper.tensor if upper is not None else None
        if lower is not None and upper is not None:
            return lower + (upper - lower) * tf.sigmoid(policy_variable)
        if lower is not None and upper is None:
            return lower + tf.exp(policy_variable)
        if lower is None and upper is not None:
            return upper - tf.exp(policy_variable)
        return policy_variable