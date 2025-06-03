# hybrid/systems/helm_system.py
"""
Helm system implementation for ship simulation.
Handles manual control of ship thrust and orientation.
"""
# hybrid/systems/helm_system.py
"""
Helm system implementation for the ship.
Handles manual control of ship thrust and orientation.
"""
from hybrid.base_system import BaseSystem
import math

class HelmSystem(BaseSystem):
    """Manages manual control of ship thrust and orientation"""
    
    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}
        
        # Manual control settings
        self.manual_override = config.get("manual_override", False)
        
        # Control modes
        self.control_mode = config.get("control_mode", "standard")  # standard, precise, rapid
        
        # Dampening settings
        self.dampening = config.get("dampening", 0.8)
        
        # Status
        self.status = "standby"
    
    def tick(self, dt, ship, event_bus):
        """Update helm system state"""
        if not self.enabled:
            self.status = "offline"
            return
            
        if self.manual_override:
            self.status = "manual_control"
            # In a full implementation, this would apply controls set via
            # commands or input devices
        else:
            self.status = "standby"
    
    def command(self, action, params):
        """Process helm system commands"""
        if action == "helm_override":
            return self._cmd_helm_override(params)
        elif action == "set_thrust":
            return self._cmd_set_thrust(params, ship)
        elif action == "set_dampening":
            return self._cmd_set_dampening(params)
        elif action == "set_mode":
            return self._cmd_set_mode(params)
        else:
            return super().command(action, params)
    
    def _cmd_helm_override(self, params):
        """Handle helm_override command"""
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        
        if "enabled" in params:
            try:
                self.manual_override = bool(params["enabled"])
                
                # Check if this conflicts with navigation autopilot
                # and disable autopilot if needed
                ship = params.get("_ship")  # Injected by command handler
                if self.manual_override and ship and "navigation" in ship.systems:
                    nav_system = ship.systems["navigation"]
                    if hasattr(nav_system, "command") and callable(nav_system.command):
                        nav_system.command("autopilot", {"enabled": False})
                
                return {
                    "status": f"Manual helm control {'enabled' if self.manual_override else 'disabled'}"
                }
            except (ValueError, TypeError):
                return {"error": f"Invalid value for 'enabled': {params['enabled']}"}
        else:
            return {"error": "Missing 'enabled' parameter"}
    
    def _cmd_set_thrust(self, params, ship):
        """Handle set_thrust command (when in manual control)"""
        if not self.enabled:
            return {"error": "Helm system is disabled"}
            
        if not self.manual_override:
            return {"error": "Manual helm control not active"}
            
        # Get propulsion system for thrust limits
        max_thrust = 100.0  # Default max thrust
        if "propulsion" in ship.systems and hasattr(ship.systems["propulsion"], "get_state"):
            prop_state = ship.systems["propulsion"].get_state()
            max_thrust = prop_state.get("max_thrust", 100.0)
            
        # Update thrust
        thrust = ship.thrust.copy()
        for axis in ["x", "y", "z"]:
            if axis in params:
                try:
                    value = float(params[axis])
                    # Limit to max thrust
                    if abs(value) > max_thrust:
                        value = math.copysign(max_thrust, value)
                    thrust[axis] = value
                except (ValueError, TypeError):
                    return {"error": f"Invalid thrust value for {axis}: {params[axis]}"}
        
        # Apply thrust to ship
        ship.thrust = thrust
        
        return {"status": "Thrust updated", "thrust": thrust}
    
    def _cmd_set_dampening(self, params):
        """Handle set_dampening command"""
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        
        if "value" in params:
            try:
                value = float(params["value"])
                if value < 0 or value > 1:
                    return {"error": "Dampening value must be between 0 and 1"}
                self.dampening = value
                return {"status": "Dampening set", "value": self.dampening}
            except (ValueError, TypeError):
                return {"error": f"Invalid dampening value: {params['value']}"}
        else:
            return {"error": "Missing 'value' parameter"}
    
    def _cmd_set_mode(self, params):
        """Handle set_mode command"""
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        
        if "mode" in params:
            mode = params["mode"]
            if mode in ["standard", "precise", "rapid"]:
                self.control_mode = mode
                return {"status": "Control mode set", "mode": self.control_mode}
            else:
                return {"error": f"Invalid mode: {mode}. Must be 'standard', 'precise', or 'rapid'"}
        else:
            return {"error": "Missing 'mode' parameter"}
    
    def get_state(self):
        """Get helm system state"""
        state = super().get_state()
        state.update({
            "status": self.status,
            "manual_override": self.manual_override,
            "control_mode": self.control_mode,
            "dampening": self.dampening
        })
        return state
