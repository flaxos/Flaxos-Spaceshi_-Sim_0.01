# hybrid/navigation/autopilot/hold.py
"""Hold position/velocity autopilot."""

import logging
from typing import Dict, Optional
from hybrid.navigation.autopilot.base import BaseAutopilot
from hybrid.utils.math_utils import magnitude, subtract_vectors
from hybrid.navigation.relative_motion import vector_to_heading

logger = logging.getLogger(__name__)

class HoldPositionAutopilot(BaseAutopilot):
    """Autopilot to hold current position (station-keeping)."""

    def __init__(self, ship, target_id: Optional[str] = None, params: Dict = None):
        """Initialize hold position autopilot.

        Args:
            ship: Ship under control
            target_id: Unused (holds current position)
            params: Additional parameters:
                - tolerance: Position hold tolerance (m), default 10.0
                - max_thrust: Maximum thrust to use (0-1), default 0.5
        """
        super().__init__(ship, target_id, params)

        # Record initial position to hold
        self.hold_position = dict(ship.position)
        self.tolerance = params.get("tolerance", 10.0)
        self.max_thrust = params.get("max_thrust", 0.5)

        self.status = "active"
        logger.info(f"Hold position engaged at {self.hold_position}")

    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute thrust to maintain position.

        Args:
            dt: Time delta
            sim_time: Current simulation time

        Returns:
            dict: Thrust command or None
        """
        # Calculate drift from hold position
        drift = subtract_vectors(self.hold_position, self.ship.position)
        drift_magnitude = magnitude(drift)

        # Check if within tolerance
        if drift_magnitude < self.tolerance:
            # Close enough - just null velocity
            current_speed = magnitude(self.ship.velocity)

            if current_speed < 0.1:
                self.status = "holding"
                return {
                    "thrust": 0.0,
                    "heading": self.ship.orientation
                }

            # Thrust against velocity to stop drift
            # Reverse velocity vector
            velocity_reversed = {
                "x": -self.ship.velocity["x"],
                "y": -self.ship.velocity["y"],
                "z": -self.ship.velocity["z"]
            }

            desired_heading = vector_to_heading(velocity_reversed)
            thrust = min(self.max_thrust, current_speed / 10.0)  # Proportional to speed

            logger.debug(f"Hold: Nulling velocity {current_speed:.2f} m/s")

            return {
                "thrust": self._clamp_thrust(thrust),
                "heading": desired_heading
            }

        # Drifted too far - thrust back toward hold position
        self.status = "correcting"

        desired_heading = vector_to_heading(drift)

        # Thrust proportional to drift
        thrust = min(self.max_thrust, drift_magnitude / 100.0)

        logger.debug(f"Hold: Correcting drift {drift_magnitude:.1f}m, thrust={thrust:.2f}")

        return {
            "thrust": self._clamp_thrust(thrust),
            "heading": desired_heading
        }

    def get_state(self) -> Dict:
        """Get hold position state.

        Returns:
            dict: State with drift info
        """
        state = super().get_state()
        state["hold_position"] = self.hold_position
        state["tolerance"] = self.tolerance

        drift = subtract_vectors(self.hold_position, self.ship.position)
        state["drift"] = magnitude(drift)

        return state


class HoldVelocityAutopilot(BaseAutopilot):
    """Autopilot to hold current velocity (cruise control)."""

    def __init__(self, ship, target_id: Optional[str] = None, params: Dict = None):
        """Initialize hold velocity autopilot.

        Args:
            ship: Ship under control
            target_id: Unused
            params: Additional parameters:
                - tolerance: Velocity tolerance (m/s), default 0.5
                - max_thrust: Maximum thrust to use (0-1), default 0.5
        """
        super().__init__(ship, target_id, params)

        # Record initial velocity to hold
        self.hold_velocity = dict(ship.velocity)
        self.tolerance = params.get("tolerance", 0.5)
        self.max_thrust = params.get("max_thrust", 0.5)

        self.status = "active"
        logger.info(f"Hold velocity engaged: {magnitude(self.hold_velocity):.1f} m/s")

    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute thrust to maintain velocity.

        Args:
            dt: Time delta
            sim_time: Current simulation time

        Returns:
            dict: Thrust command or None
        """
        # Calculate velocity error
        velocity_error = subtract_vectors(self.hold_velocity, self.ship.velocity)
        error_magnitude = magnitude(velocity_error)

        # Check if within tolerance
        if error_magnitude < self.tolerance:
            self.status = "holding"
            return {
                "thrust": 0.0,
                "heading": self.ship.orientation
            }

        # Thrust to correct velocity error
        self.status = "correcting"

        desired_heading = vector_to_heading(velocity_error)
        thrust = min(self.max_thrust, error_magnitude / 10.0)

        logger.debug(f"Hold velocity: Error {error_magnitude:.2f} m/s")

        return {
            "thrust": self._clamp_thrust(thrust),
            "heading": desired_heading
        }

    def get_state(self) -> Dict:
        """Get hold velocity state.

        Returns:
            dict: State with velocity error
        """
        state = super().get_state()
        state["hold_velocity"] = self.hold_velocity
        state["tolerance"] = self.tolerance

        velocity_error = subtract_vectors(self.hold_velocity, self.ship.velocity)
        state["velocity_error"] = magnitude(velocity_error)

        return state
