# hybrid/systems/propulsion_system.py
"""
Propulsion system implementation for ship simulation.
Handles main drive thrust and related functions.
"""

from hybrid.base_system import BaseSystem
import math
import logging

logger = logging.getLogger(__name__)

class PropulsionSystem(BaseSystem):
    """
    Propulsion system for ships. Handles main drive thrust.
    """
    
    def __init__(self, config=None):
        """
        Initialize the propulsion system
        
        Args:
            config (dict): Propulsion system configuration
        """
        super().__init__(config)
        config = config or {}
        
        # Power requirements
        self.power_draw = config.get("power_draw", 10.0)
        self.power_draw_per_thrust = config.get("power_draw_per_thrust", 0.5)
        
        # Main drive
        self.main_drive = config.get("main_drive", {
            "thrust": {"x": 0.0, "y": 0.0, "z": 0.0},
            "max_thrust": config.get("max_thrust", 100.0)
        })
        
        # Keep track of power status
        self.power_status = True
        
    def tick(self, dt, ship, event_bus):
        """
        Update propulsion system for current time step
        
        Args:
            dt (float): Time delta in seconds
            ship (Ship): The parent ship
            event_bus (EventBus): Event bus for system communication
        """
        if not self.enabled:
            # Zero out thrust if disabled
            self.main_drive["thrust"] = {"x": 0.0, "y": 0.0, "z": 0.0}
            return
            
        # Calculate power draw based on thrust magnitude
        thrust = self.main_drive["thrust"]
        thrust_magnitude = math.sqrt(
            thrust["x"]**2 + thrust["y"]**2 + thrust["z"]**2
        )
        
        # Base power draw plus additional for thrust
        total_power = self.power_draw + (self.power_draw_per_thrust * thrust_magnitude * dt)
        
        # Request power from power system
        power_system = ship.systems.get("power")
        if power_system and not power_system.request_power(total_power, "propulsion"):
            # Not enough power, disable thrust
            logger.warning(f"Propulsion on {ship.id} reduced due to power shortage")
            self.main_drive["thrust"] = {"x": 0.0, "y": 0.0, "z": 0.0}
            if self.power_status:
                self.power_status = False
                event_bus.publish("propulsion_power_loss", None, "propulsion")
        elif not self.power_status:
            # Power restored
            self.power_status = True
            event_bus.publish("propulsion_power_restored", None, "propulsion")
            
        # Check thrust magnitude and trigger signature spike if high
        if thrust_magnitude > 10.0:
            event_bus.publish("signature_spike", {
                "duration": 3.0,  # seconds
                "magnitude": thrust_magnitude
            }, "propulsion")
        
    def command(self, action, params):
        """
        Process propulsion system commands
        
        Args:
            action (str): Command action
            params (dict): Command parameters
            
        Returns:
            dict: Command response
        """
        if action == "set_thrust":
            return self.set_thrust(params)
        elif action == "status":
            return self.get_state()
        elif action == "power_on":
            return self.power_on()
        elif action == "power_off":
            return self.power_off()
        return super().command(action, params)
        
    def set_thrust(self, params):
        """
        Set main drive thrust
        
        Args:
            params (dict): Thrust parameters (x, y, z)
            
        Returns:
            dict: Command response
        """
        if not self.enabled:
            return {"error": "Propulsion system is disabled"}
            
        # Get thrust values from params
        x = float(params.get("x", self.main_drive["thrust"]["x"]))
        y = float(params.get("y", self.main_drive["thrust"]["y"]))
        z = float(params.get("z", self.main_drive["thrust"]["z"]))
        
        # Apply thrust limits
        max_thrust = self.main_drive.get("max_thrust", 100.0)
        magnitude = math.sqrt(x**2 + y**2 + z**2)
        
        if magnitude > max_thrust:
            scale = max_thrust / magnitude
            x *= scale
            y *= scale
            z *= scale
            
        # Update thrust
        self.main_drive["thrust"] = {"x": x, "y": y, "z": z}
        
        return {
            "status": "Thrust updated",
            "thrust": self.main_drive["thrust"]
        }
        
    def get_thrust(self):
        """
        Get current thrust vector
        
        Returns:
            dict: Thrust vector {x, y, z}
        """
        return self.main_drive["thrust"]
        
    def get_state(self):
        """
        Get current propulsion system state
        
        Returns:
            dict: Propulsion system state
        """
        state = super().get_state()
        state.update({
            "main_drive": self.main_drive,
            "power_status": self.power_status
        })
        return state
# hybrid/systems/propulsion_system.py
"""
Propulsion system implementation for the ship.
Handles thrust generation and fuel consumption.
"""
from hybrid.base_system import BaseSystem
import math

