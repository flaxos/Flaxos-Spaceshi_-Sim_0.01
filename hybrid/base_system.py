# hybrid/base_system.py
"""
Base system interface for all ship systems.
This defines the contract that all systems must implement.
"""

class BaseSystem:
    """Base class for all ship systems"""
    
    def __init__(self, config=None):
        """
        Initialize the system with configuration
        
        Args:
            config (dict): Configuration dictionary for this system
        """
        config = config or {}
        self.enabled = config.get("enabled", True)
        self.power_draw = config.get("power_draw", 0)
        self.mass = config.get("mass", 0)
        self.slot_type = config.get("slot_type", "utility")
        self.tech_level = config.get("tech_level", 1)
        
    def tick(self, dt, ship, event_bus):
        """
        Update system state for the current time step
        
        Args:
            dt (float): Time delta in seconds
            ship (Ship): The parent ship this system belongs to
            event_bus (EventBus): Event bus for publishing/subscribing to events
            
        Returns:
            None
        """
        raise NotImplementedError("Subclasses must implement tick()")
        
    def command(self, action, params):
        """
        Process a command directed at this system
        
        Args:
            action (str): The action to perform
            params (dict): Parameters for the action
            
        Returns:
            dict: Response containing the result or error
        """
        return {"error": f"Command '{action}' not supported by this system"}
        
    def get_state(self):
        """
        Return current system state as a dictionary
        
        Returns:
            dict: System state
        """
        return {
            "enabled": self.enabled,
            "power_draw": self.power_draw,
            "mass": self.mass,
            "slot_type": self.slot_type,
            "tech_level": self.tech_level
        }

    def power_on(self):
        """Enable the system"""
        self.enabled = True
        return {"status": "System enabled"}
        
    def power_off(self):
        """Disable the system"""
        self.enabled = False
        return {"status": "System disabled"}
