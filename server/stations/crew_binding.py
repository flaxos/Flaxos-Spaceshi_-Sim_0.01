"""
Crew-station binding: links CrewMember skills to station performance.

Unmanned stations fall back to AI crew at reduced capability.
Damage/injury logic lives in crew_damage.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any, Tuple

from .crew_system import CrewMember, CrewSkills, CrewManager, StationSkill, SkillLevel
from .station_types import StationType
from .crew_damage import (
    apply_damage_to_crew,
    on_subsystem_damaged as _on_subsystem_damaged,
)

logger = logging.getLogger(__name__)

# Which skills matter for each station
STATION_SKILL_MAP: Dict[StationType, List[StationSkill]] = {
    StationType.HELM: [StationSkill.PILOTING, StationSkill.NAVIGATION],
    StationType.TACTICAL: [StationSkill.GUNNERY, StationSkill.TARGETING],
    StationType.OPS: [StationSkill.DAMAGE_CONTROL, StationSkill.SENSORS],
    StationType.ENGINEERING: [StationSkill.ENGINEERING, StationSkill.DAMAGE_CONTROL],
    StationType.SCIENCE: [StationSkill.SENSORS, StationSkill.ELECTRONIC_WARFARE],
    StationType.COMMS: [StationSkill.COMMUNICATIONS],
    StationType.CAPTAIN: [StationSkill.COMMAND],
    StationType.FLEET_COMMANDER: [StationSkill.FLEET_TACTICS, StationSkill.COMMAND],
}

XP_PER_ACTION: float = 0.02           # XP per action (before diminishing returns)
AI_BACKUP_COMPETENCE: float = 0.35    # Unmanned station fallback multiplier


@dataclass
class StationSlot:
    """A crew slot on a specific station aboard a ship."""
    station: StationType
    crew_id: Optional[str] = None
    is_ai_backup: bool = True


@dataclass
class PerformanceReport:
    """Snapshot of crew performance at a station."""
    crew_name: str
    station: str
    efficiency: float
    skill_breakdown: Dict[str, float]
    health: float
    fatigue: float
    stress: float
    is_ai: bool


class CrewStationBinder:
    """Manages crew-to-station assignments and computes performance multipliers."""

    def __init__(self, crew_manager: CrewManager):
        self.crew_manager = crew_manager
        self._slots: Dict[str, Dict[StationType, StationSlot]] = {}

    def register_ship(self, ship_id: str) -> None:
        """Create empty station slots for a ship."""
        self._slots[ship_id] = {
            st: StationSlot(station=st) for st in StationType
        }
        logger.info(f"Crew slots registered for ship {ship_id}")

    # -- Assignment --------------------------------------------------------

    def assign_crew(self, ship_id: str, crew_id: str, station: StationType) -> Tuple[bool, str]:
        """Assign a crew member to a station. Returns (success, message)."""
        slots = self._slots.get(ship_id)
        if slots is None:
            return False, f"Ship {ship_id} has no crew slots registered"

        crew = self.crew_manager.get_crew_member(ship_id, crew_id)
        if crew is None:
            return False, f"Crew member {crew_id} not found on ship {ship_id}"
        if crew.health <= 0.0:
            return False, f"{crew.name} is dead and cannot be assigned"

        current = self._find_assignment(ship_id, crew_id)
        if current is not None:
            return False, f"{crew.name} is already assigned to {current.value}. Transfer them first."

        slot = slots[station]
        if slot.crew_id is not None:
            existing = self.crew_manager.get_crew_member(ship_id, slot.crew_id)
            name = existing.name if existing else slot.crew_id
            return False, f"{station.value} already has {name} assigned. Transfer them first."

        slot.crew_id = crew_id
        slot.is_ai_backup = False
        logger.info(f"{crew.name} assigned to {station.value} on {ship_id}")
        return True, f"{crew.name} assigned to {station.value}"

    def unassign_crew(self, ship_id: str, station: StationType) -> Tuple[bool, str]:
        """Remove crew from a station, falling back to AI backup."""
        slots = self._slots.get(ship_id)
        if slots is None:
            return False, f"Ship {ship_id} has no crew slots registered"

        slot = slots[station]
        if slot.crew_id is None:
            return False, f"{station.value} has no crew assigned"

        crew = self.crew_manager.get_crew_member(ship_id, slot.crew_id)
        name = crew.name if crew else slot.crew_id
        slot.crew_id = None
        slot.is_ai_backup = True
        logger.info(f"{name} removed from {station.value} on {ship_id}")
        return True, f"{name} removed from {station.value} (AI backup active)"

    def transfer_crew(self, ship_id: str, crew_id: str, to_station: StationType) -> Tuple[bool, str]:
        """Transfer crew from current station to a new one. Atomic operation."""
        slots = self._slots.get(ship_id)
        if slots is None:
            return False, f"Ship {ship_id} has no crew slots registered"

        crew = self.crew_manager.get_crew_member(ship_id, crew_id)
        if crew is None:
            return False, f"Crew member {crew_id} not found on ship {ship_id}"

        from_station = self._find_assignment(ship_id, crew_id)
        if from_station is None:
            return False, f"{crew.name} is not currently assigned to any station"
        if from_station == to_station:
            return False, f"{crew.name} is already at {to_station.value}"

        target_slot = slots[to_station]
        if target_slot.crew_id is not None:
            existing = self.crew_manager.get_crew_member(ship_id, target_slot.crew_id)
            name = existing.name if existing else target_slot.crew_id
            return False, f"{to_station.value} already has {name} assigned"

        slots[from_station].crew_id = None
        slots[from_station].is_ai_backup = True
        target_slot.crew_id = crew_id
        target_slot.is_ai_backup = False

        logger.info(f"{crew.name} transferred {from_station.value} -> {to_station.value} on {ship_id}")
        return True, f"{crew.name} transferred from {from_station.value} to {to_station.value}"

    # -- Performance -------------------------------------------------------

    def get_station_multiplier(self, ship_id: str, station: StationType) -> float:
        """Get combined performance multiplier for a station (0.0-1.0)."""
        slots = self._slots.get(ship_id)
        if slots is None:
            return AI_BACKUP_COMPETENCE

        slot = slots.get(station)
        if slot is None or slot.crew_id is None:
            return AI_BACKUP_COMPETENCE

        crew = self.crew_manager.get_crew_member(ship_id, slot.crew_id)
        if crew is None or crew.health <= 0.0:
            return AI_BACKUP_COMPETENCE

        # Average efficiency across station-relevant skills
        skills = STATION_SKILL_MAP.get(station, [])
        if not skills:
            return crew.get_current_efficiency(StationSkill.COMMAND)
        return sum(crew.get_current_efficiency(s) for s in skills) / len(skills)

    def get_performance_report(self, ship_id: str, station: StationType) -> Optional[PerformanceReport]:
        """Build a detailed performance report for a station."""
        slots = self._slots.get(ship_id)
        if slots is None:
            return None
        slot = slots.get(station)
        if slot is None:
            return None

        if slot.crew_id is None:
            return PerformanceReport(
                crew_name="AI Backup", station=station.value,
                efficiency=AI_BACKUP_COMPETENCE, skill_breakdown={},
                health=1.0, fatigue=0.0, stress=0.0, is_ai=True,
            )

        crew = self.crew_manager.get_crew_member(ship_id, slot.crew_id)
        if crew is None:
            return None

        skills = STATION_SKILL_MAP.get(station, [])
        breakdown = {s.value: round(crew.get_current_efficiency(s), 3) for s in skills}

        return PerformanceReport(
            crew_name=crew.name, station=station.value,
            efficiency=round(self.get_station_multiplier(ship_id, station), 3),
            skill_breakdown=breakdown,
            health=round(crew.health, 2), fatigue=round(crew.fatigue, 2),
            stress=round(crew.stress, 2), is_ai=False,
        )

    # -- Experience --------------------------------------------------------

    def record_action(self, ship_id: str, station: StationType, success: bool = True) -> None:
        """Record an action for learning-by-doing XP. Grants skill XP to the assigned crew."""
        slots = self._slots.get(ship_id)
        if slots is None:
            return
        slot = slots.get(station)
        if slot is None or slot.crew_id is None:
            return
        crew = self.crew_manager.get_crew_member(ship_id, slot.crew_id)
        if crew is None or crew.health <= 0.0:
            return

        crew.record_command(success)
        xp = XP_PER_ACTION if success else XP_PER_ACTION * 0.3
        for skill in STATION_SKILL_MAP.get(station, []):
            crew.improve_skill(skill, xp)

    # -- Crew injury (delegated to crew_damage module) ---------------------

    def apply_damage_to_station(self, ship_id: str, station: StationType, severity: float) -> Optional[Dict[str, Any]]:
        """Apply potential injury to crew at a station."""
        return apply_damage_to_crew(self, self.crew_manager, ship_id, station, severity)

    def on_subsystem_damaged(self, ship_id: str, subsystem: str, severity: float) -> List[Dict[str, Any]]:
        """Map subsystem damage to crew injuries at corresponding stations."""
        return _on_subsystem_damaged(self, self.crew_manager, ship_id, subsystem, severity)

    # -- Serialization -----------------------------------------------------

    def get_ship_crew_status(self, ship_id: str) -> List[Dict[str, Any]]:
        """Get crew assignment status for all stations on a ship."""
        slots = self._slots.get(ship_id, {})
        result = []
        for station, slot in slots.items():
            report = self.get_performance_report(ship_id, station)
            entry: Dict[str, Any] = {
                "station": station.value,
                "crew_id": slot.crew_id,
                "is_ai_backup": slot.is_ai_backup,
            }
            if report:
                entry["performance"] = {
                    "crew_name": report.crew_name,
                    "efficiency": report.efficiency,
                    "skill_breakdown": report.skill_breakdown,
                    "health": report.health,
                    "fatigue": report.fatigue,
                    "stress": report.stress,
                    "is_ai": report.is_ai,
                }
            result.append(entry)
        return result

    # -- Internal ----------------------------------------------------------

    def _find_assignment(self, ship_id: str, crew_id: str) -> Optional[StationType]:
        """Find which station a crew member is assigned to."""
        for station, slot in self._slots.get(ship_id, {}).items():
            if slot.crew_id == crew_id:
                return station
        return None