class PropulsionSystem(BaseSystem):
    """Manages ship propulsion and thrust"""
    
    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}
        
        # Main drive configuration
        main_drive = config.get("main_drive", {})
        self.max_thrust = float(main_drive.get("max_thrust", 100.0))
        self.efficiency = float(main_drive.get("efficiency", 0.9))
        self.fuel_consumption = float(main_drive.get("fuel_consumption", 0.1))
        
        # Maneuvering thrusters
        thrusters = config.get("maneuvering_thrusters", {})
        self.thruster_power = float(thrusters.get("power", self.max_thrust * 0.2))
        self.thruster_efficiency = float(thrusters.get("efficiency", 0.7))
        
        # Fuel
        self.max_fuel = float(config.get("max_fuel", 1000.0))
        self.fuel_level = float(config.get("fuel_level", self.max_fuel))
        
        # Current thrust levels
        self.current_thrust = {"x": 0.0, "y": 0.0, "z": 0.0}
        
        # System status
        self.status = "idle"
    
    def tick(self, dt, ship, event_bus):
        """Update propulsion system state"""
        if not self.enabled:
            # Zero out thrust if system is disabled
            ship.thrust = {"x": 0.0, "y": 0.0, "z": 0.0}
            ship.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
            self.status = "offline"
            return
        
        # Check if we have power and fuel
        if "power" in ship.systems and hasattr(ship.systems["power"], "get_state"):
            power_state = ship.systems["power"].get_state()
            if power_state.get("stored_power", 0) <= 0:
                # No power available
                ship.thrust = {"x": 0.0, "y": 0.0, "z": 0.0}
                ship.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
                self.status = "no_power"
                event_bus.publish("propulsion_status_change", {
                    "system": "propulsion",
                    "status": "no_power"
                })
                return
        
        # Calculate total thrust magnitude
        thrust_magnitude = math.sqrt(
            ship.thrust["x"]**2 + 
            ship.thrust["y"]**2 + 
            ship.thrust["z"]**2
        )
        
        if thrust_magnitude > 0:
            # Calculate fuel consumption based on thrust
            consumption = (thrust_magnitude / self.max_thrust) * self.fuel_consumption * dt
            if self.fuel_level >= consumption:
                # We have enough fuel
                self.fuel_level -= consumption
                
                # Apply thrust to ship acceleration
                ship.acceleration = {
                    "x": ship.thrust["x"] / ship.mass,
                    "y": ship.thrust["y"] / ship.mass,
                    "z": ship.thrust["z"] / ship.mass
                }
                
                self.status = "active"
            else:
                # Out of fuel
                ship.thrust = {"x": 0.0, "y": 0.0, "z": 0.0}
                ship.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
                self.fuel_level = 0.0
                self.status = "no_fuel"
                event_bus.publish("propulsion_status_change", {
                    "system": "propulsion",
                    "status": "no_fuel"
                })
        else:
            # No thrust applied
            ship.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
            self.status = "idle"
    
    def command(self, action, params):
        """Process propulsion system commands"""
        if action == "set_thrust":
            return self._cmd_set_thrust(params)
        elif action == "refuel":
            return self._cmd_refuel(params)
        elif action == "emergency_stop":
            return self._cmd_emergency_stop()
        else:
            return super().command(action, params)
    
    def _cmd_set_thrust(self, params):
        """Handle set_thrust command"""
        if not self.enabled:
            return {"error": "Propulsion system is disabled"}
        
        # Check each axis
        for axis in ["x", "y", "z"]:
            if axis in params:
                try:
                    value = float(params[axis])
                    # Limit to max thrust
                    if abs(value) > self.max_thrust:
                        value = math.copysign(self.max_thrust, value)
                    self.current_thrust[axis] = value
                except (ValueError, TypeError):
                    return {"error": f"Invalid thrust value for {axis}"}
        
        return {"status": "Thrust updated", "thrust": self.current_thrust}
    
    def _cmd_refuel(self, params):
        """Handle refuel command"""
        amount = float(params.get("amount", self.max_fuel - self.fuel_level))
        self.fuel_level = min(self.max_fuel, self.fuel_level + amount)
        return {
            "status": "Refueled",
            "amount": amount,
            "current_level": self.fuel_level,
            "max_fuel": self.max_fuel
        }
    
    def _cmd_emergency_stop(self):
        """Handle emergency stop command"""
        self.current_thrust = {"x": 0.0, "y": 0.0, "z": 0.0}
        return {"status": "Emergency stop activated", "thrust": self.current_thrust}
    
    def get_state(self):
        """Get propulsion system state"""
        state = super().get_state()
        state.update({
            "status": self.status,
            "max_thrust": self.max_thrust,
            "current_thrust": self.current_thrust,
            "fuel_level": self.fuel_level,
            "fuel_percent": (self.fuel_level / self.max_fuel * 100) if self.max_fuel > 0 else 0,
            "max_fuel": self.max_fuel
        })
        return state