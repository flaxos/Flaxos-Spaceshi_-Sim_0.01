# hybrid/systems/rcs_system.py
"""Reaction Control System for torque-based attitude control.

Expanse-style hard-sci physics:
- RCS thrusters provide torque for attitude changes (pitch, yaw, roll)
- No translation capability in RCS (main drive only)
- Torque = r × F (position cross force)
- Angular acceleration = torque / moment_of_inertia
- Quaternion integration handles gimbal-lock-free rotation
"""

from hybrid.core.base_system import BaseSystem
from hybrid.utils.math_utils import is_valid_number
from hybrid.utils.quaternion import Quaternion
import math
import numpy as np
import logging

logger = logging.getLogger(__name__)


class RCSThruster:
    """Represents a single RCS thruster."""
    
    def __init__(self, config: dict):
        """Initialize thruster from config.
        
        Args:
            config: Dict with id, position, direction, max_thrust, fuel_consumption
        """
        self.id = config.get("id", "unknown")
        
        # Position relative to center of mass (meters)
        pos = config.get("position", [0, 0, 0])
        self.position = np.array(pos, dtype=float)
        
        # Thrust direction (unit vector)
        direction = config.get("direction", [1, 0, 0])
        self.direction = np.array(direction, dtype=float)
        # Normalize direction
        mag = np.linalg.norm(self.direction)
        if mag > 1e-10:
            self.direction = self.direction / mag
        
        # Thrust parameters
        self.max_thrust = float(config.get("max_thrust", 1000.0))  # Newtons
        self.fuel_consumption = float(config.get("fuel_consumption", 0.1))  # kg/s at max
        
        # Current throttle (0.0 to 1.0)
        self.throttle = 0.0
        
    def get_force(self) -> np.ndarray:
        """Get current force vector in ship frame."""
        return self.direction * (self.throttle * self.max_thrust)
    
    def get_torque(self) -> np.ndarray:
        """Get torque contribution: τ = r × F."""
        force = self.get_force()
        return np.cross(self.position, force)
    
    def get_fuel_rate(self) -> float:
        """Get current fuel consumption rate (kg/s)."""
        return self.throttle * self.fuel_consumption


