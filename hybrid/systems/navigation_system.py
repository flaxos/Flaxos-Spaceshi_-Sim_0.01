# hybrid/systems/navigation_system.py
"""
Navigation system implementation for ship simulation.
Handles autopilot and course plotting.
"""

from hybrid.base_system import BaseSystem
import math
import logging

logger = logging.getLogger(__name__)

class NavigationSystem(BaseSystem):
    """
    Navigation system for ships. Handles autopilot and course plotting.
    """
    
    def __init__(self, config=None):
        """
        Initialize the navigation system
        
        Args:
            config (dict): Navigation system configuration
        """
        super().__init__(config)
        config = config or {}
        
        # Power requirements
        self.power_draw = config.get("power_draw", 3.0)
        
        # Navigation settings
        self.autopilot = config.get("autopilot", False)
        self.target = config.get("target", None)
        self.thrust = config.get("thrust", 1.0)  # Default thrust magnitude
        self.arrival_distance = config.get("arrival_distance", 1.0)
        
        # Waypoints for complex courses
        self.waypoints = config.get("waypoints", [])
        self.current_waypoint = 0
        
    def tick(self, dt, ship, event_bus):
        """
        Update navigation system for current time step
        
        Args:
            dt (float): Time delta in seconds
            ship (Ship): The parent ship
            event_bus (EventBus): Event bus for system communication
        """
        if not self.enabled:
            if self.autopilot:
                self.autopilot = False
                event_bus.publish("navigation_autopilot_disengaged", None, "navigation")
            return
            
        # Request power from power system
        power_system = ship.systems.get("power")
        if power_system and not power_system.request_power(self.power_draw * dt, "navigation"):
            # Not enough power, disable temporarily
            if self.autopilot:
                self.autopilot = False
                event_bus.publish("navigation_autopilot_disengaged", 
                                 {"reason": "power_loss"}, "navigation")
            return
            
        # Check if autopilot is enabled
        if not self.autopilot:
            return
            
        # Check if target is set
        tgt = self.target
        if not tgt:
            # If we have waypoints, use the current one
            if self.waypoints and self.current_waypoint < len(self.waypoints):
                tgt = self.waypoints[self.current_waypoint]
            else:
                return
                
        # Calculate vector to target
        pos = ship.position
        dx = tgt["x"] - pos["x"]
        dy = tgt["y"] - pos["y"]
        dz = tgt["z"] - pos["z"]
        dist = math.sqrt(dx**2 + dy**2 + dz**2)
        
        # Check if we've reached the target
        if dist < self.arrival_distance:
            # If we're following waypoints, advance to the next one
            if self.waypoints and self.current_waypoint < len(self.waypoints):
                self.current_waypoint += 1
                if self.current_waypoint >= len(self.waypoints):
                    # End of waypoints
                    self.autopilot = False
                    self.target = None
                    event_bus.publish("navigation_course_complete", None, "navigation")
                else:
                    # Move to next waypoint
                    self.target = self.waypoints[self.current_waypoint]
                    event_bus.publish("navigation_waypoint_reached", 
                                     {"waypoint": self.current_waypoint}, "navigation")
            else:
                # Single target reached
                self.autopilot = False
                self.target = None
                event_bus.publish("navigation_target_reached", None, "navigation")
            return
            
        # Calculate normalized direction and apply thrust
        if dist > 0:
            norm_x = dx / dist
            norm_y = dy / dist
            norm_z = dz / dist
            
            thrust = {
                "x": norm_x * self.thrust,
                "y": norm_y * self.thrust,
                "z": norm_z * self.thrust
            }
            
            # Apply thrust to propulsion
            propulsion = ship.systems.get("propulsion")
            if propulsion and hasattr(propulsion, 'set_thrust'):
                propulsion.set_thrust(thrust)
        
    def command(self, action, params):
        """
        Process navigation system commands
        
        Args:
            action (str): Command action
            params (dict): Command parameters
            
        Returns:
            dict: Command response
        """
        if action == "set_course":
            return self.set_course(params)
        elif action == "autopilot":
            return self.set_autopilot(params)
        elif action == "add_waypoint":
            return self.add_waypoint(params)
        elif action == "clear_waypoints":
            return self.clear_waypoints()
        elif action == "set_thrust":
            return self.set_autopilot_thrust(params)
        elif action == "status":
            return self.get_state()
        elif action == "power_on":
            return self.power_on()
        elif action == "power_off":
            return self.power_off()
        return super().command(action, params)
        
    def set_course(self, params):
        """
        Set a course to a target
        
        Args:
            params (dict): Course parameters
            
        Returns:
            dict: Command response
        """
        if not self.enabled:
            return {"error": "Navigation system is disabled"}
            
        # Check for target coordinates
        target = params.get("target")
        if not target:
            # Try to get x, y, z directly
            x = float(params.get("x", 0))
            y = float(params.get("y", 0))
            z = float(params.get("z", 0))
            target = {"x": x, "y": y, "z": z}
            
        self.target = target
        self.autopilot = True
        
        return {
            "status": "Course set",
            "target": self.target
        }
        
    def set_autopilot(self, params):
        """
        Enable or disable autopilot
        
        Args:
            params (dict): Autopilot parameters
            
        Returns:
            dict: Command response
        """
        if not self.enabled:
            return {"error": "Navigation system is disabled"}
            
        # Check for enabled parameter
        if "enabled" in params:
            self.autopilot = bool(params["enabled"])
            
        status = "enabled" if self.autopilot else "disabled"
        return {
            "status": f"Autopilot {status}",
            "autopilot": self.autopilot
        }
        
    def add_waypoint(self, params):
        """
        Add a waypoint to the course
        
        Args:
            params (dict): Waypoint parameters
            
        Returns:
            dict: Command response
        """
        if not self.enabled:
            return {"error": "Navigation system is disabled"}
            
        # Get waypoint coordinates
        x = float(params.get("x", 0))
        y = float(params.get("y", 0))
        z = float(params.get("z", 0))
        waypoint = {"x": x, "y": y, "z": z}
        
        # Add to waypoints list
        self.waypoints.append(waypoint)
        
        # If this is the first waypoint and no target is set,
        # start following it
        if len(self.waypoints) == 1 and not self.target:
            self.target = waypoint
            
        return {
            "status": "Waypoint added",
            "waypoint": waypoint,
            "waypoint_count": len(self.waypoints)
        }
        
    def clear_waypoints(self):
        """
        Clear all waypoints
        
        Returns:
            dict: Command response
        """
        self.waypoints = []
        self.current_waypoint = 0
        return {
            "status": "Waypoints cleared"
        }
        
    def set_autopilot_thrust(self, params):
        """
        Set autopilot thrust magnitude
        
        Args:
            params (dict): Thrust parameters
            
        Returns:
            dict: Command response
        """
        if "thrust" in params:
            self.thrust = float(params["thrust"])
        elif "value" in params:
            self.thrust = float(params["value"])
            
        return {
            "status": f"Autopilot thrust set to {self.thrust}",
            "thrust": self.thrust
        }
        
    def get_state(self):
        """
        Get current navigation system state
        
        Returns:
            dict: Navigation system state
        """
        state = super().get_state()
        state.update({
            "autopilot": self.autopilot,
            "target": self.target,
            "thrust": self.thrust,
            "waypoints": self.waypoints,
            "current_waypoint": self.current_waypoint,
            "waypoint_count": len(self.waypoints)
        })
        return state
