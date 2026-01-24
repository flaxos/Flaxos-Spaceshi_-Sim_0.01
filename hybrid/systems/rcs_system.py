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
        
        # Angular velocity target (degrees/second for manual control)
        self.angular_velocity_target = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        
        # Control mode: "rate" (angular velocity) or "attitude" (position hold)
        self.control_mode = "rate"
        
        # Controller gains (PD controller for attitude)
        self.kp = config.get("attitude_kp", 2.0)  # Proportional gain
        self.kd = config.get("attitude_kd", 1.5)  # Derivative gain
        
        # Maximum angular rates (degrees/second)
        self.max_rate = config.get("max_angular_rate", 30.0)
        
        # Status tracking
        self.status = "standby"
        self.total_torque = np.zeros(3)
        self.fuel_used = 0.0

    def _create_default_thrusters(self):
        """Create a basic thruster configuration for ships without explicit config."""
        # Simple 6-thruster setup for basic 3-axis control
        default_thrusters = [
            # Pitch control (nose up/down) - bow/stern vertical
            {"id": "pitch_up", "position": [5, 0, 0], "direction": [0, 0, 1], "max_thrust": 500},
            {"id": "pitch_down", "position": [5, 0, 0], "direction": [0, 0, -1], "max_thrust": 500},
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
        
        # Power check
        power_system = ship.systems.get("power")
        if power_system and not power_system.request_power(self.power_draw * dt, "rcs"):
            self.status = "no_power"
            return
        
        # Compute desired torque based on control mode
        if self.control_mode == "attitude" and self.attitude_target is not None:
            desired_torque = self._compute_attitude_control(ship, dt)
        else:
            desired_torque = self._compute_rate_control(ship, dt)
        
        # Allocate thrusters to achieve desired torque
        self._allocate_thrusters(desired_torque)
        
        # Sum torque from all thrusters
        self.total_torque = np.zeros(3)
        total_fuel_rate = 0.0
        
        for thruster in self.thrusters:
            self.total_torque += thruster.get_torque()
            total_fuel_rate += thruster.get_fuel_rate()
        
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
        
        # Fuel consumption (simplified - use ship's fuel or separate RCS fuel)
        self.fuel_used += total_fuel_rate * dt
        
        # Update status
        torque_mag = np.linalg.norm(self.total_torque)
        if torque_mag > 0.1:
            self.status = "active"
            if torque_mag > 100:
                event_bus.publish("rcs_active", {
                    "ship_id": ship.id,
                    "torque_magnitude": torque_mag
                })
        else:
            self.status = "standby"

    def _compute_attitude_control(self, ship, dt) -> np.ndarray:
        """Compute desired torque using PD attitude controller.
        
        Args:
            ship: Ship object with quaternion and angular_velocity
            dt: Time step
            
        Returns:
            Desired torque vector (ship frame)
        """
        if self.attitude_target is None:
            return np.zeros(3)
        
        # Get current attitude error
        current = ship.orientation
        target = self.attitude_target
        
        # Simple error in Euler angles (works for small angles)
        # For large errors, should use quaternion error
        pitch_error = self._angle_diff(target.get("pitch", 0), current.get("pitch", 0))
        yaw_error = self._angle_diff(target.get("yaw", 0), current.get("yaw", 0))
        roll_error = self._angle_diff(target.get("roll", 0), current.get("roll", 0))
        
        # Angular velocity (current)
        omega = ship.angular_velocity
        
        # PD control: torque = kp * error - kd * velocity
        # Negative velocity term provides damping
        desired_rate_pitch = self.kp * pitch_error - self.kd * omega.get("pitch", 0)
        desired_rate_yaw = self.kp * yaw_error - self.kd * omega.get("yaw", 0)
        desired_rate_roll = self.kp * roll_error - self.kd * omega.get("roll", 0)
        
        # Clamp to max rate
        desired_rate_pitch = max(-self.max_rate, min(self.max_rate, desired_rate_pitch))
        desired_rate_yaw = max(-self.max_rate, min(self.max_rate, desired_rate_yaw))
        desired_rate_roll = max(-self.max_rate, min(self.max_rate, desired_rate_roll))
        
        # Convert desired rates to torque request
        # Scale factor to convert rate command to torque (simplified)
        scale = getattr(ship, 'moment_of_inertia', ship.mass * 10.0) * 0.1
        
        # Torque axes: [roll (X), pitch (Y), yaw (Z)]
        return np.array([
            math.radians(desired_rate_roll) * scale,
            math.radians(desired_rate_pitch) * scale,
            math.radians(desired_rate_yaw) * scale
        ])

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
        
        # Simple proportional control for rate
        scale = getattr(ship, 'moment_of_inertia', ship.mass * 10.0) * 0.1
        
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
        
        Simple heuristic allocation - fires thrusters that produce
        torque in the desired direction.
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
        # and set throttle proportional to alignment with desired torque
        for thruster in self.thrusters:
            # Compute max torque this thruster can produce
            thruster.throttle = 1.0
            max_torque = thruster.get_torque()
            thruster.throttle = 0.0
            
            max_torque_mag = np.linalg.norm(max_torque)
            if max_torque_mag < 0.01:
                continue
            
            # Compute alignment: cos(θ) between thruster torque and desired torque
            # Range: [-1, 1] where 1 = perfectly aligned, 0 = perpendicular, -1 = opposite
            alignment = np.dot(max_torque, desired_dir) / max_torque_mag
            
            if alignment > 0:
                # This thruster helps - set throttle proportionally
                # throttle = (how much we need / how much this thruster provides) * alignment
                throttle = (desired_mag / max_torque_mag) * alignment
                thruster.throttle = max(0.0, min(1.0, throttle))

    # ----- Commands -----
    def command(self, action, params):
        if action == "set_attitude_target":
            return self.set_attitude_target(params)
        if action == "set_angular_velocity":
            return self.set_angular_velocity_target(params)
        if action == "clear_target":
            return self.clear_target()
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
        
        return {
            "status": "Angular velocity target set",
            "target": self.angular_velocity_target,
            "control_mode": self.control_mode
        }

    def clear_target(self):
        """Clear all targets and stop rotation."""
        self.attitude_target = None
        self.angular_velocity_target = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        self.control_mode = "rate"
        
        return {"status": "Targets cleared", "control_mode": self.control_mode}

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
            "active_thrusters": sum(1 for t in self.thrusters if t.throttle > 0.01)
        })
        return state
