"""
Crew injury from subsystem damage.

When a ship subsystem takes damage, crew at the corresponding station
may be injured or killed. Killed crew leave the station unmanned,
falling back to AI backup at reduced capability.

Separated from crew_binding.py to keep modules under 300 lines.
"""

from __future__ import annotations

import logging
import random
from typing import Dict, Optional, List, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .crew_system import CrewManager, CrewMember
    from .crew_binding import CrewStationBinder

from .station_types import StationType

logger = logging.getLogger(__name__)

# Maps subsystem names to the stations whose crew would be
# physically near the damage and at risk of injury.
SUBSYSTEM_STATION_MAP: Dict[str, List[StationType]] = {
    "propulsion": [StationType.HELM],
    "rcs": [StationType.HELM],
    "sensors": [StationType.SCIENCE, StationType.OPS],
    "weapons": [StationType.TACTICAL],
    "targeting": [StationType.TACTICAL],
    "reactor": [StationType.ENGINEERING],
    "life_support": [StationType.OPS],
    "radiators": [StationType.ENGINEERING],
    "comms": [StationType.COMMS],
}


def apply_damage_to_crew(
    binder: CrewStationBinder,
    crew_manager: CrewManager,
    ship_id: str,
    station: StationType,
    severity: float,
) -> Optional[Dict[str, Any]]:
    """
    Apply potential injury to the crew member at a station.

    Injury chance scales with severity: light hits (0.1) rarely injure,
    catastrophic hits (1.0) almost always do. Each hit escalates the
    crew member's injury state one step: healthy->wounded->critical->dead.

    Args:
        binder: The crew-station binder (to access slots)
        crew_manager: Crew manager (to look up crew members)
        ship_id: Ship identifier
        station: Which station was hit
        severity: 0.0 (scratch) to 1.0 (catastrophic)

    Returns:
        Dict with injury details, or None if no crew at station / crew is dead.
    """
    from .crew_progression import InjuryState

    slots = binder._slots.get(ship_id)
    if slots is None:
        return None

    slot = slots.get(station)
    if slot is None or slot.crew_id is None:
        return None

    crew = crew_manager.get_crew_member(ship_id, slot.crew_id)
    if crew is None:
        return None

    # Dead crew are not processed -- they are already gone
    if crew.injury_state == InjuryState.DEAD:
        return None

    # Injury chance: severity * 0.8 means light hits rarely hurt,
    # heavy hits almost always do
    injury_chance = severity * 0.8
    if random.random() > injury_chance:
        return {"crew_name": crew.name, "injured": False, "severity": severity}

    # Health reduction proportional to severity with some randomness
    health_loss = severity * (0.3 + random.random() * 0.4)
    crew.health = max(0.0, crew.health - health_loss)

    # Stress spike from being hit
    crew.stress = min(1.0, crew.stress + severity * 0.5)

    # Escalate injury state one step along the severity ladder.
    # However, if health reaches zero the crew member is dead outright
    # regardless of their current injury state -- a catastrophic hit
    # on a healthy person can still kill them.
    old_state = crew.injury_state
    if crew.health <= 0.0:
        new_state = InjuryState.DEAD
    else:
        new_state = _escalate_injury(crew.injury_state)
    crew.injury_state = new_state

    if new_state == InjuryState.DEAD:
        # Dead crew: station falls back to AI
        slot.crew_id = None
        slot.is_ai_backup = True
        logger.warning(f"{crew.name} killed at {station.value} on {ship_id}")
    elif new_state == InjuryState.CRITICAL:
        # Critical crew are removed from their station
        slot.crew_id = None
        slot.is_ai_backup = True
        logger.warning(
            f"{crew.name} critically injured at {station.value} on {ship_id}"
        )
    else:
        logger.info(
            f"{crew.name} injured at {station.value} on {ship_id} "
            f"({old_state} -> {new_state}, health: {crew.health:.0%})"
        )

    return {
        "crew_name": crew.name,
        "injured": True,
        "killed": new_state == InjuryState.DEAD,
        "old_state": old_state,
        "new_state": new_state,
        "health_remaining": round(crew.health, 2),
        "health_lost": round(health_loss, 2),
        "severity": severity,
    }


# Injury escalation ladder: each hit moves one step up
_INJURY_ESCALATION: Dict[str, str] = {
    "healthy": "wounded",
    "wounded": "critical",
    "critical": "dead",
}


def _escalate_injury(current_state: str) -> str:
    """Advance to the next injury state. Dead is terminal."""
    return _INJURY_ESCALATION.get(current_state, current_state)


def on_subsystem_damaged(
    binder: CrewStationBinder,
    crew_manager: CrewManager,
    ship_id: str,
    subsystem: str,
    severity: float,
) -> List[Dict[str, Any]]:
    """
    Map subsystem damage to crew injuries at corresponding stations.

    Args:
        binder: The crew-station binder
        crew_manager: Crew manager
        ship_id: Ship identifier
        subsystem: Name of the damaged subsystem (e.g. "weapons", "propulsion")
        severity: Damage severity 0.0-1.0

    Returns:
        List of injury reports (may be empty if no crew affected).
    """
    affected_stations = SUBSYSTEM_STATION_MAP.get(subsystem, [])
    results = []
    for station in affected_stations:
        report = apply_damage_to_crew(
            binder, crew_manager, ship_id, station, severity,
        )
        if report is not None:
            results.append(report)
    return results
