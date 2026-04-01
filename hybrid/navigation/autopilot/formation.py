# hybrid/navigation/autopilot/formation.py
"""Formation autopilot for fleet coordination.

Uses a PD controller to hold position relative to a flagship.
The desired position is the flagship's position plus the formation
offset rotated into the flagship's heading frame.  This means "200m
to starboard" stays to starboard even when the flagship turns.

The controller works in velocity-error space:
  1. Compute desired position from flagship pose + rotated offset.
  2. Derive a desired velocity = flagship_velocity + proportional
     correction toward the desired position, capped so the ship
     never builds more speed than it can brake from at close range.
  3. Thrust = gain * (desired_velocity - current_velocity).

A 50m / 0.5 m/s dead zone prevents jitter from numerical noise
when the ship is already in formation.

Heading always matches the flagship so the formation maintains
orientation as a unit.  Thrust corrections are gentle -- the
controller caps approach speed proportional to distance (max
10 m/s within 200m) to avoid overshoot.

Design notes (why PD, not bang-bang):
  Bang-bang (full thrust forward, full thrust backward) causes
  oscillation when the target position moves each tick (because
  the flagship is maneuvering).  The PD controller produces
  smooth, continuous corrections that converge without overshoot.
  This matches the proven approach-phase logic from rendezvous.py.
"""

import logging
import math
from typing import Dict, Optional

import numpy as np

from hybrid.navigation.autopilot.base import BaseAutopilot
from hybrid.navigation.relative_motion import vector_to_heading

logger = logging.getLogger(__name__)

# -- Dead zone thresholds --------------------------------------------------
# Within this position error, and velocity error below the speed threshold,
# the controller applies NO corrections.  This prevents constant micro-
# thruster firing from numerical noise when nominally in formation.
_DEADZONE_POSITION_M = 50.0
_DEADZONE_VELOCITY_MS = 0.5

# -- Approach speed scaling ------------------------------------------------
# Maximum approach speed within 200m of the desired position.  Beyond 200m
# the cap scales linearly: max_speed = distance * (_MAX_CLOSE_SPEED / 200).
# This prevents building more speed than the ship can brake from when close.
_MAX_CLOSE_SPEED_MS = 10.0
_CLOSE_RANGE_M = 200.0

# -- Controller gains ------------------------------------------------------
# Proportional gain for position->velocity: at 200m error, desired velocity
# correction = 200 * 0.05 = 10 m/s (matches _MAX_CLOSE_SPEED at _CLOSE_RANGE).
_POSITION_GAIN = 0.05

# Derivative gain for velocity error->thrust.  Kept moderate to avoid
# overshoot -- the alignment guard already blocks ~65% of thrust ticks,
# so commanding too much thrust results in jerky corrections.
_VELOCITY_GAIN = 0.3

# Maximum thrust fraction for formation keeping.  Kept low because
# formation corrections should be gentle -- we are not doing a combat burn.
_MAX_FORMATION_THRUST = 0.15


def _rotate_offset_by_heading(
    offset: np.ndarray, heading: Dict[str, float]
) -> np.ndarray:
    """Rotate a local-frame offset into world space using the flagship's heading.

    The formation offset is defined in the flagship's local frame:
      +X = forward (along heading), +Y = port (left), +Z = up.
    We rotate it by the flagship's yaw (and pitch) to get a world-space
    displacement.  Roll is ignored -- formation offsets are in the
    horizontal plane.

    Args:
        offset: [x, y, z] in flagship local frame.
        heading: Flagship orientation {yaw, pitch, roll} in degrees.

    Returns:
        np.ndarray: [x, y, z] displacement in world space.
    """
    yaw_rad = math.radians(heading.get("yaw", 0.0))
    pitch_rad = math.radians(heading.get("pitch", 0.0))

    cos_yaw = math.cos(yaw_rad)
    sin_yaw = math.sin(yaw_rad)
    cos_pitch = math.cos(pitch_rad)
    sin_pitch = math.sin(pitch_rad)

    # Rotation matrix: Rz(yaw) * Ry(pitch) applied to local offset.
    # local x = forward, y = port, z = up.
    lx, ly, lz = offset[0], offset[1], offset[2]

    # First rotate by pitch around local Y axis, then yaw around Z.
    wx = cos_yaw * cos_pitch * lx - sin_yaw * ly + cos_yaw * sin_pitch * lz
    wy = sin_yaw * cos_pitch * lx + cos_yaw * ly + sin_yaw * sin_pitch * lz
    wz = -sin_pitch * lx + cos_pitch * lz

    return np.array([wx, wy, wz])


