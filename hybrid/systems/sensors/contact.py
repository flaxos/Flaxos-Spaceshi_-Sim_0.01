# hybrid/systems/sensors/contact.py
"""Contact data structures and management."""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from hybrid.utils.math_utils import add_vectors, scale_vector
import random

@dataclass
class ContactData:
    """Represents a detected contact."""
    id: str
    position: Dict[str, float]
    velocity: Dict[str, float]
    confidence: float  # 0.0 to 1.0
    last_update: float  # Timestamp
    detection_method: str  # "passive", "active", "visual"
    bearing: Optional[Dict[str, float]] = None  # Relative bearing from observer
    distance: Optional[float] = None  # Distance from observer
    signature: Optional[float] = None  # Thermal/EM signature strength
    classification: Optional[str] = None  # Ship class if known
    name: Optional[str] = None  # Ship name if identified

    def is_stale(self, current_time: float, stale_threshold: float = 60.0) -> bool:
        """Check if contact is stale.

        Args:
            current_time: Current simulation time
            stale_threshold: Seconds before contact is considered stale

        Returns:
            bool: True if contact is stale
        """
        return (current_time - self.last_update) > stale_threshold

    def get_age(self, current_time: float) -> float:
        """Get contact age in seconds.

        Args:
            current_time: Current simulation time

        Returns:
            float: Age in seconds
        """
        return current_time - self.last_update

class ContactTracker:
    """Maintains stable contact IDs and tracks contact history."""

    def __init__(self, stale_threshold: float = 60.0):
        """Initialize contact tracker.

        Args:
            stale_threshold: Seconds before contact goes stale
        """
        self.contacts: Dict[str, ContactData] = {}
        self.id_mapping: Dict[str, str] = {}  # real_ship_id -> stable_contact_id
        self.next_contact_number = 1
        self.stale_threshold = stale_threshold

    def update_contact(self, ship_id: str, contact_data: ContactData, current_time: float):
        """Update or create a contact.

        Args:
            ship_id: Real ship ID
            contact_data: Contact data
            current_time: Current simulation time
        """
        # Get or create stable contact ID
        if ship_id not in self.id_mapping:
            self.id_mapping[ship_id] = f"C{self.next_contact_number:03d}"
            self.next_contact_number += 1

        stable_id = self.id_mapping[ship_id]

        # Update contact with stable ID
        contact_data.id = stable_id
        contact_data.last_update = current_time

        self.contacts[stable_id] = contact_data

    def get_contact(self, contact_id: str) -> Optional[ContactData]:
        """Get a contact by stable ID or original ship ID.

        Args:
            contact_id: Stable contact ID (e.g. C001) or original ship ID

        Returns:
            ContactData or None
        """
        # Try stable contact ID first
        contact = self.contacts.get(contact_id)
        if contact:
            return contact

        # Fall back to looking up by original ship ID
        stable_id = self.id_mapping.get(contact_id)
        if stable_id:
            return self.contacts.get(stable_id)

        return None

    def get_all_contacts(self, current_time: float, include_stale: bool = False) -> Dict[str, ContactData]:
        """Get all contacts.

        Args:
            current_time: Current simulation time
            include_stale: Include stale contacts

        Returns:
            dict: Contact ID -> ContactData
        """
        if include_stale:
            return dict(self.contacts)

        return {
            cid: contact for cid, contact in self.contacts.items()
            if not contact.is_stale(current_time, self.stale_threshold)
        }

    def get_sorted_contacts(self, observer_position: Dict[str, float], current_time: float, observer_velocity: Optional[Dict[str, float]] = None) -> list:
        """Get contacts sorted by distance.

        Args:
            observer_position: Observer's position
            current_time: Current simulation time
            observer_velocity: Observer's velocity (optional, for closing speed calculation)

        Returns:
            list: Sorted contact data with distance/bearing/closing_speed
        """
        from hybrid.utils.math_utils import calculate_distance, calculate_bearing, subtract_vectors, magnitude, normalize_vector, dot_product
        import math

        result = []
        active_contacts = self.get_all_contacts(current_time, include_stale=False)

        for contact_id, contact in active_contacts.items():
            distance = calculate_distance(observer_position, contact.position)
            bearing = calculate_bearing(observer_position, contact.position)

            # Calculate closing speed from relative velocity
            closing_speed = 0.0
            if observer_velocity and contact.velocity:
                # Relative velocity (contact velocity - observer velocity)
                rel_velocity = subtract_vectors(contact.velocity, observer_velocity)

                # Direction from observer to contact
                direction = subtract_vectors(contact.position, observer_position)

                # Closing speed is the component of relative velocity along the line between them
                # Negative if closing (contact moving toward observer), positive if opening
                if distance > 0:
                    direction_normalized = normalize_vector(direction)
                    closing_speed = -dot_product(rel_velocity, direction_normalized)

            # Calculate confidence decay based on age
            age = contact.get_age(current_time)
            confidence_decay = max(0.0, 1.0 - (age / self.stale_threshold))
            effective_confidence = contact.confidence * confidence_decay

            result.append({
                "id": contact_id,
                "distance": distance,
                "bearing": bearing,
                "closing_speed": closing_speed,
                "confidence": effective_confidence,
                "age": age,
                "stale": contact.is_stale(current_time, self.stale_threshold),
                "detection_method": contact.detection_method,
                "classification": contact.classification or "Unknown",
                "name": contact.name,
            })

        # Sort by distance
        result.sort(key=lambda c: c["distance"])

        return result

    def prune_stale_contacts(self, current_time: float, existing_ship_ids: set = None):
        """Remove stale contacts, preserving those whose ships still exist.

        Contacts whose source ship still exists in the simulation are kept
        at minimum confidence rather than fully pruned. This prevents the
        autopilot from losing a target that is still physically present
        but temporarily undetected.

        Args:
            current_time: Current simulation time
            existing_ship_ids: Set of ship IDs still in the simulation.
                If provided, contacts mapped to these IDs are preserved.
        """
        if existing_ship_ids is None:
            existing_ship_ids = set()

        stale_ids = [
            cid for cid, contact in self.contacts.items()
            if contact.is_stale(current_time, self.stale_threshold * 2)
        ]

        for cid in stale_ids:
            # Find the real ship ID mapped to this contact
            real_id = next((rid for rid, sid in self.id_mapping.items() if sid == cid), None)

            # If the ship still exists in the sim, keep the contact at
            # minimum confidence instead of purging it entirely
            if real_id and real_id in existing_ship_ids:
                self.contacts[cid].confidence = max(self.contacts[cid].confidence, 0.05)
                continue

            # Ship no longer exists — safe to fully remove
            if real_id:
                del self.id_mapping[real_id]
            del self.contacts[cid]

