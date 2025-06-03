# hybrid/systems/bio_monitor_system.py
"""
Bio monitor system implementation for ship simulation.
Tracks crew health and g-force limits.
"""

from hybrid.base_system import BaseSystem
import math
import logging

logger = logging.getLogger(__name__)

class BioMonitorSystem(BaseSystem):
    """
    Bio monitor system for ships. Tracks crew health and g-force limits.
    """
    
    def __init__(self, config=None):
        """
        Initialize the bio monitor system
        
        Args:
            config (dict): Bio monitor system configuration
        """
        super().__init__(config)
        config = config or {}
        
        # Power requirements
        self.power_draw = config.get("power_draw", 1.0)
        
        # Bio monitoring settings
        self.g_limit = config.get("g_limit", 8.0)
        self.fail_timer = config.get("fail_timer", 0.0)
        self.current_g = config.get("current_g", 0.0)
        self.status = config.get("status", "nominal")
        self.crew_health = config.get("crew_health", 1.0)
        
        # Safety override
        self.override = config.get("override", False)
        
    def tick(self, dt, ship, event_bus):
        """
        Update bio monitor for current time step
        
        Args:
            dt (float): Time delta in seconds
            ship (Ship): The parent ship
            event_bus (EventBus): Event bus for system communication
        """
        if not self.enabled:
            return
            
        # Request power from power system
        power_system = ship.systems.get("power")
        if power_system and not power_system.request_power(self.power_draw * dt, "bio_monitor"):
            # Not enough power, disable temporarily
            event_bus.publish("bio_monitor_offline", None, "bio_monitor")
            return
            
        # Calculate g-force
        a = ship.acceleration
        g_force = math.sqrt(a["x"]**2 + a["y"]**2 + a["z"]**2) / 9.81
        self.current_g = g_force
        
        # Check for override
        if self.override:
            self.status = "override"
            self.fail_timer = 0
            return
            
        # Check g-force limits
        old_status = self.status
        
        if g_force > self.g_limit:
            self.fail_timer += dt
            if self.fail_timer > 3:
                self.status = "fatal"
                self.crew_health = 0.0
                event_bus.publish("crew_fatal", None, "bio_monitor")
            else:
                self.status = "warning"
                event_bus.publish("high_g_warning", {"g_force": g_force, "timer": self.fail_timer}, "bio_monitor")
        else:
            self.status = "nominal"
            self.fail_timer = 0
            
        # Notify of status changes
        if old_status != self.status:
            event_bus.publish("bio_status_change", {"status": self.status}, "bio_monitor")
        
    def command(self, action, params):
        """
        Process bio monitor commands
        
        Args:
            action (str): Command action
            params (dict): Command parameters
            
        Returns:
            dict: Command response
        """
        if action == "override_bio_monitor" or action == "override":
            return self.set_override(True)
        elif action == "reset_override":
            return self.set_override(False)
        elif action == "status":
            return self.get_state()
        elif action == "power_on":
            return self.power_on()
        elif action == "power_off":
            return self.power_off()
        return super().command(action, params)
        
    def set_override(self, enabled=True):
        """
        Set safety override
        
        Args:
            enabled (bool): Whether override is enabled
            
        Returns:
            dict: Command response
        """
        self.override = enabled
        status = "enabled" if enabled else "disabled"
        return {
            "status": f"Bio monitor override {status}",
            "override": enabled
        }
        
    def get_state(self):
        """
        Get current bio monitor state
        
        Returns:
            dict: Bio monitor state
        """
        state = super().get_state()
        state.update({
            "g_limit": self.g_limit,
            "fail_timer": round(self.fail_timer, 1),
            "current_g": round(self.current_g, 2),
            "status": self.status,
            "crew_health": self.crew_health,
            "override": self.override
        })
        return state
# hybrid/systems/bio_monitor_system.py
"""
Bio-monitor system implementation for the ship.
Tracks crew health and g-force limits.
"""
from hybrid.base_system import BaseSystem
import math