# hybrid/systems/navigation_system.py
"""
Navigation system implementation for the ship.
Handles autopilot and course plotting.
"""
from hybrid.base_system import BaseSystem
import math

class NavigationSystem(BaseSystem):
    """Manages ship navigation and autopilot"""
    
    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}
        
        # Autopilot settings
        self.autopilot_enabled = config.get("autopilot_enabled", False)
        self.auto_avoidance = config.get("auto_avoidance", True)
        
        # Target coordinates
        self.target = {
            "x": float(config.get("target_x", 0.0)),
            "y": float(config.get("target_y", 0.0)),
            "z": float(config.get("target_z", 0.0))
        }
        
        # Navigation parameters
        self.approach_distance = float(config.get("approach_distance", 10.0))
        self.max_speed = float(config.get("max_speed", 100.0))
        self.braking_distance = float(config.get("braking_distance", 200.0))
        
        # Course status
        self.distance_to_target = 0.0
        self.status = "standby"
    
    def tick(self, dt, ship, event_bus):
        """Update navigation system state"""
        if not self.enabled:
            self.status = "offline"
            return
            
        # Calculate distance to target
        self.distance_to_target = math.sqrt(
            (ship.position["x"] - self.target["x"]) ** 2 +
            (ship.position["y"] - self.target["y"]) ** 2 +
            (ship.position["z"] - self.target["z"]) ** 2
        )
        
        # If autopilot is enabled, navigate to target
        if self.autopilot_enabled:
            self._autopilot_navigate(dt, ship, event_bus)
    
    def _autopilot_navigate(self, dt, ship, event_bus):
        """Handle autopilot navigation to target"""
        # Calculate direction to target
        direction = {
            "x": self.target["x"] - ship.position["x"],
            "y": self.target["y"] - ship.position["y"],
            "z": self.target["z"] - ship.position["z"]
        }
        
        # Normalize direction
        magnitude = math.sqrt(direction["x"]**2 + direction["y"]**2 + direction["z"]**2)
        if magnitude > 0:
            direction["x"] /= magnitude
            direction["y"] /= magnitude
            direction["z"] /= magnitude
        
        # Calculate desired speed based on distance
        desired_speed = self.max_speed
        if self.distance_to_target < self.braking_distance:
            # Start braking as we approach the target
            braking_factor = self.distance_to_target / self.braking_distance
            desired_speed = self.max_speed * braking_factor
        
        # Calculate desired velocity
        desired_velocity = {
            "x": direction["x"] * desired_speed,
            "y": direction["y"] * desired_speed,
            "z": direction["z"] * desired_speed
        }
        
        # Calculate velocity error
        velocity_error = {
            "x": desired_velocity["x"] - ship.velocity["x"],
            "y": desired_velocity["y"] - ship.velocity["y"],
            "z": desired_velocity["z"] - ship.velocity["z"]
        }
        
        # Get propulsion system for thrust limits
        max_thrust = 100.0  # Default max thrust
        if "propulsion" in ship.systems and hasattr(ship.systems["propulsion"], "get_state"):
            prop_state = ship.systems["propulsion"].get_state()
            max_thrust = prop_state.get("max_thrust", 100.0)
        
        # Calculate thrust (simple P controller)
        kp = 1.0  # Proportional gain
        thrust = {
            "x": velocity_error["x"] * kp,
            "y": velocity_error["y"] * kp,
            "z": velocity_error["z"] * kp
        }
        
        # Limit thrust to max_thrust
        thrust_magnitude = math.sqrt(thrust["x"]**2 + thrust["y"]**2 + thrust["z"]**2)
        if thrust_magnitude > max_thrust:
            scale_factor = max_thrust / thrust_magnitude
            thrust["x"] *= scale_factor
            thrust["y"] *= scale_factor
            thrust["z"] *= scale_factor
        
        # Apply thrust to the ship
        ship.thrust = thrust
        
        # Update status
        if self.distance_to_target < self.approach_distance:
            self.status = "arrived"
            self.autopilot_enabled = False
            event_bus.publish("navigation_arrived", {
                "system": "navigation",
                "target": self.target
            })
        else:
            self.status = "navigating"
    
    def command(self, action, params):
        """Process navigation system commands"""
        if action == "set_course":
            return self._cmd_set_course(params)
        elif action == "autopilot":
            return self._cmd_autopilot(params)
        elif action == "abort_course":
            return self._cmd_abort_course()
        else:
            return super().command(action, params)
    
    def _cmd_set_course(self, params):
        """Handle set_course command"""
        if not self.enabled:
            return {"error": "Navigation system is disabled"}
        
        # Update target coordinates
        for axis in ["x", "y", "z"]:
            if axis in params:
                try:
                    self.target[axis] = float(params[axis])
                except (ValueError, TypeError):
                    return {"error": f"Invalid coordinate for {axis}: {params[axis]}"}
        
        # Calculate new distance
        if hasattr(self, "ship"):
            self.distance_to_target = math.sqrt(
                (self.ship.position["x"] - self.target["x"]) ** 2 +
                (self.ship.position["y"] - self.target["y"]) ** 2 +
                (self.ship.position["z"] - self.target["z"]) ** 2
            )
        
        return {
            "status": "Course set",
            "target": self.target,
            "autopilot": self.autopilot_enabled,
            "distance": self.distance_to_target
        }
    
    def _cmd_autopilot(self, params):
        """Handle autopilot command"""
        if not self.enabled:
            return {"error": "Navigation system is disabled"}
        
        # Enable or disable autopilot
        if "enabled" in params:
            try:
                self.autopilot_enabled = bool(params["enabled"])
                
                # Update status
                if self.autopilot_enabled:
                    self.status = "navigating"
                else:
                    self.status = "standby"
                    
                return {
                    "status": f"Autopilot {'enabled' if self.autopilot_enabled else 'disabled'}",
                    "target": self.target,
                    "distance": self.distance_to_target
                }
            except (ValueError, TypeError):
                return {"error": f"Invalid value for 'enabled': {params['enabled']}"}
        else:
            return {"error": "Missing 'enabled' parameter"}
    
    def _cmd_abort_course(self):
        """Handle abort_course command"""
        if not self.enabled:
            return {"error": "Navigation system is disabled"}
        
        self.autopilot_enabled = False
        self.status = "standby"
        
        return {
            "status": "Course aborted",
            "autopilot": False
        }
    
    def get_state(self):
        """Get navigation system state"""
        state = super().get_state()
        state.update({
            "status": self.status,
            "autopilot_enabled": self.autopilot_enabled,
            "target": self.target,
            "distance_to_target": self.distance_to_target,
            "approach_distance": self.approach_distance,
            "max_speed": self.max_speed,
            "braking_distance": self.braking_distance,
            "auto_avoidance": self.auto_avoidance
        })
        return state