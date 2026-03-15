# hybrid/systems/sensors/passive.py
"""Passive sensor system for background detection.

Passive sensors detect targets based on their physical emissions:
- **IR (infrared)**: Detects drive plumes, radiator heat, hull thermal.
  A ship burning hard at 5g is visible across the system; a cold drifter
  might only appear at short range.

Detection range is emission-driven — the sensor doesn't have an arbitrary
range cap. Instead, it detects anything whose IR flux exceeds the sensor's
noise floor at the given distance. The hardware ``passive_range`` acts as
an upper bound (sensor saturation / processing limit).

Resolution degrades with distance: at long range you get a bearing and
maybe a rough range, not a detailed track.
"""

import logging
import random
from typing import Dict, List
from hybrid.systems.sensors.contact import (
    ContactData, add_detection_noise, calculate_detection_signature,
    calculate_detection_accuracy
)
from hybrid.systems.sensors.emission_model import (
    calculate_ir_signature, calculate_ir_detection_range,
    calculate_detection_quality
)
from hybrid.utils.math_utils import calculate_distance, calculate_bearing

logger = logging.getLogger(__name__)


class PassiveSensor:
    """Passive sensor for continuous background scanning.

    Detection is emission-driven: the sensor detects IR sources whose
    flux exceeds the noise floor at the target's distance. A thrusting
    ship has an enormous IR signature and can be seen system-wide;
    a cold drifting ship might only appear at close range.
    """

    def __init__(self, config: dict):
        """Initialize passive sensor.

        Args:
            config: Configuration dict with:
                - range: Maximum hardware detection range in metres
                - update_interval: Ticks between updates
                - min_signature: Minimum IR watts to attempt detection
                - ir_sensitivity: Sensor noise floor (W/m^2), lower = better
        """
        self.range = config.get("passive_range", config.get("range", 100000))  # 100km default
        self.base_range = self.range
        self.update_interval = config.get("sensor_tick_interval", config.get("update_interval", 10))
        # Minimum IR emission (watts) to even attempt detection
        self.min_signature = config.get("min_signature", 1000.0)
        # Sensor noise floor — lower = more sensitive IR detector
        self.ir_sensitivity = config.get("ir_sensitivity", 1.0e-6)

        self.contacts: Dict[str, ContactData] = {}
        # Initialize to negative value so first tick triggers immediate scan
        self.last_update_tick = -self.update_interval

    def set_range_multiplier(self, multiplier: float):
        self.range = max(0.0, self.base_range * max(0.0, multiplier))

    def update(self, current_tick: int, dt: float, observer_ship, all_ships: List, sim_time: float):
        """Update passive sensor contacts.

        Detection is emission-based: for each potential target, calculate
        its IR signature, determine the range at which that signature is
        detectable by this sensor, and check if the target is within that
        range. Resolution degrades with distance.

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

            # Calculate target's IR emission
            ir_watts = calculate_ir_signature(target_ship)

            # ECM: If target has active flares, the flare IR competes with
            # real signature, degrading passive lock quality (not range).
            # Flares create a decoy source that adds noise to bearing.
            ecm_flare_active = False
            ecm_flare_ir = 0.0
            target_ecm = target_ship.systems.get("ecm")
            if target_ecm and hasattr(target_ecm, "is_flare_active"):
                ecm_flare_active = target_ecm.is_flare_active()
                if ecm_flare_active:
                    ecm_flare_ir = target_ecm.get_flare_ir_power()

            # Skip targets with negligible emissions
            if ir_watts < self.min_signature:
                continue

            # Calculate the range at which this target's IR is detectable
            # by this sensor's noise floor
            ir_range = calculate_ir_detection_range(ir_watts, self.ir_sensitivity)

            # Effective detection range: minimum of emission-based range and
            # sensor hardware limit (processing/saturation cap)
            effective_range = min(ir_range, self.range)

            # Check if target is within detection range
            if distance > effective_range:
                continue

            # Calculate detection quality (resolution degrades with distance)
            quality = calculate_detection_quality(distance, effective_range)

            # ECM: Flares degrade tracking quality — the decoy confuses
            # bearing/range resolution. More effective when flare IR is
            # comparable to target's real signature.
            if ecm_flare_active and ecm_flare_ir > 0:
                # Ratio of flare IR to target IR — higher = more confusion
                flare_ratio = min(1.0, ecm_flare_ir / max(ir_watts, 1.0))
                # At flare_ratio=1 (flare matches target), quality halved
                quality *= max(0.2, 1.0 - flare_ratio * 0.5)

            accuracy = min(0.95, max(0.1, quality))

            # Detection probability
            detection_probability = min(0.95, accuracy)

            # Random detection check (skip on initial scan to populate immediately)
            if not initial_scan:
                if random.random() > detection_probability:
                    continue

            # Determine detection method based on what's driving the detection
            detection_method = "ir"

            # Create contact with noise proportional to quality
            noisy_position = add_detection_noise(target_ship.position, accuracy)
            noisy_velocity = add_detection_noise(target_ship.velocity, accuracy * 0.7)

            bearing = calculate_bearing(observer_ship.position, target_ship.position)

            contact = ContactData(
                id=target_ship.id,  # Will be remapped by ContactTracker
                position=noisy_position,
                velocity=noisy_velocity,
                confidence=accuracy,
                last_update=sim_time,
                detection_method=detection_method,
                bearing=bearing,
                distance=distance,
                signature=ir_watts,
                classification=self._classify_contact(target_ship, accuracy),
                name=getattr(target_ship, "name", None) if accuracy > 0.5 else None,
            )

            detected[target_ship.id] = contact

        # Merge new detections with existing contacts (don't drop on failed re-detect)
        for existing_id, existing_contact in self.contacts.items():
            if existing_id not in detected:
                # Degrade confidence on missed re-detection, but never drop below
                # a minimum floor — the ship still exists and emits IR, so it
                # should remain as a degraded contact rather than vanishing.
                existing_contact.confidence *= 0.95
                existing_contact.confidence = max(existing_contact.confidence, 0.05)
                detected[existing_id] = existing_contact
            else:
                new_contact = detected[existing_id]
                new_contact.confidence = max(new_contact.confidence, existing_contact.confidence)

        self.contacts = detected

        logger.debug(f"Passive IR sensor on {observer_ship.id}: {len(detected)} contacts")

    def _classify_contact(self, target_ship, accuracy: float) -> str:
        """Attempt to classify a contact based on accuracy.

        At low accuracy (long range), classification is impossible.
        At medium accuracy, only size class is available.
        At high accuracy (close range or bright target), full class.

        Args:
            target_ship: Target ship object
            accuracy: Detection accuracy

        Returns:
            str: Classification or "Unknown"
        """
        if accuracy < 0.6:
            return "Unknown"

        if accuracy > 0.9:
            return target_ship.class_type  # Full classification
        elif accuracy > 0.7:
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
