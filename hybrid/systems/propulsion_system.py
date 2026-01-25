# hybrid/systems/propulsion_system.py
"""Propulsion system providing thrust and fuel management.

Expanse-style hard-sci physics:
- Main drive provides thrust along ship's forward axis (+X in ship frame)
- Ship quaternion rotates thrust into world frame for acceleration
- Scalar throttle (0..1) is the primary control input
- Debug vector thrust preserved for development/testing only
"""

from hybrid.core.base_system import BaseSystem
from hybrid.utils.math_utils import is_valid_number, clamp
import math
import logging

logger = logging.getLogger(__name__)

# Earth gravity constant (m/s²)
G_FORCE = 9.81


class PropulsionSystem(BaseSystem):
    """Manages ship propulsion with Expanse-style main drive."""

    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}

        # Power usage
        self.power_draw = config.get("power_draw", 10.0)
        self.power_draw_per_thrust = config.get("power_draw_per_thrust", 0.5)

        # Main drive configuration
        self.max_thrust = float(config.get("max_thrust", 100.0))
        
        # Primary control: scalar throttle (0.0 to 1.0)
        self.throttle = 0.0
        
        # Debug mode: direct vector thrust (bypasses ship-frame transform)
        self._debug_thrust_vector = None  # None means use throttle + ship frame
        
        # Legacy compatibility - keep main_drive dict for telemetry
        self.main_drive = {
            "throttle": 0.0,
            "max_thrust": self.max_thrust,
        }

        # Fuel and efficiency
        self.efficiency = float(config.get("efficiency", 0.9))
        self.fuel_consumption = float(config.get("fuel_consumption", 0.1))
        self.max_fuel = float(config.get("max_fuel", 1000.0))
        self.fuel_level = float(config.get("fuel_level", self.max_fuel))

        # Tracking - world-frame thrust after rotation
        self.thrust_world = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.power_status = True
        self.status = "idle"
        
        # G-force tracking (calculated from acceleration)
        self.current_thrust_g = 0.0
        self.max_thrust_g = 0.0  # Will be calculated from max_thrust and ship mass

    def tick(self, dt, ship, event_bus):
        """Update propulsion and apply thrust.
        
        Hard-sci model:
        1. Throttle sets force magnitude along ship's +X axis (forward)
        2. Ship quaternion rotates this into world frame
        3. F=ma gives acceleration in world frame
        """
        if not self.enabled:
            ship.thrust = {"x": 0.0, "y": 0.0, "z": 0.0}
            ship.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
            self.thrust_world = {"x": 0.0, "y": 0.0, "z": 0.0}
            self.status = "offline"
            return

        # Calculate thrust magnitude
        if self._debug_thrust_vector is not None:
            # Debug mode: use arbitrary vector directly (world frame)
            thrust_world_x = self._debug_thrust_vector["x"]
            thrust_world_y = self._debug_thrust_vector["y"]
            thrust_world_z = self._debug_thrust_vector["z"]
            thrust_magnitude = math.sqrt(
                thrust_world_x**2 + thrust_world_y**2 + thrust_world_z**2
            )
        else:
            # Normal mode: main drive thrust along ship's forward axis (+X)
            thrust_magnitude = self.throttle * self.max_thrust
            
            # Ship-frame force vector: [thrust, 0, 0] (forward)
            ship_frame_force = (thrust_magnitude, 0.0, 0.0)
            
            # Rotate ship-frame force into world frame using quaternion
            thrust_world_x, thrust_world_y, thrust_world_z = self._rotate_to_world(
                ship, ship_frame_force
            )

        # Power check
        total_power = self.power_draw + (self.power_draw_per_thrust * thrust_magnitude * dt)
        power_system = ship.systems.get("power")
        if power_system and not power_system.request_power(total_power, "propulsion"):
            logger.warning(f"Propulsion on {ship.id} reduced due to power shortage")
            thrust_world_x = thrust_world_y = thrust_world_z = 0.0
            thrust_magnitude = 0.0
            if self.power_status:
                self.power_status = False
                event_bus.publish("propulsion_power_loss", {"source": "propulsion"})
        elif not self.power_status:
            self.power_status = True
            event_bus.publish("propulsion_power_restored", {"source": "propulsion"})

        # Store world-frame thrust for telemetry
        self.thrust_world = {"x": thrust_world_x, "y": thrust_world_y, "z": thrust_world_z}
        ship.thrust = dict(self.thrust_world)
        
        # Calculate G-force from acceleration magnitude (will be updated after acceleration is set)
        # We'll update this after acceleration is calculated

        if thrust_magnitude > 0:
            # Guard against invalid mass
            if ship.mass <= 0:
                logger.error(f"Ship {ship.id} has invalid mass {ship.mass}, cannot calculate acceleration")
                ship.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
                self.status = "error"
                return

            # Fuel consumption
            consumption = (thrust_magnitude / max(self.max_thrust, 1e-10)) * self.fuel_consumption * dt
            if self.fuel_level >= consumption:
                self.fuel_level -= consumption

                # F = ma -> a = F/m
                accel_x = thrust_world_x / ship.mass
                accel_y = thrust_world_y / ship.mass
                accel_z = thrust_world_z / ship.mass

                # Validate acceleration values
                if all(is_valid_number(a) for a in [accel_x, accel_y, accel_z]):
                    ship.acceleration = {"x": accel_x, "y": accel_y, "z": accel_z}
                    # Calculate current G-force from acceleration magnitude
                    accel_magnitude = math.sqrt(accel_x**2 + accel_y**2 + accel_z**2)
                    self.current_thrust_g = accel_magnitude / G_FORCE
                    self.status = "active"
                else:
                    logger.error(f"Ship {ship.id}: Invalid acceleration calculated, zeroing thrust")
                    ship.thrust = {"x": 0.0, "y": 0.0, "z": 0.0}
                    ship.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
                    self.status = "error"
            else:
                ship.thrust = {"x": 0.0, "y": 0.0, "z": 0.0}
                ship.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
                self.fuel_level = 0.0
                self.status = "no_fuel"
                event_bus.publish("propulsion_status_change", {"system": "propulsion", "status": "no_fuel"})
        else:
            ship.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
            self.current_thrust_g = 0.0
            self.status = "idle"
        
        # Update max G-force capability (if we have ship mass)
        if hasattr(ship, 'mass') and ship.mass > 0:
            max_accel = self.max_thrust / ship.mass
            self.max_thrust_g = max_accel / G_FORCE

        # Signature spike for sensor detection
        if thrust_magnitude > 10.0:
            event_bus.publish("signature_spike", {
                "duration": 3.0, 
                "magnitude": thrust_magnitude, 
                "source": "propulsion"
            })

    def _rotate_to_world(self, ship, ship_frame_vec):
        """Rotate a vector from ship frame to world frame using ship quaternion.
        
        Args:
            ship: Ship object with quaternion attribute
            ship_frame_vec: Tuple (x, y, z) in ship frame
            
        Returns:
            Tuple (x, y, z) in world frame
        """
        # Get quaternion from ship (if available)
        quat = getattr(ship, 'quaternion', None)
        if quat is None or not hasattr(quat, 'rotate_vector'):
            # Fallback: no rotation (assume identity orientation)
            return ship_frame_vec
        
        # Rotate ship-frame vector to world frame
        return quat.rotate_vector(ship_frame_vec)

    # ----- Commands -----
    def command(self, action, params):
        if action == "set_throttle":
            return self.set_throttle(params)
        if action == "set_thrust_vector":
            return self.set_thrust_vector(params)
        if action == "set_thrust":
            # Legacy compatibility: route based on params
            if any(k in params for k in ("x", "y", "z")):
                return self.set_thrust_vector(params)
            else:
                return self.set_throttle(params)
        if action == "refuel":
            return self.refuel(params)
        if action == "emergency_stop":
            return self.emergency_stop()
        if action == "status":
            return self.get_state()
        if action == "power_on":
            return self.power_on()
        if action == "power_off":
            return self.power_off()
        return super().command(action, params)

    def set_throttle(self, params):
        """Set main drive throttle (0.0 to 1.0) or G-force.
        
        This is the primary gameplay API. Thrust is applied along ship's
        forward axis (+X in ship frame), rotated to world frame by quaternion.
        
        Args:
            params: Dict with either:
                - 'thrust' or 'throttle': 0.0 to 1.0 scalar
                - 'g': Desired G-force (requires ship mass)
        """
        if not self.enabled:
            return {"error": "Propulsion system is disabled"}

        try:
            # Check if G-force is specified (takes precedence)
            if "g" in params:
                g_force = float(params["g"])
                if not is_valid_number(g_force):
                    return {"error": "Invalid G-force value (NaN or Inf detected)"}
                
                # Need ship reference to calculate throttle from G
                ship = params.get("ship") or params.get("_ship")
                if not ship or not hasattr(ship, "mass") or ship.mass <= 0:
                    return {"error": "Ship mass required to set throttle by G-force"}
                
                # Convert G to throttle: g * 9.81 * mass = thrust, throttle = thrust / max_thrust
                required_thrust = g_force * G_FORCE * ship.mass
                throttle = required_thrust / self.max_thrust if self.max_thrust > 0 else 0.0
                throttle = max(0.0, min(1.0, throttle))  # Clamp to valid range
            else:
                # Accept 'thrust' or 'throttle' parameter (legacy scalar)
                throttle = params.get("thrust", params.get("throttle", 0.0))
                throttle = float(throttle)
                
                if not is_valid_number(throttle):
                    return {"error": "Invalid throttle value (NaN or Inf detected)"}
                
                # Clamp to valid range
                throttle = max(0.0, min(1.0, throttle))
            
            self.throttle = throttle
            
            # Clear debug mode
            self._debug_thrust_vector = None
            
            # Update telemetry
            self.main_drive["throttle"] = self.throttle
            
            return {
                "status": "Throttle updated",
                "throttle": self.throttle,
                "thrust_magnitude": self.throttle * self.max_thrust
            }
        except (ValueError, TypeError) as e:
            logger.error(f"Error setting throttle: {e}")
            return {"error": f"Invalid throttle parameter: {e}"}

    def set_thrust_vector(self, params):
        """Set arbitrary thrust vector (DEBUG ONLY).
        
        This bypasses ship-frame rotation and applies thrust directly in world frame.
        Intended for debugging and testing only - not realistic for gameplay.
        """
        if not self.enabled:
            return {"error": "Propulsion system is disabled"}

        try:
            x = float(params.get("x", 0.0))
            y = float(params.get("y", 0.0))
            z = float(params.get("z", 0.0))

            # Validate thrust values
            if not all(is_valid_number(v) for v in [x, y, z]):
                return {"error": "Invalid thrust values (NaN or Inf detected)"}

            magnitude = math.sqrt(x**2 + y**2 + z**2)

            # Clamp to max thrust
            if magnitude > self.max_thrust:
                if magnitude > 0:
                    scale = self.max_thrust / magnitude
                    x *= scale
                    y *= scale
                    z *= scale
                else:
                    x = y = z = 0.0

            self._debug_thrust_vector = {"x": x, "y": y, "z": z}
            
            # Update throttle to reflect magnitude (for telemetry)
            self.throttle = magnitude / self.max_thrust if self.max_thrust > 0 else 0.0
            self.main_drive["throttle"] = self.throttle
            
            return {
                "status": "Debug thrust vector set",
                "thrust_vector": self._debug_thrust_vector,
                "debug_mode": True
            }
        except (ValueError, TypeError) as e:
            logger.error(f"Error setting thrust vector: {e}")
            return {"error": f"Invalid thrust vector parameters: {e}"}

    def refuel(self, params):
        amount = float(params.get("amount", self.max_fuel - self.fuel_level))
        self.fuel_level = min(self.max_fuel, self.fuel_level + amount)
        return {
            "status": "Refueled",
            "amount": amount,
            "current_level": self.fuel_level,
            "max_fuel": self.max_fuel,
        }

    def emergency_stop(self):
        """Emergency stop - zero throttle and clear debug vector."""
        self.throttle = 0.0
        self._debug_thrust_vector = None
        self.thrust_world = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.main_drive["throttle"] = 0.0
        return {"status": "Emergency stop activated", "throttle": 0.0}

    def get_thrust(self):
        """Get current world-frame thrust vector."""
        return self.thrust_world

    def get_state(self):
        state = super().get_state()
        state.update({
            "status": self.status,
            "throttle": self.throttle,
            "max_thrust": self.max_thrust,
            "thrust_magnitude": self.throttle * self.max_thrust,
            "thrust_world": self.thrust_world,
            "debug_mode": self._debug_thrust_vector is not None,
            "fuel_level": self.fuel_level,
            "fuel_percent": (self.fuel_level / self.max_fuel * 100) if self.max_fuel > 0 else 0,
            "max_fuel": self.max_fuel,
            "power_status": self.power_status,
            # G-force metrics
            "thrust_g": self.current_thrust_g,
            "max_thrust_g": self.max_thrust_g,
            # Legacy compatibility
            "main_drive": self.main_drive,
            "current_thrust": self.thrust_world,
        })
        return state