from hybrid.base_system import BaseSystem
import math
import logging

logger = logging.getLogger(__name__)

class HelmSystem(BaseSystem):
    """
    Helm system for ships. Handles manual control.
    """
    
    def __init__(self, config=None):
        """
        Initialize the helm system
        
        Args:
            config (dict): Helm system configuration
        """
        super().__init__(config)
        config = config or {}
        
        # Power requirements
        self.power_draw = config.get("power_draw", 2.0)
        
        # Control mode (manual or autopilot)
        self.mode = config.get("mode", "autopilot")
        
        # Manual thrust settings
        self.manual_thrust = config.get("manual_thrust", {"x": 0.0, "y": 0.0, "z": 0.0})
        
    def tick(self, dt, ship, event_bus):
        """
        Update helm system for current time step
        
        Args:
            dt (float): Time delta in seconds
            ship (Ship): The parent ship
            event_bus (EventBus): Event bus for system communication
        """
        if not self.enabled:
            return
            
        # Request power from power system
        power_system = ship.systems.get("power")
        if power_system and not power_system.request_power(self.power_draw * dt, "helm"):
            # Not enough power, disable temporarily
            return
            
        # Apply manual thrust if in manual mode
        if self.mode == "manual":
            propulsion = ship.systems.get("propulsion")
            if propulsion and hasattr(propulsion, 'set_thrust'):
                propulsion.set_thrust(self.manual_thrust)
                
        # Subscribe to relevant events
        # This could be done at initialization but is shown here for clarity
        event_bus.subscribe("navigation_autopilot_engaged", self._handle_autopilot_engaged)
        event_bus.subscribe("navigation_autopilot_disengaged", self._handle_autopilot_disengaged)
        
    def command(self, action, params):
        """
        Process helm system commands
        
        Args:
            action (str): Command action
            params (dict): Command parameters
            
        Returns:
            dict: Command response
        """
        if action == "helm_override" or action == "set_mode":
            return self.set_mode(params)
        elif action == "set_manual_thrust":
            return self.set_manual_thrust(params)
        elif action == "status":
            return self.get_state()
        elif action == "power_on":
            return self.power_on()
        elif action == "power_off":
            return self.power_off()
        return super().command(action, params)
        
    def set_mode(self, params):
        """
        Set helm control mode
        
        Args:
            params (dict): Mode parameters
            
        Returns:
            dict: Command response
        """
        if "enabled" in params:
            # Convert to boolean (accepts 0/1, true/false, etc.)
            manual_enabled = bool(params["enabled"])
            self.mode = "manual" if manual_enabled else "autopilot"
        elif "mode" in params:
            mode = params["mode"]
            if mode in ["manual", "autopilot"]:
                self.mode = mode
            else:
                return {"error": f"Invalid mode: {mode}"}
                
        return {
            "status": f"Helm mode set to {self.mode}",
            "mode": self.mode
        }
        
    def set_manual_thrust(self, params):
        """
        Set manual thrust values
        
        Args:
            params (dict): Thrust parameters
            
        Returns:
            dict: Command response
        """
        if not self.enabled:
            return {"error": "Helm system is disabled"}
            
        # Update thrust values
        for axis in ["x", "y", "z"]:
            if axis in params:
                self.manual_thrust[axis] = float(params[axis])
                
        return {
            "status": "Manual thrust updated",
            "thrust": self.manual_thrust
        }
        
    def _handle_autopilot_engaged(self, event):
        """
        Handle autopilot engaged event
        
        Args:
            event (dict): Event data
        """
        self.mode = "autopilot"
        logger.info("Autopilot engaged, helm switching to autopilot mode")
        
    def _handle_autopilot_disengaged(self, event):
        """
        Handle autopilot disengaged event
        
        Args:
            event (dict): Event data
        """
        # Stay in current mode, could optionally switch to manual here
        logger.info("Autopilot disengaged")
        
    def get_state(self):
        """
        Get current helm system state
        
        Returns:
            dict: Helm system state
        """
        state = super().get_state()
        state.update({
            "mode": self.mode,
            "manual_thrust": self.manual_thrust
        })
        return state
