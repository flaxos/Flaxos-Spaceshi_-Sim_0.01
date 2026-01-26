# hybrid/systems/sensors/active.py
"""Active sensor system for high-accuracy pinging."""

import logging
import time
from typing import Dict, List
from hybrid.systems.sensors.contact import (
    ContactData, add_detection_noise,
    calculate_detection_signature
)
from hybrid.utils.math_utils import calculate_distance, calculate_bearing

logger = logging.getLogger(__name__)

class ActiveSensor:
    """Active sensor for manual high-accuracy pings."""

    def __init__(self, config: dict):
        """Initialize active sensor.

        Args:
            config: Configuration dict with:
                - range: Maximum ping range in meters
                - cooldown: Seconds between pings
                - power_cost: Power required per ping
                - resolution_boost: Accuracy multiplier vs passive
        """
        self.range = config.get("active_range", config.get("scan_range", 500000))  # 500km default
        self.base_range = self.range
        self.cooldown = config.get("ping_cooldown", config.get("cooldown", 30.0))  # 30 seconds
        self.power_cost = config.get("ping_power_cost", config.get("power_cost", 50.0))
        self.resolution_boost = config.get("resolution_boost", 0.95)  # Much better than passive
        self.base_resolution_boost = self.resolution_boost

        self.last_ping_time = -1000.0  # Start ready
        self.contacts: Dict[str, ContactData] = {}

    def set_range_multiplier(self, multiplier: float):
        clamped = max(0.0, multiplier)
        self.range = max(0.0, self.base_range * clamped)
        self.resolution_boost = min(0.98, self.base_resolution_boost * max(0.2, clamped))

    def can_ping(self, current_time: float) -> bool:
        """Check if ping is available.

        Args:
            current_time: Current simulation time

        Returns:
            bool: True if can ping
        """
        return (current_time - self.last_ping_time) >= self.cooldown

    def get_cooldown_remaining(self, current_time: float) -> float:
        """Get remaining cooldown time.

        Args:
            current_time: Current simulation time

        Returns:
            float: Seconds remaining (0 if ready)
        """
        if self.can_ping(current_time):
            return 0.0

        return self.cooldown - (current_time - self.last_ping_time)

    def ping(self, observer_ship, all_ships: List, sim_time: float, event_bus) -> Dict[str, str]:
        """Execute an active sensor ping.

        Args:
            observer_ship: Ship executing the ping
            all_ships: List of all ships in simulation
            sim_time: Current simulation time
            event_bus: Event bus for publishing ping event

        Returns:
            dict: Result with ok/error and contacts detected
        """
        from hybrid.utils.errors import success_dict, error_dict

        # Check cooldown
        if not self.can_ping(sim_time):
            remaining = self.get_cooldown_remaining(sim_time)
            return error_dict(
                "PING_ON_COOLDOWN",
                f"Ping on cooldown: {remaining:.1f}s remaining"
            )

        # Check power (if power system available)
        power_system = observer_ship.systems.get("power_management") or observer_ship.systems.get("power")
        if power_system and hasattr(power_system, "request_power"):
            if not power_system.request_power(self.power_cost, "sensors"):
                return error_dict(
                    "INSUFFICIENT_POWER",
                    f"Insufficient power for ping (requires {self.power_cost})"
                )

        # Execute ping
        self.last_ping_time = sim_time
        detected = {}

        for target_ship in all_ships:
            # Don't detect self
            if target_ship.id == observer_ship.id:
                continue

            # Calculate distance
            distance = calculate_distance(observer_ship.position, target_ship.position)

            # Check if in range
            if distance > self.range:
                continue

            # Active sensor provides high accuracy
            base_accuracy = self.resolution_boost
            range_factor = 1.0 - (distance / self.range) * 0.2  # Only 20% degradation with range
            accuracy = min(0.98, base_accuracy * range_factor)

            # Very minimal noise for active sensor
            noisy_position = add_detection_noise(target_ship.position, accuracy)
            noisy_velocity = add_detection_noise(target_ship.velocity, accuracy)

            bearing = calculate_bearing(observer_ship.position, target_ship.position)
            signature = calculate_detection_signature(target_ship)

            contact = ContactData(
                id=target_ship.id,  # Will be remapped by ContactTracker
                position=noisy_position,
                velocity=noisy_velocity,
                confidence=accuracy,
                last_update=sim_time,
                detection_method="active",
                bearing=bearing,
                distance=distance,
                signature=signature,
                classification=target_ship.class_type if accuracy > 0.8 else "Unknown"
            )

            detected[target_ship.id] = contact

        # Update contacts
        self.contacts = detected

        # Publish ping event (makes us detectable!)
        if event_bus:
            event_bus.publish("sensor_ping", {
                "ship_id": observer_ship.id,
                "position": observer_ship.position,
                "range": self.range,
                "timestamp": sim_time
            })
            event_bus.publish("active_ping_complete", {
                "ship_id": observer_ship.id,
                "contacts_detected": len(detected),
                "contacts": list(detected.keys()),
                "timestamp": sim_time
            })
            for contact_id, contact in detected.items():
                event_bus.publish("sensor_contact_updated", {
                    "ship_id": observer_ship.id,
                    "contact_id": contact_id,
                    "contact": {
                        "position": contact.position,
                        "velocity": contact.velocity,
                        "confidence": contact.confidence,
                        "bearing": contact.bearing,
                        "distance": contact.distance,
                        "signature": contact.signature,
                        "classification": contact.classification,
                        "detection_method": contact.detection_method,
                    },
                })

        logger.info(f"Active ping from {observer_ship.id}: {len(detected)} contacts detected")

        return success_dict(
            f"Ping complete: {len(detected)} contacts detected",
            contacts_detected=len(detected),
            cooldown=self.cooldown,
            next_ping_available=sim_time + self.cooldown
        )

    def get_contacts(self) -> Dict[str, ContactData]:
        """Get current active sensor contacts.

        Returns:
            dict: Contact ID -> ContactData
        """
        return dict(self.contacts)

    def get_contact(self, contact_id: str) -> ContactData:
        """Get a specific contact.

        Args:
            contact_id: Contact ID

        Returns:
            ContactData or None
        """
        return self.contacts.get(contact_id)