def add_detection_noise(position: Dict[str, float], accuracy: float) -> Dict[str, float]:
    """Add noise to a position based on detection accuracy.

    Args:
        position: True position
        accuracy: Accuracy factor (0.0 = max noise, 1.0 = no noise)

    Returns:
        dict: Noisy position
    """
    # Noise magnitude inversely proportional to accuracy
    noise_magnitude = 1000.0 * (1.0 - accuracy)  # Up to 1km error at 0% accuracy

    noise = {
        "x": random.gauss(0, noise_magnitude),
        "y": random.gauss(0, noise_magnitude),
        "z": random.gauss(0, noise_magnitude)
    }

    return add_vectors(position, noise)


def add_velocity_noise(velocity: Dict[str, float], accuracy: float) -> Dict[str, float]:
    """Add noise to a velocity vector based on detection accuracy.

    Unlike position noise (up to 1km), velocity noise must use a much
    smaller scale.  At 0% accuracy the error is up to 50 m/s per axis;
    at 95% accuracy it's ~2.5 m/s — enough to be realistic sensor jitter
    without overwhelming autopilot control loops that rely on rel_speed
    thresholds of 20-180 m/s.

    Args:
        velocity: True velocity vector {x, y, z}
        accuracy: Accuracy factor (0.0 = max noise, 1.0 = no noise)

    Returns:
        dict: Noisy velocity
    """
    noise_magnitude = 50.0 * (1.0 - accuracy)  # Up to 50 m/s error at 0% accuracy

    noise = {
        "x": random.gauss(0, noise_magnitude),
        "y": random.gauss(0, noise_magnitude),
        "z": random.gauss(0, noise_magnitude)
    }

    return add_vectors(velocity, noise)


def calculate_detection_signature(ship) -> float:
    """Calculate detection signature for a ship.

    Delegates to the physics-based emission model. The returned value is
    the IR emission power in watts, which is the dominant passive
    detection signature (drive plumes, radiator heat, hull thermal).

    Args:
        ship: Ship object

    Returns:
        float: Signature strength in watts (higher = easier to detect)
    """
    from hybrid.systems.sensors.emission_model import calculate_ir_signature
    return calculate_ir_signature(ship)


def calculate_detection_accuracy(distance: float, signature: float, sensor_range: float) -> float:
    """Calculate detection accuracy based on distance and signature.

    Uses the physics-based detection quality model. Resolution degrades
    with distance — at long range you get a bearing and maybe a range
    estimate, not a detailed track.

    Args:
        distance: Distance to target in metres
        signature: Target IR signature in watts (used for range calc)
        sensor_range: Maximum sensor range in metres (from emission model)

    Returns:
        float: Accuracy (0.0 to 1.0)
    """
    from hybrid.systems.sensors.emission_model import (
        calculate_ir_detection_range, calculate_detection_quality
    )

    if sensor_range <= 0:
        return 0.0

    # Use emission-based detection range if signature is provided
    # The effective range is the minimum of sensor hardware range and
    # the range at which this target's emissions are detectable
    if signature > 0:
        emission_range = calculate_ir_detection_range(signature)
        effective_range = min(sensor_range, emission_range)
    else:
        effective_range = sensor_range

    if distance > effective_range:
        return 0.0

    quality = calculate_detection_quality(distance, effective_range)

    return min(0.95, max(0.1, quality))  # Clamp to 10-95%
