# hybrid/navigation/autopilot/all_stop.py
"""All-stop autopilot - decelerates ship to zero velocity.

Phases:
    CUT -> FLIP -> BRAKE -> ZERO -> HOLD

Follows the proven rendezvous pattern:
  - CUT zeroes throttle immediately (1 tick).
  - FLIP rotates to a *snapshot* of the retrograde heading so RCS doesn't
    chase a drifting velocity vector.
  - BRAKE fires main drive with cosine-scaled alignment guard until speed
    drops below 5 m/s.
  - ZERO feathers thrust to null out remaining drift, tracking the live
    retrograde heading (safe because heading changes are tiny at <5 m/s).
  - HOLD sits at zero thrust once speed is below 0.1 m/s.

No target is required -- the ship decelerates against its own velocity.
"""

import logging
import math
from typing import Dict, Optional

from hybrid.navigation.autopilot.base import BaseAutopilot
from hybrid.navigation.relative_motion import vector_to_heading
from hybrid.utils.math_utils import magnitude

logger = logging.getLogger(__name__)

# Phase transition thresholds
_FLIP_TOLERANCE_DEG = 10.0   # Heading error below which FLIP -> BRAKE
_BRAKE_SPEED_THRESH = 5.0    # m/s -- below this, BRAKE -> ZERO
_ZERO_SPEED_THRESH = 0.1     # m/s -- below this, ZERO -> HOLD
_TAPER_SPEED = 50.0           # m/s -- below this, BRAKE tapers thrust

# Alignment guard constants (same as rendezvous)
_GUARD_DEADZONE_DEG = 5.0    # Below this, no cosine scaling
_GUARD_CUTOFF_DEG = 90.0     # Above this, zero thrust

# ZERO phase throttle range
_ZERO_MIN_THROTTLE = 0.01
_ZERO_MAX_THROTTLE = 0.05


