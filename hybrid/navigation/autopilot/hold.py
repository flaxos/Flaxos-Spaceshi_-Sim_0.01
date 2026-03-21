# hybrid/navigation/autopilot/hold.py
"""Hold position/velocity autopilot."""

import logging
import math
from typing import Dict, Optional
from hybrid.navigation.autopilot.base import BaseAutopilot
from hybrid.utils.math_utils import magnitude, subtract_vectors
from hybrid.navigation.relative_motion import vector_to_heading

logger = logging.getLogger(__name__)

# --- Deadband thresholds ---
# Below these values the ship is considered "stopped" or "on station".
# Prevents thruster chatter from floating-point drift or sub-meter oscillation.
_VELOCITY_DEADBAND = 0.5      # m/s — below this, velocity is "zero"
_POSITION_DEADBAND = 50.0     # m — below this, position is "on station"

# Alignment guard constants — same thresholds used by rendezvous autopilot.
# Thrust acts along the ship's physical nose, so firing while misaligned
# pushes the ship off-course.  Cosine scaling is physically correct (force
# projection onto the desired axis).
_GUARD_DEADZONE_DEG = 5.0     # Below this, no cosine scaling
_GUARD_CUTOFF_DEG = 90.0      # Above this, zero thrust


class HoldPositionAutopilot(BaseAutopilot):
    """Autopilot to hold current position (station-keeping).

    Two-phase approach:
      1. DECEL — kill all velocity with a retrograde burn.
      2. HOLD  — maintain position with small correction burns.

    Phase 1 always takes priority.  If the ship is engaged at 500 m/s
    it will burn retrograde until speed drops below the velocity deadband
    before it even looks at positional drift.  This prevents the old bug
    where the autopilot aimed at the hold point while still carrying
    enormous velocity, producing an endless spiral.
    """

    def __init__(self, ship, target_id: Optional[str] = None, params: Dict = None):
        """Initialize hold position autopilot.

        Args:
            ship: Ship under control
            target_id: Unused (holds current position)
            params: Additional parameters:
                - tolerance: Position hold tolerance (m), default 50.0
                - velocity_tolerance: Speed tolerance (m/s), default 0.5
                - max_thrust: Maximum thrust to use (0-1), default 1.0
        """
        super().__init__(ship, target_id, params)

        # Record initial position to hold
        self.hold_position = dict(ship.position)
        self.tolerance = params.get("tolerance", _POSITION_DEADBAND)
        self.velocity_tolerance = params.get("velocity_tolerance", _VELOCITY_DEADBAND)
        self.max_thrust = params.get("max_thrust", 1.0)

        self.status = "decelerating"
        logger.info(f"Hold position engaged at {self.hold_position}")

    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute thrust to decelerate then maintain position.

        Priority order:
          1. If speed > deadband → burn retrograde (decel phase).
          2. If position drift > tolerance → correct back toward hold point,
             but blend in a braking component so we don't overshoot.
          3. Otherwise → thrust zero, hold station.

        Args:
            dt: Time delta
            sim_time: Current simulation time

        Returns:
            dict: Thrust command {thrust, heading}
        """
        current_speed = magnitude(self.ship.velocity)
        drift = subtract_vectors(self.hold_position, self.ship.position)
        drift_magnitude = magnitude(drift)

        # ----- Phase 1: Kill velocity -----
        # This fires whenever the ship has meaningful velocity, regardless
        # of position.  Without this the old code would aim at the hold
        # point while still doing hundreds of m/s and never converge.
        if current_speed > self.velocity_tolerance:
            # Pure retrograde burn — point opposite to velocity vector.
            retro = {
                "x": -self.ship.velocity["x"],
                "y": -self.ship.velocity["y"],
                "z": -self.ship.velocity["z"],
            }
            desired_heading = vector_to_heading(retro)

            # Proportional thrust: full power when fast, gentle when slow.
            # The divisor (10 m/s) means we reach max_thrust at 10 m/s and
            # taper linearly below that to avoid overshoot.
            thrust = min(self.max_thrust, current_speed / 10.0)

            # If we're also drifting away from the hold point AND our
            # velocity is carrying us further away, use full thrust — no
            # reason to be gentle when we're both fast and diverging.
            if drift_magnitude > self.tolerance:
                thrust = self.max_thrust

            self.status = "decelerating"
            logger.debug(
                "Hold: Decelerating — speed %.1f m/s, drift %.0f m, thrust %.2f",
                current_speed, drift_magnitude, thrust,
            )
            cmd = {
                "thrust": self._clamp_thrust(thrust),
                "heading": desired_heading,
            }
            # Alignment guard: don't fire main drive while pointed wrong
            if cmd["thrust"] > 0:
                heading_err = self._heading_error(cmd["heading"])
                if heading_err > _GUARD_CUTOFF_DEG:
                    cmd["thrust"] = 0.0
                elif heading_err > _GUARD_DEADZONE_DEG:
                    cmd["thrust"] *= max(0.0, math.cos(math.radians(heading_err)))
            return cmd

        # ----- Phase 2: Correct positional drift -----
        if drift_magnitude > self.tolerance:
            self.status = "correcting"

            desired_heading = vector_to_heading(drift)

            # Gentle proportional thrust — we're nearly stopped, so a
            # small nudge goes a long way.  Cap relative to drift so we
            # don't slam back and oscillate.
            thrust = min(self.max_thrust, drift_magnitude / 500.0)
            # Floor at a tiny value so we actually move
            thrust = max(0.02, thrust)

            logger.debug(
                "Hold: Correcting drift %.1f m, thrust %.2f",
                drift_magnitude, thrust,
            )
            cmd = {
                "thrust": self._clamp_thrust(thrust),
                "heading": desired_heading,
            }
            # Alignment guard: don't fire main drive while pointed wrong
            if cmd["thrust"] > 0:
                heading_err = self._heading_error(cmd["heading"])
                if heading_err > _GUARD_CUTOFF_DEG:
                    cmd["thrust"] = 0.0
                elif heading_err > _GUARD_DEADZONE_DEG:
                    cmd["thrust"] *= max(0.0, math.cos(math.radians(heading_err)))
            return cmd

        # ----- Phase 3: On station -----
        self.status = "holding"
        return {
            "thrust": 0.0,
            "heading": self.ship.orientation,
        }

    def _heading_error(self, desired_heading: Optional[Dict]) -> float:
        """Angular error between ship orientation and desired heading.

        Returns max of yaw and pitch error -- thrust acts along the nose,
        so any axis being misaligned sends force off-course.
        """
        if desired_heading is None:
            return 0.0
        cur = self.ship.orientation
        yaw_err = abs(self._normalize_angle(
            desired_heading.get("yaw", 0) - cur.get("yaw", 0)))
        pitch_err = abs(self._normalize_angle(
            desired_heading.get("pitch", 0) - cur.get("pitch", 0)))
        return max(yaw_err, pitch_err)

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

        cmd = {
            "thrust": self._clamp_thrust(thrust),
            "heading": desired_heading
        }
        # Alignment guard: don't fire main drive while pointed wrong
        if cmd["thrust"] > 0:
            heading_err = self._heading_error(cmd["heading"])
            if heading_err > _GUARD_CUTOFF_DEG:
                cmd["thrust"] = 0.0
            elif heading_err > _GUARD_DEADZONE_DEG:
                cmd["thrust"] *= max(0.0, math.cos(math.radians(heading_err)))
        return cmd

    def _heading_error(self, desired_heading: Optional[Dict]) -> float:
        """Angular error between ship orientation and desired heading.

        Returns max of yaw and pitch error -- thrust acts along the nose,
        so any axis being misaligned sends force off-course.
        """
        if desired_heading is None:
            return 0.0
        cur = self.ship.orientation
        yaw_err = abs(self._normalize_angle(
            desired_heading.get("yaw", 0) - cur.get("yaw", 0)))
        pitch_err = abs(self._normalize_angle(
            desired_heading.get("pitch", 0) - cur.get("pitch", 0)))
        return max(yaw_err, pitch_err)

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
