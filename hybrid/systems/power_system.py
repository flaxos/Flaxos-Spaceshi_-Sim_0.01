# hybrid/systems/power_system.py
"""
Power system implementation for ship simulation.
Handles power generation, storage, and distribution.
"""
# hybrid/systems/power_system.py
"""
Power system implementation for the ship.
Handles power generation, storage, and distribution to other systems.
"""
from hybrid.base_system import BaseSystem

class PowerSystem(BaseSystem):
    """Manages power generation, storage, and distribution"""
    
    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}
        
        # Power generation capacity (power units per second)
        self.generation_rate = float(config.get("generation", 10.0))
        
        # Power storage capacity
        self.capacity = float(config.get("capacity", 100.0))
        self.stored_power = float(config.get("initial", self.capacity * 0.8))
        
        # Power allocation to systems
        self.allocations = config.get("allocations", {})
        
        # System status
        self.status = "online"
        
        # Efficiency factor
        self.efficiency = float(config.get("efficiency", 0.95))
    
    def tick(self, dt, ship, event_bus):
        """Update power system state"""
        if not self.enabled:
            self.status = "offline"
            return
            
        # Generate power
        new_power = self.generation_rate * dt * self.efficiency
        self.stored_power = min(self.capacity, self.stored_power + new_power)
        
        # Distribute power to systems
        total_draw = 0
        for system_id, system in ship.systems.items():
            if system_id != "power":  # Don't supply power to self
                if hasattr(system, "power_draw"):
                    draw = system.power_draw * dt
                    total_draw += draw
        
        # Reduce stored power by the total draw
        self.stored_power = max(0, self.stored_power - total_draw)
        
        # Check power status
        if self.stored_power <= 0:
            self.status = "critical"
            # Publish power critical event
            event_bus.publish("power_critical", {"system": "power"})
        elif self.stored_power < (self.capacity * 0.2):
            self.status = "low"
            # Publish power low event
            event_bus.publish("power_low", {"system": "power", "level": self.stored_power / self.capacity})
        else:
            self.status = "online"
    
    def command(self, action, params):
        """Process power system commands"""
        if action == "power_on":
            return self.power_on()
        elif action == "power_off":
            return self.power_off()
        elif action == "get_status":
            return self.get_state()
        elif action == "boost_generation":
            # Temporarily increase generation rate
            boost_factor = float(params.get("factor", 1.5))
            original_rate = self.generation_rate
            self.generation_rate *= boost_factor
            return {"status": "Generation boosted", "factor": boost_factor, "rate": self.generation_rate}
        elif action == "add_power":
            # Add power directly (for refueling)
            amount = float(params.get("amount", 0))
            self.stored_power = min(self.capacity, self.stored_power + amount)
            return {"status": "Power added", "amount": amount, "current": self.stored_power}
        else:
            return super().command(action, params)
    
    def get_state(self):
        """Get power system state"""
        state = super().get_state()
        state.update({
            "status": self.status,
            "generation_rate": self.generation_rate,
            "capacity": self.capacity,
            "stored_power": self.stored_power,
            "percent": (self.stored_power / self.capacity * 100) if self.capacity > 0 else 0,
            "allocations": self.allocations
        })
        return state
from hybrid.base_system import BaseSystem

class PowerSystem(BaseSystem):
    """
    Power system for ships. Handles generation, storage, and distribution.
    """
    
    def __init__(self, config=None):
        """
        Initialize the power system
        
        Args:
            config (dict): Power system configuration
        """
        super().__init__(config)
        config = config or {}
        
        self.generation = config.get("generation", 5.0)  # power units per second
        self.capacity = config.get("capacity", 100.0)
        self.current = config.get("current", self.capacity)
        
        # Additional tracking for power draw from other systems
        self.total_draw = 0.0
        self.drawing_systems = {}
        
    def tick(self, dt, ship, event_bus):
        """
        Update power system state for current time step
        
        Args:
            dt (float): Time delta in seconds
            ship (Ship): The parent ship
            event_bus (EventBus): Event bus for system communication
        """
        if not self.enabled:
            event_bus.publish("power_offline", None, "power")
            return
            
        # Generate power
        generated = self.generation * dt
        self.current = min(self.capacity, self.current + generated)
        
        # Reset tracking for this tick
        self.total_draw = 0.0
        self.drawing_systems = {}
        
        # Publish power availability event
        event_bus.publish("power_available", {
            "available": self.current,
            "capacity": self.capacity
        }, "power")
        
    def command(self, action, params):
        """
        Process power system commands
        
        Args:
            action (str): Command action
            params (dict): Command parameters
            
        Returns:
            dict: Command response
        """
        if action == "status":
            return self.get_state()
        elif action == "power_on":
            return self.power_on()
        elif action == "power_off":
            return self.power_off()
        elif action == "set_generation":
            if "value" in params:
                self.generation = float(params["value"])
                return {"status": f"Power generation set to {self.generation}"}
        return super().command(action, params)
        
    def request_power(self, amount, system_name):
        """
        Request power for a system
        
        Args:
            amount (float): Amount of power requested
            system_name (str): Name of the requesting system
            
        Returns:
            bool: True if power was successfully allocated, False otherwise
        """
        if not self.enabled:
            return False
            
        if amount <= 0:
            return True
            
        # Track the request
        self.drawing_systems[system_name] = amount
        self.total_draw += amount
        
        # Check if we have enough power
        if self.current >= amount:
            self.current -= amount
            return True
        else:
            return False
            
    def get_state(self):
        """
        Get current power system state
        
        Returns:
            dict: Power system state
        """
        state = super().get_state()
        state.update({
            "generation": self.generation,
            "capacity": self.capacity,
            "current": self.current,
            "total_draw": self.total_draw,
            "drawing_systems": self.drawing_systems
        })
        return state
