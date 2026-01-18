# hybrid/navigation/autopilot/match_velocity.py
"""Match velocity autopilot - nulls relative velocity with target."""

import logging
from typing import Dict, Optional
from hybrid.navigation.autopilot.base import BaseAutopilot
from hybrid.navigation.relative_motion import (
    calculate_relative_motion, calculate_required_burn, vector_to_heading
)
from hybrid.utils.math_utils import magnitude

logger = logging.getLogger(__name__)

class MatchVelocityAutopilot(BaseAutopilot):
    """Autopilot to match velocity with target (zero relative velocity)."""

    def __init__(self, ship, target_id: Optional[str] = None, params: Dict = None):
        """Initialize match velocity autopilot.

        Args:
            ship: Ship under control
            target_id: Target to match velocity with
            params: Additional parameters:
                - tolerance: Velocity match tolerance (m/s), default 1.0
                - max_thrust: Maximum thrust to use (0-1), default 1.0
                - deceleration_factor: Safety factor for deceleration, default 0.8
        """
        super().__init__(ship, target_id, params)

        self.tolerance = params.get("tolerance", 1.0)  # m/s
        self.max_thrust = params.get("max_thrust", 1.0)
        self.deceleration_factor = params.get("deceleration_factor", 0.8)

        self.status = "active"

        if not target_id:
            self.status = "error"
            self.error_message = "No target specified for velocity matching"

    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute thrust command to match target velocity.

        Uses PID-style control to null relative velocity.

        Args:
            dt: Time delta
            sim_time: Current simulation time

        Returns:
            dict: Thrust command or None
        """
        # Get target
        target = self.get_target()
        if not target:
            self.status = "error"
            self.error_message = f"Target {self.target_id} not found"
            logger.warning(f"Match velocity: Target {self.target_id} not in sensor contacts")
            return None

        # Calculate relative motion
        rel_motion = calculate_relative_motion(self.ship, target)
        rel_vel = rel_motion["relative_velocity_vector"]
        rel_vel_mag = magnitude(rel_vel)

        # Check if we're matched
        if rel_vel_mag < self.tolerance:
            self.status = "matched"
            logger.debug(f"Velocity matched with {self.target_id}: {rel_vel_mag:.2f} m/s")
            return {
                "thrust": 0.0,
                "heading": self.ship.orientation  # Maintain current heading
            }

        self.status = "matching"

        # Calculate required burn to match velocity
        target_vel = getattr(target, 'velocity', {"x": 0, "y": 0, "z": 0})
        burn_info = calculate_required_burn(self.ship, target_vel)

        # Point toward velocity difference
        desired_heading = vector_to_heading(burn_info["burn_direction"])

        # Calculate thrust magnitude with deceleration planning
        thrust_magnitude = self._calculate_thrust(rel_vel_mag, burn_info.get("duration"))

        logger.debug(
            f"Match velocity {self.target_id}: Δv={rel_vel_mag:.1f} m/s, "
            f"thrust={thrust_magnitude:.2f}, heading=Y:{desired_heading['yaw']:.1f}°"
        )

        return {
            "thrust": thrust_magnitude,
            "heading": desired_heading
        }

    def _calculate_thrust(self, delta_v_remaining: float, burn_duration: Optional[float]) -> float:
        """Calculate appropriate thrust magnitude.

        Args:
            delta_v_remaining: Remaining delta-v to null (m/s)
            burn_duration: Estimated burn duration at full thrust (s)

        Returns:
            float: Thrust magnitude [0, 1]
        """
        # Proportional control: reduce thrust as we get closer
        # Use exponential decay for smooth approach
        if delta_v_remaining < self.tolerance * 2:
            # Very close - minimal thrust
            thrust = 0.1
        elif delta_v_remaining < 10:
            # Close - proportional thrust
            thrust = delta_v_remaining / 10.0
        elif delta_v_remaining < 50:
            # Medium range - ramp up
            thrust = 0.5 + (delta_v_remaining - 10) / 80.0  # 0.5 to 1.0
        else:
            # Far - full thrust
            thrust = self.max_thrust

        # Apply deceleration factor for safety
        thrust *= self.deceleration_factor

        return self._clamp_thrust(thrust)

    def get_state(self) -> Dict:
        """Get match velocity autopilot state.

        Returns:
            dict: State with progress info
        """
        state = super().get_state()

        target = self.get_target()
        if target:
            rel_motion = calculate_relative_motion(self.ship, target)
            state["relative_velocity"] = magnitude(rel_motion["relative_velocity_vector"])
            state["tolerance"] = self.tolerance
            state["matched"] = state["relative_velocity"] < self.tolerance

        return state
