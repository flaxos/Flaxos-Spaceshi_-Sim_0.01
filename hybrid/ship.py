# hybrid/ship.py

"""
Ship implementation that manages systems and handles physics.
"""
from hybrid.core.event_bus import EventBus
from hybrid.utils.math_utils import (
    sanitize_physics_state, is_valid_number, clamp,
    normalize_angle as normalize_angle_util
)
from hybrid.utils.quaternion import Quaternion, quaternion_identity
import math
import time
import copy
import logging

logger = logging.getLogger(__name__)

class Ship:
    """Class representing a ship with multiple systems"""
    
    def __init__(self, ship_id, config=None):
        """
        Initialize a ship with the given configuration

        Args:
            ship_id (str): Unique identifier for the ship
            config (dict): Configuration dictionary for the ship
        """
        self.id = ship_id
        config = config or {}

        # Initialize ship properties with defaults
        self.name = config.get("name", ship_id)
        self.mass = config.get("mass", 1000.0)  # kg
        self.class_type = config.get("class", "shuttle")
        self.faction = config.get("faction", "neutral")

        # Rotational inertia (kg⋅m²)
        # For S3: moment of inertia for rotational dynamics (torque = I * angular_acceleration)
        # Currently scalar (spherical approximation), can be extended to 3x3 tensor for complex shapes
        # Default: I ≈ (1/6) * m * L² where L ≈ ∛(m) (rough estimate for spacecraft)
        self.moment_of_inertia = config.get("moment_of_inertia", self.mass * (self.mass ** (1.0/3.0)) / 6.0)

        # D6: Hull integrity for damage model
        # Base hull on mass: roughly 1 hull point per 10 kg of mass
        self.max_hull_integrity = config.get("max_hull_integrity", self.mass / 10.0)
        self.hull_integrity = config.get("hull_integrity", self.max_hull_integrity)

        # Initialize physical state
        self.position = self._get_vector3_config(config.get("position", {}))
        self.velocity = self._get_vector3_config(config.get("velocity", {}))
        self.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}

        # Orientation: Euler angles for backward compatibility, quaternion for physics
        self.orientation = self._get_vector3_config(config.get("orientation", {}), "pitch", "yaw", "roll")

        # S3: Quaternion-based attitude (eliminates gimbal lock)
        # Initialize from Euler angles
        self.quaternion = Quaternion.from_euler(
            self.orientation["pitch"],
            self.orientation["yaw"],
            self.orientation["roll"]
        )

        self.angular_velocity = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        self.angular_acceleration = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}  # For S3: RCS torque integration
        self.thrust = {"x": 0.0, "y": 0.0, "z": 0.0}

        # Create the event bus for system communication
        self.event_bus = EventBus()

        # Initialize systems
        self.systems = {}
        self._load_systems(config.get("systems", {}))

        # Fleet and AI control
        self.fleet_id = None  # Fleet this ship belongs to
        self.ai_controller = None  # AI controller (if AI-controlled)
        self.ai_enabled = config.get("ai_enabled", False)
        
        # Initialize command handler
        self.command_handlers = {
            "get_state": self._cmd_get_state,
            "get_position": self._cmd_get_position,
            "get_velocity": self._cmd_get_velocity,
            "get_orientation": self._cmd_get_orientation,
            "set_thrust": self._cmd_set_thrust,
            "set_course": self._cmd_set_course,
            "rotate": self._cmd_rotate,
            "get_system_state": self._cmd_get_system_state,
            "request_power": self._cmd_request_power,
            "reroute_power": self._cmd_reroute_power,
            "get_power_state": self._cmd_get_power_state,
        }
        
    def _get_vector3_config(self, config, x_key="x", y_key="y", z_key="z"):
        """Extract a vector3 from config with defaults"""
        return {
            x_key: float(config.get(x_key, 0.0)),
            y_key: float(config.get(y_key, 0.0)),
            z_key: float(config.get(z_key, 0.0))
        }
        
    def _load_systems(self, systems_config):
        """
        Load ship systems from configuration
        
        Args:
            systems_config (dict): Dictionary of system configurations
        """
        from hybrid.systems import get_system_class
        
        # Load each system type
        for system_type, config in systems_config.items():
            # Skip systems with None config
            if config is None:
                continue
                
            try:
                # Get the appropriate class for this system type
                system_class = get_system_class(system_type)
                
                # Create an instance of the system
                if system_class:
                    system = system_class(config)
                    self.systems[system_type] = system
                    print(f"Loaded system: {system_type}")
                else:
                    print(f"Unknown system type: {system_type}")
            except Exception as e:
                print(f"Error loading system {system_type}: {e}")
                # Create a basic dictionary for failed systems
                self.systems[system_type] = {
                    "status": "error",
                    "error": str(e)
                }
    
    def tick(self, dt, all_ships=None, sim_time=0.0):
        """
        Update ship state for the current time step

        Args:
            dt (float): Time delta in seconds
            all_ships (list, optional): List of all ships in simulation
            sim_time (float): Current simulation time
        """
        # Update AI controller if enabled
        if self.ai_enabled and self.ai_controller:
            try:
                self.ai_controller.update(dt, sim_time)
            except Exception as e:
                logger.error(f"Error in AI controller for {self.id}: {e}")

        # First pass: update all systems
        for system_type, system in self.systems.items():
            if hasattr(system, "tick") and callable(system.tick):
                try:
                    system.tick(dt, self, self.event_bus)
                except Exception as e:
                    print(f"Error in system {system_type} tick: {e}")

        # Update physics after systems have updated
        self._update_physics(dt)
    
    def _update_physics(self, dt, force=None):
        """Update ship physics for the current time step

        Args:
            dt (float): Time delta in seconds
            force (dict, optional): Net force vector acting on the ship. If not
                provided, the existing acceleration is used.
        """
        # Guard against invalid dt
        if not is_valid_number(dt) or dt <= 0:
            logger.warning(f"Ship {self.id}: Invalid dt={dt}, skipping physics update")
            return

        # Guard against zero or invalid mass
        if not is_valid_number(self.mass) or self.mass <= 0:
            logger.error(f"Ship {self.id}: Invalid mass={self.mass}, resetting to default")
            self.mass = 1000.0

        if force is not None:
            # Calculate acceleration from force, with safe division
            self.acceleration = {
                "x": force.get("x", 0.0) / self.mass,
                "y": force.get("y", 0.0) / self.mass,
                "z": force.get("z", 0.0) / self.mass,
            }

            # Update velocity
            self.velocity["x"] += self.acceleration["x"] * dt
            self.velocity["y"] += self.acceleration["y"] * dt
            self.velocity["z"] += self.acceleration["z"] * dt
        else:
            # Update velocity based on current acceleration
            self.velocity["x"] += self.acceleration["x"] * dt
            self.velocity["y"] += self.acceleration["y"] * dt
            self.velocity["z"] += self.acceleration["z"] * dt

        # Update position based on velocity
        self.position["x"] += self.velocity["x"] * dt
        self.position["y"] += self.velocity["y"] * dt
        self.position["z"] += self.velocity["z"] * dt

        # Sanitize physics state (check for NaN/Inf and clamp to reasonable bounds)
        self.position, self.velocity, self.acceleration, recovered = sanitize_physics_state(
            self.position, self.velocity, self.acceleration, self.id
        )

        if recovered:
            logger.warning(f"Ship {self.id}: Physics state recovered from invalid values")
            # Publish event for monitoring/debugging
            self.event_bus.publish("physics_recovery", {
                "ship_id": self.id,
                "position": self.position,
                "velocity": self.velocity,
                "acceleration": self.acceleration
            })

        # S3: Update orientation using quaternion integration (no gimbal lock!)
        # Quaternion derivative: dq/dt = 0.5 * q * ω
        # where ω is represented as pure quaternion (0, ωx, ωy, ωz)

        # Convert angular velocity from degrees/s to radians/s
        # Axis mapping: aerospace convention (pitch=Y, yaw=Z, roll=X)
        omega_x = math.radians(self.angular_velocity.get("roll", 0.0))   # Roll = rotation around X
        omega_y = math.radians(self.angular_velocity.get("pitch", 0.0))  # Pitch = rotation around Y
        omega_z = math.radians(self.angular_velocity.get("yaw", 0.0))    # Yaw = rotation around Z

        # Create pure quaternion from angular velocity
        omega_quat = Quaternion(0.0, omega_x, omega_y, omega_z)

        # Compute quaternion derivative
        q_dot = (self.quaternion * omega_quat).scale(0.5)

        # Integrate quaternion (Euler integration)
        self.quaternion = self.quaternion + q_dot.scale(dt)

        # Normalize quaternion to prevent drift
        self.quaternion.normalize()

        # Sync Euler angles from quaternion for backward compatibility and telemetry
        pitch, yaw, roll = self.quaternion.to_euler()
        self.orientation["pitch"] = pitch
        self.orientation["yaw"] = yaw
        self.orientation["roll"] = roll

        # Guard against NaN in Euler angles (shouldn't happen with quaternions, but safety check)
        for key in self.orientation:
            if not is_valid_number(self.orientation[key]):
                logger.error(f"Ship {self.id}: Invalid orientation {key}={self.orientation[key]}, resetting quaternion")
                self.quaternion = quaternion_identity()
                self.orientation[key] = 0.0

        # S3: No more gimbal lock warnings! Quaternions handle all orientations perfectly.
        # The old gimbal lock warning has been removed - quaternions eliminate this issue entirely.

    def command(self, command_type, params=None):
        """
        Process a command
        
        Args:
            command_type (str): The type of command
            params (dict): Parameters for the command
            
        Returns:
            dict: Response containing the result or error
        """
        if params is None:
            params = {}
            
        # Check if this is a system-specific command
        if "system" in params:
            system_type = params["system"]
            if system_type in self.systems:
                system = self.systems[system_type]
                # Check if this is a direct system command
                if "command" in params:
                    system_cmd = params["command"]
                    system_params = params.get("params", {})
                    
                    if hasattr(system, "command") and callable(system.command):
                        return system.command(system_cmd, system_params)
                    else:
                        return {"error": f"System {system_type} does not support commands"}
                        
                # Otherwise, pass the command to the system's command handler
                elif hasattr(system, "command") and callable(system.command):
                    return system.command(command_type, params)
        
        # Check ship's command handlers
        if command_type in self.command_handlers:
            return self.command_handlers[command_type](params)
            
        # Try to find a system that can handle this command
        for system_type, system in self.systems.items():
            if hasattr(system, "command") and callable(system.command):
                try:
                    result = system.command(command_type, params)
                    if result and "error" not in result:
                        return result
                except Exception:
                    pass  # Ignore exceptions, try next system
        
        return {"error": f"Command '{command_type}' not recognized"}
    
    def get_state(self):
        """
        Get the current state of the ship and all systems
        
        Returns:
            dict: Complete ship state
        """
        # Start with the ship's physical state
        state = {
            "id": self.id,
            "name": self.name,
            "class": self.class_type,
            "faction": self.faction,
            "mass": self.mass,
            "hull_integrity": self.hull_integrity,
            "max_hull_integrity": self.max_hull_integrity,
            "hull_percent": (self.hull_integrity / self.max_hull_integrity * 100) if self.max_hull_integrity > 0 else 0,
            "position": self.position,
            "velocity": self.velocity,
            "acceleration": self.acceleration,
            "orientation": self.orientation,
            "angular_velocity": self.angular_velocity,
            "thrust": self.thrust,
            "systems": {}
        }
        
        # Add systems state
        for system_type, system in self.systems.items():
            if hasattr(system, "get_state") and callable(system.get_state):
                try:
                    state["systems"][system_type] = system.get_state()
                except Exception as e:
                    state["systems"][system_type] = {
                        "status": "error",
                        "error": str(e)
                    }
            elif isinstance(system, dict):
                # If it's a plain dictionary, include it directly
                state["systems"][system_type] = copy.deepcopy(system)
        
        return state

    def take_damage(self, amount, source=None):
        """
        Apply damage to the ship's hull.

        Args:
            amount (float): Amount of damage to apply
            source (str, optional): ID of ship/weapon that caused damage

        Returns:
            dict: Damage result with current hull status
        """
        if amount <= 0:
            return {"ok": False, "error": "Invalid damage amount"}

        previous_hull = self.hull_integrity
        self.hull_integrity = max(0.0, self.hull_integrity - amount)

        # Publish damage event
        self.event_bus.publish("ship_damaged", {
            "ship_id": self.id,
            "damage": amount,
            "hull_before": previous_hull,
            "hull_after": self.hull_integrity,
            "source": source,
            "destroyed": self.is_destroyed()
        })

        if self.is_destroyed():
            logger.warning(f"Ship {self.id} destroyed! Hull integrity: {self.hull_integrity:.1f}")
            self.event_bus.publish("ship_destroyed", {
                "ship_id": self.id,
                "source": source
            })

        return {
            "ok": True,
            "damage_applied": amount,
            "hull_integrity": self.hull_integrity,
            "max_hull_integrity": self.max_hull_integrity,
            "hull_percent": (self.hull_integrity / self.max_hull_integrity * 100) if self.max_hull_integrity > 0 else 0,
            "destroyed": self.is_destroyed()
        }

    def is_destroyed(self):
        """
        Check if the ship is destroyed (hull integrity <= 0).

        Returns:
            bool: True if ship is destroyed
        """
        return self.hull_integrity <= 0

    def _cmd_get_state(self, params):
        """Command handler for get_state"""
        return self.get_state()

    def _cmd_get_position(self, params):
        """Return current ship position"""
        return dict(self.position)

    def _cmd_get_velocity(self, params):
        """Return current ship velocity"""
        return dict(self.velocity)

    def _cmd_get_orientation(self, params):
        """Return current ship orientation"""
        return dict(self.orientation)
    
    def _cmd_set_thrust(self, params):
        """Command handler for set_thrust"""
        # Check for override by helm system
        helm_system = self.systems.get("helm", None)
        if helm_system and hasattr(helm_system, "get_state"):
            helm_state = helm_system.get_state()
            if helm_state.get("manual_override", False):
                return {"error": "Cannot set thrust while helm has manual control"}
        
        # Check for override by navigation system
        nav_system = self.systems.get("navigation", None)
        if nav_system and hasattr(nav_system, "get_state"):
            nav_state = nav_system.get_state()
            if nav_state.get("autopilot_enabled", False):
                return {"error": "Cannot set thrust while autopilot is engaged"}
        
        # Update thrust
        for axis in ["x", "y", "z"]:
            if axis in params:
                try:
                    self.thrust[axis] = float(params[axis])
                except (ValueError, TypeError):
                    return {"error": f"Invalid thrust value for {axis}: {params[axis]}"}
        
        return {"status": "Thrust updated", "thrust": self.thrust}
    
    def _cmd_set_course(self, params):
        """Command handler for set_course"""
        # Pass to navigation system if available
        if "navigation" in self.systems:
            nav_system = self.systems["navigation"]
            if hasattr(nav_system, "command") and callable(nav_system.command):
                return nav_system.command("set_course", params)
        
        return {"error": "Navigation system not available"}
    
    def _cmd_rotate(self, params):
        """Command handler for rotate"""
        axis = params.get("axis", "yaw")
        if axis not in ["pitch", "yaw", "roll"]:
            return {"error": f"Invalid rotation axis: {axis}"}
        
        try:
            value = float(params.get("value", 0))
            self.orientation[axis] += value
            
            # Normalize to [-180, 180)
            while self.orientation[axis] >= 180:
                self.orientation[axis] -= 360
            while self.orientation[axis] < -180:
                self.orientation[axis] += 360
                
            return {"status": "Rotation applied", "orientation": self.orientation}
        except (ValueError, TypeError):
            return {"error": f"Invalid rotation value: {params.get('value')}"}
    
    def _cmd_get_system_state(self, params):
        """Command handler for get_system_state"""
        system_type = params.get("system")
        if not system_type:
            return {"error": "System type not specified"}
            
        if system_type in self.systems:
            system = self.systems[system_type]
            
            if hasattr(system, "get_state") and callable(system.get_state):
                return system.get_state()
            elif isinstance(system, dict):
                return copy.deepcopy(system)
            else:
                return {"status": "System found but state not available"}
        else:
            return {"error": f"System '{system_type}' not found"}

    def _cmd_request_power(self, params):
        """Request power via the power management system"""
        pm = self.systems.get("power_management")
        if not pm:
            return {"error": "Power management system not available"}
        amount = float(params.get("amount", 0))
        system = params.get("system", "")
        layer = params.get("layer")
        success = pm.request_power(amount, system, layer)
        return {"success": success, "state": pm.get_state()}

    def _cmd_reroute_power(self, params):
        """Reroute power between layers"""
        pm = self.systems.get("power_management")
        if not pm:
            return {"error": "Power management system not available"}
        amount = float(params.get("amount", 0))
        from_layer = params.get("from_layer", "primary")
        to_layer = params.get("to_layer", "secondary")
        moved = pm.reroute_power(amount, from_layer, to_layer)
        return {"moved": moved, "state": pm.get_state()}

    def _cmd_get_power_state(self, params):
        """Return power management system state"""
        pm = self.systems.get("power_management")
        if not pm:
            return {"error": "Power management system not available"}
        return pm.get_state()

    def enable_ai(self, behavior=None, params=None):
        """
        Enable AI control for this ship.

        Args:
            behavior (AIBehavior, optional): Initial AI behavior
            params (dict, optional): Behavior parameters

        Returns:
            bool: True if AI was enabled successfully
        """
        try:
            from hybrid.fleet.ai_controller import AIController, AIBehavior

            # Create AI controller if it doesn't exist
            if not self.ai_controller:
                self.ai_controller = AIController(self)

            # Set behavior if specified
            if behavior:
                self.ai_controller.set_behavior(behavior, params)

            self.ai_enabled = True
            logger.info(f"AI enabled for {self.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to enable AI for {self.id}: {e}")
            return False

    def disable_ai(self):
        """
        Disable AI control for this ship.

        Returns:
            bool: True if AI was disabled successfully
        """
        self.ai_enabled = False
        logger.info(f"AI disabled for {self.id}")
        return True

    def set_ai_behavior(self, behavior, params=None):
        """
        Set AI behavior (AI must be enabled first).

        Args:
            behavior (AIBehavior): Behavior to set
            params (dict, optional): Behavior parameters

        Returns:
            bool: True if behavior was set successfully
        """
        if not self.ai_controller:
            logger.warning(f"Cannot set AI behavior for {self.id}: AI not initialized")
            return False

        try:
            self.ai_controller.set_behavior(behavior, params)
            return True
        except Exception as e:
            logger.error(f"Failed to set AI behavior for {self.id}: {e}")
            return False
