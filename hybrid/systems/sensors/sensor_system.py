# hybrid/systems/sensors/sensor_system.py

from hybrid.core.event_bus import EventBus


class SensorSystem:
    def __init__(self, config):
        """Basic sensor system placeholder."""
        # config: range, FOV, cooldown, passive/active settings
        self.config = config
        self.event_bus = EventBus.get_instance()

    def tick(self, dt, ship=None, event_bus=None):
        """Publish a sensor tick event for observers."""

        bus = event_bus or self.event_bus
        bus.publish("sensor_tick", {"dt": dt, "ship_id": getattr(ship, "id", None)})
