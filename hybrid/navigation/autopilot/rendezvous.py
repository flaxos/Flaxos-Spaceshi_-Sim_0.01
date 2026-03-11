# hybrid/navigation/autopilot/rendezvous.py
"""Rendezvous autopilot - flip-and-burn trajectory to arrive at a target
with near-zero relative velocity.  Burn -> flip -> brake -> stationkeep."""

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


class RendezvousAutopilot(BaseAutopilot):
    """Flip-and-burn autopilot for arriving at a stationary or slow target.

    Phases:
        burn        - Accelerate toward target.
        flip        - Rotate 180 degrees to face retrograde.
        brake       - Decelerate toward target.
        stationkeep - Hold position via MatchVelocityAutopilot.
    """

    STATIONKEEP_RANGE = 100.0       # metres
    STATIONKEEP_SPEED = 1.0         # m/s relative
    FLIP_TOLERANCE_DEG = 10.0       # degrees
    # Start braking slightly early to avoid overshooting
    BRAKE_MARGIN = 1.05

    def __init__(self, ship, target_id: Optional[str] = None,
                 params: Optional[Dict] = None):
        """Initialise rendezvous autopilot.

        Args:
            ship: Ship under autopilot control.
            target_id: Sensor contact ID of the target.
            params: Optional overrides -- max_thrust (0-1),
                    stationkeep_range (m), stationkeep_speed (m/s).
        """
        super().__init__(ship, target_id, params or {})
        self.max_thrust: float = self.params.get("max_thrust", 1.0)
        self.stationkeep_range: float = self.params.get(
            "stationkeep_range", self.STATIONKEEP_RANGE)
        self.stationkeep_speed: float = self.params.get(
            "stationkeep_speed", self.STATIONKEEP_SPEED)
        self.phase: str = "burn"
        self._match_ap: Optional[MatchVelocityAutopilot] = None
        self.status = "active"
        if not target_id:
            self.status = "error"
            self.error_message = "No target specified for rendezvous"

    def _get_max_accel(self) -> float:
        """Max linear acceleration (m/s^2) from propulsion, with safe floor."""
        propulsion = self.ship.systems.get("propulsion")
        if propulsion and hasattr(propulsion, "max_thrust") and self.ship.mass > 0:
            return max(propulsion.max_thrust / self.ship.mass, 0.01)
        return 0.01

    @staticmethod
    def _braking_distance(speed: float, accel: float) -> float:
        """Kinematic braking distance: d = v^2 / (2a)."""
        if accel <= 0:
            return float("inf")
        return (speed * speed) / (2.0 * accel)

    # ----- core compute ------------------------------------------------

    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute thrust/heading command for this tick.

        Args:
            dt: Simulation time step (seconds).
            sim_time: Current simulation clock (seconds).
        Returns:
            ``{thrust, heading}`` or ``None`` on error.
        """
        target = self.get_target()
        if not target:
            self.status = "error"
            self.error_message = f"Target {self.target_id} not found"
            return None

        rel = calculate_relative_motion(self.ship, target)
        current_range: float = rel["range"]
        closing_speed: float = -rel["range_rate"] if rel["closing"] else 0.0

        # Station-keep handoff (highest priority)
        rel_speed = magnitude(rel["relative_velocity_vector"])
        if current_range <= self.stationkeep_range and rel_speed < self.stationkeep_speed:
            self.phase = "stationkeep"
            self.status = "stationkeeping"
            return self._compute_stationkeep(dt, sim_time)

        a_max = self._get_max_accel()
        d_brake = self._braking_distance(closing_speed, a_max) * self.BRAKE_MARGIN

        # Phase transitions
        if self.phase == "burn":
            if closing_speed > 0 and current_range <= d_brake:
                logger.info(
                    "Rendezvous: BURN -> FLIP at range %.0f m, "
                    "closing %.1f m/s, d_brake %.0f m",
                    current_range, closing_speed, d_brake)
                self.phase = "flip"
        elif self.phase == "flip":
            if self._heading_is_retrograde(rel):
                logger.info("Rendezvous: FLIP -> BRAKE (aligned retrograde)")
                self.phase = "brake"
        elif self.phase == "brake":
            if closing_speed <= 0 and current_range > self.stationkeep_range:
                logger.info("Rendezvous: BRAKE -> BURN (lost closing speed)")
                self.phase = "burn"

        # Execute current phase
        if self.phase == "burn":
            self.status = "burning"
            return self._compute_burn(target)
        elif self.phase == "flip":
            self.status = "flipping"
            return self._compute_flip(rel)
        elif self.phase == "brake":
            self.status = "braking"
            return self._compute_brake(rel)
        return self._compute_stationkeep(dt, sim_time)

    # ----- phase implementations ---------------------------------------

    def _compute_burn(self, target) -> Dict:
        """Accelerate toward the target."""
        target_pos = target.position if hasattr(target, "position") else target
        vec = subtract_vectors(target_pos, self.ship.position)
        return {"thrust": self._clamp_thrust(self.max_thrust),
                "heading": vector_to_heading(vec)}

    def _compute_flip(self, rel: Dict) -> Dict:
        """Command retrograde heading, zero thrust while RCS rotates."""
        return {"thrust": 0.0, "heading": self._retrograde_heading(rel)}

    def _compute_brake(self, rel: Dict) -> Dict:
        """Thrust retrograde to bleed closing speed."""
        return {"thrust": self._clamp_thrust(self.max_thrust),
                "heading": self._retrograde_heading(rel)}

    def _compute_stationkeep(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Delegate to MatchVelocityAutopilot for station-keeping."""
        if self._match_ap is None:
            self._match_ap = MatchVelocityAutopilot(
                self.ship, self.target_id,
                {"tolerance": 0.5, "max_thrust": self.max_thrust})
        return self._match_ap.compute(dt, sim_time)

    # ----- heading helpers ---------------------------------------------

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

    # ----- state / telemetry -------------------------------------------

    def get_state(self) -> Dict:
        """Rich state dict for GUI: phase, range, closing_speed,
        braking_distance, time_to_arrival, status_text."""
        state = super().get_state()
        state["phase"] = self.phase

        target = self.get_target()
        if not target:
            state["status_text"] = "Target lost"
            return state

        rel = calculate_relative_motion(self.ship, target)
        current_range = rel["range"]
        closing_speed = -rel["range_rate"] if rel["closing"] else 0.0
        a_max = self._get_max_accel()
        d_brake = self._braking_distance(closing_speed, a_max)
        eta = self._estimate_eta(current_range, closing_speed, a_max)

        state.update({
            "range": current_range,
            "closing_speed": closing_speed,
            "braking_distance": d_brake,
            "time_to_arrival": eta,
            "status_text": self._build_status_text(current_range, eta),
        })
        return state

    def _estimate_eta(self, distance: float, closing_speed: float,
                      a_max: float) -> Optional[float]:
        """Rough ETA in seconds, or None if indeterminate."""
        if self.phase == "stationkeep":
            return 0.0
        if self.phase in ("burn", "flip"):
            # Symmetric brachistochrone: t = 2*sqrt(d/a)
            if a_max > 0 and distance > 0:
                return 2.0 * math.sqrt(distance / a_max)
            return None
        # brake phase: t = v / a
        if a_max > 0 and closing_speed > 0:
            return closing_speed / a_max
        if closing_speed > 0.01:
            return distance / closing_speed
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
        return f"Station-keeping at {d}"


# ----- module-level formatting helpers ---------------------------------

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
