# hybrid/navigation/autopilot/goto_position.py
"""Go-to-position autopilot for set_course navigation.

Phases:
    ACCELERATE -> COAST -> FLIP -> BRAKE -> ZERO -> HOLD

Follows the proven rendezvous/all-stop pattern:
  - ACCELERATE burns toward the target until reaching coast speed or
    the braking trigger distance.
  - COAST drifts unpowered at cruise speed until the braking trigger.
  - FLIP rotates to a *snapshot* of the retrograde heading with zero
    thrust so RCS doesn't chase a drifting velocity vector.
  - BRAKE fires main drive with cosine-scaled alignment guard until
    speed drops below a low threshold.
  - ZERO feathers thrust to null residual drift (like AllStop).
  - HOLD sits at zero thrust once stopped.

The braking trigger accounts for guard-derated acceleration (the
alignment guard blocks ~65% of thrust ticks) AND the coast distance
during the flip, preventing the overshoot oscillation that occurs
when braking distance is computed using theoretical accel.

Supports nav-solution profiles (aggressive / balanced / conservative)
that adjust thrust and braking safety margins.
"""

import logging
import math
from typing import Dict, Optional

from hybrid.navigation.autopilot.base import BaseAutopilot
from hybrid.navigation.relative_motion import vector_to_heading
from hybrid.utils.math_utils import (
    subtract_vectors,
    magnitude,
    normalize_vector,
    dot_product,
)

logger = logging.getLogger(__name__)


# -- Nav solution profiles ---------------------------------------------------

GOTO_PROFILES: Dict[str, Dict] = {
    "aggressive": {
        "max_thrust": 0.50,            # ~5G on a 10G corvette
        "brake_buffer_factor": 1.1,
        "description": "5G combat burn. Fast but crew-punishing.",
        "risk_level": "high",
    },
    "balanced": {
        "max_thrust": 0.30,            # ~3G -- standard military transit
        "brake_buffer_factor": 1.2,
        "description": "3G military transit. Moderate crew fatigue.",
        "risk_level": "medium",
    },
    "conservative": {
        "max_thrust": 0.10,            # ~1G -- comfortable cruise
        "brake_buffer_factor": 1.3,
        "description": "1G cruise. No crew strain, fuel-efficient.",
        "risk_level": "low",
    },
}

# -- Phase transition thresholds ---------------------------------------------

# Alignment guard constants -- same as all_stop and rendezvous.
# Thrust acts along the ship's physical nose, so firing while misaligned
# pushes the ship off-course.
_GUARD_DEADZONE_DEG = 5.0     # Below this, no cosine scaling
_GUARD_CUTOFF_DEG = 90.0      # Above this, zero thrust
_FLIP_TOLERANCE_DEG = 10.0    # Heading error below which FLIP -> BRAKE

# Guard efficiency: the alignment guard blocks ~65% of thrust ticks on
# average during the post-flip transient.  Braking distance must be
# computed with this derated accel, not theoretical, or we overshoot.
_GUARD_EFFICIENCY = 0.35

# BRAKE tapers thrust below this speed to avoid overshoot into oscillation
_TAPER_SPEED = 50.0
# Below this speed, BRAKE -> ZERO for fine convergence
_BRAKE_SPEED_THRESH = 5.0
# Below this speed, ZERO snaps velocity to zero (RCS translation proxy)
_ZERO_SPEED_THRESH = 0.5

# Default flip time estimate when RCS data unavailable
_DEFAULT_FLIP_TIME = 20.0
# Safety factor on flip coast distance
_FLIP_SAFETY_FACTOR = 1.5