class AllStopAutopilot(BaseAutopilot):
    """Decelerates the ship to zero velocity (all-stop).

    Unlike rendezvous or intercept, this autopilot has no target -- it simply
    kills whatever velocity the ship currently carries.  The g_level parameter
    controls braking intensity (default 1G).
    """

    def __init__(self, ship, target_id: Optional[str] = None, params: Dict = None):
        """Initialize all-stop autopilot.

        Args:
            ship: Ship under control.
            target_id: Unused (no target for all-stop).
            params: Optional parameters:
                - g_level (float): Desired braking G-force, default 1.0.
        """
        params = params or {}
        super().__init__(ship, target_id, params)

        self.g_level: float = float(params.get("g_level", 1.0))
        self.phase: str = "cut"
        self.status = "ALL STOP initiated"

        # Snapshot heading set at FLIP entry -- prevents RCS from chasing
        # a drifting velocity vector during rotation.
        self._flip_heading_snapshot: Optional[Dict] = None

        logger.info(
            "AllStop engaged: speed=%.1f m/s, g_level=%.1f",
            magnitude(ship.velocity), self.g_level,
        )

    # ----- main loop ----------------------------------------------------------

    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute thrust command for this tick.

        Args:
            dt: Time delta (seconds).
            sim_time: Current simulation time.

        Returns:
            dict with {thrust, heading} or None.
        """
        speed = magnitude(self.ship.velocity)

        if self.phase == "cut":
            return self._compute_cut(speed)
        elif self.phase == "flip":
            return self._compute_flip(speed)
        elif self.phase == "brake":
            return self._compute_brake(speed)
        elif self.phase == "zero":
            return self._compute_zero(speed)
        elif self.phase == "hold":
            return self._compute_hold()

        # Fallback -- should never happen
        logger.error("AllStop: unknown phase '%s', zeroing thrust", self.phase)
        return {"thrust": 0.0, "heading": self.ship.orientation}

    # ----- phase implementations ----------------------------------------------

    def _compute_cut(self, speed: float) -> Dict:
        """CUT phase: zero throttle immediately, transition to FLIP."""
        # If already nearly stopped, skip straight to HOLD
        if speed < _ZERO_SPEED_THRESH:
            self.phase = "hold"
            self.status = "ALL STOP"
            logger.info("AllStop: speed already < %.1f m/s, going to HOLD", _ZERO_SPEED_THRESH)
            return {"thrust": 0.0, "heading": self.ship.orientation}

        # At low speed, skip FLIP and go straight to ZERO.  The FLIP
        # phase snapshot heading is unreliable at <10 m/s because the
        # velocity vector drifts significantly during rotation.  ZERO
        # uses live retrograde + alignment guard which handles this.
        if speed < _BRAKE_SPEED_THRESH * 2:  # <10 m/s
            self.phase = "zero"
            self.status = "zeroing residual velocity"
            logger.info("AllStop: CUT -> ZERO (low speed %.1f m/s, skipping FLIP)", speed)
            return {"thrust": 0.0, "heading": self._retrograde_heading()}

        self.phase = "flip"
        # Snapshot the retrograde heading at this instant so FLIP doesn't
        # chase a drifting vector while the ship rotates.
        self._flip_heading_snapshot = self._retrograde_heading()
        self.status = "rotating to retrograde"
        logger.info("AllStop: CUT -> FLIP, speed=%.1f m/s", speed)
        return {"thrust": 0.0, "heading": self._flip_heading_snapshot}

    def _compute_flip(self, speed: float) -> Dict:
        """FLIP phase: rotate to retrograde heading, zero thrust."""
        # If speed dropped below threshold while rotating (e.g. external
        # drag or collision), skip to HOLD.
        if speed < _ZERO_SPEED_THRESH:
            self.phase = "hold"
            self.status = "ALL STOP"
            return {"thrust": 0.0, "heading": self.ship.orientation}

        heading = self._flip_heading_snapshot or self._retrograde_heading()
        heading_err = self._heading_error(heading)

        if heading_err < _FLIP_TOLERANCE_DEG:
            self.phase = "brake"
            self.status = "braking"
            logger.info("AllStop: FLIP -> BRAKE, heading_err=%.1f deg", heading_err)

        # Always zero thrust during flip -- only RCS rotates the ship
        return {"thrust": 0.0, "heading": heading}

    def _compute_brake(self, speed: float) -> Dict:
        """BRAKE phase: main drive with alignment guard and proportional thrust."""
        if speed < _BRAKE_SPEED_THRESH:
            self.phase = "zero"
            self.status = "zeroing residual velocity"
            logger.info("AllStop: BRAKE -> ZERO, speed=%.1f m/s", speed)
            return {"thrust": 0.0, "heading": self._retrograde_heading()}

        heading = self._retrograde_heading()
        throttle = self._g_level_throttle()

        # Proportional taper below _TAPER_SPEED so we don't overshoot
        # into negative velocity and start oscillating.
        if speed < _TAPER_SPEED:
            throttle *= speed / _TAPER_SPEED

        throttle = self._clamp_thrust(throttle)

        # Alignment guard: cosine-scale thrust when misaligned, zero when
        # severely off-axis.  Prevents the drive from pushing the ship
        # sideways (or forward!) when the nose hasn't caught up to the
        # commanded retrograde heading.
        heading_err = self._heading_error(heading)
        if heading_err > _GUARD_CUTOFF_DEG:
            throttle = 0.0
        elif heading_err > _GUARD_DEADZONE_DEG:
            throttle *= max(0.0, math.cos(math.radians(heading_err)))

        self.status = f"braking {speed:.0f} m/s"
        return {"thrust": throttle, "heading": heading}

    def _compute_zero(self, speed: float) -> Dict:
        """ZERO phase: feather thrust to null out residual velocity."""
        if speed < _ZERO_SPEED_THRESH:
            self.phase = "hold"
            self.status = "ALL STOP"
            logger.info("AllStop: ZERO -> HOLD, speed=%.3f m/s", speed)
            return {"thrust": 0.0, "heading": self.ship.orientation}

        # At very low speed (<1 m/s), the alignment guard limit cycle
        # prevents convergence — the retrograde heading shifts faster
        # than the ship can rotate.  In reality, RCS translational
        # thrusters would handle this.  Since we don't have RCS
        # translation, zero the velocity directly.  At 1 m/s = 60 m/min
        # this is negligible drift for gameplay purposes.
        if speed < 1.0:
            self.ship.velocity = {"x": 0.0, "y": 0.0, "z": 0.0}
            self.phase = "hold"
            self.status = "ALL STOP"
            logger.info("AllStop: ZERO -> HOLD (RCS zeroed at %.2f m/s)", speed)
            return {"thrust": 0.0, "heading": self.ship.orientation}

        # At <5 m/s the velocity vector barely drifts, so tracking the
        # live retrograde heading is safe and avoids a stale snapshot
        # pointing the wrong way after the velocity vector rotated.
        heading = self._retrograde_heading()

        # Tiny throttle proportional to remaining speed
        frac = speed / _BRAKE_SPEED_THRESH  # 0..1 over 0..5 m/s
        throttle = _ZERO_MIN_THROTTLE + frac * (_ZERO_MAX_THROTTLE - _ZERO_MIN_THROTTLE)
        throttle = self._clamp_thrust(throttle)

        # Alignment guard — critical at low speed where the retrograde
        # heading can be noisy.  Without this, thrust fires in a random
        # direction and the ship accelerates instead of stopping.
        heading_err = self._heading_error(heading)
        if heading_err > _GUARD_CUTOFF_DEG:
            throttle = 0.0
        elif heading_err > _GUARD_DEADZONE_DEG:
            throttle *= max(0.0, math.cos(math.radians(heading_err)))

        self.status = f"zeroing {speed:.1f} m/s"
        return {"thrust": throttle, "heading": heading}

    def _compute_hold(self) -> Dict:
        """HOLD phase: zero thrust, velocity is negligible."""
        # Ensure velocity stays zeroed while in hold — without RCS
        # translation, there's no physical mechanism to correct sub-m/s
        # drift, so we snap to zero each tick.
        speed = magnitude(self.ship.velocity)
        if speed > 0.01:
            self.ship.velocity = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.status = "ALL STOP"
        return {"thrust": 0.0, "heading": self.ship.orientation}

    # ----- state reporting ----------------------------------------------------

    def get_state(self) -> Dict:
        """Get autopilot state for telemetry.

        Returns:
            dict with phase, speed, g_level, time_to_stop estimate, status_text.
        """
        state = super().get_state()
        speed = magnitude(self.ship.velocity)
        accel = self.g_level * 9.81

        state.update({
            "phase": self.phase,
            "speed": round(speed, 2),
            "g_level": self.g_level,
            "time_to_stop": round(speed / accel, 1) if accel > 0 else 0.0,
            "status_text": self.status,
        })
        return state

    # ----- helpers ------------------------------------------------------------

    def _retrograde_heading(self) -> Dict:
        """Heading that opposes the ship's absolute velocity.

        Unlike rendezvous (which uses relative velocity to a target), all-stop
        uses the ship's own velocity vector.  Pointing along -velocity is
        retrograde; firing the drive in that direction decelerates.
        """
        vel = self.ship.velocity
        retro = {"x": -vel["x"], "y": -vel["y"], "z": -vel["z"]}
        if magnitude(retro) < 0.01:
            # Essentially zero velocity -- keep current orientation
            return self.ship.orientation
        heading = vector_to_heading(retro)
        # All-stop uses full 3D retrograde heading (yaw + pitch) because
        # the ship may have significant velocity in all 3 axes.  Unlike
        # rendezvous (which uses yaw-only to avoid sensor noise in Z),
        # all-stop works from the ship's own velocity which is noise-free.
        # Roll is locked to current orientation.
        return {
            "yaw": heading.get("yaw", 0),
            "pitch": heading.get("pitch", 0),
            "roll": self.ship.orientation.get("roll", 0),
        }

    def _heading_error(self, desired_heading: Optional[Dict]) -> float:
        """Angular error between ship orientation and desired heading.

        Returns the max of yaw and pitch error so that ANY axis being
        misaligned triggers the guard.  Thrust acts along the ship's
        physical nose, so even pure pitch misalignment sends thrust
        off-course.

        Args:
            desired_heading: Target heading {yaw, pitch} in degrees,
                             or None (returns 0.0).

        Returns:
            Maximum of absolute yaw and pitch error in degrees.
        """
        if desired_heading is None:
            return 0.0
        cur = self.ship.orientation
        yaw_err = abs(self._normalize_angle(
            desired_heading.get("yaw", 0) - cur.get("yaw", 0)))
        pitch_err = abs(self._normalize_angle(
            desired_heading.get("pitch", 0) - cur.get("pitch", 0)))
        return max(yaw_err, pitch_err)

    def _g_level_throttle(self) -> float:
        """Convert g_level to a throttle fraction (0..1).

        throttle = (g * 9.81 * mass) / max_thrust

        Falls back to 1.0 if propulsion data is unavailable.
        """
        propulsion = self.ship.systems.get("propulsion")
        if propulsion and hasattr(propulsion, "max_thrust") and self.ship.mass > 0:
            max_thrust_n = propulsion.max_thrust
            desired_force = self.g_level * 9.81 * self.ship.mass
            return min(desired_force / max_thrust_n, 1.0)
        # No propulsion data -- use full throttle as safe fallback
        return 1.0
