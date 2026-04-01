"""
Crew injury from subsystem damage.

When a ship subsystem takes damage, crew at the corresponding station
may be injured or killed. The injury state escalates through a defined
ladder: HEALTHY -> WOUNDED -> CRITICAL -> DEAD.

Injury escalation probabilities:
- HEALTHY -> WOUNDED: damage_fraction * 0.3
- WOUNDED -> CRITICAL: 50% if hit again while wounded
- CRITICAL -> DEAD: 30% if hit again while critical

Recovery:
- WOUNDED -> HEALTHY: automatic after mission ends
- CRITICAL -> WOUNDED: requires station dock + medical bay (campaign)

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
from .crew_system import InjuryState

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

    Uses the InjuryState escalation ladder rather than raw health
    reduction. Each hit while already injured has a chance to push the
    crew member to the next injury state.

    Args:
        binder: The crew-station binder (to access slots)
        crew_manager: Crew manager (to look up crew members)
        ship_id: Ship identifier
        station: Which station was hit
        severity: 0.0 (scratch) to 1.0 (catastrophic)

    Returns:
        Dict with injury details, or None if no crew at station.
    """
    slots = binder._slots.get(ship_id)
    if slots is None:
        return None

    slot = slots.get(station)
    if slot is None or slot.crew_id is None:
        return None

    crew = crew_manager.get_crew_member(ship_id, slot.crew_id)
    if crew is None or crew.injury_state == InjuryState.DEAD:
        return None

    # Determine injury outcome based on current state
    old_state = crew.injury_state
    new_state = old_state
    injured = False

    if old_state == InjuryState.HEALTHY:
        # Injury chance scales with severity: light hits rarely hurt,
        # catastrophic hits almost always do
        injury_chance = severity * 0.3
        if random.random() < injury_chance:
            new_state = InjuryState.WOUNDED
            injured = True

    elif old_state == InjuryState.WOUNDED:
        # Already hurt -- 50% chance of escalating to CRITICAL
        if random.random() < 0.5:
            new_state = InjuryState.CRITICAL
            injured = True

    elif old_state == InjuryState.CRITICAL:
        # Already critical -- 30% chance of death
        if random.random() < 0.3:
            new_state = InjuryState.DEAD
            injured = True

    # Apply state change
    crew.injury_state = new_state

    # Apply health reduction proportional to severity (cosmetic tracking)
    health_loss = 0.0
    if injured:
        health_loss = severity * (0.3 + random.random() * 0.4)
        crew.health = max(0.0, crew.health - health_loss)

    # Stress spike from being hit (even if not injured)
    crew.stress = min(1.0, crew.stress + severity * 0.5)

    killed = new_state == InjuryState.DEAD
    if killed:
        crew.health = 0.0
        # Dead crew: station falls back to AI
        slot.crew_id = None
        slot.is_ai_backup = True
        logger.warning(f"{crew.name} killed at {station.value} on {ship_id}")
    elif new_state == InjuryState.CRITICAL:
        # Critical crew cannot work -- remove from station
        slot.crew_id = None
        slot.is_ai_backup = True
        logger.warning(
            f"{crew.name} critically injured at {station.value} on {ship_id}"
        )
    elif injured:
        logger.info(
            f"{crew.name} wounded at {station.value} on {ship_id} "
            f"(health: {crew.health:.0%})"
        )

    return {
        "crew_name": crew.name,
        "injured": injured,
        "killed": killed,
        "old_state": old_state,
        "new_state": new_state,
        "health_remaining": round(crew.health, 2),
        "health_lost": round(health_loss, 2),
        "severity": severity,
    }


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
