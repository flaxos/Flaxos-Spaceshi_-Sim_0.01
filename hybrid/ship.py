# hybrid/ship.py
"""
Ship implementation that manages systems and handles physics.
"""
from hybrid.event_bus import EventBus
import math
import time
import copy

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
        
        # Initialize physical state
        self.position = self._get_vector3_config(config.get("position", {}))
        self.velocity = self._get_vector3_config(config.get("velocity", {}))
        self.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.orientation = self._get_vector3_config(config.get("orientation", {}), "pitch", "yaw", "roll")
        self.angular_velocity = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        self.thrust = {"x": 0.0, "y": 0.0, "z": 0.0}
        
        # Create the event bus for system communication
        self.event_bus = EventBus()
        
        # Initialize systems
        self.systems = {}
        self._load_systems(config.get("systems", {}))
        
        # Initialize command handler
        self.command_handlers = {
            "get_state": self._cmd_get_state,
            "set_thrust": self._cmd_set_thrust,
            "set_course": self._cmd_set_course,
            "rotate": self._cmd_rotate,
            "get_system_state": self._cmd_get_system_state,
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
    
    def tick(self, dt):
        """
        Update ship state for the current time step
        
        Args:
            dt (float): Time delta in seconds
        """
        # First pass: update all systems
        for system_type, system in self.systems.items():
            if hasattr(system, "tick") and callable(system.tick):
                try:
                    system.tick(dt, self, self.event_bus)
                except Exception as e:
                    print(f"Error in system {system_type} tick: {e}")
        
        # Update physics after systems have updated
        self._update_physics(dt)
    
    def _update_physics(self, dt):
        """
        Update ship physics for the current time step
        
        Args:
            dt (float): Time delta in seconds
        """
        # Update position based on velocity
        self.position["x"] += self.velocity["x"] * dt
        self.position["y"] += self.velocity["y"] * dt
        self.position["z"] += self.velocity["z"] * dt
        
        # Update velocity based on acceleration
        self.velocity["x"] += self.acceleration["x"] * dt
        self.velocity["y"] += self.acceleration["y"] * dt
        self.velocity["z"] += self.acceleration["z"] * dt
        
        # Update orientation based on angular velocity
        self.orientation["pitch"] += self.angular_velocity["pitch"] * dt
        self.orientation["yaw"] += self.angular_velocity["yaw"] * dt
        self.orientation["roll"] += self.angular_velocity["roll"] * dt
        
        # Normalize orientation to [-180, 180)
        for key in self.orientation:
            while self.orientation[key] >= 180:
                self.orientation[key] -= 360
            while self.orientation[key] < -180:
                self.orientation[key] += 360
    
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

        # Simple ship-level queries
        if command_type == "get_position":
            return self.position
        if command_type == "get_velocity":
            return self.velocity
        if command_type == "get_orientation":
            return self.orientation
        if command_type == "get_state":
            return self.get_state()
            
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
    
    def _cmd_get_state(self, params):
        """Command handler for get_state"""
        return self.get_state()
    
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