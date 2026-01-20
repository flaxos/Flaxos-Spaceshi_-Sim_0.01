# hybrid/systems/sensors/sensor_system.py
"""Enhanced sensor system with passive/active detection and contact management."""

import logging
from hybrid.core.event_bus import EventBus
from hybrid.core.base_system import BaseSystem
from hybrid.systems.sensors.passive import PassiveSensor
from hybrid.systems.sensors.active import ActiveSensor
from hybrid.systems.sensors.contact import ContactTracker
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)

class SensorSystem(BaseSystem):
    """Comprehensive sensor system with passive and active detection."""

    def __init__(self, config: dict):
        """Initialize sensor system.

        Args:
            config: Configuration dict with:
                - passive: Passive sensor config
                - active: Active sensor config
                - stale_threshold: Seconds before contacts go stale
        """
        super().__init__(config)
        self.config = config

        # Initialize subsystems
        passive_config = config.get("passive", config)  # Fallback to main config
        active_config = config.get("active", config)

        self.passive = PassiveSensor(passive_config)
        self.active = ActiveSensor(active_config)

        # Contact tracker for unified contact management
        stale_threshold = config.get("stale_threshold", 60.0)
        self.contact_tracker = ContactTracker(stale_threshold)

        # Simulation reference (set during tick)
        self.all_ships = []
        self.current_tick = 0
        self.sim_time = 0.0

    def tick(self, dt: float, ship, event_bus):
        """Update sensor system.

        Args:
            dt: Time delta
            ship: Ship with this sensor
            event_bus: Event bus for publishing events
        """
        if not self.enabled:
            return

        self.sim_time = getattr(ship, "sim_time", self.sim_time + dt)
        self.current_tick += 1

        # Get all ships from simulator (injected during simulator tick)
        # This will be set by the simulator when it calls tick
        if hasattr(ship, "_all_ships_ref"):
            self.all_ships = ship._all_ships_ref

        # Update passive sensor
        self.passive.update(
            self.current_tick,
            dt,
            ship,
            self.all_ships,
            self.sim_time
        )

        # Merge passive contacts into contact tracker
        for ship_id, contact in self.passive.get_contacts().items():
            self.contact_tracker.update_contact(ship_id, contact, self.sim_time)

        # Merge active contacts (from previous ping) into contact tracker
        for ship_id, contact in self.active.get_contacts().items():
            self.contact_tracker.update_contact(ship_id, contact, self.sim_time)

        # Prune stale contacts periodically
        if self.current_tick % 100 == 0:  # Every 100 ticks
            self.contact_tracker.prune_stale_contacts(self.sim_time)

        # Publish sensor tick event
        event_bus.publish("sensor_tick", {
            "dt": dt,
            "ship_id": ship.id,
            "contacts": len(self.contact_tracker.get_all_contacts(self.sim_time))
        })

    def command(self, action: str, params: dict):
        """Handle sensor commands.

        Args:
            action: Command action
            params: Command parameters

        Returns:
            dict: Command result
        """
        if action == "ping":
            return self.ping(params)
        elif action == "get_contacts":
            return self.get_contacts_list(params)
        elif action == "status":
            return self.get_state()

        return super().command(action, params)

    def ping(self, params: dict = None):
        """Execute active sensor ping.

        Args:
            params: Optional parameters

        Returns:
            dict: Ping result
        """
        if params is None:
            params = {}

        # Need ship reference from params or stored
        ship = params.get("ship")
        if not ship:
            return error_dict("NO_SHIP_REFERENCE", "Ship reference required for ping")

        # Need all_ships list
        all_ships = self.all_ships or params.get("all_ships", [])

        # Need event bus
        event_bus = params.get("event_bus") or EventBus.get_instance()

        return self.active.ping(ship, all_ships, self.sim_time, event_bus)

    def get_contacts(self) -> dict:
        """Get all current contacts.

        Returns:
            dict: Contact ID -> ContactData
        """
        return self.contact_tracker.get_all_contacts(self.sim_time)

    def get_contacts_list(self, params: dict = None):
        """Get contacts as a formatted list.

        Args:
            params: Optional parameters with:
                - observer_position: Position to calculate distance/bearing from
                - observer_velocity: Velocity to calculate closing speed (optional)
                - include_stale: Include stale contacts

        Returns:
            dict: Contact list response
        """
        if params is None:
            params = {}

        observer_position = params.get("observer_position", {"x": 0, "y": 0, "z": 0})
        observer_velocity = params.get("observer_velocity", None)
        include_stale = params.get("include_stale", False)

        if include_stale:
            contacts = self.contact_tracker.get_all_contacts(self.sim_time, include_stale=True)
            contacts_list = list(contacts.values())
        else:
            contacts_list = self.contact_tracker.get_sorted_contacts(observer_position, self.sim_time, observer_velocity)

        return success_dict(
            f"{len(contacts_list)} contacts",
            contacts=contacts_list,
            count=len(contacts_list)
        )

    def get_contact(self, contact_id: str):
        """Get a specific contact.

        Args:
            contact_id: Contact ID

        Returns:
            ContactData or None
        """
        return self.contact_tracker.get_contact(contact_id)

    def get_state(self) -> dict:
        """Get sensor system state.

        Returns:
            dict: Current state
        """
        state = super().get_state()

        active_contacts = len(self.contact_tracker.get_all_contacts(self.sim_time))
        can_ping = self.active.can_ping(self.sim_time)
        ping_cooldown = self.active.get_cooldown_remaining(self.sim_time)

        state.update({
            "passive_range": self.passive.range,
            "active_range": self.active.range,
            "contacts": active_contacts,
            "can_ping": can_ping,
            "ping_cooldown_remaining": ping_cooldown,
            "ping_cooldown_total": self.active.cooldown
        })

        return state
