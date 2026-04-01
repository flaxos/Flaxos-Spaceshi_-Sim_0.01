"""Threat assessment and target prioritization for AI ships.

Stateless utility class that scores and sorts sensor contacts by
threat level.  Used by AIController to decide which target to
engage first.

Scoring factors (Phase 1 — distance, velocity, classification):
  - Distance: closer contacts score higher
  - Closing velocity: approaching contacts score higher
  - Classification: larger/deadlier ship classes score higher

Tactical scoring (Phase 3 — doctrine-aware):
  - Weapon threat: ships with active railguns are high-value targets
  - Sensor damage: easier to hit = opportunistic bonus
  - Propulsion damage: can't evade = sitting duck bonus
  - Spread fire: targets already engaged by friendlies get a penalty
    to prevent all AI from dogpiling the same victim
"""

from typing import List, Optional, Tuple
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
    def assess_threat_tactical(
        contact_id: str,
        contact,
        own_ship,
        friendly_targets: Optional[dict] = None,
    ) -> float:
        """Tactical threat assessment with doctrine-aware scoring.

        Extends the base threat score with subsystem-aware bonuses
        and a spread-fire penalty to distribute AI fire across
        multiple targets.

        Args:
            contact_id: Stable contact ID.
            contact: ContactData dataclass instance.
            own_ship: The ship assessing threats.
            friendly_targets: Dict of {contact_id: count} showing how
                many friendly AI ships already target each contact.
                None disables the spread-fire logic.

        Returns:
            Tactical threat score (can exceed 10.0).
        """
        base = AIThreatAssessment.assess_threat(contact_id, contact, own_ship)

        # Resolve the actual ship behind this contact to inspect
        # its subsystems.  If we can't resolve, skip tactical bonuses.
        target_ship = _resolve_contact_ship(contact_id, own_ship)

        if target_ship:
            damage_model = getattr(target_ship, "damage_model", None)

            # Active railguns: high weapon threat
            combat = target_ship.systems.get("combat") if hasattr(target_ship, "systems") else None
            if combat and hasattr(combat, "truth_weapons"):
                has_railgun = any(
                    w.mount_id.startswith("railgun")
                    for w in combat.truth_weapons.values()
                    if w.ammo is None or w.ammo > 0
                )
                if has_railgun:
                    base += 3.0

                # PDC-only range (<2km): lower priority -- PDC can't
                # penetrate armor, so this ship is a nuisance not a
                # lethal threat.  Only applies if the target has NO
                # railgun ammo left.
                if not has_railgun:
                    pos = getattr(contact, "position", {})
                    contact_pos = np.array([
                        pos.get("x", 0), pos.get("y", 0), pos.get("z", 0),
                    ])
                    own_pos = _get_pos_array(own_ship)
                    dist = float(np.linalg.norm(contact_pos - own_pos))
                    if dist < 2_000:
                        base += 1.0

            # Damaged sensors: easier to track, opportunistic target
            if damage_model:
                sensor_factor = damage_model.get_combined_factor("sensors")
                if sensor_factor < 0.7:
                    base += 1.5

                # Damaged propulsion: can't evade effectively.
                # +1.0 (not as high as sensors because a crippled
                # ship is already less of a threat to us).
                prop_factor = damage_model.get_combined_factor("propulsion")
                if prop_factor < 0.7:
                    base += 1.0

        # Spread fire: penalize targets already engaged by friendlies
        # so AI ships distribute damage across multiple enemies.
        if friendly_targets and contact_id in friendly_targets:
            engaged_count = friendly_targets[contact_id]
            base -= 2.0 * engaged_count

        return base

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

    @staticmethod
    def prioritize_targets_tactical(
        contacts: List[Tuple[str, object]],
        own_ship,
        friendly_targets: Optional[dict] = None,
    ) -> List[Tuple[str, object]]:
        """Sort contacts using tactical threat scoring.

        Args:
            contacts: List of (contact_id, ContactData) tuples.
            own_ship: The ship assessing threats.
            friendly_targets: Dict of {contact_id: count} of friendly
                AI engagements per target.

        Returns:
            Sorted list of (contact_id, ContactData) tuples.
        """
        scored = [
            (
                cid,
                contact,
                AIThreatAssessment.assess_threat_tactical(
                    cid, contact, own_ship, friendly_targets,
                ),
            )
            for cid, contact in contacts
        ]
        scored.sort(key=lambda x: x[2], reverse=True)
        return [(cid, contact) for cid, contact, _score in scored]


# ── Module-level helpers ───────────────────────────────────────────

def _resolve_contact_ship(contact_id: str, own_ship) -> object:
    """Resolve a contact ID to the actual Ship object.

    Uses the sensor contact tracker's id_mapping to reverse-lookup
    the real ship ID, then finds it in _all_ships_ref.

    Args:
        contact_id: Stable contact ID.
        own_ship: Ship performing the lookup.

    Returns:
        Ship object or None.
    """
    if not hasattr(own_ship, "_all_ships_ref"):
        return None

    all_ships = own_ship._all_ships_ref or []
    ships_by_id = {s.id: s for s in all_ships}

    # Direct lookup first
    if contact_id in ships_by_id:
        return ships_by_id[contact_id]

    # Reverse-map stable contact ID -> real ship ID
    sensors = own_ship.systems.get("sensors") if hasattr(own_ship, "systems") else None
    if sensors and hasattr(sensors, "contact_tracker"):
        for real_id, stable_id in sensors.contact_tracker.id_mapping.items():
            if stable_id == contact_id:
                return ships_by_id.get(real_id)

    return None


def _get_pos_array(ship) -> np.ndarray:
    """Extract position as numpy array from a ship object."""
    pos = getattr(ship, "position", {})
    if isinstance(pos, dict):
        return np.array([pos.get("x", 0), pos.get("y", 0), pos.get("z", 0)])
    return np.array([0.0, 0.0, 0.0])
