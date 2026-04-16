# hybrid/navigation/autopilot/rendezvous.py
"""Rendezvous autopilot - flip-and-burn trajectory to arrive at a target
with near-zero relative velocity.

Phases:
    burn    -> flip -> brake -> approach -> stationkeep

The braking trigger accounts for the distance the ship travels during the
flip (when main drive is off but inertia keeps closing), which prevents
the overshoot bug that a naive v^2/2a margin can't cover.

The *approach* phase sits between brake and stationkeep.  Once the ship
has bled most of its closing speed but is still too far for stationkeep,
approach uses proportional thrust to creep in without rebuilding excessive
velocity.  This eliminates the oscillation where aggressive profiles
would overshoot, re-burn, overshoot again and never converge.

Key design decisions (bug fixes from 2026-03-15):
  - FLIP uses a snapshot of the retrograde heading at entry, not the
    live (shifting) retrograde vector.  This prevents RCS from chasing
    a moving target and timing out.
  - BRAKE exit uses rel_speed (magnitude of relative velocity) instead
    of clamped closing_speed.  The old code clamped closing_speed to 0
    when range_rate flipped positive, causing immediate BRAKE exit even
    though the ship still had significant velocity.  Now BRAKE stays
    active until rel_speed drops below a threshold proportional to the
    approach speed limit.
  - BRAKE ALWAYS exits to APPROACH, never back to BURN.  The old
    BRAKE->BURN path caused oscillation where the ship would decelerate,
    re-burn, flip, brake, repeat -- each cycle making only 25-80 km of
    progress.  APPROACH's proportional controller handles convergence
    from any range, eliminating the oscillation entirely.
  - APPROACH only re-enters BURN if closing_speed is significantly
    negative (opening faster than APPROACH_SPEED_LIMIT), not based on
    a fixed distance threshold.  The old range-based check
    (range > approach_range * 3) false-triggered at 302 km when the
    ship entered APPROACH after braking from long range, immediately
    re-entering BURN and restarting the oscillation cycle.

Moving-target oscillation fix (2026-03-16):
  Three bugs combined to cause infinite BURN->FLIP->BRAKE->APPROACH->BURN
  loops when chasing a fleeing target (intercept scenario):

  - Bug 1: APPROACH thrust was capped at 0.5 * max_thrust even when
    the target was accelerating away, making it physically impossible
    to close.  Fix: allow full thrust when the ship is opening/falling
    behind (actual_closing < 0).

  - Bug 2: APPROACH desired_closing was calculated purely from range,
    ignoring target recession.  A target fleeing at 500 m/s meant the
    P-controller aimed for e.g. 200 m/s closing but needed 500+ just
    to not lose ground.  Fix: when opening, boost desired_closing to
    overcome recession plus a convergence margin.

  - Bug 3: BRAKE exited at rel_speed < 250 m/s regardless of range or
    target motion.  At 90 km from a fleeing target, the approach
    P-controller couldn't compensate and fell back to BURN.  Fix: when
    far out AND the target is receding, require much lower rel_speed
    (20% of normal threshold) before handing off to APPROACH.
    Escape valve: if radial closing_speed is near zero, exit anyway --
    BRAKE can't reduce rel_speed further against a fleeing target.

  - Bug 4 (physics audit): APPROACH->BURN guard false-triggered on
    P-controller braking transients.  When BRAKE exits to APPROACH at
    high rel_speed, the P-controller brakes, briefly pushing
    closing_speed below -APPROACH_SPEED_LIMIT.  Fix: hysteresis of
    50 ticks (5s) before re-entering BURN.

  - Bug 5 (physics audit): recession-boosted desired_closing could
    build speed the ship can't brake from if the target stops.  Fix:
    cap desired_closing at sqrt(2 * a_max * range * 0.8) to ensure
    braking is always possible within current range.
"""

import logging
import math
from typing import Dict, Optional

from hybrid.navigation.autopilot.base import BaseAutopilot
from hybrid.navigation.autopilot.match_velocity import MatchVelocityAutopilot
from hybrid.navigation.relative_motion import (
    calculate_relative_motion, vector_to_heading,
)
from hybrid.utils.math_utils import subtract_vectors, magnitude

logger = logging.getLogger(__name__)


# -- Nav solution profiles ---------------------------------------------------
# Each profile trades arrival speed vs fuel efficiency vs precision.

NAV_PROFILES: Dict[str, Dict] = {
    "aggressive": {
        "max_thrust": 0.50,              # ~5G on a 10G corvette -- crash couches required
        "brake_margin": 1.8,             # Post-flip alignment lag means BRAKE delivers
                                         # ~60% of BURN accel for first 10-15s.
        "flip_safety_factor": 1.5,
        "approach_range": 50_000.0,      # 50 km -- "close" in space
        "stationkeep_range": 300.0,      # 300 m -- tight handoff
        "approach_coast_speed": 800.0,   # m/s -- fast approach cruise
        "description": "5G combat burn. Crew impaired, crash couches required.",
        "risk_level": "high",
    },
    "balanced": {
        "max_thrust": 0.30,              # ~3G -- standard military transit
        "brake_margin": 1.6,
        "flip_safety_factor": 1.5,
        "approach_range": 75_000.0,      # 75 km -- between conservative and aggressive
        "stationkeep_range": 500.0,      # 500 m -- close handoff to MatchVelocity.
                                         # Old 15 km meant MatchVelocity had to
                                         # close 15 km at <20 m/s -- too slow.
                                         # approach_coast handles the full range.
        "approach_coast_speed": 500.0,   # m/s -- fast cruise for long approach.
                                         # Old 150 m/s meant 100km took 700s.
                                         # 500 m/s still brakeable at 500m handoff.
        "description": "3G military transit. Moderate crew fatigue.",
        "risk_level": "medium",
    },
    "conservative": {
        "max_thrust": 0.10,              # ~1G -- comfortable, fuel-efficient
        "brake_margin": 1.5,
        "flip_safety_factor": 1.5,
        "approach_range": 100_000.0,     # 100 km -- "close" starts far out
        "stationkeep_range": 1_000.0,    # 1 km -- generous handoff
        "approach_coast_speed": 200.0,   # m/s -- moderate approach cruise
        "description": "1G cruise. No crew strain, generous margins.",
        "risk_level": "low",
    },
}

# Threshold for considering braking "done": rel_speed must drop below
# this fraction of APPROACH_SPEED_LIMIT before BRAKE will exit.
# This prevents premature BRAKE exit when closing_speed briefly hits
# zero but the ship still has significant lateral or residual velocity.
#
# Lowered from 0.3 to 0.15 so BRAKE does more work (exits at ~75 m/s
# instead of ~150 m/s).  The new APPROACH architecture handles the rest
# without oscillation, but starting slower means less work for it.
_BRAKE_DONE_SPEED_FACTOR = 0.15

# How many consecutive ticks APPROACH must be opening faster than
# APPROACH_SPEED_LIMIT before re-entering BURN.  At dt=0.1 this is
# 5 seconds — long enough to absorb P-controller braking transients
# but short enough to detect a genuine miss.
_APPROACH_BURN_HYSTERESIS = 50


