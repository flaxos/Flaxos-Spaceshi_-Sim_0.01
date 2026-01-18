# hybrid/navigation/autopilot/intercept.py
"""Intercept autopilot - intercepts moving target using lead pursuit."""

import logging
from typing import Dict, Optional
from hybrid.navigation.autopilot.base import BaseAutopilot
from hybrid.navigation.autopilot.match_velocity import MatchVelocityAutopilot
from hybrid.navigation.relative_motion import (
    calculate_relative_motion, calculate_intercept_time,
    calculate_intercept_point, vector_to_heading, predict_position
)
from hybrid.utils.math_utils import subtract_vectors, magnitude

logger = logging.getLogger(__name__)

class InterceptAutopilot(BaseAutopilot):
    """Autopilot for intercepting a moving target using proportional navigation."""

    # Phase transition thresholds
    APPROACH_RANGE = 10000  # Switch to approach at 10km
    MATCH_RANGE = 1000  # Switch to match velocity at 1km
    MAX_APPROACH_SPEED = 100  # m/s

    def __init__(self, ship, target_id: Optional[str] = None, params: Dict = None):
        """Initialize intercept autopilot.

        Args:
            ship: Ship under control
            target_id: Target to intercept
            params: Additional parameters:
                - approach_speed: Desired approach speed (m/s), default 100
                - match_range: Range to switch to velocity matching (m), default 1000
                - max_thrust: Maximum thrust to use (0-1), default 1.0
        """
        super().__init__(ship, target_id, params)

        self.desired_approach_speed = params.get("approach_speed", self.MAX_APPROACH_SPEED)
        self.match_range = params.get("match_range", self.MATCH_RANGE)
        self.max_thrust = params.get("max_thrust", 1.0)

        self.phase = "intercept"  # "intercept", "approach", "match"
        self.match_velocity_ap = None  # For final phase

        self.status = "active"

        if not target_id:
            self.status = "error"
            self.error_message = "No target specified for intercept"

    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute intercept course.

        Three-phase approach:
        1. Intercept: Lead pursuit to intercept point
        2. Approach: Direct pursuit with speed management
        3. Match: Match velocity with target

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
            logger.warning(f"Intercept: Target {self.target_id} not in sensor contacts")
            return None

        # Calculate relative motion
        rel_motion = calculate_relative_motion(self.ship, target)

        # Phase transitions
        current_range = rel_motion["range"]
        closing_speed = -rel_motion["range_rate"] if rel_motion["closing"] else 0

        # Transition logic
        if current_range < self.match_range and abs(closing_speed) < 50:
            if self.phase != "match":
                logger.info(f"Intercept: Switching to MATCH phase at {current_range:.0f}m")
                self.phase = "match"
                # Initialize match velocity autopilot
                self.match_velocity_ap = MatchVelocityAutopilot(
                    self.ship,
                    self.target_id,
                    {"tolerance": 1.0, "max_thrust": self.max_thrust}
                )
        elif current_range < self.APPROACH_RANGE:
            if self.phase == "intercept":
                logger.info(f"Intercept: Switching to APPROACH phase at {current_range:.0f}m")
                self.phase = "approach"

        # Execute phase-specific logic
        if self.phase == "match":
            self.status = "matching"
            return self._compute_match_phase(target, dt, sim_time)
        elif self.phase == "approach":
            self.status = "approaching"
            return self._compute_approach_phase(target, rel_motion)
        else:  # intercept
            self.status = "intercepting"
            return self._compute_intercept_phase(target, rel_motion)

    def _compute_intercept_phase(self, target, rel_motion: Dict) -> Dict:
        """Compute intercept using lead pursuit.

        Args:
            target: Target object
            rel_motion: Relative motion data

        Returns:
            dict: Thrust command
        """
        # Estimate intercept time
        intercept_time = calculate_intercept_time(self.ship, target)

        if intercept_time and intercept_time > 0:
            # Predict intercept point
            intercept_point = calculate_intercept_point(self.ship, target, intercept_time)

            # Aim at intercept point
            vector_to_intercept = subtract_vectors(intercept_point, self.ship.position)
            desired_heading = vector_to_heading(vector_to_intercept)

            # Full thrust during intercept
            thrust = self.max_thrust

            logger.debug(
                f"Intercept (lead): T-{intercept_time:.0f}s, "
                f"range={rel_motion['range']:.0f}m, "
                f"heading=Y:{desired_heading['yaw']:.1f}°"
            )
        else:
            # Can't calculate intercept, use direct pursuit
            vector_to_target = subtract_vectors(
                target.position if hasattr(target, 'position') else target,
                self.ship.position
            )
            desired_heading = vector_to_heading(vector_to_target)
            thrust = self.max_thrust

            logger.debug(f"Intercept (direct): range={rel_motion['range']:.0f}m")

        return {
            "thrust": thrust,
            "heading": desired_heading
        }

    def _compute_approach_phase(self, target, rel_motion: Dict) -> Dict:
        """Compute approach with speed management.

        Args:
            target: Target object
            rel_motion: Relative motion data

        Returns:
            dict: Thrust command
        """
        # Direct pursuit to target
        vector_to_target = subtract_vectors(
            target.position if hasattr(target, 'position') else target,
            self.ship.position
        )
        desired_heading = vector_to_heading(vector_to_target)

        # Speed management: don't close too fast
        closing_speed = -rel_motion["range_rate"] if rel_motion["closing"] else 0

        if closing_speed > self.desired_approach_speed:
            # Closing too fast - reduce thrust
            thrust = 0.0
            logger.debug(f"Approach: Coasting (closing speed {closing_speed:.1f} m/s)")
        elif closing_speed < self.desired_approach_speed * 0.5:
            # Too slow - increase thrust
            thrust = self.max_thrust
            logger.debug(f"Approach: Accelerating (closing speed {closing_speed:.1f} m/s)")
        else:
            # Moderate thrust to maintain speed
            thrust = 0.5 * self.max_thrust

        return {
            "thrust": self._clamp_thrust(thrust),
            "heading": desired_heading
        }

    def _compute_match_phase(self, target, dt: float, sim_time: float) -> Dict:
        """Delegate to match velocity autopilot.

        Args:
            target: Target object
            dt: Time delta
            sim_time: Simulation time

        Returns:
            dict: Thrust command
        """
        if not self.match_velocity_ap:
            self.match_velocity_ap = MatchVelocityAutopilot(
                self.ship,
                self.target_id,
                {"tolerance": 1.0, "max_thrust": self.max_thrust}
            )

        return self.match_velocity_ap.compute(dt, sim_time)

    def get_state(self) -> Dict:
        """Get intercept autopilot state.

        Returns:
            dict: State with phase info
        """
        state = super().get_state()
        state["phase"] = self.phase
        state["desired_approach_speed"] = self.desired_approach_speed

        target = self.get_target()
        if target:
            rel_motion = calculate_relative_motion(self.ship, target)
            state["range"] = rel_motion["range"]
            state["closing_speed"] = -rel_motion["range_rate"] if rel_motion["closing"] else 0

        return state
