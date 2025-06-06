# hybrid/core/base_system.py

class BaseSystem:
    """Common functionality shared by all ship systems."""

    def __init__(self, config=None):
        config = config or {}
        self.config = config

        # Whether the system is currently powered on
        self.enabled = bool(config.get("enabled", True))

        # Nominal power draw in kinetic units (kW)
        self.power_draw = float(config.get("power_draw", 0.0))

    def tick(self, dt, ship=None, event_bus=None):
        """Update the system each frame (to be implemented by subclasses)."""
        raise NotImplementedError("tick must be implemented by subclasses")

    # ------------------------------------------------------------------
    # Generic power helpers
    def power_on(self):
        self.enabled = True
        return {"status": "powered on"}

    def power_off(self):
        self.enabled = False
        return {"status": "powered off"}

    # ------------------------------------------------------------------
    # Default command handler and state reporting
    def command(self, action, params):
        return {"error": f"Unknown command: {action}"}

    def get_state(self):
        return {
            "enabled": self.enabled,
            "power_draw": self.power_draw,
        }
