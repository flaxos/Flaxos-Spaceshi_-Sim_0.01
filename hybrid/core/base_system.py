# hybrid/core/base_system.py

"""Common interface for all ship systems."""


class BaseSystem:
    """Base class providing shared fields and helpers for ship systems."""

    def __init__(self, config=None):
        config = config or {}
        # Whether the system is active and drawing power
        self.enabled = config.get("enabled", True)
        # Base power draw when enabled (kW)
        self.power_draw = config.get("power_draw", 0.0)
        self.mass = config.get("mass", 0.0)
        self.slot_type = config.get("slot_type", "utility")
        self.tech_level = config.get("tech_level", 1)

    def tick(self, dt, *args, **kwargs):
        """Advance system state each frame."""
        raise NotImplementedError("tick must be implemented by subclasses")

    # ----- Command Helpers -----
    def command(self, action, params):
        return {"error": f"Command '{action}' not supported by this system"}

    def get_state(self):
        return {
            "enabled": self.enabled,
            "power_draw": self.power_draw,
            "mass": self.mass,
            "slot_type": self.slot_type,
            "tech_level": self.tech_level,
        }

    def power_on(self):
        self.enabled = True
        return {"status": "System enabled"}

    def power_off(self):
        self.enabled = False
        return {"status": "System disabled"}
