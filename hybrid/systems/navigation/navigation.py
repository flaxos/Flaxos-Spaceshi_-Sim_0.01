# hybrid/systems/navigation/navigation.py

from hybrid.core.event_bus import EventBus


class NavigationSystem:
    def __init__(self, config):
        """Simple navigation system placeholder."""
        # config: navigation parameters (e.g., max_acceleration)
        self.config = config
        self.event_bus = EventBus.get_instance()

    def tick(self, dt, ship=None, event_bus=None):
        """Publish a tick event for observers.

        Parameters
        ----------
        dt : float
            Delta time for this simulation step.
        ship : Ship, optional
            Ship owning this system. Unused but accepted for compatibility.
        event_bus : EventBus, optional
            Bus used for event publication. Defaults to the system bus.
        """

        bus = event_bus or self.event_bus
        # In a full implementation this would update autopilot/course logic.
        bus.publish("navigation_tick", {"dt": dt, "ship_id": getattr(ship, "id", None)})