class BioMonitorSystem(BaseSystem):
    """Monitors crew health and g-force limitations"""
    
    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}
        
        # Crew configuration
        self.crew_count = int(config.get("crew_count", 1))
        
        # Health status tracking
        self.health_status = config.get("health_status", "nominal")
        
        # G-force limits
        self.max_sustained_g = float(config.get("max_sustained_g", 3.0))
        self.max_peak_g = float(config.get("max_peak_g", 8.0))
        
        # Current g-forces
        self.current_g = 0.0
        
        # Safety override
        self.safety_override = config.get("safety_override", False)
        
        # System status
        self.status = "monitoring"
        
        # Event tracking
        self.events = []
    
    def tick(self, dt, ship, event_bus):
        """Update bio monitor system state"""
        if not self.enabled:
            self.status = "offline"
            return
        
        # Calculate g-forces from acceleration
        g_forces = math.sqrt(
            ship.acceleration["x"]**2 + 
            ship.acceleration["y"]**2 + 
            ship.acceleration["z"]**2
        ) / 9.81  # Convert to g's
        
        self.current_g = g_forces
        
        # Check g-force limits if safety override is not active
        if not self.safety_override:
            if g_forces > self.max_peak_g:
                # Critical g-forces detected, emergency intervention
                self.health_status = "critical"
                
                # Publish emergency event
                event_bus.publish("bio_emergency", {
                    "system": "bio",
                    "g_forces": g_forces,
                    "limit": self.max_peak_g
                })
                
                # Cut thrust to protect crew
                if "propulsion" in ship.systems:
                    prop = ship.systems["propulsion"]
                    if hasattr(prop, "command") and callable(prop.command):
                        prop.command("emergency_stop", {})
                
                # Record event
                self.events.append({
                    "type": "g_force_critical",
                    "g_forces": g_forces,
                    "limit": self.max_peak_g
                })
                
                self.status = "emergency"
                
            elif g_forces > self.max_sustained_g:
                # Warning level g-forces
                self.health_status = "warning"
                
                # Publish warning event
                event_bus.publish("bio_warning", {
                    "system": "bio",
                    "g_forces": g_forces,
                    "limit": self.max_sustained_g
                })
                
                # Record event
                self.events.append({
                    "type": "g_force_warning",
                    "g_forces": g_forces,
                    "limit": self.max_sustained_g
                })
                
                self.status = "warning"
                
            else:
                # Normal g-forces
                self.health_status = "nominal"
                self.status = "monitoring"
    
    def command(self, action, params):
        """Process bio monitor system commands"""
        if action == "override_bio_monitor":
            return self._cmd_override(params)
        elif action == "reset_warnings":
            return self._cmd_reset_warnings()
        elif action == "get_crew_status":
            return self._cmd_get_crew_status()
        else:
            return super().command(action, params)
    
    def _cmd_override(self, params):
        """Handle bio monitor override command"""
        if not self.enabled:
            return {"error": "Bio monitor system is disabled"}
        
        if "override" in params:
            try:
                override = bool(params["override"])
                
                # Confirm override intention
                if override and not self.safety_override:
                    if not params.get("confirm", False):
                        return {
                            "warning": "Overriding bio safety limits is dangerous. Set 'confirm': true to proceed."
                        }
                
                self.safety_override = override
                
                return {
                    "status": f"Bio monitor safety {'overridden' if self.safety_override else 'restored'}",
                    "warning": "Crew safety at risk" if self.safety_override else None
                }
            except (ValueError, TypeError):
                return {"error": f"Invalid value for 'override': {params['override']}"}
        else:
            return {"error": "Missing 'override' parameter"}
    
    def _cmd_reset_warnings(self):
        """Handle reset_warnings command"""
        if not self.enabled:
            return {"error": "Bio monitor system is disabled"}
        
        # Reset health status if not currently in a critical state
        if self.current_g <= self.max_sustained_g:
            self.health_status = "nominal"
            self.status = "monitoring"
            
            # Clear events
            self.events = []
            
            return {"status": "Bio monitor warnings reset"}
        else:
            return {
                "status": "Warnings not reset",
                "error": "Current g-forces still exceed safe limits"
            }
    
    def _cmd_get_crew_status(self):
        """Handle get_crew_status command"""
        if not self.enabled:
            return {"error": "Bio monitor system is disabled"}
        
        # Generate crew status report
        crew_status = []
        for i in range(self.crew_count):
            # In a real system, this would track individual crew members
            crew_status.append({
                "id": f"crew_{i+1}",
                "health": self.health_status,
                "g_tolerance": {
                    "current": self.current_g,
                    "max_sustained": self.max_sustained_g,
                    "max_peak": self.max_peak_g
                }
            })
        
        return {
            "status": "Crew status retrieved",
            "crew_count": self.crew_count,
            "crew": crew_status,
            "overall": self.health_status
        }
    
    def get_state(self):
        """Get bio monitor system state"""
        state = super().get_state()
        state.update({
            "status": self.status,
            "crew_count": self.crew_count,
            "health_status": self.health_status,
            "current_g": self.current_g,
            "max_sustained_g": self.max_sustained_g,
            "max_peak_g": self.max_peak_g,
            "safety_override": self.safety_override
        })
        return state