class FormationAutopilot(BaseAutopilot):
    """Autopilot to maintain position in fleet formation.

    Continuously tracks flagship and maintains relative position
    according to formation parameters.  Uses a PD controller in
    velocity-error space with a dead zone to prevent jitter.
    """

    def __init__(
        self,
        ship,
        target_id: Optional[str] = None,
        params: Optional[Dict] = None,
    ):
        """Initialize formation autopilot.

        Args:
            ship: Ship under control.
            target_id: Flagship ID to follow.
            params: Additional parameters:
                - formation_position: Relative position [x, y, z] in flagship
                  local frame (meters). +X = forward, +Y = port, +Z = up.
                - tolerance: Position hold tolerance (m), default 50.0.
                - max_thrust: Maximum thrust to use (0-1), default 0.15.
                - match_heading: Match flagship heading, default True.
        """
        super().__init__(ship, target_id, params or {})

        self.flagship_id = target_id
        self.relative_position = np.array(
            self.params.get("formation_position", [0, 0, 0]), dtype=float
        )
        self.tolerance = float(self.params.get("tolerance", _DEADZONE_POSITION_M))
        self.max_thrust = float(
            self.params.get("max_thrust", _MAX_FORMATION_THRUST)
        )
        self.match_heading = bool(self.params.get("match_heading", True))

        # State tracking
        self.target_position = None
        self.target_velocity = None
        self.last_error = 0.0
        self.status = "seeking"

        logger.info(
            "Formation autopilot engaged: following %s, offset %s",
            self.flagship_id,
            self.relative_position,
        )

    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute thrust to maintain formation position.

        PD controller in velocity-error space:
          desired_vel = flagship_vel + proportional_correction(pos_error)
          thrust_cmd  = gain * (desired_vel - current_vel)

        Dead zone: if within tolerance AND velocity-matched, do nothing.

        Args:
            dt: Time delta (seconds).
            sim_time: Current simulation time (seconds).

        Returns:
            dict with {thrust, heading} or None if flagship not found.
        """
        flagship = self._get_flagship()
        if not flagship:
            self.status = "no_flagship"
            self.error_message = f"Flagship {self.flagship_id} not found"
            return None

        # -- Flagship state --
        flagship_pos = np.array([
            flagship.position["x"],
            flagship.position["y"],
            flagship.position["z"],
        ])
        flagship_vel = np.array([
            flagship.velocity["x"],
            flagship.velocity["y"],
            flagship.velocity["z"],
        ])
        flagship_heading = getattr(flagship, "orientation", None) or {
            "yaw": 0.0, "pitch": 0.0, "roll": 0.0,
        }

        # -- Desired position: flagship pos + offset rotated to flagship heading --
        rotated_offset = _rotate_offset_by_heading(
            self.relative_position, flagship_heading
        )
        self.target_position = flagship_pos + rotated_offset

        # -- Own state --
        current_pos = np.array([
            self.ship.position["x"],
            self.ship.position["y"],
            self.ship.position["z"],
        ])
        current_vel = np.array([
            self.ship.velocity["x"],
            self.ship.velocity["y"],
            self.ship.velocity["z"],
        ])

        # -- Position error --
        position_error = self.target_position - current_pos
        error_magnitude = float(np.linalg.norm(position_error))

        # -- Velocity error relative to flagship --
        relative_velocity = current_vel - flagship_vel
        velocity_error_magnitude = float(np.linalg.norm(relative_velocity))

        self.target_velocity = flagship_vel
        self.last_error = error_magnitude

        # -- Dead zone: skip corrections when close enough and velocity-matched --
        if (
            error_magnitude < _DEADZONE_POSITION_M
            and velocity_error_magnitude < _DEADZONE_VELOCITY_MS
        ):
            self.status = "in_formation"
            # Match flagship heading even while coasting in formation
            heading = self._desired_heading(flagship_heading)
            return {"thrust": 0.0, "heading": heading}

        # -- PD controller --
        # Proportional term: desired velocity correction toward target position.
        # Cap the correction speed proportional to distance so we never build
        # more closing speed than we can brake from at close range.
        if error_magnitude > 1e-6:
            error_direction = position_error / error_magnitude
        else:
            error_direction = np.zeros(3)

        # Speed cap: linearly scales with distance, clamped at max
        max_approach_speed = min(
            error_magnitude * (_MAX_CLOSE_SPEED_MS / _CLOSE_RANGE_M),
            _MAX_CLOSE_SPEED_MS * 5.0,  # 50 m/s absolute cap far out
        )
        desired_correction = error_direction * min(
            error_magnitude * _POSITION_GAIN, max_approach_speed
        )

        # Desired velocity = flagship velocity + correction toward position
        desired_velocity = flagship_vel + desired_correction

        # Velocity error: what we need to change
        vel_error = desired_velocity - current_vel
        vel_error_mag = float(np.linalg.norm(vel_error))

        if vel_error_mag < 0.01:
            # Already on the right velocity vector
            self.status = "adjusting" if error_magnitude > self.tolerance else "in_formation"
            heading = self._desired_heading(flagship_heading)
            return {"thrust": 0.0, "heading": heading}

        # Thrust magnitude: proportional to velocity error
        propulsion = self.ship.systems.get("propulsion")
        if propulsion and hasattr(propulsion, "max_thrust") and self.ship.mass > 0:
            max_accel = propulsion.max_thrust / self.ship.mass
        else:
            max_accel = 10.0

        # Desired acceleration from velocity gain
        desired_accel = vel_error_mag * _VELOCITY_GAIN
        thrust_fraction = min(desired_accel / max_accel, self.max_thrust)
        thrust_fraction = self._clamp_thrust(thrust_fraction)

        # Heading: point along the correction vector for thrust to work,
        # BUT only if the correction is significant.  For tiny corrections
        # keep matching flagship heading to avoid heading jitter.
        if vel_error_mag > 1.0:
            thrust_heading = vector_to_heading({
                "x": float(vel_error[0]),
                "y": float(vel_error[1]),
                "z": float(vel_error[2]),
            })
        else:
            thrust_heading = self._desired_heading(flagship_heading)

        # Update status
        if error_magnitude < self.tolerance:
            self.status = "adjusting"
        elif error_magnitude < self.tolerance * 4:
            self.status = "closing"
        else:
            self.status = "seeking"

        # Periodic logging
        if int(sim_time * 10) % 100 == 0:
            logger.debug(
                "Formation: pos_err=%.1fm, vel_err=%.1fm/s, thrust=%.3f, "
                "status=%s",
                error_magnitude,
                velocity_error_magnitude,
                thrust_fraction,
                self.status,
            )

        return {"thrust": thrust_fraction, "heading": thrust_heading}

    def _desired_heading(self, flagship_heading: Dict) -> Dict:
        """Return the heading this ship should hold.

        If match_heading is True, copy flagship heading (the formation
        maintains orientation as a unit).  Otherwise keep current heading.
        """
        if self.match_heading:
            return dict(flagship_heading)
        return dict(self.ship.orientation)

    def update_formation_position(self, new_position: np.ndarray) -> None:
        """Update the relative formation position.

        Args:
            new_position: New relative position [x, y, z] in flagship local frame.
        """
        self.relative_position = np.array(new_position, dtype=float)
        logger.info("Formation position updated to %s", self.relative_position)

    def _get_flagship(self):
        """Get flagship ship object from simulator or sensors."""
        # Primary: direct ship reference via _all_ships_ref (set by hybrid_runner)
        all_ships = getattr(self.ship, "_all_ships_ref", [])
        for ship in all_ships:
            if getattr(ship, "id", None) == self.flagship_id:
                return ship

        # Fallback: simulator reference
        if hasattr(self.ship, "simulator") and self.ship.simulator:
            simulator = self.ship.simulator
            if self.flagship_id in simulator.ships:
                return simulator.ships[self.flagship_id]

        # Last resort: sensor contacts
        sensors = self.ship.systems.get("sensors")
        if sensors and hasattr(sensors, "get_contact"):
            contact = sensors.get_contact(self.flagship_id)
            if contact:

                class _FlagshipProxy:
                    """Wraps sensor contact data to match Ship interface."""

                    def __init__(self, data):
                        pos = data.get("position", {})
                        vel = data.get("velocity", {})
                        self.position = {
                            "x": pos.get("x", 0.0),
                            "y": pos.get("y", 0.0),
                            "z": pos.get("z", 0.0),
                        }
                        self.velocity = {
                            "x": vel.get("x", 0.0),
                            "y": vel.get("y", 0.0),
                            "z": vel.get("z", 0.0),
                        }
                        self.orientation = {
                            "yaw": 0.0,
                            "pitch": 0.0,
                            "roll": 0.0,
                        }

                return _FlagshipProxy(contact)

        return None

    def get_state(self) -> Dict:
        """Get formation autopilot state for telemetry.

        Returns:
            dict: State with formation info, position/velocity errors.
        """
        state = super().get_state()
        state["flagship_id"] = self.flagship_id
        state["formation_position"] = self.relative_position.tolist()
        state["tolerance"] = self.tolerance

        if self.target_position is not None:
            current_pos = np.array([
                self.ship.position["x"],
                self.ship.position["y"],
                self.ship.position["z"],
            ])
            state["position_error"] = float(
                np.linalg.norm(self.target_position - current_pos)
            )
        else:
            state["position_error"] = None

        if self.target_velocity is not None:
            current_vel = np.array([
                self.ship.velocity["x"],
                self.ship.velocity["y"],
                self.ship.velocity["z"],
            ])
            state["velocity_error"] = float(
                np.linalg.norm(self.target_velocity - current_vel)
            )
        else:
            state["velocity_error"] = None

        return state
