# hybrid/navigation/autopilot/hold.py
"""Hold position/velocity autopilot.

HoldPositionAutopilot uses the proven flip-then-brake pattern from
AllStopAutopilot for its deceleration phase:

  1. FLIP -- snapshot retrograde heading, zero thrust while RCS rotates.
  2. BRAKE -- main drive with alignment guard until speed < 5 m/s.
  3. ZERO -- feather thrust / snap velocity to zero at very low speed.
  4. CORRECT -- nudge back toward hold point if drifted.
  5. HOLD -- on station, zero thrust.

The old code fired thrust while simultaneously commanding a retrograde
heading, but the alignment guard (correctly) blocked most of that
thrust because the ship hadn't finished rotating yet.  This created a
limit cycle at ~10 m/s where the guard reduced effective deceleration
to near zero.  The fix: separate the rotation (FLIP, zero thrust)
from the burn (BRAKE, alignment-guarded thrust).
"""

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
_VELOCITY_DEADBAND = 0.5      # m/s -- below this, velocity is "zero"
_POSITION_DEADBAND = 50.0     # m -- below this, position is "on station"

# Alignment guard constants -- same thresholds used by rendezvous autopilot.
# Thrust acts along the ship's physical nose, so firing while misaligned
# pushes the ship off-course.  Cosine scaling is physically correct (force
# projection onto the desired axis).
_GUARD_DEADZONE_DEG = 5.0     # Below this, no cosine scaling
_GUARD_CUTOFF_DEG = 90.0      # Above this, zero thrust

# Phase transition thresholds (same as AllStop)
_FLIP_TOLERANCE_DEG = 10.0    # Heading error below which FLIP -> BRAKE
_BRAKE_SPEED_THRESH = 5.0     # m/s -- below this, BRAKE -> ZERO
_TAPER_SPEED = 50.0           # m/s -- below this, BRAKE tapers thrust
_ZERO_SPEED_THRESH = 1.0      # m/s -- below this, snap velocity to zero

# Speed above which we use the full flip-then-brake pattern.
# Below this, the retrograde heading is unreliable (velocity vector
# drifts faster than the ship can rotate), so we skip FLIP.
_FLIP_SPEED_THRESH = 10.0


