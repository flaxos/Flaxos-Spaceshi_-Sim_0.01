"""Threat assessment and target prioritization for AI ships.

Stateless utility class that scores and sorts sensor contacts by
threat level.  Used by AIController to decide which target to
engage first.

Scoring factors:
  - Distance: closer contacts score higher
  - Closing velocity: approaching contacts score higher
  - Classification: larger/deadlier ship classes score higher
"""

from typing import List, Tuple
import numpy as np


class AIThreatAssessment:
    """Assess threats and prioritize targets.

    Works with (contact_id, ContactData) tuples from the sensor
    contact tracker, not raw dicts.
    """

    @staticmethod
    def assess_threat(contact_id: str, contact, own_ship) -> float:
        """Assess threat level of a contact.

        Args:
            contact_id: Stable contact ID (e.g. "C001").
            contact: ContactData dataclass instance.
            own_ship: The ship being threatened.

        Returns:
            Threat score (0-10, higher is more threatening).
        """
        threat = 0.0

        # Distance factor (closer = more threatening)
        pos = getattr(contact, "position", {})
        contact_pos = np.array([pos.get("x", 0), pos.get("y", 0), pos.get("z", 0)])
        own_pos_dict = own_ship.position if hasattr(own_ship, "position") else {}
        own_pos = np.array([
            own_pos_dict.get("x", 0),
            own_pos_dict.get("y", 0),
            own_pos_dict.get("z", 0),
        ])
        distance = float(np.linalg.norm(contact_pos - own_pos))

        if distance < 10_000:       # Within 10km -- critical
            threat += 5.0
        elif distance < 50_000:     # Within 50km -- high
            threat += 3.0
        elif distance < 100_000:    # Within 100km -- moderate
            threat += 1.0

        # Closing velocity (approaching = more threatening)
        vel = getattr(contact, "velocity", {})
        contact_vel = np.array([vel.get("x", 0), vel.get("y", 0), vel.get("z", 0)])
        own_vel_dict = own_ship.velocity if hasattr(own_ship, "velocity") else {}
        own_vel = np.array([
            own_vel_dict.get("x", 0),
            own_vel_dict.get("y", 0),
            own_vel_dict.get("z", 0),
        ])
        relative_vel = contact_vel - own_vel

        if distance > 0:
            closing_velocity = -np.dot(relative_vel, (contact_pos - own_pos)) / distance
            if closing_velocity > 0:
                threat += min(closing_velocity / 100.0, 3.0)

        # Classification factor
        classification = (getattr(contact, "classification", None) or "unknown").lower()
        if "fighter" in classification:
            threat += 1.0
        elif "frigate" in classification or "destroyer" in classification:
            threat += 2.0
        elif "cruiser" in classification:
            threat += 3.0
        elif "battleship" in classification or "carrier" in classification:
            threat += 4.0

        return min(threat, 10.0)

    @staticmethod
    def prioritize_targets(
        contacts: List[Tuple[str, object]],
        own_ship,
    ) -> List[Tuple[str, object]]:
        """Sort contacts by threat level (highest first).

        Args:
            contacts: List of (contact_id, ContactData) tuples.
            own_ship: The ship assessing threats.

        Returns:
            Sorted list of (contact_id, ContactData) tuples.
        """
        scored = [
            (cid, contact, AIThreatAssessment.assess_threat(cid, contact, own_ship))
            for cid, contact in contacts
        ]
        scored.sort(key=lambda x: x[2], reverse=True)
        return [(cid, contact) for cid, contact, _score in scored]
