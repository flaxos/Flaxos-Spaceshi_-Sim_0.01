# hybrid/navigation/autopilot/orbit.py
"""Orbit autopilot - maintains circular orbit around a point."""

import logging
import math
from typing import Dict, Optional

from hybrid.navigation.autopilot.base import BaseAutopilot
from hybrid.navigation.relative_motion import vector_to_heading
from hybrid.utils.math_utils import (
    subtract_vectors, magnitude, normalize_vector, dot_product, scale_vector,
    add_vectors,
)

logger = logging.getLogger(__name__)


class OrbitAutopilot(BaseAutopilot):
    """Autopilot that maintains a circular orbit around a fixed point.

    Phases:
        APPROACH   - fly toward the orbit insertion point
        CIRCULARIZE - match tangential velocity at the orbit radius
        ORBIT      - steady-state station-keeping on the circle
    """

    PHASE_APPROACH = "APPROACH"
    PHASE_CIRCULARIZE = "CIRCULARIZE"
    PHASE_ORBIT = "ORBIT"

    def __init__(self, ship, target_id: Optional[str] = None, params: Dict = None):
        """Initialize orbit autopilot.

        Args:
            ship: Ship under control.
            target_id: Unused (orbiting a fixed point).
            params: Additional parameters:
                - center: Dict {x, y, z} of orbit center (required).
                - radius: Orbit radius in metres (required, > 0).
                - speed: Desired orbital speed in m/s (optional, default computed
                  from max accel to keep comfortable centripetal acceleration).
                - direction: 1 for counter-clockwise, -1 for clockwise (default 1).
                - max_thrust: Maximum thrust fraction (0..1, default 1.0).
                - tolerance: Radius tolerance in metres (default 50.0).
        """
        super().__init__(ship, target_id, params or {})

        center = self.params.get("center") or {
            "x": self.params.get("x"),
            "y": self.params.get("y"),
            "z": self.params.get("z"),
        }
        self.center = center
        self.radius = float(self.params.get("radius", 0))
        self.direction = int(self.params.get("direction", 1))
        self.max_thrust = float(self.params.get("max_thrust", 1.0))
        self.tolerance = float(self.params.get("tolerance", 50.0))

        # Desired orbital speed - default: v such that a_c = 0.5 * max_accel
        self.desired_speed: Optional[float] = None
        speed_param = self.params.get("speed")
        if speed_param is not None:
            self.desired_speed = float(speed_param)

        self.phase = self.PHASE_APPROACH
        self.completed = False
        self.status = "active"

        if not self._center_is_valid() or self.radius <= 0:
            self.status = "error"
            self.error_message = "Orbit requires valid center {x,y,z} and radius > 0"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _center_is_valid(self) -> bool:
        """Return True if center coordinates are all present and numeric."""
        return all(
            k in self.center and self.center[k] is not None
            for k in ("x", "y", "z")
        )

    def _get_max_accel(self) -> float:
        """Return maximum linear acceleration (m/s^2)."""
        propulsion = self.ship.systems.get("propulsion")
        if propulsion and hasattr(propulsion, "max_thrust") and self.ship.mass > 0:
            return max(propulsion.max_thrust / self.ship.mass, 0.01)
        return 0.01

    def _get_orbital_speed(self) -> float:
        """Return desired orbital speed."""
        if self.desired_speed is not None:
            return self.desired_speed
        # Default: centripetal accel = 0.5 * max_accel  =>  v = sqrt(a * r)
        max_accel = self._get_max_accel()
        return math.sqrt(0.5 * max_accel * self.radius)

    # ------------------------------------------------------------------
    # Main compute
    # ------------------------------------------------------------------

    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute thrust/heading for orbit maintenance.

        Args:
            dt: Time delta.
            sim_time: Current simulation time.

        Returns:
            dict with thrust and heading, or None on error.
        """
        if self.status == "error":
            return None

        vec_to_center = subtract_vectors(self.center, self.ship.position)
        dist_to_center = magnitude(vec_to_center)

        # Phase transitions --------------------------------------------------
        on_circle = abs(dist_to_center - self.radius) < self.tolerance

        if self.phase == self.PHASE_APPROACH and on_circle:
            self.phase = self.PHASE_CIRCULARIZE
            logger.info("Orbit: switching to CIRCULARIZE phase")

        if self.phase == self.PHASE_CIRCULARIZE:
            tangential_error = self._tangential_velocity_error(vec_to_center, dist_to_center)
            if tangential_error < 2.0 and on_circle:
                self.phase = self.PHASE_ORBIT
                self.completed = True
                logger.info("Orbit: switching to ORBIT phase (steady state)")

        # Phase execution -----------------------------------------------------
        if self.phase == self.PHASE_APPROACH:
            return self._compute_approach(vec_to_center, dist_to_center)
        elif self.phase == self.PHASE_CIRCULARIZE:
            return self._compute_circularize(vec_to_center, dist_to_center)
        else:
            return self._compute_orbit(vec_to_center, dist_to_center)

    # ------------------------------------------------------------------
    # Phase logic
    # ------------------------------------------------------------------

    def _compute_approach(self, vec_to_center: Dict, dist: float) -> Dict:
        """Fly toward the orbit insertion point on the circle."""
        self.status = "approaching"

        # Target point is the closest point on the circle
        if dist < 0.001:
            # Already at center - pick arbitrary direction
            target_point = add_vectors(self.center, {"x": self.radius, "y": 0, "z": 0})
        else:
            direction_from_center = normalize_vector(
                subtract_vectors(self.ship.position, self.center)
            )
            target_point = add_vectors(
                self.center, scale_vector(direction_from_center, self.radius)
            )

        vec_to_target = subtract_vectors(target_point, self.ship.position)
        dist_to_target = magnitude(vec_to_target)

        if dist_to_target < 1.0:
            return {"thrust": 0.0, "heading": self.ship.orientation}

        heading = vector_to_heading(vec_to_target)

        # Simple proportional thrust
        speed = magnitude(self.ship.velocity)
        max_accel = self._get_max_accel()
        braking_dist = (speed ** 2) / (2 * max_accel) if speed > 0 else 0

        if dist_to_target <= braking_dist + self.tolerance:
            # Brake
            brake_vec = {
                "x": -self.ship.velocity["x"],
                "y": -self.ship.velocity["y"],
                "z": -self.ship.velocity["z"],
            }
            heading = vector_to_heading(brake_vec) if speed > 0.1 else heading
            return {"thrust": self._clamp_thrust(self.max_thrust), "heading": heading}

        return {"thrust": self._clamp_thrust(self.max_thrust), "heading": heading}

    def _compute_circularize(self, vec_to_center: Dict, dist: float) -> Dict:
        """Null radial velocity and build tangential velocity."""
        self.status = "circularizing"
        desired_vel = self._desired_velocity(vec_to_center, dist)
        return self._steer_to_velocity(desired_vel)

    def _compute_orbit(self, vec_to_center: Dict, dist: float) -> Dict:
        """Steady-state orbit station-keeping."""
        self.status = "orbiting"
        desired_vel = self._desired_velocity(vec_to_center, dist)
        return self._steer_to_velocity(desired_vel)

    # ------------------------------------------------------------------
    # Velocity helpers
    # ------------------------------------------------------------------

    def _desired_velocity(self, vec_to_center: Dict, dist: float) -> Dict:
        """Compute the desired velocity for circular orbit at current position.

        Includes a radial correction term to nudge back toward the orbit circle.
        """
        if dist < 0.001:
            return {"x": 0, "y": 0, "z": 0}

        # Tangential direction (perpendicular to radial, in the XY plane).
        radial = normalize_vector(vec_to_center)
        tangent = {
            "x": -radial["y"] * self.direction,
            "y": radial["x"] * self.direction,
            "z": 0.0,
        }

        orbital_speed = self._get_orbital_speed()
        desired = scale_vector(tangent, orbital_speed)

        # Radial correction: nudge inward/outward to stay on circle
        radius_error = dist - self.radius  # positive = too far from center
        correction_speed = max(-orbital_speed * 0.3, min(orbital_speed * 0.3, radius_error * 0.5))
        correction = scale_vector(radial, correction_speed)
        desired = add_vectors(desired, correction)

        return desired

    def _tangential_velocity_error(self, vec_to_center: Dict, dist: float) -> float:
        """Return magnitude of velocity error vs desired orbit velocity."""
        desired = self._desired_velocity(vec_to_center, dist)
        error = subtract_vectors(desired, self.ship.velocity)
        return magnitude(error)

    def _steer_to_velocity(self, desired_vel: Dict) -> Dict:
        """Steer toward the desired velocity vector."""
        vel_error = subtract_vectors(desired_vel, self.ship.velocity)
        error_mag = magnitude(vel_error)

        if error_mag < 0.5:
            return {"thrust": 0.0, "heading": self.ship.orientation}

        heading = vector_to_heading(vel_error)
        # Proportional thrust
        if error_mag < 5.0:
            thrust = 0.1 + (error_mag / 5.0) * 0.4
        elif error_mag < 20.0:
            thrust = 0.5
        else:
            thrust = self.max_thrust

        return {"thrust": self._clamp_thrust(thrust), "heading": heading}

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> Dict:
        """Get orbit autopilot state."""
        state = super().get_state()
        vec_to_center = subtract_vectors(self.center, self.ship.position)
        dist = magnitude(vec_to_center)
        state.update({
            "phase": self.phase,
            "center": self.center,
            "radius": self.radius,
            "current_distance": dist,
            "radius_error": abs(dist - self.radius),
            "orbital_speed": self._get_orbital_speed(),
            "direction": self.direction,
            "complete": self.completed,
        })
        return state