class HoldPositionAutopilot(BaseAutopilot):
    """Autopilot to hold current position (station-keeping).

    Three operational modes, selected by current speed:

    High speed (>10 m/s) -- FLIP then BRAKE:
      Snapshot retrograde heading, rotate with zero thrust, then fire
      with alignment guard.  Proven pattern from AllStop that avoids
      the limit cycle caused by simultaneous rotate+thrust.

    Low speed (1-10 m/s) -- direct ZERO:
      Feather thrust tracking live retrograde heading.  At this speed
      the heading barely drifts so live tracking is safe.

    Very low speed (<1 m/s) -- snap to zero:
      Without RCS translation, the main drive can't converge when the
      retrograde heading shifts faster than the ship rotates.  Snap
      velocity to zero (physically: RCS translational thrusters).

    Once stopped, positional drift is corrected with gentle nudges
    toward the hold point, guarded by the same alignment logic.
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

        # Flip-then-brake state.  _decel_aligned tracks whether the ship
        # has completed the FLIP rotation.  Reset when re-entering decel
        # from correction/hold phases.
        self._decel_aligned: bool = False
        self._flip_heading_snapshot: Optional[Dict] = None

        self.status = "decelerating"
        logger.info(f"Hold position engaged at {self.hold_position}")

    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute thrust to decelerate then maintain position.

        Priority order:
          1. If speed > deadband -> decelerate (flip-then-brake pattern).
          2. If position drift > tolerance -> correct back toward hold point.
          3. Otherwise -> thrust zero, hold station.

        Args:
            dt: Time delta
            sim_time: Current simulation time

        Returns:
            dict: Thrust command {thrust, heading}
        """
        current_speed = magnitude(self.ship.velocity)
        drift = subtract_vectors(self.hold_position, self.ship.position)
        drift_magnitude = magnitude(drift)

        # ----- Phase 1: Kill velocity (flip-then-brake) -----
        if current_speed > self.velocity_tolerance:
            return self._compute_decel(current_speed, drift_magnitude)

        # Velocity is below deadband -- clear flip state so next time
        # we enter decel (e.g. after a correction burn builds speed)
        # we start fresh with a new FLIP.
        self._decel_aligned = False
        self._flip_heading_snapshot = None

        # ----- Phase 2: Correct positional drift -----
        if drift_magnitude > self.tolerance:
            return self._compute_correction(drift, drift_magnitude)

        # ----- Phase 3: On station -----
        self.status = "holding"
        return {
            "thrust": 0.0,
            "heading": self.ship.orientation,
        }

    def _compute_decel(self, speed: float, drift_magnitude: float) -> Dict:
        """Deceleration using flip-then-brake pattern.

        At high speed (>10 m/s): snapshot retrograde heading, rotate with
        zero thrust (FLIP), then fire with alignment guard (BRAKE).

        At low speed (1-10 m/s): skip FLIP, use live retrograde + feathered
        thrust (ZERO pattern).

        At very low speed (<1 m/s): snap velocity to zero (RCS proxy).
        """
        # Very low speed: snap to zero -- main drive can't converge here
        # because the retrograde heading shifts faster than the ship rotates.
        if speed < _ZERO_SPEED_THRESH:
            self.ship.velocity = {"x": 0.0, "y": 0.0, "z": 0.0}
            self._decel_aligned = False
            self._flip_heading_snapshot = None
            self.status = "holding"
            logger.debug("Hold: velocity snapped to zero at %.2f m/s", speed)
            return {"thrust": 0.0, "heading": self.ship.orientation}

        # Low speed (1-10 m/s): skip FLIP, use live retrograde + feathered
        # thrust.  At this speed the heading barely drifts.
        if speed < _FLIP_SPEED_THRESH:
            return self._compute_zero_phase(speed)

        # High speed (>10 m/s): flip-then-brake pattern.
        if not self._decel_aligned:
            return self._compute_flip(speed)
        else:
            return self._compute_brake(speed, drift_magnitude)

    def _compute_flip(self, speed: float) -> Dict:
        """FLIP sub-phase: rotate to retrograde with zero thrust.

        Snapshot the retrograde heading at entry so RCS doesn't chase a
        drifting velocity vector during rotation.
        """
        if self._flip_heading_snapshot is None:
            self._flip_heading_snapshot = self._retrograde_heading()
            logger.info(
                "Hold: entering FLIP, speed=%.1f m/s, heading snapshot taken",
                speed,
            )

        heading = self._flip_heading_snapshot
        heading_err = self._heading_error(heading)

        if heading_err < _FLIP_TOLERANCE_DEG:
            # Flip complete -- transition to BRAKE
            self._decel_aligned = True
            self.status = "braking"
            logger.info(
                "Hold: FLIP complete, heading_err=%.1f deg -> BRAKE", heading_err,
            )
            # Fall through to brake on next tick; this tick still zero thrust
            # to avoid a single frame of unguarded thrust.

        self.status = "flipping"
        return {"thrust": 0.0, "heading": heading}

    def _compute_brake(self, speed: float, drift_magnitude: float) -> Dict:
        """BRAKE sub-phase: fire retrograde with alignment guard.

        Uses live retrograde heading (safe post-flip because the heading
        error is small and the guard handles any residual misalignment).
        Proportional taper below _TAPER_SPEED prevents overshoot.
        """
        if speed < _BRAKE_SPEED_THRESH:
            # Transition to ZERO phase for fine convergence
            self._decel_aligned = False
            self._flip_heading_snapshot = None
            return self._compute_zero_phase(speed)

        heading = self._retrograde_heading()
        throttle = self.max_thrust

        # Proportional taper below _TAPER_SPEED
        if speed < _TAPER_SPEED:
            throttle *= speed / _TAPER_SPEED

        # If also drifting away from hold point, use full thrust
        if drift_magnitude > self.tolerance:
            throttle = self.max_thrust

        throttle = self._clamp_thrust(throttle)

        # Alignment guard
        heading_err = self._heading_error(heading)
        if heading_err > _GUARD_CUTOFF_DEG:
            throttle = 0.0
        elif heading_err > _GUARD_DEADZONE_DEG:
            throttle *= max(0.0, math.cos(math.radians(heading_err)))

        self.status = f"braking {speed:.0f} m/s"
        logger.debug(
            "Hold: BRAKE -- speed=%.1f m/s, heading_err=%.1f, throttle=%.3f",
            speed, heading_err, throttle,
        )
        return {"thrust": throttle, "heading": heading}

    def _compute_zero_phase(self, speed: float) -> Dict:
        """ZERO sub-phase: feather thrust to null residual velocity.

        Uses live retrograde heading (safe at <10 m/s) with alignment
        guard.  At <1 m/s, snaps velocity to zero.
        """
        if speed < _ZERO_SPEED_THRESH:
            self.ship.velocity = {"x": 0.0, "y": 0.0, "z": 0.0}
            self._decel_aligned = False
            self._flip_heading_snapshot = None
            self.status = "holding"
            logger.debug("Hold: ZERO -> stopped (%.2f m/s zeroed)", speed)
            return {"thrust": 0.0, "heading": self.ship.orientation}

        heading = self._retrograde_heading()

        # Tiny proportional throttle
        frac = speed / _BRAKE_SPEED_THRESH
        throttle = 0.01 + frac * 0.04  # 0.01 .. 0.05
        throttle = self._clamp_thrust(throttle)

        # Alignment guard
        heading_err = self._heading_error(heading)
        if heading_err > _GUARD_CUTOFF_DEG:
            throttle = 0.0
        elif heading_err > _GUARD_DEADZONE_DEG:
            throttle *= max(0.0, math.cos(math.radians(heading_err)))

        self.status = f"zeroing {speed:.1f} m/s"
        return {"thrust": throttle, "heading": heading}

    def _compute_correction(self, drift: Dict, drift_magnitude: float) -> Dict:
        """Correct positional drift with gentle nudge toward hold point.

        Uses alignment guard to prevent firing while misaligned.
        """
        self.status = "correcting"
        desired_heading = vector_to_heading(drift)

        # Gentle proportional thrust -- we're nearly stopped, so a
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
        # Alignment guard
        if cmd["thrust"] > 0:
            heading_err = self._heading_error(cmd["heading"])
            if heading_err > _GUARD_CUTOFF_DEG:
                cmd["thrust"] = 0.0
            elif heading_err > _GUARD_DEADZONE_DEG:
                cmd["thrust"] *= max(0.0, math.cos(math.radians(heading_err)))
        return cmd

    def _retrograde_heading(self) -> Dict:
        """Heading that opposes the ship's velocity vector.

        Returns current orientation if velocity is near-zero.
        """
        vel = self.ship.velocity
        retro = {"x": -vel["x"], "y": -vel["y"], "z": -vel["z"]}
        if magnitude(retro) < 0.01:
            return self.ship.orientation
        heading = vector_to_heading(retro)
        return {
            "yaw": heading.get("yaw", 0),
            "pitch": heading.get("pitch", 0),
            "roll": self.ship.orientation.get("roll", 0),
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
        state["status_text"] = self.status

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