class RCSSystem(BaseSystem):
    """Reaction Control System for attitude control."""

    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}
        
        # Power draw
        self.power_draw = config.get("power_draw", 5.0)
        
        # Fuel configuration
        self.fuel_type = config.get("fuel_type", "rcs_propellant")
        
        # Parse thruster configuration
        self.thrusters = []
        thruster_configs = config.get("thrusters", [])
        for tc in thruster_configs:
            self.thrusters.append(RCSThruster(tc))
        
        # If no thrusters configured, create default set for basic control
        if not self.thrusters:
            self._create_default_thrusters()
        
        # Attitude target (Euler angles in degrees)
        self.attitude_target = None  # None = no target (manual rate control)

        # Smoothed attitude target: rate-limited version of attitude_target.
        # When the autopilot commands wildly different headings on
        # consecutive ticks (e.g. alternating prograde/retrograde in the
        # approach P-controller), the raw target can jump 150+ degrees
        # between ticks.  The PD controller cannot track this — it
        # produces maximum torque in alternating directions, exciting a
        # divergent yaw oscillation that the alignment guard then blocks.
        #
        # The smoothed target moves toward attitude_target at max_rate
        # degrees per second, giving the PD controller a physically
        # achievable reference trajectory.  For slowly-changing targets
        # (normal BRAKE retrograde drift) the smooth target equals the
        # raw target within one tick.  Large jumps (>45 degrees) are
        # suppressed — the smoothed target rate-limits the slew so the
        # PD controller always has an achievable reference.
        self._smoothed_target = None  # set when attitude_target is first set

        # Angular velocity target (degrees/second for manual control)
        self.angular_velocity_target = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}

        # Control mode: "rate" (angular velocity) or "attitude" (position hold)
        self.control_mode = "rate"

        # Controller gains (PD controller for attitude)
        # At dt=0.1s Euler integration, continuous-time critical damping
        # (kd=2*sqrt(kp)~2.83) still produces ~7° overshoot due to phase lag.
        # kd=5.0 with kp=2.0 gives true overdamped response at our tick rate:
        # heavy, deliberate rotations that settle without wobble — the ship
        # commits to a turn and locks on heading like a real mass should.
        self.kp = config.get("attitude_kp", 2.0)  # Proportional gain
        self.kd = config.get("attitude_kd", 5.0)  # Derivative gain (overdamped at dt=0.1s)

        # Maximum angular rates (degrees/second)
        self.max_rate = config.get("max_angular_rate", 30.0)

        # Direct thruster overrides for MANUAL tier control.
        # Maps thruster_id -> {"throttle": float, "remaining": float|None}
        # where remaining is seconds until auto-cutoff (None = held indefinitely).
        self._direct_thruster_overrides: dict = {}

        # Status tracking
        self.status = "standby"
        self.total_torque = np.zeros(3)
        self.fuel_used = 0.0
        self._last_torque_magnitude = 0.0
        self._last_dt = 0.0

    def _create_default_thrusters(self):
        """Create a basic thruster configuration for ships without explicit config."""
        # Simple 6-thruster setup for basic 3-axis control
        default_thrusters = [
            # Pitch control (nose up/down) - bow/stern vertical
            {"id": "pitch_up", "position": [5, 0, 0], "direction": [0, 0, -1], "max_thrust": 500},
            {"id": "pitch_down", "position": [5, 0, 0], "direction": [0, 0, 1], "max_thrust": 500},
            {"id": "pitch_up_aft", "position": [-5, 0, 0], "direction": [0, 0, -1], "max_thrust": 500},
            {"id": "pitch_down_aft", "position": [-5, 0, 0], "direction": [0, 0, 1], "max_thrust": 500},
            # Yaw control (nose left/right) - bow/stern lateral
            {"id": "yaw_left", "position": [5, 0, 0], "direction": [0, 1, 0], "max_thrust": 500},
            {"id": "yaw_right", "position": [5, 0, 0], "direction": [0, -1, 0], "max_thrust": 500},
            {"id": "yaw_left_aft", "position": [-5, 0, 0], "direction": [0, -1, 0], "max_thrust": 500},
            {"id": "yaw_right_aft", "position": [-5, 0, 0], "direction": [0, 1, 0], "max_thrust": 500},
            # Roll control - port/starboard dorsal/ventral
            {"id": "roll_cw", "position": [0, 3, 0], "direction": [0, 0, 1], "max_thrust": 300},
            {"id": "roll_ccw", "position": [0, 3, 0], "direction": [0, 0, -1], "max_thrust": 300},
            {"id": "roll_cw_2", "position": [0, -3, 0], "direction": [0, 0, -1], "max_thrust": 300},
            {"id": "roll_ccw_2", "position": [0, -3, 0], "direction": [0, 0, 1], "max_thrust": 300},
        ]
        for tc in default_thrusters:
            self.thrusters.append(RCSThruster(tc))

    def tick(self, dt, ship, event_bus):
        """Update RCS and apply torque for attitude control.

        Args:
            dt: Time step in seconds
            ship: Ship object
            event_bus: Event bus for publishing events
        """
        if not self.enabled:
            self.status = "offline"
            return

        # Apply damage degradation to RCS torque output (includes cascade effects)
        damage_factor = 1.0
        if hasattr(ship, "get_effective_factor"):
            damage_factor = ship.get_effective_factor("rcs")
        elif hasattr(ship, "damage_model"):
            damage_factor = ship.damage_model.get_combined_factor("rcs")

        if damage_factor <= 0.0:
            self.status = "failed"
            ship.angular_acceleration = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
            return

        # Power check
        power_system = ship.systems.get("power_management") or ship.systems.get("power")
        if power_system and not power_system.request_power(self.power_draw * dt, "rcs"):
            self.status = "no_power"
            return

        # --- Direct thruster overrides (MANUAL tier) ---
        # Tick down durations and expire finished overrides before PD runs.
        expired_overrides = []
        for tid, ov in self._direct_thruster_overrides.items():
            if ov["remaining"] is not None:
                ov["remaining"] -= dt
                if ov["remaining"] <= 0:
                    expired_overrides.append(tid)
        for tid in expired_overrides:
            del self._direct_thruster_overrides[tid]

        # Compute desired torque based on control mode
        if self.control_mode == "attitude" and self.attitude_target is not None:
            desired_torque = self._compute_attitude_control(ship, dt)
        else:
            desired_torque = self._compute_rate_control(ship, dt)

        # Allocate thrusters to achieve desired torque (PD controller)
        self._allocate_thrusters(desired_torque)

        # Apply direct overrides ON TOP of PD allocation.
        # Overridden thrusters ignore the PD-computed throttle and use the
        # player's commanded value instead, giving raw manual authority.
        for thruster in self.thrusters:
            if thruster.id in self._direct_thruster_overrides:
                thruster.throttle = self._direct_thruster_overrides[thruster.id]["throttle"]

        # Sum torque from all thrusters
        self.total_torque = np.zeros(3)
        total_fuel_rate = 0.0

        for thruster in self.thrusters:
            self.total_torque += thruster.get_torque()
            total_fuel_rate += thruster.get_fuel_rate()

        # Scale torque output by damage factor (damaged RCS = reduced torque)
        self.total_torque *= damage_factor

        # Crew skill: HELM station crew affects RCS responsiveness.
        # A skilled pilot coordinates thruster firing for tighter attitude
        # control; unmanned helm runs at AI-backup efficiency.
        from hybrid.systems.crew_binding_system import CrewBindingSystem
        from server.stations.station_types import StationType
        self.total_torque *= CrewBindingSystem.get_multiplier(
            ship.id, StationType.HELM, ship=ship
        )

        # Apply torque to ship angular velocity
        # τ = I * α  =>  α = τ / I
        moment_of_inertia = getattr(ship, 'moment_of_inertia', ship.mass * 10.0)
        
        if moment_of_inertia > 0:
            # Angular acceleration (rad/s²)
            angular_accel = self.total_torque / moment_of_inertia

            # Convert to degrees/s² and apply
            # Axis mapping: torque[0]=roll (X), torque[1]=pitch (Y), torque[2]=yaw (Z)
            ship.angular_velocity["roll"] += math.degrees(angular_accel[0]) * dt
            ship.angular_velocity["pitch"] += math.degrees(angular_accel[1]) * dt
            ship.angular_velocity["yaw"] += math.degrees(angular_accel[2]) * dt

            # Clamp angular velocity to max_rate.  RCS thrusters physically
            # cannot spin the ship faster than the control authority allows;
            # without this clamp the PD controller can overshoot by building
            # unchecked angular momentum during large rotations (e.g. a
            # 180-degree flip-and-burn maneuver).
            for axis in ("roll", "pitch", "yaw"):
                ship.angular_velocity[axis] = max(
                    -self.max_rate,
                    min(self.max_rate, ship.angular_velocity[axis]),
                )
        
        # Fuel consumption (simplified - use ship's fuel or separate RCS fuel)
        self.fuel_used += total_fuel_rate * dt
        
        # Update status and track torque for heat reporting
        torque_mag = np.linalg.norm(self.total_torque)
        self._last_torque_magnitude = torque_mag
        self._last_dt = dt
        if torque_mag > 0.1:
            self.status = "active"
            if torque_mag > 100:
                event_bus.publish("rcs_active", {
                    "ship_id": ship.id,
                    "torque_magnitude": torque_mag
                })
        else:
            self.status = "standby"

    def report_heat(self, ship, event_bus):
        """Report heat generated by RCS thruster activity."""
        if not ship or not hasattr(ship, "damage_model"):
            return
        if self._last_torque_magnitude <= 0 or self._last_dt <= 0:
            return
        subsystem = ship.damage_model.subsystems.get("rcs")
        if not subsystem:
            return
        heat_amount = subsystem.heat_generation * self._last_torque_magnitude * self._last_dt
        if heat_amount <= 0:
            return
        ship.damage_model.add_heat("rcs", heat_amount, event_bus, ship.id)
        self._last_torque_magnitude = 0.0
        self._last_dt = 0.0

    def _update_smoothed_target(self, dt: float) -> dict:
        """Rate-limit the attitude target so the PD controller tracks an achievable reference.

        When the commanded target jumps by more than max_rate * dt degrees
        in a single tick (e.g. the approach controller flipping between
        prograde and retrograde), the smoothed target moves toward the
        command at max_rate deg/s instead of teleporting.  For small
        changes (< max_rate * dt) the smoothed target equals the raw
        target instantly — normal BRAKE retrograde drift is unaffected.

        The rate limit matches the physical rotation capability of the
        RCS, so the smoothed target is always achievable.  Without this,
        150-degree target jumps cause the PD controller to command maximum
        torque in alternating directions, exciting a divergent yaw
        oscillation that blocks the alignment guard on >50% of ticks.

        Returns:
            The smoothed target dict {pitch, yaw, roll}.
        """
        raw = self.attitude_target
        if raw is None:
            self._smoothed_target = None
            return raw

        if self._smoothed_target is None:
            # First time — snap to target (no history to smooth from)
            self._smoothed_target = dict(raw)
            return self._smoothed_target

        max_step = self.max_rate * dt  # degrees per tick

        for axis in ("pitch", "yaw", "roll"):
            raw_val = raw.get(axis, 0.0)
            smooth_val = self._smoothed_target.get(axis, 0.0)
            diff = raw_val - smooth_val
            # Normalize to [-180, 180] for shortest-path tracking
            while diff > 180:
                diff -= 360
            while diff < -180:
                diff += 360
            if abs(diff) <= max_step:
                self._smoothed_target[axis] = raw_val
            else:
                # Move toward raw target at max_rate
                self._smoothed_target[axis] = smooth_val + math.copysign(max_step, diff)

        return self._smoothed_target

    def _compute_attitude_control(self, ship, dt) -> np.ndarray:
        """Compute desired torque using quaternion-based PD attitude controller.

        Uses quaternion error to avoid gimbal-lock and cross-coupling issues
        that plague Euler-angle controllers during large rotations (e.g. a
        180-degree flip-and-burn maneuver). The PD gains are tuned for
        slight overdamping to eliminate wobble on arrival.

        Args:
            ship: Ship object with orientation and angular_velocity
            dt: Time step

        Returns:
            Desired torque vector (ship frame)
        """
        if self.attitude_target is None:
            return np.zeros(3)

        current = ship.orientation
        target = self._update_smoothed_target(dt)

        # Build quaternions from Euler angles for gimbal-lock-free error
        q_current = Quaternion.from_euler(
            current.get("pitch", 0),
            current.get("yaw", 0),
            current.get("roll", 0),
        )
        q_target = Quaternion.from_euler(
            target.get("pitch", 0),
            target.get("yaw", 0),
            target.get("roll", 0),
        )

        # Error quaternion: q_err = q_target * q_current^-1
        # The vector part of q_err gives the rotation axis * sin(half_angle),
        # which is proportional to error for small angles and well-behaved
        # for large angles without cross-coupling.
        q_err = q_target * q_current.conjugate()

        # Ensure shortest-path rotation (avoid > 180-degree the long way)
        if q_err.w < 0:
            q_err = Quaternion(-q_err.w, -q_err.x, -q_err.y, -q_err.z)

        # Error axis components (body frame): proportional to sin(theta/2)
        # For small errors this is ~theta/2, for large errors it saturates
        # at 1.0, giving us natural rate limiting.
        # Convert to degrees-equivalent for gain compatibility:
        # 2 * arcsin(|v|) gives the error angle in radians.
        err_mag = math.sqrt(q_err.x**2 + q_err.y**2 + q_err.z**2)
        if err_mag > 1e-6:
            err_angle_rad = 2.0 * math.asin(min(err_mag, 1.0))
            err_angle_deg = math.degrees(err_angle_rad)
            # Decompose into per-axis errors (degrees)
            scale_factor = err_angle_deg / err_mag
            # Quaternion vector part maps to body-frame axes:
            # x -> roll, y -> pitch, z -> yaw
            roll_error = q_err.x * scale_factor
            pitch_error = q_err.y * scale_factor
            yaw_error = q_err.z * scale_factor
        else:
            roll_error = 0.0
            pitch_error = 0.0
            yaw_error = 0.0

        # Angular velocity (current)
        omega = ship.angular_velocity

        # PD control: command = kp * error - kd * angular_velocity
        # The kd term damps any existing rotation, preventing overshoot.
        desired_rate_pitch = self.kp * pitch_error - self.kd * omega.get("pitch", 0)
        desired_rate_yaw = self.kp * yaw_error - self.kd * omega.get("yaw", 0)
        desired_rate_roll = self.kp * roll_error - self.kd * omega.get("roll", 0)

        # Braking-distance rate limit: cap the desired rate so the ship
        # can decelerate to zero within the remaining error angle.
        # Without this, the PD controller builds angular velocity to
        # max_rate during large rotations, then cannot brake in time
        # because Kd*omega only exceeds Kp*error when the error is
        # already small — leading to overshoot and oscillation.
        #
        # Uses the kinematic formula: v_max = sqrt(2 * a * d) where
        # a = effective deceleration (Kd, in deg/s^2) and d = |error|.
        # For kp=2.0, kd=5.0, this limits rate to ~10 deg/s when 10
        # degrees from the target, preventing the 3-5 degree overshoot
        # that the unmodified PD produces on large rotations.
        desired_rate_pitch = self._brake_limited_rate(
            desired_rate_pitch, pitch_error)
        desired_rate_yaw = self._brake_limited_rate(
            desired_rate_yaw, yaw_error)
        desired_rate_roll = self._brake_limited_rate(
            desired_rate_roll, roll_error)

        # Clamp to max angular rate using proportional scaling.
        # Independent per-axis clamping distorts the torque direction when
        # multiple axes saturate: a rotation that is mostly yaw with some
        # pitch/roll gets flattened to (30, 30, 30) deg/s, pointing the
        # torque vector along (1,1,1) instead of primarily along yaw.
        # The thruster allocator then rejects all thrusters because every
        # thruster's cross-axis torque exceeds its useful contribution.
        # Proportional scaling preserves the direction so the dominant
        # axis still dominates the torque request.
        max_abs = max(abs(desired_rate_pitch), abs(desired_rate_yaw),
                      abs(desired_rate_roll))
        if max_abs > self.max_rate:
            rate_scale = self.max_rate / max_abs
            desired_rate_pitch *= rate_scale
            desired_rate_yaw *= rate_scale
            desired_rate_roll *= rate_scale

        # Convert desired rates to torque request.
        # scale = I so that the requested torque produces angular acceleration
        # equal to desired_rate (in rad/s) per second: τ = I * α.
        # Previously scale was I*0.1, which meant the controller only
        # requested ~3% of available RCS torque -- a 180° flip took 30+
        # seconds instead of the theoretical ~6s.
        inertia = getattr(ship, 'moment_of_inertia', ship.mass * 10.0)
        scale = inertia

        # Torque axes: [roll (X), pitch (Y), yaw (Z)]
        return np.array([
            math.radians(desired_rate_roll) * scale,
            math.radians(desired_rate_pitch) * scale,
            math.radians(desired_rate_yaw) * scale,
        ])

    def _brake_limited_rate(self, desired_rate: float, error: float) -> float:
        """Cap desired angular rate so the ship can stop within the remaining error.

        Uses the kinematic formula: v_max = sqrt(2 * a * d) where
        a = effective deceleration (Kd, in deg/s^2) and d = |error| (degrees).

        Args:
            desired_rate: PD-computed desired angular rate (deg/s).
            error: Heading error on this axis (degrees, signed).

        Returns:
            Rate-limited desired angular rate (deg/s), preserving sign.
        """
        abs_err = abs(error)
        if abs_err < 0.5:
            # Very close to target — no additional limiting needed
            return desired_rate
        safe_rate = math.sqrt(2.0 * self.kd * abs_err)
        safe_rate = min(safe_rate, self.max_rate)
        if abs(desired_rate) > safe_rate:
            return math.copysign(safe_rate, desired_rate)
        return desired_rate

    def _compute_rate_control(self, ship, dt) -> np.ndarray:
        """Compute torque to achieve desired angular velocity.

        Args:
            ship: Ship object
            dt: Time step
            
        Returns:
            Desired torque vector (ship frame)
        """
        target = self.angular_velocity_target
        current = ship.angular_velocity
        
        # Rate error
        pitch_error = target.get("pitch", 0) - current.get("pitch", 0)
        yaw_error = target.get("yaw", 0) - current.get("yaw", 0)
        roll_error = target.get("roll", 0) - current.get("roll", 0)
        
        # Proportional control for rate: τ = I * rate_error (in rad/s)
        # The 2x multiplier gives faster convergence to the target rate.
        scale = getattr(ship, 'moment_of_inertia', ship.mass * 10.0)

        return np.array([
            math.radians(roll_error) * scale * 2.0,
            math.radians(pitch_error) * scale * 2.0,
            math.radians(yaw_error) * scale * 2.0
        ])

    def _angle_diff(self, target: float, current: float) -> float:
        """Compute shortest angular difference (handles wraparound)."""
        diff = target - current
        while diff > 180:
            diff -= 360
        while diff < -180:
            diff += 360
        return diff

    def _allocate_thrusters(self, desired_torque: np.ndarray):
        """Allocate thruster outputs to achieve desired torque.

        Uses projection-based allocation: each thruster is throttled
        proportional to its torque projection onto the desired axis.
        Thrusters whose cross-axis torque exceeds their useful torque
        are rejected to prevent unwanted pitch/roll during yaw commands
        (and vice versa). This avoids the cross-coupling bug where bow
        thrusters firing for yaw also induce pitch.
        """
        # Reset all thrusters
        for thruster in self.thrusters:
            thruster.throttle = 0.0

        desired_mag = np.linalg.norm(desired_torque)
        if desired_mag < 0.01:
            return

        # Normalize desired torque direction
        desired_dir = desired_torque / desired_mag

        # For each thruster, compute its torque contribution at max throttle
        # and set throttle proportional to alignment with desired torque.
        # Reject thrusters with excessive cross-axis torque.
        for thruster in self.thrusters:
            # Compute max torque this thruster can produce
            thruster.throttle = 1.0
            max_torque = thruster.get_torque()
            thruster.throttle = 0.0

            max_torque_mag = np.linalg.norm(max_torque)
            if max_torque_mag < 0.01:
                continue

            # Project thruster torque onto desired direction
            projection = np.dot(max_torque, desired_dir)

            if projection <= 0:
                # Thruster opposes or is perpendicular -- skip
                continue

            # Check cross-axis contamination: the component of thruster
            # torque orthogonal to the desired axis. If it's larger than
            # the useful component, this thruster causes more harm than
            # good (e.g. yaw thruster that also pitches).
            cross_torque_sq = max_torque_mag**2 - projection**2
            if cross_torque_sq > projection**2:
                # Cross-axis torque exceeds useful torque -- reject
                continue

            # Throttle proportional to how much of the desired torque
            # this thruster can contribute along the desired axis
            throttle = desired_mag * projection / (max_torque_mag**2)
            thruster.throttle = max(0.0, min(1.0, throttle))

    # ----- Rotation estimation -----

    def _get_max_angular_accel(self, ship) -> float:
        """Max angular acceleration (deg/s^2) from thruster torque and inertia.

        Sums the maximum torque magnitude across all thrusters on the
        dominant axis (yaw, since flip-and-burn is a yaw maneuver) and
        divides by moment of inertia.

        Args:
            ship: Ship object (for mass / moment of inertia)

        Returns:
            Angular acceleration in degrees per second squared
        """
        inertia = getattr(ship, 'moment_of_inertia', ship.mass * 10.0)
        if inertia <= 0:
            return 1.0  # safe floor

        # Find max torque about yaw axis (index 2) from paired thrusters
        max_yaw_torque = 0.0
        for thruster in self.thrusters:
            thruster.throttle = 1.0
            torque = thruster.get_torque()
            thruster.throttle = 0.0
            # Only count positive yaw contribution (we'd fire matching pairs)
            if abs(torque[2]) > 0.01:
                max_yaw_torque += abs(torque[2])

        # Thrusters fire in pairs (one side), so effective torque is
        # roughly half the total (CW pair or CCW pair, not both).
        effective_torque = max_yaw_torque / 2.0
        if effective_torque < 0.01:
            return 1.0

        # alpha = tau / I  (rad/s^2), convert to deg/s^2
        alpha_rad = effective_torque / inertia
        return math.degrees(alpha_rad)

    def estimate_rotation_time(self, angle_degrees: float, ship=None) -> float:
        """Estimate time for a rotation of the given angle.

        Uses a bang-bang (accelerate-then-decelerate) profile:
        the RCS accelerates for half the angle, then decelerates for
        the other half. Total time = 2 * sqrt(angle / alpha).

        Also accounts for the maximum angular rate clamp -- if the
        ship would exceed max_rate, it coasts at max_rate for the
        middle portion.

        Args:
            angle_degrees: Rotation magnitude in degrees (always positive)
            ship: Ship object (for inertia). If None, uses a rough default.

        Returns:
            Estimated rotation time in seconds
        """
        angle = abs(angle_degrees)
        if angle < 0.5:
            return 0.0

        if ship is not None:
            alpha = self._get_max_angular_accel(ship)
        else:
            # Fallback: assume modest angular acceleration
            alpha = 5.0  # deg/s^2

        alpha = max(alpha, 0.1)  # prevent division by zero

        # Time and angle to reach max_rate under constant acceleration
        t_accel_to_max = self.max_rate / alpha
        angle_accel_to_max = 0.5 * alpha * t_accel_to_max**2

        if angle <= 2.0 * angle_accel_to_max:
            # Pure bang-bang: accelerate half, decelerate half
            ideal = 2.0 * math.sqrt(angle / alpha)
        else:
            # Trapezoidal: accel -> coast at max_rate -> decel
            coast_angle = angle - 2.0 * angle_accel_to_max
            coast_time = coast_angle / self.max_rate
            ideal = 2.0 * t_accel_to_max + coast_time

        # The bang-bang model assumes instantaneous torque reversal, but
        # the actual PD attitude controller (kd-overdamped) overshoots
        # the ideal profile by ~30% due to damping lag and finite-rate
        # thruster allocation.  The 1.5x factor keeps flip timeout
        # calculations conservative enough to avoid false timeouts.
        return ideal * 1.5

    # ----- Commands -----
    def command(self, action, params):
        if action == "set_attitude_target":
            return self.set_attitude_target(params)
        if action == "set_angular_velocity":
            return self.set_angular_velocity_target(params)
        if action == "clear_target":
            return self.clear_target()
        if action == "fire_thruster":
            return self.fire_thruster(params)
        if action == "status":
            return self.get_state()
        if action == "power_on":
            return self.power_on()
        if action == "power_off":
            return self.power_off()
        return super().command(action, params)

    def set_attitude_target(self, params):
        """Set target attitude (RCS will maneuver to achieve it).
        
        Args:
            params: Dict with pitch, yaw, roll in degrees
        """
        if not self.enabled:
            return {"error": "RCS system is disabled"}
        
        pitch = float(params.get("pitch", 0.0))
        yaw = float(params.get("yaw", 0.0))
        roll = float(params.get("roll", 0.0))
        
        self.attitude_target = {"pitch": pitch, "yaw": yaw, "roll": roll}
        self.control_mode = "attitude"
        
        return {
            "status": "Attitude target set",
            "target": self.attitude_target,
            "control_mode": self.control_mode
        }

    def set_angular_velocity_target(self, params):
        """Set target angular velocity (rate command).
        
        Args:
            params: Dict with pitch, yaw, roll rates in degrees/second
        """
        if not self.enabled:
            return {"error": "RCS system is disabled"}
        
        self.angular_velocity_target = {
            "pitch": float(params.get("pitch", 0.0)),
            "yaw": float(params.get("yaw", 0.0)),
            "roll": float(params.get("roll", 0.0))
        }
        self.control_mode = "rate"
        self.attitude_target = None
        self._smoothed_target = None

        return {
            "status": "Angular velocity target set",
            "target": self.angular_velocity_target,
            "control_mode": self.control_mode
        }

    def clear_target(self):
        """Clear all targets and stop rotation."""
        self.attitude_target = None
        self._smoothed_target = None
        self.angular_velocity_target = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        self.control_mode = "rate"

        return {"status": "Targets cleared", "control_mode": self.control_mode}

    def fire_thruster(self, params: dict, ship=None, event_bus=None) -> dict:
        """Direct control of individual RCS thrusters (MANUAL tier).

        Bypasses the PD attitude controller for the specified thruster,
        giving the player raw rotational authority. The override persists
        until the duration expires or the player zeros the throttle.

        Args:
            params: Dict with:
                thruster_id: str -- thruster ID (e.g. "pitch_up", "yaw_left")
                throttle: float 0.0-1.0 -- desired throttle
                duration: float (optional) -- auto-cutoff in seconds.
                    If omitted the override is held until explicitly cleared.

        Returns:
            dict with thruster state after applying the override.
        """
        if not self.enabled:
            return {"error": "RCS system is disabled"}

        thruster_id = params.get("thruster_id")
        if not thruster_id:
            return {"error": "thruster_id is required"}

        # Look up the thruster by ID
        thruster = None
        for t in self.thrusters:
            if t.id == thruster_id:
                thruster = t
                break

        if thruster is None:
            valid_ids = [t.id for t in self.thrusters]
            return {
                "error": f"Unknown thruster '{thruster_id}'",
                "valid_ids": valid_ids,
            }

        throttle = float(params.get("throttle", 0.0))
        throttle = max(0.0, min(1.0, throttle))

        duration = params.get("duration")
        if duration is not None:
            duration = max(0.0, float(duration))

        if throttle <= 0.0:
            # Clearing the override -- remove from tracking and zero throttle
            self._direct_thruster_overrides.pop(thruster_id, None)
            thruster.throttle = 0.0
        else:
            self._direct_thruster_overrides[thruster_id] = {
                "throttle": throttle,
                "remaining": duration,
            }
            thruster.throttle = throttle

        return {
            "status": "ok",
            "thruster_id": thruster_id,
            "throttle": throttle,
            "duration": duration,
            "torque": thruster.get_torque().tolist(),
            "override_active": thruster_id in self._direct_thruster_overrides,
        }

    def get_thruster_state(self) -> list:
        """Return per-thruster telemetry for MANUAL tier display.

        Returns:
            List of dicts, one per thruster, with full physical state.
        """
        return [
            {
                "id": t.id,
                "throttle": t.throttle,
                "max_thrust": t.max_thrust,
                "fuel_rate": t.get_fuel_rate(),
                "torque": t.get_torque().tolist(),
                "position": t.position.tolist(),
                "direction": t.direction.tolist(),
                "override": t.id in self._direct_thruster_overrides,
            }
            for t in self.thrusters
        ]

    def get_state(self):
        state = super().get_state()
        state.update({
            "status": self.status,
            "control_mode": self.control_mode,
            "attitude_target": self.attitude_target,
            "angular_velocity_target": self.angular_velocity_target,
            "total_torque": {
                "roll": self.total_torque[0],
                "pitch": self.total_torque[1],
                "yaw": self.total_torque[2]
            },
            "fuel_used": self.fuel_used,
            "thruster_count": len(self.thrusters),
            "active_thrusters": sum(1 for t in self.thrusters if t.throttle > 0.01),
            # Per-thruster state for MANUAL tier
            "thrusters": [
                {
                    "id": t.id,
                    "throttle": round(t.throttle, 3),
                    "max_thrust": t.max_thrust,
                    "fuel_rate": round(t.get_fuel_rate(), 4),
                    "torque": [round(x, 2) for x in t.get_torque().tolist()],
                    "position": t.position.tolist(),
                    "direction": t.direction.tolist(),
                }
                for t in self.thrusters
            ],
            # PD controller state for MANUAL tier
            "controller": {
                "kp": self.kp,
                "kd": self.kd,
                "max_rate": self.max_rate,
                "smoothed_target": self._smoothed_target,
            },
        })
        return state