class RendezvousAutopilot(BaseAutopilot):
    """Flip-and-burn autopilot for arriving at a stationary or slow target.

    Phases:
        burn        - Accelerate toward target.
        flip        - Rotate 180 degrees to face retrograde.
        brake       - Decelerate toward target.
        approach    - Proportional-thrust creep to close remaining distance
                      without rebuilding dangerous speed.
        stationkeep - Hold position via MatchVelocityAutopilot.
    """

    PROFILES = NAV_PROFILES

    STATIONKEEP_RANGE = 500.0       # metres -- default handoff to MatchVelocityAutopilot.
                                    # Profile overrides this (300-1000 m).
                                    # The old 10-20 km meant MatchVelocity had
                                    # to close too far at low speed. Approach
                                    # coast handles the full range instead.
    STATIONKEEP_SPEED = 20.0        # m/s relative -- lowered from 100 to 20.
                                    # MatchVelocityAutopilot lacks an alignment
                                    # guard and diverges catastrophically when
                                    # handed >50 m/s.  At 20 m/s the heading
                                    # changes are small enough for safe control.
    FLIP_TOLERANCE_DEG = 10.0       # degrees
    _BASE_APPROACH_SPEED_LIMIT = 500.0  # m/s -- base speed limit at ~1G
                                        # Scaled up for higher-G ships so
                                        # approach phase doesn't bottleneck.

    def __init__(self, ship, target_id: Optional[str] = None,
                 params: Optional[Dict] = None):
        """Initialise rendezvous autopilot.

        Args:
            ship: Ship under autopilot control.
            target_id: Sensor contact ID of the target.
            params: Optional overrides -- profile ("aggressive"|"balanced"|
                    "conservative"), max_thrust (0-1), brake_margin,
                    flip_safety_factor, stationkeep_range (m),
                    stationkeep_speed (m/s).
                    Individual params override profile values.
        """
        super().__init__(ship, target_id, params or {})

        # Resolve profile, then overlay any explicit param overrides
        self.profile_name: str = self.params.get("profile", "balanced")
        profile = dict(self.PROFILES.get(self.profile_name, self.PROFILES["balanced"]))

        # Individual params override profile defaults
        self.max_thrust: float = float(self.params.get(
            "max_thrust", profile["max_thrust"]))
        self.brake_margin: float = float(self.params.get(
            "brake_margin", profile["brake_margin"]))
        self.flip_safety_factor: float = float(self.params.get(
            "flip_safety_factor", profile["flip_safety_factor"]))
        self.stationkeep_range: float = float(self.params.get(
            "stationkeep_range", profile.get("stationkeep_range", self.STATIONKEEP_RANGE)))
        self.stationkeep_speed: float = float(self.params.get(
            "stationkeep_speed", self.STATIONKEEP_SPEED))
        self.approach_range: float = float(self.params.get(
            "approach_range", profile.get("approach_range", 50_000.0)))
        # Target cruise speed during approach coast — profile-dependent.
        # Aggressive ships close faster, conservative ships are gentler.
        self.approach_coast_speed: float = float(self.params.get(
            "approach_coast_speed", profile.get("approach_coast_speed", 150.0)))

        # Dynamic APPROACH_SPEED_LIMIT and approach_range: both must be
        # consistent with the CONSERVATIVE acceleration estimate.  At init
        # we have no measurement yet, so use 50% of theoretical — the same
        # fallback _get_effective_accel() uses before measurements exist.
        # This ensures approach_range is safe even before the first burn.
        conservative_accel = self._get_max_accel() * self.max_thrust * 0.30
        g_ratio = max(1.0, conservative_accel / 10.0)
        self.APPROACH_SPEED_LIMIT: float = min(
            self._BASE_APPROACH_SPEED_LIMIT * math.sqrt(g_ratio),
            3000.0,
        )
        # Ensure approach_range is large enough to brake from the speed limit.
        # Without this, at eff=17.5 m/s² the ship builds to 661 m/s but
        # needs 12.5km to stop — more than the 10km approach_range.
        # Only apply for high-thrust ships (eff > 15 m/s²) where the
        # dynamic speed limit is significantly above the 500 m/s base.
        if "approach_range" not in self.params and conservative_accel > 15.0:
            min_approach_range = (self.APPROACH_SPEED_LIMIT ** 2
                                  / (2.0 * conservative_accel) * 2.0)
            self.approach_range = min(
                max(self.approach_range, min_approach_range),
                100_000.0,
            )

        self.phase: str = "burn"
        self._match_ap: Optional[MatchVelocityAutopilot] = None
        self._flip_entered_time: Optional[float] = None
        self._flip_entered_range: Optional[float] = None

        # --- Measured acceleration tracking ---
        # Instead of guessing a static guard_eff factor, we measure the
        # actual delivered acceleration over a rolling window and use
        # that for all braking/safety calculations.  This adapts to
        # whatever thrust the ship actually delivers — no more guessing.
        self._prev_speed: Optional[float] = None
        self._accel_samples: list = []  # (dt, delta_speed) pairs
        self._measured_accel: float = 0.0  # rolling average
        self._ACCEL_WINDOW: float = 10.0  # seconds of history to average
        # Snapshot of the retrograde heading at flip entry.  Using a fixed
        # heading prevents the RCS from chasing a moving target as the
        # velocity vector drifts during unpowered coast.
        self._flip_target_heading: Optional[Dict] = None
        # Hysteresis counter: how many consecutive ticks APPROACH has been
        # opening faster than APPROACH_SPEED_LIMIT.  Only re-enter BURN if
        # this persists, preventing false triggers from P-controller braking
        # transients that briefly push closing_speed below zero.
        self._approach_opening_ticks: int = 0
        # Approach sub-phase state: tracks which step of the 3-step
        # approach architecture (decel -> rotate -> coast) we are in.
        self._approach_rotated: bool = False  # True once prograde rotation done
        self._approach_coast_ticks: int = 0   # ticks spent in coast sub-phase
        self.status = "active"
        if not target_id:
            self.status = "error"
            self.error_message = "No target specified for rendezvous"

    # ----- physics helpers --------------------------------------------------

    def _get_max_accel(self) -> float:
        """Max linear acceleration (m/s^2) from propulsion, with safe floor."""
        propulsion = self.ship.systems.get("propulsion")
        if propulsion and hasattr(propulsion, "max_thrust") and self.ship.mass > 0:
            return max(propulsion.max_thrust / self.ship.mass, 0.01)
        return 0.01

    def _update_measured_accel(self, dt: float) -> None:
        """Update rolling measurement of actual delivered acceleration.

        Tracks speed changes over a window and computes the average
        acceleration the ship is actually achieving — including all
        alignment guard losses, RCS lag, power throttling, etc.
        This replaces the static guard_eff guessing game.
        """
        current_speed = magnitude(self.ship.velocity)
        if self._prev_speed is not None and dt > 0.001:
            delta_speed = abs(current_speed - self._prev_speed)
            self._accel_samples.append((dt, delta_speed))

            # Trim samples older than the window
            total_dt = sum(s[0] for s in self._accel_samples)
            while total_dt > self._ACCEL_WINDOW and len(self._accel_samples) > 2:
                removed = self._accel_samples.pop(0)
                total_dt -= removed[0]

            # Compute rolling average: total delta_speed / total dt
            if total_dt > 1.0:  # need at least 1s of data
                total_dv = sum(s[1] for s in self._accel_samples)
                self._measured_accel = total_dv / total_dt

        self._prev_speed = current_speed

    def _get_effective_accel(self) -> float:
        """Actual delivered acceleration for braking/safety calculations.

        Uses real-time measured acceleration when available (after ~2s of
        thrust data).  Falls back to a conservative 50% of theoretical
        when no measurement exists yet (e.g., first seconds of BURN).

        This eliminates the static guard_eff factor that never matched
        reality across different phases and heading change rates.
        """
        theoretical = self._get_max_accel() * self.max_thrust

        if self._measured_accel > 1.0:
            # Use measured, but never trust it to be MORE than theoretical
            # (measurement noise could briefly spike above real capability)
            eff = min(self._measured_accel, theoretical)
        else:
            # No measurement yet (or samples cleared at phase transition).
            # Use very conservative 30% — the post-flip alignment transient
            # can reduce delivered thrust to 20-40% of theoretical.
            eff = theoretical * 0.30

        if not hasattr(self, '_logged_accel'):
            propulsion = self.ship.systems.get("propulsion")
            prop_thrust = getattr(propulsion, 'max_thrust', 'N/A') if propulsion else 'N/A'
            logger.info(
                "Rendezvous accel: raw=%.2f (prop_thrust=%s, mass=%.0f), "
                "profile_throttle=%.2f, theoretical=%.2f m/s^2 "
                "(measured accel used when available)",
                self._get_max_accel(), prop_thrust, self.ship.mass,
                self.max_thrust, theoretical)
            self._logged_accel = True
        return max(eff, 0.5)  # floor at 0.5 m/s^2 to avoid division by zero

    @staticmethod
    def _braking_distance(speed: float, accel: float) -> float:
        """Kinematic braking distance: d = v^2 / (2a)."""
        if accel <= 0:
            return float("inf")
        return (speed * speed) / (2.0 * accel)

    def _estimate_flip_time(self) -> float:
        """Estimate how long a 180-degree flip takes using RCS capability.

        Queries the RCS system's estimate_rotation_time() if available,
        otherwise falls back to a conservative default.

        Returns:
            Estimated flip duration in seconds.
        """
        rcs = self.ship.systems.get("rcs")
        if rcs and hasattr(rcs, "estimate_rotation_time"):
            return rcs.estimate_rotation_time(180.0, self.ship)
        # Fallback: assume a modest RCS can do 180 in ~20 seconds
        return 20.0

    def _corrected_braking_distance(self, closing_speed: float,
                                    a_max: float) -> float:
        """Braking trigger distance that accounts for flip coasting.

        During the flip the ship cannot brake but still closes at
        current speed.  The old BRAKE_MARGIN of 1.05 only added 5%
        to kinematic distance, which is vastly insufficient at high
        closing speeds.

        Formula:
            d_needed = d_brake * brake_margin
                     + closing_speed * flip_time * flip_safety_factor
        """
        d_brake = self._braking_distance(closing_speed, a_max)
        flip_time = self._estimate_flip_time()
        flip_coast = closing_speed * flip_time * self.flip_safety_factor
        return d_brake * self.brake_margin + flip_coast

    def _resolve_precise_target(self, target, current_range: float):
        """Use exact ship geometry for close-in docking phases.

        Long-range rendezvous can use the sensor contact solution, but the
        final docking envelope (<5 km) is too tight for the residual
        position noise on IR contacts.  Once we are inside the close
        approach region and can unambiguously map the contact back to a
        real ship, switch to that precise target state for final guidance.
        """
        if not hasattr(target, "id"):
            return target

        if current_range > max(self.stationkeep_range * 10.0, 5_000.0):
            return target

        sensors = self.ship.systems.get("sensors")
        tracker = getattr(sensors, "contact_tracker", None) if sensors else None
        if not tracker:
            return target

        real_id = None
        for candidate_real_id, stable_id in tracker.id_mapping.items():
            if stable_id == target.id:
                real_id = candidate_real_id
                break

        if not real_id:
            return target

        for ship in getattr(self.ship, "_all_ships_ref", []):
            if getattr(ship, "id", None) == real_id:
                return ship

        return target

    # ----- core compute ----------------------------------------------------

    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute thrust/heading command for this tick.

        Args:
            dt: Simulation time step (seconds).
            sim_time: Current simulation clock (seconds).
        Returns:
            ``{thrust, heading}`` or ``None`` on error.
        """
        # Update measured acceleration from actual velocity changes.
        # This must happen every tick BEFORE braking distance calculations.
        self._update_measured_accel(dt)

        target = self.get_target()
        if not target:
            self.status = "error"
            self.error_message = f"Target {self.target_id} not found"
            return None

        rel = calculate_relative_motion(self.ship, target)
        current_range: float = rel["range"]
        precise_target = self._resolve_precise_target(target, current_range)
        if precise_target is not target:
            target = precise_target
            rel = calculate_relative_motion(self.ship, target)
            current_range = rel["range"]
        # Signed closing speed: positive = closing, negative = opening.
        # Unlike the old code which clamped to 0 when not closing, we
        # keep the true value so BRAKE can distinguish "just stopped"
        # from "drifting away".
        closing_speed: float = -rel["range_rate"]

        # Station-keep handoff (highest priority)
        rel_speed = magnitude(rel["relative_velocity_vector"])
        if current_range <= self.stationkeep_range and rel_speed < self.stationkeep_speed:
            self.phase = "stationkeep"
            self.status = "stationkeeping"
            self._flip_target_heading = None
            return self._compute_stationkeep(dt, sim_time)

        a_max = self._get_effective_accel()
        # Use max(closing_speed, 0) for braking distance calc -- negative
        # closing speed means we are opening, so braking distance is 0.
        d_trigger = self._corrected_braking_distance(
            max(closing_speed, 0.0), a_max)

        # Speed threshold below which BRAKE considers deceleration "done".
        # Using rel_speed (magnitude of full relative velocity vector)
        # instead of just the radial closing_speed prevents premature exit
        # when the ship has significant lateral drift.
        brake_done_speed = self.APPROACH_SPEED_LIMIT * _BRAKE_DONE_SPEED_FACTOR

        # Phase transitions
        if self.phase == "burn":
            if closing_speed > 0 and current_range <= d_trigger:
                logger.info(
                    "Rendezvous: BURN -> FLIP at range %.0f m, "
                    "closing %.1f m/s, d_trigger %.0f m (flip %.1fs, "
                    "measured_accel=%.1f m/s^2)",
                    current_range, closing_speed, d_trigger,
                    self._estimate_flip_time(), self._measured_accel)
                self.phase = "flip"
                self._flip_entered_time = sim_time
                self._flip_entered_range = current_range
                # Clear stale BURN acceleration measurements so BRAKE
                # uses the conservative 30% fallback until it builds
                # its own measurement.  BURN delivery != BRAKE delivery
                # due to post-flip alignment lag.
                self._accel_samples.clear()
                self._measured_accel = 0.0
                # Snapshot the retrograde heading at flip entry so the RCS
                # has a stable target to rotate toward.  During coast the
                # velocity vector drifts (lateral motion, target velocity),
                # and chasing a moving heading caused ~50% of flips to time
                # out because the RCS could never converge.
                #
                # Flatten to yaw-only (pitch=0, roll=0) so the flip is a
                # single-axis rotation.  Sensor noise adds spurious Z
                # velocity that gives the retrograde heading a pitch
                # component; a 180-degree rotation with pitch makes the
                # quaternion error decompose into multi-axis torque
                # requests that the single-axis RCS thrusters cannot
                # satisfy, causing total thruster allocation failure.
                # The braking phase uses the full 3D retrograde heading
                # for precision alignment.
                retro = self._retrograde_heading(rel)
                retro["pitch"] = 0.0
                retro["roll"] = 0.0
                self._flip_target_heading = retro
        elif self.phase == "flip":
            # Check alignment against the SNAPSHOT heading, not live
            # retrograde.  This is the key fix for the flip timeout bug.
            # Pass rel as fallback in case no snapshot exists (external
            # phase override or edge case).
            if self._flip_heading_aligned(rel):
                logger.info("Rendezvous: FLIP -> BRAKE (aligned to snapshot heading)")
                self.phase = "brake"
                self._flip_entered_time = None
                self._flip_target_heading = None
            elif self._flip_entered_time is not None:
                # Safety: if the flip takes much longer than expected the
                # ship is overshooting while coasting unpowered.  Cap at
                # 8x estimated flip time to prevent infinite coasting.
                # The generous multiplier absorbs PD controller overhead
                # (~1.5x ideal) plus thruster allocation variance.
                flip_elapsed = sim_time - self._flip_entered_time
                flip_limit = self._estimate_flip_time() * 8.0
                if flip_elapsed > flip_limit:
                    logger.warning(
                        "Rendezvous: FLIP timed out after %.1fs "
                        "(limit %.1fs, range now %.0f m vs %.0f m at "
                        "entry). Forcing BRAKE to stop overshoot.",
                        flip_elapsed, flip_limit, current_range,
                        self._flip_entered_range or 0.0,
                    )
                    self.phase = "brake"
                    self._flip_entered_time = None
                    self._flip_target_heading = None
        elif self.phase == "brake":
            # BRAKE exit logic.  Two paths to APPROACH:
            #
            # Path A (normal): rel_speed drops below threshold — braking
            # has bled most relative velocity.
            #
            # Path B (fleeing target escape): closing_speed is near zero
            # or negative AND rel_speed is moderately low — the ship has
            # killed radial approach velocity.  For a fleeing target,
            # rel_speed stays high (target recession inflates it), but
            # we still need to exit BRAKE because retrograde thrust
            # can't help — APPROACH can flip prograde and chase.
            #
            # CRITICAL: Path B must NOT fire during high-speed overshoot
            # (ship flies past stationary target).  During overshoot
            # closing_speed goes negative but rel_speed is still very
            # high (the ship hasn't actually decelerated).  BRAKE must
            # continue firing retrograde to bleed that speed.  The
            # rel_speed guard (< 2x brake_done_speed) prevents this.
            brake_exit = False

            if rel_speed < brake_done_speed and current_range > self.stationkeep_range:
                # Path A (primary): rel_speed is low enough that APPROACH
                # can handle convergence from here.
                logger.info(
                    "Rendezvous: BRAKE -> APPROACH (decelerated to %.1f m/s, "
                    "range %.0f m)",
                    rel_speed, current_range)
                brake_exit = True
            elif (closing_speed <= 0
                    and rel_speed < brake_done_speed
                    and current_range > self.stationkeep_range):
                # Path B (rare): radial closure exactly zero while total
                # velocity is also low.  Can happen when BRAKE bleeds
                # speed unevenly across radial/lateral components.
                logger.info(
                    "Rendezvous: BRAKE -> APPROACH (radial closure done, "
                    "closing=%.1f m/s, rel_speed=%.1f m/s, range %.0f m)",
                    closing_speed, rel_speed, current_range)
                brake_exit = True

            if brake_exit:
                # Clear stale BURN/BRAKE acceleration measurements —
                # APPROACH thrust levels are much lower and the stale
                # data would cause the safety caps to overestimate
                # braking capability.
                self._accel_samples.clear()
                self._measured_accel = 0.0
                self._approach_rotated = False
                self._approach_coast_ticks = 0
                self.phase = "approach_decel"
                logger.info(
                    "Rendezvous: BRAKE -> APPROACH_DECEL (continuing "
                    "retrograde decel, rel_speed=%.1f m/s, range %.0f m)",
                    rel_speed, current_range)

        elif self.phase == "approach_decel":
            # Step 1: Continue retrograde braking until slow enough.
            # NO heading change from BRAKE -- same retrograde direction.
            #
            # The exit threshold depends on range context:
            # - Far out (> 3x stationkeep): brake to 5 m/s for a clean
            #   rotate->coast cycle (50m drift during 10s rotation is
            #   negligible at 50+ km range).
            # - Near stationkeep zone (< 3x stationkeep): brake to
            #   stationkeep_speed * 0.5 so the subsequent coast can
            #   hand off cleanly.  Braking all the way to 5 m/s here
            #   wastes time when we just need to enter stationkeep at
            #   moderate speed.
            if current_range < self.stationkeep_range * 3:
                decel_target = self.stationkeep_speed * 0.5
            else:
                decel_target = 5.0

            if rel_speed < decel_target:
                self.phase = "approach_rotate"
                self._approach_rotated = False
                logger.info(
                    "Rendezvous: APPROACH_DECEL -> APPROACH_ROTATE "
                    "(braked to %.1f m/s < %.1f m/s target, range %.0f m)",
                    rel_speed, decel_target, current_range)

        elif self.phase == "approach_rotate":
            # Step 2: Single rotation toward target.  NO thrust during
            # rotation — just point the nose at the target.  Transition
            # to coast once aligned (heading error < 10 degrees).
            target_pos = target.position if hasattr(target, "position") else target
            vec = subtract_vectors(target_pos, self.ship.position)
            heading = vector_to_heading(vec)
            heading_err = self._heading_error({
                "yaw": heading.get("yaw", 0),
                "pitch": self.ship.orientation.get("pitch", 0),
                "roll": self.ship.orientation.get("roll", 0),
            })
            if heading_err < 10.0:
                self._approach_rotated = True
                self._approach_coast_ticks = 0
                self.phase = "approach_coast"
                logger.info(
                    "Rendezvous: APPROACH_ROTATE -> APPROACH_COAST "
                    "(aligned to target, heading_err=%.1f deg, "
                    "range %.0f m)",
                    heading_err, current_range)

        elif self.phase == "approach_coast":
            # Step 3: Gentle prograde thrust to maintain closing speed.
            # Target speed is profile-dependent (100-200 m/s).
            #
            # Four transition checks (in priority order):
            #   1. Stationkeep handoff: close enough AND slow enough
            #   2. Final braking: approaching stationkeep zone too fast
            #   3. Overspeed emergency: fall back to approach_decel
            #   4. Normal coast with inline retrograde braking

            # --- Check 1: Stationkeep handoff ---
            # When range drops below stationkeep_range and speed is low
            # enough, hand off to stationkeep.  This is the normal
            # successful end of the approach sequence.  The global
            # stationkeep check (line ~402) also catches this, but
            # having an explicit check here provides clearer logging
            # and prevents the phase from doing unnecessary work.
            if (current_range < self.stationkeep_range
                    and rel_speed < self.stationkeep_speed):
                self.phase = "stationkeep"
                self.status = "stationkeeping"
                self._flip_target_heading = None
                logger.info(
                    "Rendezvous: APPROACH_COAST -> STATIONKEEP "
                    "(range %.0f m < %.0f m, rel_speed %.1f m/s < %.1f m/s)",
                    current_range, self.stationkeep_range,
                    rel_speed, self.stationkeep_speed)

            # --- Check 2: Final braking before stationkeep ---
            # When the ship needs to decelerate before reaching
            # stationkeep range, trigger approach_decel.  Uses braking
            # distance to determine when to start: d_brake = v^2/(2a).
            # The 2.5x safety margin accounts for approach_decel using
            # gentle proportional thrust (not full braking) and for the
            # alignment guard blocking some ticks.
            elif rel_speed > self.stationkeep_speed:
                # Use the DECEL-phase accel estimate (30% of theoretical),
                # NOT the coast-phase measured accel.  During coast the ship
                # thrusts gently (~2 m/s²), but decel uses full retrograde
                # (~10-15 m/s²).  Using coast measurements makes d_brake
                # 4-5x too large, triggering braking at 90km instead of 20km.
                theoretical = self._get_max_accel() * self.max_thrust
                a_decel = theoretical * 0.30
                speed_excess = rel_speed - self.stationkeep_speed * 0.5
                d_brake_needed = self._braking_distance(
                    max(speed_excess, 0), a_decel) * 2.5
                if current_range < d_brake_needed + self.stationkeep_range:
                    self.phase = "approach_decel"
                    self._approach_rotated = False
                    self._accel_samples.clear()
                    self._measured_accel = 0.0
                    logger.info(
                        "Rendezvous: APPROACH_COAST -> APPROACH_DECEL "
                        "(final braking: range %.0f m, rel_speed %.1f m/s "
                        "> stationkeep_speed %.1f m/s, d_brake %.0f m)",
                        current_range, rel_speed, self.stationkeep_speed,
                        d_brake_needed)

            # --- Check 3: Overspeed emergency ---
            # If speed exceeds safety limit for sustained period, fall
            # back to the full approach_decel->rotate->coast cycle.
            # This handles catastrophic overspeed that inline braking
            # (check 3) cannot correct -- e.g. target stopped suddenly.
            #
            # Safety limit: 1.5x the coast speed -- enough headroom for
            # thrust overshoot and sensor noise, but catches real problems.
            elif rel_speed > self.approach_coast_speed * 1.5:
                self._approach_opening_ticks += 1
                # Hysteresis: 30 ticks (3s) above safety before braking.
                # This absorbs sensor noise spikes without oscillating.
                if self._approach_opening_ticks > 30:
                    self.phase = "approach_decel"
                    self._approach_rotated = False
                    self._accel_samples.clear()
                    self._measured_accel = 0.0
                    logger.info(
                        "Rendezvous: APPROACH_COAST -> APPROACH_DECEL "
                        "(speed %.1f m/s > safety %.1f m/s for 3s, "
                        "range %.0f m)",
                        rel_speed, self.approach_coast_speed * 1.5,
                        current_range)
            else:
                self._approach_opening_ticks = 0

        # Execute current phase
        cmd: Optional[Dict] = None
        if self.phase == "burn":
            self.status = "burning"
            cmd = self._compute_burn(target)
        elif self.phase == "flip":
            self.status = "flipping"
            cmd = self._compute_flip(rel)
        elif self.phase == "brake":
            self.status = "braking"
            cmd = self._compute_brake(rel)
        elif self.phase == "approach_decel":
            self.status = "approach_braking"
            cmd = self._compute_approach_decel(rel)
        elif self.phase == "approach_rotate":
            self.status = "approach_rotating"
            cmd = self._compute_approach_rotate(target)
        elif self.phase == "approach_coast":
            self.status = "approach_coasting"
            cmd = self._compute_approach_coast(target, rel, current_range)
        else:
            cmd = self._compute_stationkeep(dt, sim_time)

        # -- Alignment guard ------------------------------------------------
        # Expanse-style rule: NEVER fire the main drive while the ship is
        # significantly misaligned with the commanded heading.  In hard
        # sci-fi, thrust acts along the ship's physical nose, not the
        # commanded direction.  Firing while pointed the wrong way pushes
        # the ship off-course (or backward after a BRAKE->APPROACH
        # transition where the ship is still retrograde but needs to
        # thrust prograde).
        #
        # The FLIP phase is excluded because it already commands thrust=0
        # and exists solely to rotate the ship.  Stationkeep delegates to
        # MatchVelocityAutopilot which is a separate concern.
        # Skip the alignment guard in approach phase at close range.
        # The approach velocity-matching controller commands heading
        # changes every tick as it corrects both radial and lateral
        # velocity.  The alignment guard blocks thrust for ~10s during
        # each heading change, which defeats the controller.  At close
        # range the thrust magnitudes are small (0.02-0.5 * max_thrust)
        # and the misalignment-induced error is self-correcting —
        # thrust slightly off-axis just means a minor lateral component
        # that the controller compensates on the next tick.
        # The old APPROACH P-controller needed a guard exemption because
        # it changed heading every tick.  The new approach_brake/creep
        # sub-phases hold stable headings, so the guard stays active.
        guard_exempt = False
        if (cmd and cmd.get("thrust", 0) > 0
                and self.phase not in ("flip", "stationkeep")
                and not guard_exempt):
            heading_err = self._heading_error(cmd.get("heading"))
            if heading_err > 90.0:
                # Severely misaligned — would thrust backward. Zero it.
                cmd["thrust"] = 0.0
            elif heading_err > 5.0:
                # Proportional scaling: thrust contributes cos(error) of
                # useful force along the desired direction.  This replaces
                # the old binary 30° cutoff that flickered on/off and
                # averaged only 35% thrust delivery.  The cosine falloff
                # is physically correct (force projection) and smooth.
                scale = math.cos(math.radians(heading_err))
                cmd["thrust"] *= max(0.0, scale)

        return cmd

    # ----- phase implementations -------------------------------------------

    def _compute_burn(self, target) -> Dict:
        """Accelerate toward the target."""
        target_pos = target.position if hasattr(target, "position") else target
        vec = subtract_vectors(target_pos, self.ship.position)
        heading = vector_to_heading(vec)
        # Yaw-only heading: constrain to single-axis rotation to prevent
        # the alignment guard from firing on spurious pitch changes from
        # sensor noise.  Same pattern as APPROACH phase (line ~717).
        return {"thrust": self._clamp_thrust(self.max_thrust),
                "heading": {
                    "yaw": heading.get("yaw", 0),
                    "pitch": self.ship.orientation.get("pitch", 0),
                    "roll": self.ship.orientation.get("roll", 0),
                }}

    def _compute_flip(self, rel: Dict) -> Dict:
        """Command yaw-only rotation toward retrograde, zero thrust.

        Only commands yaw rotation, preserving current pitch/roll.
        This keeps the flip as a single-axis maneuver so the RCS
        thrusters can deliver maximum torque without cross-axis
        contamination.  Pitch/roll alignment is handled by the
        subsequent BRAKE phase which uses the full 3D retrograde.
        """
        heading = self._flip_target_heading
        if heading is None:
            heading = self._retrograde_heading(rel)
        # Command only yaw — keep current pitch/roll to avoid
        # multi-axis torque that the allocator struggles with.
        return {"thrust": 0.0, "heading": {
            "yaw": heading.get("yaw", 0),
            "pitch": self.ship.orientation.get("pitch", 0),
            "roll": self.ship.orientation.get("roll", 0),
        }}

    def _compute_brake(self, rel: Dict) -> Dict:
        """Thrust retrograde to bleed closing speed.

        Uses yaw-only heading (like FLIP) to avoid the multi-axis torque
        instability that causes the RCS to spin the ship.  When the PD
        controller receives both yaw and pitch corrections simultaneously,
        the thruster allocator produces cross-axis contamination that can
        excite a divergent oscillation — the ship never stabilizes on
        heading, the alignment guard zeros thrust every tick, and braking
        fails entirely.

        The pitch component of the retrograde vector is negligible for
        in-plane maneuvers (Z velocity ≈ 0), so yaw-only is physically
        accurate.  For out-of-plane scenarios, the small pitch error
        means thrust is slightly off-axis, but the ship still decelerates
        effectively (cos(1°) ≈ 0.9998 efficiency).
        """
        retro = self._retrograde_heading(rel)
        return {"thrust": self._clamp_thrust(self.max_thrust),
                "heading": {
                    "yaw": retro.get("yaw", 0),
                    "pitch": self.ship.orientation.get("pitch", 0),
                    "roll": self.ship.orientation.get("roll", 0),
                }}

    def _compute_approach_decel(self, rel: Dict) -> Dict:
        """Continue retrograde thrust until nearly stopped (<5 m/s).

        Same heading as BRAKE — no heading change needed.  The ship is
        already pointing retrograde.  Uses gentle proportional thrust
        so we don't overshoot zero and start opening.

        This is step 1 of the 3-step approach: decel -> rotate -> coast.
        """
        heading = self._retrograde_heading(rel)
        # Proportional thrust: harder when fast, feathering near zero.
        current_speed = magnitude(rel["relative_velocity_vector"])
        thrust_frac = min(self.max_thrust, current_speed / 30.0)
        thrust_frac = max(0.02, thrust_frac)
        return {"thrust": self._clamp_thrust(thrust_frac),
                "heading": {
                    "yaw": heading.get("yaw", 0),
                    "pitch": self.ship.orientation.get("pitch", 0),
                    "roll": self.ship.orientation.get("roll", 0),
                }}

    def _compute_approach_rotate(self, target) -> Dict:
        """Rotate toward target with zero thrust.

        The ship is nearly stopped (<5 m/s).  We command the heading
        toward the target but fire NO thrust.  At 5 m/s the drift
        during a 10-second rotation is only 50 metres — negligible
        at 50+ km range.

        This is step 2 of the 3-step approach: decel -> rotate -> coast.
        The single rotation avoids the dangerous heading-reversal pattern
        that caused oscillation in the old approach architecture.
        """
        target_pos = target.position if hasattr(target, "position") else target
        vec = subtract_vectors(target_pos, self.ship.position)
        heading = vector_to_heading(vec)
        return {"thrust": 0.0,
                "heading": {
                    "yaw": heading.get("yaw", 0),
                    "pitch": self.ship.orientation.get("pitch", 0),
                    "roll": self.ship.orientation.get("roll", 0),
                }}

    def _compute_approach_coast(self, target, rel: Dict,
                                current_range: float) -> Dict:
        """Gentle prograde thrust to maintain profile-dependent closing speed.

        The ship is pointed at the target and nearly stopped.  Apply
        proportional thrust to reach and maintain approach_coast_speed
        (100-200 m/s depending on profile).  Coast when at speed.

        Desired closing speed tapers as range decreases:
          - At approach_range: full coast speed
          - At stationkeep_range: stationkeep_speed (for smooth handoff)
          - Sqrt interpolation between (kinematically correct for
            constant-deceleration braking — ship stays fast longer)
          - Below stationkeep_range: stationkeep_speed (floor)

        When the ship is closing faster than desired by >20%, command
        retrograde heading and brake proportionally.  This prevents the
        "coast overshoot" where the ship enters approach_coast at high
        speed and has no way to slow down (space has no drag).  The 20%
        hysteresis band prevents oscillation between prograde and
        retrograde thrust.

        This is step 3 of the 3-step approach: decel -> rotate -> coast.
        """
        target_pos = target.position if hasattr(target, "position") else target
        vec = subtract_vectors(target_pos, self.ship.position)
        prograde_heading = vector_to_heading(vec)
        actual_closing = -rel["range_rate"]

        # Taper desired speed across the full approach range.  Sqrt
        # curve from coast_speed at approach_range (75km for balanced)
        # down to stationkeep_speed at stationkeep_range (500m).
        #
        # The old taper started at stationkeep_range * 3 (1500m),
        # meaning the ship targeted 500 m/s until 1.5km from target.
        # This caused a sawtooth of coast→emergency-brake→rotate cycles
        # (3-12 cycles per approach).  Spanning the full approach range
        # gives smooth proportional deceleration and eliminates the
        # sawtooth entirely.
        taper_start = self.approach_range
        if current_range >= taper_start:
            # Far out: full coast speed
            desired_closing = self.approach_coast_speed
        else:
            # Sqrt taper: v(r) = v_low + (v_high - v_low) * sqrt((r - r_low) / (r_high - r_low))
            # Kinematically correct for constant-deceleration braking.
            # The ship stays fast longer and decelerates harder near the
            # target — matching what a real pilot would do.  ~45% faster
            # than the old linear taper at the same safety margins.
            taper_span = max(taper_start - self.stationkeep_range, 1.0)
            taper_frac = (current_range - self.stationkeep_range) / taper_span
            taper_frac = max(0.0, min(1.0, taper_frac))
            desired_closing = (self.stationkeep_speed
                               + (self.approach_coast_speed - self.stationkeep_speed)
                               * math.sqrt(taper_frac))

        # --- Inline retrograde braking when overspeeding ---
        # If the ship is closing >20% faster than desired, brake.
        # The 20% hysteresis prevents oscillation: we start braking at
        # 1.2x desired and stop braking when we drop below 1.0x desired.
        # Tighter than the old 30% band because the sqrt taper keeps the
        # ship faster at intermediate ranges — need earlier corrections.
        # This is safe within a single phase (no phase transition) and
        # the proportional thrust keeps corrections gentle.
        overspeed_threshold = desired_closing * 1.2
        if actual_closing > overspeed_threshold and actual_closing > 0:
            # Overspeeding — command retrograde and brake proportionally.
            # Brake harder when further over speed, capped at 50% thrust
            # to keep corrections gentle and avoid the old oscillation.
            retro_heading = self._retrograde_heading(rel)
            overspeed_ratio = (actual_closing - desired_closing) / max(desired_closing, 1.0)
            thrust_frac = min(self.max_thrust * 0.5, overspeed_ratio * 0.3 * self.max_thrust)
            thrust = self._clamp_thrust(max(0.02, thrust_frac))
            heading = retro_heading
        elif actual_closing >= desired_closing:
            # At or slightly above desired speed — coast (no thrust).
            # Within the 0-20% overspeed band, just coasting is enough;
            # in vacuum the speed won't increase without thrust.
            thrust = 0.0
            heading = prograde_heading
        elif actual_closing >= desired_closing * 0.8:
            # Close enough — minimal maintenance thrust
            thrust = self._clamp_thrust(0.02)
            heading = prograde_heading
        else:
            # Need to build speed — proportional thrust based on deficit
            speed_deficit = desired_closing - actual_closing
            thrust_frac = min(self.max_thrust * 0.5,
                              speed_deficit / 200.0 * self.max_thrust)
            thrust = self._clamp_thrust(max(0.02, thrust_frac))
            heading = prograde_heading

        return {"thrust": thrust,
                "heading": {
                    "yaw": heading.get("yaw", 0),
                    "pitch": self.ship.orientation.get("pitch", 0),
                    "roll": self.ship.orientation.get("roll", 0),
                }}

    def _compute_approach_creep(self, target, rel: Dict,
                                current_range: float) -> Dict:
        """Gently thrust toward target at low speed.

        The ship is nearly stopped (< 180 m/s).  Point toward the target
        and apply tiny thrust to build a slow closing speed.  Coast when
        closing fast enough.  Hand off to stationkeep when range < 5km.

        No heading reversals — if the ship is closing, it just coasts.
        If it's opening or drifting laterally, tiny corrections only.
        """
        target_pos = target.position if hasattr(target, "position") else target
        vec = subtract_vectors(target_pos, self.ship.position)
        heading = vector_to_heading(vec)

        # Desired closing speed: proportional to range, capped.
        # At 100km: 100 m/s.  At 50km: 50 m/s.  At 5km: 10 m/s.
        desired_closing = max(5.0, min(self.stationkeep_speed * 2.0,
                                       current_range / 1000.0))
        actual_closing = -rel["range_rate"]

        if actual_closing >= desired_closing:
            # Closing fast enough — coast (no thrust)
            thrust = 0.0
        elif actual_closing < -5.0:
            # Opening — need to reverse. Use approach_brake instead
            # (the phase transition will handle this via rel_speed check)
            thrust = 0.0
        else:
            # Need to close faster — thrust proportional to ABSOLUTE speed
            # deficit (not normalized), so farther targets with larger
            # deficits get proportionally more thrust.
            speed_deficit = desired_closing - actual_closing
            thrust_frac = speed_deficit / 500.0 * self.max_thrust
            thrust = self._clamp_thrust(max(0.02, min(self.max_thrust, thrust_frac)))

        return {"thrust": thrust,
                "heading": {
                    "yaw": heading.get("yaw", 0),
                    "pitch": self.ship.orientation.get("pitch", 0),
                    "roll": self.ship.orientation.get("roll", 0),
                }}

    def _compute_approach(self, target, rel: Dict, current_range: float,
                          rel_speed: float) -> Dict:
        """Velocity-governed approach: desired closing speed proportional to range.

        Uses a P controller that targets a closing speed proportional to
        distance.  Far from the target the desired speed is high (up to
        APPROACH_SPEED_LIMIT), near the target it tapers to near-zero.
        The thrust is then proportional to (desired_speed - actual_speed),
        which naturally prevents both overshooting and stalling.

        When closing faster than desired, the ship points retrograde and
        brakes.  When closing slower (or drifting away), it points prograde
        and thrusts.  This eliminates the mini-oscillation where the old
        proportional-thrust approach would build speed, hit the speed
        limit, mini-brake, rotate back, and repeat.
        """
        # Desired closing speed: proportional to distance, capped at
        # APPROACH_SPEED_LIMIT.  Linear ramp from 0 at 100m (the
        # "zero speed" target) to APPROACH_SPEED_LIMIT at approach_range.
        # Uses a fixed 100m target rather than stationkeep_range because
        # stationkeep_range is widened for handoff (5 km) but the speed
        # ramp should taper to zero near the target, not at 5 km.
        approach_zero_range = 100.0  # metres — where desired_closing = 0
        effective_range = max(current_range - approach_zero_range, 0.0)
        effective_approach = self.approach_range - approach_zero_range
        if effective_approach > 0:
            speed_frac = min(effective_range / effective_approach, 1.0)
        else:
            speed_frac = 0.0
        desired_closing = speed_frac * self.APPROACH_SPEED_LIMIT

        # Actual closing speed along the line to target (positive = closing)
        actual_closing = -rel["range_rate"]

        a_max = self._get_effective_accel()

        # Moving-target compensation: if the target is receding faster
        # than the stationkeep threshold, the range-proportional
        # desired_closing is not enough -- we need extra speed just to
        # overcome the recession before we can even begin closing.
        # Without this, the P-controller aims for e.g. 200 m/s closing
        # but the target flees at 500 m/s, so the ship falls behind and
        # eventually triggers APPROACH->BURN.
        #
        # Guards:
        #   - Only activate for significant recession (above
        #     stationkeep_speed) to avoid amplifying micro-oscillation.
        #   - Only activate at long range (> approach_range).  At short
        #     range, negative actual_closing usually means the ship
        #     overshot during initial braking, not that the target is
        #     fleeing.  Boosting desired_closing during overshoot
        #     recovery worsens the oscillation and lands the ship in
        #     a different (non-converging) limit cycle.
        if (actual_closing < -self.stationkeep_speed
                and current_range > self.approach_range):
            recession_rate = -actual_closing  # positive magnitude
            # Overcome the full recession plus a convergence margin
            # (half the range-proportional speed) so we actually close.
            desired_closing = max(desired_closing,
                                  recession_rate + desired_closing * 0.5)

        # Braking-distance safety cap: never target a closing speed the
        # ship can't brake from before reaching the target.
        max_safe_speed = float("inf")  # default: no cap if a_max unavailable  If the
        # target suddenly stops (drive destroyed), the ship must be able
        # to decelerate within 80% of current range.  Without this cap,
        # the recession-boosted desired_closing could build so much
        # speed that the ship overshoots and enters a flyby loop.
        if a_max > 0 and current_range > self.stationkeep_range:
            max_safe_speed = math.sqrt(2.0 * a_max * current_range * 0.8)
            desired_closing = min(desired_closing, max_safe_speed)

        # Total-velocity overshoot guard: the P-controller targets radial
        # closing speed, but the ship may also have significant lateral
        # velocity.  At closest approach, lateral velocity converts to
        # radial (opening), causing overshoot.  If TOTAL relative speed
        # exceeds what's safe for the current range, force braking
        # regardless of closing speed.  This prevents the scenario where
        # the ship maintains 500+ m/s at 15 km range, overshoots, and
        # triggers APPROACH->BURN.
        if a_max > 0 and rel_speed > max_safe_speed:
            # Ship is going too fast for this range — must slow down.
            # Override speed_error to force retrograde thrust.
            speed_error = -(rel_speed - max_safe_speed)
        else:
            # Speed error: positive = close faster, negative = too fast.
            speed_error = desired_closing - actual_closing

        # Proportional thrust: scale by the ratio of speed error to max accel
        # so the response is smooth across different ship sizes.
        # Time constant: how many seconds of full thrust to correct the error
        tau = 5.0  # seconds -- overdamped for stability
        thrust_frac = abs(speed_error) / (a_max * tau) if a_max > 0 else 0.05

        # Thrust cap: when already closing on target, cap at 0.5 to keep
        # the approach gentle and avoid overshoot.  But when the ship is
        # falling behind a fleeing target (opening), allow full thrust --
        # the gentle cap made it physically impossible to catch up when
        # the target was accelerating away at > 0.5 * max_thrust.
        if (speed_error > 0 and actual_closing < -self.stationkeep_speed
                and current_range > self.approach_range):
            # Far out and significantly opening -- need full authority
            # to overcome target recession.  The range guard prevents
            # this from triggering during short-range overshoot recovery.
            thrust_cap = 1.0
        else:
            thrust_cap = 0.5
        thrust_frac = max(0.02, min(thrust_frac, thrust_cap))
        thrust = self._clamp_thrust(thrust_frac * self.max_thrust)

        # Compute thrust direction.  At long range (> approach_range),
        # use simple prograde/retrograde (radial-only P-controller).
        # At close range (<= approach_range), use velocity-matching:
        # point toward the delta-v vector that would give us the desired
        # velocity toward the target.  This handles both radial AND
        # lateral components, preventing the spiral drift pattern where
        # the radial-only controller builds lateral velocity it can't
        # correct.
        target_pos = target.position if hasattr(target, "position") else target

        if current_range <= self.approach_range:
            # Close-range: velocity-matching mode.
            # Desired velocity: point toward target at desired_closing speed.
            to_target = subtract_vectors(target_pos, self.ship.position)
            dist = magnitude(to_target)
            if dist > 0.01:
                # Desired velocity vector: toward target at desired_closing
                scale = desired_closing / dist
                desired_vel = {
                    "x": to_target["x"] * scale,
                    "y": to_target["y"] * scale,
                    "z": to_target["z"] * scale,
                }
                # Delta-v: desired - current
                delta_v = subtract_vectors(
                    desired_vel,
                    {"x": self.ship.velocity["x"] - (target.velocity["x"] if hasattr(target, "velocity") else 0),
                     "y": self.ship.velocity["y"] - (target.velocity["y"] if hasattr(target, "velocity") else 0),
                     "z": self.ship.velocity["z"] - (target.velocity["z"] if hasattr(target, "velocity") else 0)},
                )
                dv_mag = magnitude(delta_v)
                if dv_mag > 0.01:
                    heading = vector_to_heading(delta_v)
                    # Thrust proportional to delta-v magnitude
                    thrust_frac = min(dv_mag / (a_max * 5.0), thrust_cap) if a_max > 0 else 0.05
                    thrust = self._clamp_thrust(max(0.02, thrust_frac) * self.max_thrust)
                else:
                    heading = self.ship.orientation
                    thrust = 0.0
            else:
                heading = self.ship.orientation
                thrust = 0.0
        elif speed_error >= 0:
            # Long-range: need to close faster — thrust toward target
            vec = subtract_vectors(target_pos, self.ship.position)
            heading = vector_to_heading(vec)
        else:
            # Long-range: closing too fast — brake retrograde
            heading = self._retrograde_heading(rel)

        # Yaw-only heading: constrain to single-axis rotation to prevent
        # the multi-axis PD controller instability that causes the RCS to
        # spin the ship (same issue as the FLIP/BRAKE fix).
        return {"thrust": thrust, "heading": {
            "yaw": heading.get("yaw", 0),
            "pitch": self.ship.orientation.get("pitch", 0),
            "roll": self.ship.orientation.get("roll", 0),
        }}

    def _compute_stationkeep(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Close remaining range and dock using a unified delta-v controller.

        Instead of alternating between retrograde (kill speed) and prograde
        (creep toward target) — which required 180° rotations every few
        seconds — use a single velocity-matching controller:

        1. Compute desired velocity: toward target at a range-proportional speed
        2. Compute delta-v: desired velocity minus current relative velocity
        3. Thrust along the delta-v vector with proportional magnitude

        The heading tracks the delta-v direction continuously, so heading
        changes are small (typically <30°) and the alignment guard rarely
        blocks thrust.  This eliminates the rotation waste that made the
        old two-phase controller take 500+ seconds.
        """
        target = self.get_target()
        if not target:
            return None

        target_pos = target.position if hasattr(target, "position") else target
        target_vel = target.velocity if hasattr(target, "velocity") else {"x": 0, "y": 0, "z": 0}

        rel = calculate_relative_motion(self.ship, target)
        rel_speed = magnitude(rel["relative_velocity_vector"])
        current_range = rel["range"]

        # Within docking range and slow enough — done
        if current_range < 50.0 and rel_speed < 1.0:
            self.status = "docking_ready"
            return {"thrust": 0.0, "heading": self.ship.orientation}

        # Taper to sub-1 m/s closure near the docking envelope so the
        # docking system's <50m / <1m/s criterion is actually reachable.
        # The old floor of 1.5 m/s kept the ship perpetually too "hot" to dock.
        if current_range <= 100.0:
            desired_speed = max(0.2, current_range / 60.0)
        else:
            desired_speed = max(0.4, min(12.0, math.sqrt(current_range) * 0.18))

        # Desired velocity vector: toward target at desired_speed
        to_target = subtract_vectors(target_pos, self.ship.position)
        dist = magnitude(to_target)
        if dist < 0.01:
            return {"thrust": 0.0, "heading": self.ship.orientation}

        scale = desired_speed / dist
        desired_vel = {
            "x": to_target["x"] * scale + target_vel["x"],
            "y": to_target["y"] * scale + target_vel["y"],
            "z": to_target["z"] * scale + target_vel["z"],
        }

        # Delta-v: what velocity change is needed
        delta_v = {
            "x": desired_vel["x"] - self.ship.velocity["x"],
            "y": desired_vel["y"] - self.ship.velocity["y"],
            "z": desired_vel["z"] - self.ship.velocity["z"],
        }
        dv_mag = magnitude(delta_v)

        if dv_mag < 0.1:
            # Already at desired velocity — coast
            return {"thrust": 0.0, "heading": self.ship.orientation}

        # Heading: along delta-v direction
        heading = vector_to_heading(delta_v)

        # Proportional thrust: scale with delta-v magnitude
        # Tau = 3s time constant — responsive but not twitchy
        a_max = self._get_max_accel() * self.max_thrust
        if a_max > 0:
            thrust_frac = min(0.30, dv_mag / (a_max * 3.0))
        else:
            thrust_frac = 0.05
        thrust_frac = max(0.02, thrust_frac)

        cmd = {
            "thrust": self._clamp_thrust(thrust_frac),
            "heading": {
                "yaw": heading.get("yaw", 0),
                "pitch": self.ship.orientation.get("pitch", 0),
                "roll": self.ship.orientation.get("roll", 0),
            },
        }

        # Alignment guard: cosine scaling for misalignment
        if cmd["thrust"] > 0:
            heading_err = self._heading_error(cmd["heading"])
            if heading_err > 90.0:
                cmd["thrust"] = 0.0
            elif heading_err > 5.0:
                cmd["thrust"] *= max(0.0, math.cos(math.radians(heading_err)))

        return cmd

    # ----- heading helpers -------------------------------------------------

    def _retrograde_heading(self, rel: Dict) -> Dict:
        """Heading that opposes the ship's velocity relative to target.

        rel_vel = target_vel - ship_vel, so the ship's own motion toward
        target is -rel_vel.  Pointing along +rel_vel is retrograde.
        """
        rv = rel["relative_velocity_vector"]
        retro = {"x": rv["x"], "y": rv["y"], "z": rv["z"]}
        if magnitude(retro) < 0.01:
            return self.ship.orientation
        return vector_to_heading(retro)

    def _heading_is_retrograde(self, rel: Dict) -> bool:
        """True if ship heading is within FLIP_TOLERANCE_DEG of retrograde."""
        desired = self._retrograde_heading(rel)
        cur = self.ship.orientation
        yaw_err = abs(self._normalize_angle(
            desired.get("yaw", 0) - cur.get("yaw", 0)))
        pitch_err = abs(self._normalize_angle(
            desired.get("pitch", 0) - cur.get("pitch", 0)))
        return yaw_err < self.FLIP_TOLERANCE_DEG and pitch_err < self.FLIP_TOLERANCE_DEG

    def _heading_error(self, desired_heading: Optional[Dict]) -> float:
        """Angular error between ship's current orientation and a desired heading.

        Computes the max of yaw and pitch error so that ANY axis being
        significantly misaligned triggers the guard.  This is the right
        metric because thrust acts along the ship's nose -- even pure
        pitch misalignment sends thrust off-course.

        Args:
            desired_heading: Target heading {yaw, pitch, ...} in degrees,
                             or None (returns 0.0 -- no error if no heading).

        Returns:
            Maximum of absolute yaw error and absolute pitch error in degrees.
        """
        if desired_heading is None:
            return 0.0
        cur = self.ship.orientation
        yaw_err = abs(self._normalize_angle(
            desired_heading.get("yaw", 0) - cur.get("yaw", 0)))
        pitch_err = abs(self._normalize_angle(
            desired_heading.get("pitch", 0) - cur.get("pitch", 0)))
        return max(yaw_err, pitch_err)

    def _flip_heading_aligned(self, rel: Optional[Dict] = None) -> bool:
        """True if ship yaw is within FLIP_TOLERANCE_DEG of the snapshot heading.

        Only checks yaw alignment — pitch/roll are irrelevant for the flip
        because the BRAKE phase will correct them using the full 3D retrograde
        heading.  Requiring pitch alignment was causing 17% of flips to timeout
        when the ship had accumulated pitch drift during the burn phase.

        Falls back to live retrograde if no snapshot is available (e.g. when
        phase was set externally without going through BURN->FLIP transition).
        """
        target_heading = self._flip_target_heading
        if target_heading is None and rel is not None:
            target_heading = self._retrograde_heading(rel)
        if target_heading is None:
            return False
        cur = self.ship.orientation
        yaw_err = abs(self._normalize_angle(
            target_heading.get("yaw", 0) - cur.get("yaw", 0)))
        return yaw_err < self.FLIP_TOLERANCE_DEG

    # ----- state / telemetry -----------------------------------------------

    def get_state(self) -> Dict:
        """Rich state dict for GUI: phase, range, closing_speed,
        braking_distance, time_to_arrival, profile, status_text."""
        state = super().get_state()
        state["phase"] = self.phase
        state["profile"] = self.profile_name

        target = self.get_target()
        if not target:
            state["status_text"] = "Target lost"
            return state

        rel = calculate_relative_motion(self.ship, target)
        current_range = rel["range"]
        closing_speed = max(-rel["range_rate"], 0.0)
        a_max = self._get_effective_accel()
        d_brake = self._braking_distance(closing_speed, a_max)
        eta = self._estimate_eta(current_range, closing_speed, a_max)

        state.update({
            "range": current_range,
            "closing_speed": closing_speed,
            "braking_distance": d_brake,
            "flip_time_estimate": self._estimate_flip_time(),
            "time_to_arrival": eta,
            "status_text": self._build_status_text(current_range, eta),
        })
        return state

    def _estimate_eta(self, distance: float, closing_speed: float,
                      a_max: float) -> Optional[float]:
        """ETA in seconds, or None if indeterminate.

        Models the actual multi-phase trajectory:
        - BURN/FLIP: brachistochrone for distance ABOVE approach_range only
        - BRAKE: v/a deceleration time
        - APPROACH: sqrt-taper integral from current speed to stationkeep speed
        - STATIONKEEP: sqrt-proportional creep to dock (~100-200s)

        Key fixes:
        - BURN/FLIP brachistochrone covers only the burn leg, not full distance
          (approach_eta covers the rest — no double-counting)
        - Stationkeep uses the delta-v controller's actual sqrt(range)*0.3
          speed model, not a flat 2 m/s guess
        """
        v_high = self.approach_coast_speed
        v_low = self.stationkeep_speed
        taper_span = max(self.approach_range - self.stationkeep_range, 1.0)

        # --- Stationkeep ETA: sqrt-proportional speed model ---
        # The delta-v controller targets sqrt(range)*0.3, clamped [0.5, 15].
        # Integrate dr/v(r) from stationkeep_range to 50m (dock).
        # Numerically: ~100-200s depending on stationkeep_range.
        sk_dist = max(self.stationkeep_range - 50.0, 0.0)
        if sk_dist > 1.0:
            avg_sk_speed = max(1.0, math.sqrt(self.stationkeep_range) * 0.5)
            stationkeep_eta = sk_dist / avg_sk_speed * 0.7
        else:
            stationkeep_eta = 0.0

        if self.phase == "stationkeep":
            if distance > 1.0:
                # The delta-v controller targets sqrt(range)*0.3 but
                # overshoots slightly, giving ~50% higher average speed.
                # Empirically, convergence takes ~60% of naive estimate.
                avg_speed = max(1.0, math.sqrt(distance) * 0.5)
                return distance / avg_speed * 0.7
            return 0.0

        # --- Approach taper ETA from current position ---
        def _taper_eta_from(range_m: float) -> float:
            """Time to coast from range_m to stationkeep_range via taper."""
            if range_m <= self.stationkeep_range:
                return 0.0
            above = max(0.0, range_m - self.approach_range)
            above_t = above / v_high if above > 0 and v_high > 0 else 0.0
            in_taper = min(range_m - self.stationkeep_range,
                           self.approach_range - self.stationkeep_range)
            if in_taper > 0 and v_high > v_low > 0:
                frac = in_taper / taper_span
                v_cur = v_low + (v_high - v_low) * math.sqrt(frac)
                if v_cur > v_low * 1.01:
                    # Sqrt taper: v(r) = v_lo + (v_hi-v_lo)*sqrt(r/R)
                    # The log-mean gives the correct harmonic average:
                    # avg = (v_hi - v_lo) / ln(v_hi / v_lo)
                    log_mean = (v_cur - v_low) / math.log(v_cur / v_low)
                    taper_t = in_taper / log_mean
                else:
                    taper_t = in_taper / max(v_low, 1.0)
            else:
                taper_t = in_taper / max(v_high * 0.5, 1.0)
            return above_t + taper_t

        if self.phase in ("burn", "flip"):
            if a_max > 0 and distance > 0:
                # Brachistochrone only for the burn+brake leg
                # (distance above approach_range)
                burn_dist = max(0.0, distance - self.approach_range)
                if burn_dist > 0:
                    burn_brake_t = 2.0 * math.sqrt(burn_dist / a_max)
                else:
                    burn_brake_t = 0.0
                approach_t = _taper_eta_from(min(distance, self.approach_range))
                return burn_brake_t + approach_t + stationkeep_eta
            return None

        if self.phase == "brake":
            brake_t = closing_speed / a_max if a_max > 0 else 0.0
            approach_t = _taper_eta_from(distance)
            return brake_t + approach_t + stationkeep_eta

        if self.phase in ("approach_decel", "approach_rotate"):
            sub_phase_t = 15.0
            approach_t = _taper_eta_from(distance)
            return sub_phase_t + approach_t + stationkeep_eta

        if self.phase in ("approach_coast", "approach", "approach_creep",
                         "approach_drift", "approach_brake"):
            approach_t = _taper_eta_from(distance)
            return approach_t + stationkeep_eta

        return None

    def _build_status_text(self, distance: float,
                           eta: Optional[float]) -> str:
        """Human-readable one-liner for the GUI."""
        d = _format_distance(distance)
        t = _format_time(eta) if eta is not None else "unknown"
        if self.phase == "burn":
            return f"Burning toward target -- {d}, ETA {t}"
        if self.phase == "flip":
            return "Flipping for deceleration burn"
        if self.phase == "brake":
            return f"Braking -- {d} remaining, ETA {t}"
        if self.phase in ("approach_brake", "approach_decel"):
            return f"Approach braking -- {d} remaining, ETA {t}"
        if self.phase == "approach_rotate":
            return f"Rotating for approach -- {d} remaining"
        if self.phase in ("approach", "approach_creep", "approach_drift",
                          "approach_coast"):
            return f"Final approach -- {d} remaining, ETA {t}"
        return f"Station-keeping at {d}"


# ----- module-level formatting helpers ------------------------------------

def _format_distance(metres: float) -> str:
    """Format a distance for display."""
    if metres >= 1_000_000:
        return f"{metres / 1000:.0f}km"
    if metres >= 1_000:
        return f"{metres / 1000:.1f}km"
    return f"{metres:.0f}m"

def _format_time(seconds: float) -> str:
    """Format seconds into a compact human string."""
    if seconds < 0:
        return "0s"
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"
