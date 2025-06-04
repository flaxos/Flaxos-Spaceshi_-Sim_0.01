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