class GoToPositionAutopilot(BaseAutopilot):
    """Autopilot that flies to a fixed position and stops there.

    Uses the proven flip-then-brake pattern from AllStopAutopilot:
    the ship rotates to retrograde heading with zero thrust (FLIP),
    then fires the main drive with alignment guard derating (BRAKE).
    Braking distance is computed using guard-derated acceleration
    (theoretical * 0.35) plus flip coast distance, preventing the
    overshoot oscillation caused by naive v^2/(2a).
    """

    PROFILES = GOTO_PROFILES

    PHASE_ACCELERATE = "ACCELERATE"
    PHASE_COAST = "COAST"
    PHASE_FLIP = "FLIP"
    PHASE_BRAKE = "BRAKE"
    PHASE_ZERO = "ZERO"
    PHASE_HOLD = "HOLD"

    def __init__(self, ship, target_id: Optional[str] = None, params: Dict = None):
        """Initialize go-to-position autopilot.

        Args:
            ship: Ship under control
            target_id: Unused (fixed position target)
            params: Additional parameters:
                - profile: "aggressive"|"balanced"|"conservative" (default "balanced")
                - x, y, z: Target coordinates
                - destination: Optional dict {x, y, z}
                - stop: Whether to stop at target (bool, default True)
                - tolerance: Distance tolerance for arrival (m, default 50.0)
                - max_thrust: Maximum thrust fraction (0..1, overrides profile)
                - coast_speed: Speed threshold to coast (m/s, default 50.0)
                - max_speed: Optional max closing speed for non-stop courses
                - brake_buffer: Extra distance before braking (m, overrides profile)
                - arrival_speed_tolerance: Speed tolerance to consider stopped (m/s, default 0.5)
        """
        super().__init__(ship, target_id, params or {})

        # Resolve profile
        self.profile_name: str = self.params.get("profile", "balanced")
        profile = dict(self.PROFILES.get(self.profile_name, self.PROFILES["balanced"]))

        destination = self.params.get("destination") or {
            "x": self.params.get("x"),
            "y": self.params.get("y"),
            "z": self.params.get("z"),
        }

        self.target_position = destination
        self.stop_at_target = bool(self.params.get("stop", True))
        self.tolerance = float(self.params.get("tolerance", 50.0))
        self.max_thrust = float(self.params.get(
            "max_thrust", profile["max_thrust"]))
        self.coast_speed = float(self.params.get("coast_speed", 50.0))
        self.max_speed = self.params.get("max_speed")

        # brake_buffer: if explicitly provided use that, otherwise derive
        # from profile factor * tolerance for a proportional margin.
        if "brake_buffer" in self.params and self.params["brake_buffer"] is not None:
            self.brake_buffer = float(self.params["brake_buffer"])
        else:
            self.brake_buffer = self.tolerance * profile["brake_buffer_factor"]

        self.arrival_speed_tolerance = float(
            self.params.get("arrival_speed_tolerance", 0.5))

        self.phase = self.PHASE_ACCELERATE
        self.completed = False
        self.status = "active"

        # Snapshot heading set at FLIP entry -- prevents RCS from chasing
        # a drifting velocity vector during rotation.
        self._flip_heading_snapshot: Optional[Dict] = None

        if not self._destination_is_valid():
            self.status = "error"
            self.error_message = "No destination specified for set_course"

    def _destination_is_valid(self) -> bool:
        return all(
            key in self.target_position and self.target_position[key] is not None
            for key in ("x", "y", "z")
        )

    def _get_max_accel(self) -> float:
        propulsion = self.ship.systems.get("propulsion")
        if propulsion and hasattr(propulsion, "max_thrust") and self.ship.mass > 0:
            return max(propulsion.max_thrust / self.ship.mass, 0.01)
        return 0.01

    def _get_effective_accel(self) -> float:
        """Profile-limited acceleration for braking calculations.

        Uses the guard efficiency factor (0.35) because the alignment
        guard blocks ~65% of thrust ticks during the post-flip transient.
        All braking distance calcs must use this, not theoretical accel.
        """
        return self._get_max_accel() * self.max_thrust * _GUARD_EFFICIENCY

    def _estimate_flip_time(self) -> float:
        """Estimate how long a 180-degree flip takes using RCS capability.

        Returns:
            Estimated flip duration in seconds.
        """
        rcs = self.ship.systems.get("rcs")
        if rcs and hasattr(rcs, "estimate_rotation_time"):
            return rcs.estimate_rotation_time(180.0, self.ship)
        return _DEFAULT_FLIP_TIME

    def _corrected_braking_distance(self, closing_speed: float) -> float:
        """Braking trigger distance accounting for flip coast and guard derating.

        During the flip the ship cannot brake but still closes at current
        speed.  The braking distance itself uses guard-derated accel (0.35)
        because the alignment guard will block most thrust ticks during the
        post-flip alignment transient.

        Formula:
            d_needed = v^2 / (2 * a_derated)
                     + closing_speed * flip_time * safety_factor
                     + brake_buffer
        """
        a_derated = self._get_effective_accel()
        d_brake = (closing_speed ** 2) / (2.0 * a_derated) if a_derated > 0 else float("inf")
        flip_time = self._estimate_flip_time()
        flip_coast = closing_speed * flip_time * _FLIP_SAFETY_FACTOR
        return d_brake + flip_coast + self.brake_buffer

    def _retrograde_heading(self) -> Dict:
        """Heading that opposes the ship's absolute velocity (yaw-only).

        Yaw-only heading avoids pitch oscillation from the alignment
        guard fighting RCS on two axes simultaneously.  Roll is locked
        to current orientation.
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

    def _apply_guard(self, cmd: Dict) -> Dict:
        """Apply alignment guard to a thrust command.

        Prevents the main drive from firing while the ship's nose
        hasn't caught up to the commanded heading.  Without this,
        thrust fires along the current (stale) orientation, pushing
        the ship off-course -- critical after ZERO/HOLD when the
        ship may still be pointing retrograde.
        """
        if cmd["thrust"] > 0:
            heading_err = self._heading_error(cmd["heading"])
            if heading_err > _GUARD_CUTOFF_DEG:
                cmd["thrust"] = 0.0
            elif heading_err > _GUARD_DEADZONE_DEG:
                cmd["thrust"] *= max(
                    0.0, math.cos(math.radians(heading_err)))
        return cmd

    # ----- main compute -------------------------------------------------------

    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute thrust/heading command for go-to-position."""
        if self.status == "error":
            return None

        vector_to_target = subtract_vectors(self.target_position, self.ship.position)
        distance = magnitude(vector_to_target)
        speed = magnitude(self.ship.velocity)

        # Route to phase-specific handlers for FLIP/BRAKE/ZERO/HOLD
        if self.phase == self.PHASE_FLIP:
            return self._compute_flip(speed, distance)
        if self.phase == self.PHASE_BRAKE:
            return self._compute_brake(speed, distance)
        if self.phase == self.PHASE_ZERO:
            return self._compute_zero(speed, distance)
        if self.phase == self.PHASE_HOLD:
            return self._compute_hold(distance, vector_to_target)

        # ----- Arrival check -----
        if distance <= self.tolerance:
            if self.stop_at_target:
                if speed <= self.arrival_speed_tolerance:
                    self.phase = self.PHASE_HOLD
                    self.status = "holding"
                    self.completed = True
                    return {"thrust": 0.0, "heading": self.ship.orientation}
                # Still moving at destination -- enter FLIP to brake
                return self._enter_flip(speed)

            self.phase = self.PHASE_COAST
            self.status = "coasting"
            self.completed = True
            return {"thrust": 0.0, "heading": vector_to_heading(vector_to_target)}

        direction_to_target = normalize_vector(vector_to_target)
        closing_speed = dot_product(self.ship.velocity, direction_to_target)

        # ----- Braking trigger (stop_at_target only) -----
        if self.stop_at_target and closing_speed > 0:
            d_trigger = self._corrected_braking_distance(closing_speed)
            if distance <= d_trigger:
                logger.info(
                    "GoTo: braking trigger at dist=%.0f m, d_trigger=%.0f m, "
                    "speed=%.1f m/s",
                    distance, d_trigger, speed,
                )
                return self._enter_flip(speed)

        # ----- Coast check (reached cruise speed, not yet braking) -----
        if self.stop_at_target:
            if closing_speed >= self.coast_speed:
                d_trigger = self._corrected_braking_distance(closing_speed)
                if distance > d_trigger:
                    self.phase = self.PHASE_COAST
                    self.status = "coasting"
                    return {"thrust": 0.0, "heading": vector_to_heading(vector_to_target)}

            self.phase = self.PHASE_ACCELERATE
            self.status = "accelerating"
            # Alignment guard: prevents backward thrust when the ship
            # is still pointed retrograde after a ZERO/HOLD re-approach.
            return self._apply_guard({
                "thrust": self._clamp_thrust(self.max_thrust),
                "heading": vector_to_heading(vector_to_target),
            })

        # ----- Non-stop course (flyby) -----
        if self.max_speed is not None and closing_speed >= float(self.max_speed):
            self.phase = self.PHASE_COAST
            self.status = "coasting"
            return {"thrust": 0.0, "heading": vector_to_heading(vector_to_target)}

        self.phase = self.PHASE_ACCELERATE
        self.status = "accelerating"
        return self._apply_guard({
            "thrust": self._clamp_thrust(self.max_thrust),
            "heading": vector_to_heading(vector_to_target),
        })

    # ----- phase implementations -----------------------------------------------

    def _enter_flip(self, speed: float) -> Dict:
        """Transition to FLIP phase: snapshot retrograde heading, zero thrust.

        At low speed (<10 m/s) skip FLIP and go straight to ZERO -- the
        snapshot heading is unreliable when the velocity vector can rotate
        significantly during the flip.
        """
        if speed < _BRAKE_SPEED_THRESH * 2:
            self.phase = self.PHASE_ZERO
            self.status = "zeroing residual velocity"
            logger.info("GoTo: -> ZERO (low speed %.1f m/s, skipping FLIP)", speed)
            return {"thrust": 0.0, "heading": self._retrograde_heading()}

        self._flip_heading_snapshot = self._retrograde_heading()
        self.phase = self.PHASE_FLIP
        self.status = "rotating to retrograde"
        logger.info("GoTo: -> FLIP, speed=%.1f m/s", speed)
        return {"thrust": 0.0, "heading": self._flip_heading_snapshot}

    def _compute_flip(self, speed: float, distance: float) -> Dict:
        """FLIP phase: rotate to retrograde heading with zero thrust.

        Once the heading error is below the flip tolerance, transition
        to BRAKE.  If speed dropped to near-zero during the flip (e.g.
        external factors), skip to HOLD.
        """
        if speed < _ZERO_SPEED_THRESH:
            self.phase = self.PHASE_HOLD
            self.status = "holding"
            self.completed = True
            return {"thrust": 0.0, "heading": self.ship.orientation}

        heading = self._flip_heading_snapshot or self._retrograde_heading()
        heading_err = self._heading_error(heading)

        if heading_err < _FLIP_TOLERANCE_DEG:
            self.phase = self.PHASE_BRAKE
            self.status = "braking"
            logger.info(
                "GoTo: FLIP -> BRAKE, heading_err=%.1f deg, speed=%.1f m/s",
                heading_err, speed,
            )

        # Always zero thrust during flip -- only RCS rotates the ship
        return {"thrust": 0.0, "heading": heading}

    def _compute_brake(self, speed: float, distance: float) -> Dict:
        """BRAKE phase: main drive with alignment guard and proportional taper.

        Cosine-scaled alignment guard prevents the drive from pushing the
        ship sideways when the nose hasn't caught up to retrograde.
        Proportional taper below _TAPER_SPEED prevents overshoot.
        """
        if speed < _BRAKE_SPEED_THRESH:
            self.phase = self.PHASE_ZERO
            self.status = "zeroing residual velocity"
            self._flip_heading_snapshot = None
            logger.info("GoTo: BRAKE -> ZERO, speed=%.1f m/s", speed)
            return {"thrust": 0.0, "heading": self._retrograde_heading()}

        heading = self._retrograde_heading()
        throttle = self.max_thrust

        # Proportional taper below _TAPER_SPEED to avoid overshoot
        if speed < _TAPER_SPEED:
            throttle *= speed / _TAPER_SPEED

        throttle = self._clamp_thrust(throttle)

        # Alignment guard: cosine-scale when misaligned, zero when severely
        # off-axis.  This is WHY theoretical accel != delivered accel.
        heading_err = self._heading_error(heading)
        if heading_err > _GUARD_CUTOFF_DEG:
            throttle = 0.0
        elif heading_err > _GUARD_DEADZONE_DEG:
            throttle *= max(0.0, math.cos(math.radians(heading_err)))

        self.status = f"braking {speed:.0f} m/s"
        return {"thrust": throttle, "heading": heading}

    def _compute_zero(self, speed: float, distance: float = None) -> Dict:
        """ZERO phase: feather thrust to null residual velocity.

        At very low speed (<0.5 m/s) snap velocity to zero -- without RCS
        translation there's no physical way to converge via main drive
        when the retrograde heading shifts faster than the ship can rotate.

        If stopped short of target (outside tolerance), re-enter ACCELERATE
        for another approach cycle.
        """
        if distance is None:
            distance = magnitude(subtract_vectors(
                self.target_position, self.ship.position))

        if speed < _ZERO_SPEED_THRESH:
            self.ship.velocity = {"x": 0.0, "y": 0.0, "z": 0.0}
            self._flip_heading_snapshot = None
            if distance <= self.tolerance:
                self.phase = self.PHASE_HOLD
                self.status = "holding"
                self.completed = True
                logger.info("GoTo: ZERO -> HOLD (speed %.2f m/s zeroed)", speed)
            else:
                # Stopped short of target -- re-approach
                self.phase = self.PHASE_ACCELERATE
                self.status = "accelerating"
                logger.info(
                    "GoTo: ZERO -> ACCELERATE (stopped short, "
                    "dist=%.0f m > tol=%.0f m)", distance, self.tolerance)
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

    def _compute_hold(self, distance: float = None,
                      vector_to_target: Dict = None) -> Dict:
        """HOLD phase: zero thrust.  Re-approach if stopped short."""
        speed = magnitude(self.ship.velocity)
        if speed > 0.01:
            self.ship.velocity = {"x": 0.0, "y": 0.0, "z": 0.0}

        if distance is None:
            vector_to_target = subtract_vectors(
                self.target_position, self.ship.position)
            distance = magnitude(vector_to_target)

        if distance > self.tolerance:
            # Stopped short of target -- re-approach
            self.phase = self.PHASE_ACCELERATE
            self.status = "accelerating"
            self.completed = False
            if vector_to_target is None:
                vector_to_target = subtract_vectors(
                    self.target_position, self.ship.position)
            logger.info(
                "GoTo: HOLD -> ACCELERATE (drift %.0f m > tol %.0f m)",
                distance, self.tolerance)
            return self._apply_guard({
                "thrust": self._clamp_thrust(self.max_thrust),
                "heading": vector_to_heading(vector_to_target),
            })

        self.status = "holding"
        self.completed = True
        return {"thrust": 0.0, "heading": self.ship.orientation}

    # ----- state reporting ----------------------------------------------------

    def get_state(self) -> Dict:
        """Get autopilot state including profile information."""
        state = super().get_state()
        vector_to_target = subtract_vectors(self.target_position, self.ship.position)
        distance = magnitude(vector_to_target)
        direction_to_target = normalize_vector(vector_to_target)
        closing_speed = dot_product(self.ship.velocity, direction_to_target)

        # Use derated accel for braking distance display so the GUI shows
        # the distance the ship will ACTUALLY need, not the theoretical min.
        a_derated = self._get_effective_accel()
        braking_distance = (
            (closing_speed ** 2) / (2 * a_derated) if closing_speed > 0 else 0.0
        )

        # ETA estimate
        time_to_arrival = None
        if closing_speed > 0.1:
            time_to_arrival = distance / closing_speed
        elif a_derated > 0 and distance > 0 and self.phase == self.PHASE_ACCELERATE:
            # Rough brachistochrone estimate: t = 2 * sqrt(d / a)
            time_to_arrival = 2.0 * math.sqrt(distance / a_derated)

        # Also expose as "range" for consistent field naming across autopilots
        state.update({
            "phase": self.phase,
            "profile": self.profile_name,
            "destination": self.target_position,
            "distance": distance,
            "range": distance,
            "closing_speed": closing_speed,
            "braking_distance": braking_distance,
            "time_to_arrival": time_to_arrival,
            "stop": self.stop_at_target,
            "tolerance": self.tolerance,
            "complete": self.completed,
            "status_text": self._build_status_text(distance, closing_speed, time_to_arrival),
        })
        return state

    def _build_status_text(self, distance: float, closing_speed: float,
                           eta: float = None) -> str:
        """Human-readable status for the GUI."""
        range_str = f"{distance / 1000:.1f}km" if distance >= 1000 else f"{distance:.0f}m"
        eta_str = ""
        if eta is not None:
            if eta < 60:
                eta_str = f", ETA {eta:.0f}s"
            else:
                minutes = int(eta) // 60
                secs = int(eta) % 60
                eta_str = f", ETA {minutes}m {secs:02d}s"

        if self.phase == self.PHASE_ACCELERATE:
            return f"Accelerating -- {range_str}{eta_str}"
        elif self.phase == self.PHASE_COAST:
            return f"Coasting -- {range_str}, {closing_speed:.1f} m/s{eta_str}"
        elif self.phase == self.PHASE_FLIP:
            return f"Flipping -- {range_str}, {closing_speed:.1f} m/s"
        elif self.phase == self.PHASE_BRAKE:
            return f"Braking -- {range_str} remaining{eta_str}"
        elif self.phase == self.PHASE_ZERO:
            speed = magnitude(self.ship.velocity)
            return f"Zeroing -- {speed:.1f} m/s remaining"
        elif self.phase == self.PHASE_HOLD:
            return f"Holding position at destination"
        return f"En route -- {range_str}"
