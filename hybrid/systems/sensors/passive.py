# hybrid/systems/sensors/passive.py
"""Passive sensor system for background detection."""

import logging
from typing import Dict, List
from hybrid.systems.sensors.contact import (
    ContactData, add_detection_noise, calculate_detection_signature,
    calculate_detection_accuracy
)
from hybrid.utils.math_utils import calculate_distance, calculate_bearing

logger = logging.getLogger(__name__)

class PassiveSensor:
    """Passive sensor for continuous background scanning."""

    def __init__(self, config: dict):
        """Initialize passive sensor.

        Args:
            config: Configuration dict with:
                - range: Detection range in meters
                - update_interval: Ticks between updates
                - min_signature: Minimum signature to detect
        """
        self.range = config.get("passive_range", config.get("range", 100000))  # 100km default
        self.base_range = self.range
        self.update_interval = config.get("sensor_tick_interval", config.get("update_interval", 10))
        self.min_signature = config.get("min_signature", 5.0)

        self.contacts: Dict[str, ContactData] = {}
        # Initialize to negative value so first tick triggers immediate scan
        self.last_update_tick = -self.update_interval

    def set_range_multiplier(self, multiplier: float):
        self.range = max(0.0, self.base_range * max(0.0, multiplier))

    def update(self, current_tick: int, dt: float, observer_ship, all_ships: List, sim_time: float):
        """Update passive sensor contacts.

        Args:
            current_tick: Current simulation tick
            dt: Time delta
            observer_ship: Ship with this sensor
            all_ships: List of all ships in simulation
            sim_time: Current simulation time
        """
        # Only update at specified interval
        if current_tick - self.last_update_tick < self.update_interval:
            return

        initial_scan = self.last_update_tick < 0
        self.last_update_tick = current_tick

        # Scan for contacts
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

            # Calculate signature
            signature = calculate_detection_signature(target_ship)

            # Check minimum signature
            if signature < self.min_signature:
                continue

            # Calculate detection probability
            accuracy = calculate_detection_accuracy(distance, signature, self.range)

            # Passive detection has additional probability factor
            detection_probability = min(0.95, accuracy ** 2)  # Squared for lower passive detection

            # Random detection check (skip on initial scan to populate contacts immediately)
            if not initial_scan:
                import random
                if random.random() > detection_probability:
                    continue

            # Create contact with noise
            noisy_position = add_detection_noise(target_ship.position, accuracy)
            noisy_velocity = add_detection_noise(target_ship.velocity, accuracy * 0.7)  # Less accurate velocity

            bearing = calculate_bearing(observer_ship.position, target_ship.position)

            contact = ContactData(
                id=target_ship.id,  # Will be remapped by ContactTracker
                position=noisy_position,
                velocity=noisy_velocity,
                confidence=accuracy,
                last_update=sim_time,
                detection_method="passive",
                bearing=bearing,
                distance=distance,
                signature=signature,
                classification=self._classify_contact(target_ship, accuracy)
            )

            detected[target_ship.id] = contact

        # Update contacts
        self.contacts = detected

        logger.debug(f"Passive sensor on {observer_ship.id}: {len(detected)} contacts")

    def _classify_contact(self, target_ship, accuracy: float) -> str:
        """Attempt to classify a contact based on accuracy.

        Args:
            target_ship: Target ship object
            accuracy: Detection accuracy

        Returns:
            str: Classification or "Unknown"
        """
        # Only classify if accuracy is high enough
        if accuracy < 0.6:
            return "Unknown"

        # Higher accuracy = more detail
        if accuracy > 0.9:
            return target_ship.class_type  # Full classification
        elif accuracy > 0.7:
            # Partial classification (size class)
            if target_ship.mass > 100000:
                return "Large"
            elif target_ship.mass > 10000:
                return "Medium"
            else:
                return "Small"

        return "Unknown"

    def get_contacts(self) -> Dict[str, ContactData]:
        """Get current passive contacts.

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
