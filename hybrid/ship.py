# hybrid/ship.py
"""
Ship class that manages multiple systems and handles physics simulation.
"""

import math
import logging
from datetime import datetime
from hybrid.event_bus import EventBus

logger = logging.getLogger(__name__)

class Ship:
    """
    Ship class that contains and manages all ship systems.
    Handles physics simulation and delegates system-specific behavior to system classes.
    """
    
    def __init__(self, ship_id, config):
        """
        Initialize a ship with the given configuration
        
        Args:
            ship_id (str): Unique identifier for the ship
            config (dict): Ship configuration including position, systems, etc.
        """
        self.id = ship_id
        self.position = config.get("position", {"x": 0.0, "y": 0.0, "z": 0.0})
        self.velocity = config.get("velocity", {"x": 0.0, "y": 0.0, "z": 0.0})
        self.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.orientation = config.get("orientation", {"pitch": 0.0, "yaw": 0.0, "roll": 0.0})
        self.angular_velocity = config.get("angular_velocity", {"pitch": 0.0, "yaw": 0.0, "roll": 0.0})
        self.mass = config.get("mass", 1.0)
        
        # Create event bus for inter-system communication
        self.event_bus = EventBus()
        
        # Initialize systems
        systems_config = config.get("systems", {})
        self.systems = self._initialize_systems(systems_config)
        
        # Track the last tick time
        self.last_tick_time = datetime.utcnow()
        
    def _initialize_systems(self, systems_config):
        """
        Initialize ship systems based on configuration
        
        Args:
            systems_config (dict): Configuration for all systems
            
        Returns:
            dict: Dictionary of initialized system objects
        """
        from hybrid.systems.power_system import PowerSystem
        from hybrid.systems.sensor_system import SensorSystem
        from hybrid.systems.helm_system import HelmSystem
        from hybrid.systems.navigation_system import NavigationSystem
        from hybrid.systems.bio_monitor_system import BioMonitorSystem
        from hybrid.systems.propulsion_system import PropulsionSystem
        
        # Map system names to their class implementations
        system_map = {
            "power": PowerSystem,
            "sensors": SensorSystem,
            "helm": HelmSystem,
            "navigation": NavigationSystem,
            "bio_monitor": BioMonitorSystem,
            "propulsion": PropulsionSystem
        }
        
        systems = {}
        
        # Initialize each system
        for system_name, config in systems_config.items():
            if system_name in system_map:
                try:
                    systems[system_name] = system_map[system_name](config)
                    logger.info(f"Initialized {system_name} system for ship {self.id}")
                except Exception as e:
                    logger.error(f"Failed to initialize {system_name} system: {e}")
                    # Use a basic version as fallback
                    from hybrid.base_system import BaseSystem
                    systems[system_name] = BaseSystem(config)
            else:
                logger.warning(f"Unknown system type: {system_name}")
                
        return systems
        
    def tick(self, dt, all_ships=None):
        """
        Update ship state for the current time step
        
        Args:
            dt (float): Time delta in seconds
            all_ships (list, optional): List of all ships in the simulation
            
        Returns:
            None
        """
        # Store current tick time
        current_time = datetime.utcnow()
        self.last_tick_time = current_time
        
        # Calculate net force from all systems
        net_force = {"x": 0.0, "y": 0.0, "z": 0.0}
        
        # Update all systems
        for system_name, system in self.systems.items():
            if system.enabled:
                try:
                    system.tick(dt, self, self.event_bus)
                    
                    # Special handling for propulsion system
                    if system_name == "propulsion":
                        thrust = system.get_thrust()
                        if thrust:
                            net_force["x"] += thrust.get("x", 0)
                            net_force["y"] += thrust.get("y", 0)
                            net_force["z"] += thrust.get("z", 0)
                except Exception as e:
                    logger.error(f"Error in {system_name} system tick: {e}")
        
        # Update physics
        self._update_physics(dt, net_force)
        
    def _update_physics(self, dt, force):
        """
        Update ship physics based on forces and time delta
        
        Args:
            dt (float): Time delta in seconds
            force (dict): Net force vector acting on the ship
            
        Returns:
            None
        """
        # Calculate acceleration (F = ma)
        self.acceleration = {
            "x": force["x"] / self.mass,
            "y": force["y"] / self.mass,
            "z": force["z"] / self.mass
        }
        
        # Update velocity (v = v0 + a*t)
        self.velocity = {
            "x": self.velocity["x"] + self.acceleration["x"] * dt,
            "y": self.velocity["y"] + self.acceleration["y"] * dt,
            "z": self.velocity["z"] + self.acceleration["z"] * dt
        }
        
        # Update position (p = p0 + v*t)
        self.position = {
            "x": self.position["x"] + self.velocity["x"] * dt,
            "y": self.position["y"] + self.velocity["y"] * dt,
            "z": self.position["z"] + self.velocity["z"] * dt
        }
        
        # Update orientation based on angular velocity
        self.orientation = {
            "pitch": (self.orientation["pitch"] + self.angular_velocity["pitch"] * dt) % 360,
            "yaw": (self.orientation["yaw"] + self.angular_velocity["yaw"] * dt) % 360,
            "roll": (self.orientation["roll"] + self.angular_velocity["roll"] * dt) % 360
        }
        
    def command(self, command_type, params):
        """
        Process a command for this ship or route to appropriate system
        
        Args:
            command_type (str): The type of command
            params (dict): Command parameters
            
        Returns:
            dict: Command response
        """
        # Handle ship-level commands
        if command_type == "get_position":
            return self.position
        elif command_type == "get_velocity":
            return self.velocity
        elif command_type == "get_orientation":
            return self.orientation
        elif command_type == "get_state":
            return self.get_state()
            
        # Route system-specific commands
        if "system" in params:
            system_name = params["system"]
            if system_name in self.systems:
                action = params.get("action", command_type)
                return self.systems[system_name].command(action, params)
            else:
                return {"error": f"System {system_name} not found"}
                
        # Try to find a system that can handle this command
        for system in self.systems.values():
            response = system.command(command_type, params)
            if "error" not in response:
                return response
                
        return {"error": f"Unknown command: {command_type}"}
        
    def get_state(self):
        """
        Get the complete state of the ship and all its systems
        
        Returns:
            dict: Ship state
        """
        state = {
            "id": self.id,
            "position": self.position,
            "velocity": self.velocity,
            "acceleration": self.acceleration,
            "orientation": self.orientation,
            "angular_velocity": self.angular_velocity,
            "mass": self.mass,
            "systems": {}
        }
        
        # Add state for each system
        for system_name, system in self.systems.items():
            state["systems"][system_name] = system.get_state()
            
        return state
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
            "get_position": self._cmd_get_position,
            "get_velocity": self._cmd_get_velocity,
            "get_orientation": self._cmd_get_orientation,
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
    
    def tick(self, dt, all_ships=None):
        """
        Update ship state for the current time step

        Args:
            dt (float): Time delta in seconds
            all_ships (list, optional): Unused but accepted for compatibility
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
    
    def _update_physics(self, dt, force=None):
        """Update ship physics for the current time step

        Args:
            dt (float): Time delta in seconds
            force (dict, optional): Net force vector acting on the ship. If not
                provided, the existing acceleration is used.
        """
        if force is not None:
            self.acceleration = {
                "x": force.get("x", 0.0) / self.mass,
                "y": force.get("y", 0.0) / self.mass,
                "z": force.get("z", 0.0) / self.mass,
            }

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