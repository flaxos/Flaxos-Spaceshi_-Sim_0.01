"""
Crew efficiency and skill management system.

Tracks individual crew members, their skills, fatigue, and performance.
Integrates with the station system to affect command execution efficiency.
"""

import time
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class SkillLevel(Enum):
    """Crew skill proficiency levels"""
    NOVICE = 1       # 0-20% efficiency
    TRAINEE = 2      # 20-40% efficiency
    COMPETENT = 3    # 40-60% efficiency
    SKILLED = 4      # 60-80% efficiency
    EXPERT = 5       # 80-95% efficiency
    MASTER = 6       # 95-100% efficiency


class StationSkill(Enum):
    """Skills for different station roles"""
    PILOTING = "piloting"                  # Helm station
    NAVIGATION = "navigation"              # Helm station
    GUNNERY = "gunnery"                    # Tactical station
    TARGETING = "targeting"                # Tactical station
    SENSORS = "sensors"                    # Ops station
    ELECTRONIC_WARFARE = "electronic_warfare"  # Ops station
    ENGINEERING = "engineering"            # Engineering station
    DAMAGE_CONTROL = "damage_control"      # Engineering station
    COMMUNICATIONS = "communications"      # Comms station
    COMMAND = "command"                    # Captain station
    FLEET_TACTICS = "fleet_tactics"        # Fleet Commander station


@dataclass
class CrewSkills:
    """Skill levels for a crew member"""
    piloting: int = 3           # Default to COMPETENT
    navigation: int = 3
    gunnery: int = 3
    targeting: int = 3
    sensors: int = 3
    electronic_warfare: int = 3
    engineering: int = 3
    damage_control: int = 3
    communications: int = 3
    command: int = 3
    fleet_tactics: int = 3

    def get_skill(self, skill: StationSkill) -> int:
        """Get skill level for a specific skill"""
        return getattr(self, skill.value, 3)

    def set_skill(self, skill: StationSkill, level: int):
        """Set skill level for a specific skill"""
        level = max(1, min(6, level))  # Clamp to 1-6
        setattr(self, skill.value, level)

    def get_efficiency(self, skill: StationSkill) -> float:
        """
        Get efficiency multiplier for a skill (0.0 to 1.0).

        Returns:
            Efficiency multiplier based on skill level
        """
        level = self.get_skill(skill)

        # Map skill level to efficiency
        efficiency_map = {
            1: 0.10,  # NOVICE
            2: 0.30,  # TRAINEE
            3: 0.50,  # COMPETENT
            4: 0.70,  # SKILLED
            5: 0.90,  # EXPERT
            6: 0.98,  # MASTER
        }

        return efficiency_map.get(level, 0.50)


@dataclass
class CrewMember:
    """Represents a crew member with skills, fatigue, and performance tracking"""
    name: str
    crew_id: str
    skills: CrewSkills = field(default_factory=CrewSkills)

    # Fatigue and stress
    fatigue: float = 0.0          # 0.0 = rested, 1.0 = exhausted
    stress: float = 0.0           # 0.0 = calm, 1.0 = max stress
    health: float = 1.0           # 0.0 = dead, 1.0 = healthy

    # Progression (Phase 4D) -- XP accumulates per-skill, injury escalates.
    # Note: experience uses a sentinel default (None) so that
    # hasattr(CrewMember, "experience") returns True at the class level,
    # which the test skip-guard relies on. __post_init__ converts to {}.
    experience: Optional[Dict[str, int]] = None  # skill_name -> accumulated XP
    injury_state: str = "healthy"  # "healthy", "wounded", "critical", "dead"

    # Performance tracking
    commands_executed: int = 0
    successful_commands: int = 0
    failures: int = 0
    time_at_station: float = 0.0  # Hours at current station

    # Timestamps
    last_shift_start: float = field(default_factory=time.time)
    last_rest: float = field(default_factory=time.time)

    def __post_init__(self):
        """Initialize mutable defaults that need to be unique per instance."""
        if self.experience is None:
            self.experience = {}

    def get_current_efficiency(self, skill: StationSkill) -> float:
        """
        Get current efficiency including skill level, fatigue/stress, and injury.

        Critical and dead crew return 0.0 -- they cannot operate stations.
        Wounded crew suffer a 50% penalty on top of other modifiers.

        Args:
            skill: The skill to check

        Returns:
            Efficiency multiplier (0.0 to 1.0)
        """
        from server.stations.crew_progression import InjuryState

        # Critical/dead crew cannot function at all
        if self.injury_state in (InjuryState.CRITICAL, InjuryState.DEAD):
            return 0.0

        # Base efficiency from skill
        base_efficiency = self.skills.get_efficiency(skill)

        # Apply fatigue penalty (max -40%)
        fatigue_penalty = self.fatigue * 0.4

        # Apply stress penalty (max -30%)
        stress_penalty = self.stress * 0.3

        # Apply health penalty (max -50%)
        health_penalty = (1.0 - self.health) * 0.5

        # Calculate final efficiency
        efficiency = base_efficiency - fatigue_penalty - stress_penalty - health_penalty

        # Wounded crew operate at half capacity
        if self.injury_state == InjuryState.WOUNDED:
            efficiency *= 0.5

        return max(0.0, min(1.0, efficiency))  # Clamp to 0.0-1.0

    def get_success_rate(self) -> float:
        """
        Get command success rate (0.0 to 1.0).

        Returns:
            Success rate as a float
        """
        if self.commands_executed == 0:
            return 1.0
        return self.successful_commands / self.commands_executed

    def record_command(self, success: bool):
        """
        Record a command execution.

        Args:
            success: Whether the command succeeded
        """
        self.commands_executed += 1
        if success:
            self.successful_commands += 1
        else:
            self.failures += 1
            # Failures increase stress
            self.stress = min(1.0, self.stress + 0.05)

    def update_fatigue(self, dt: float):
        """
        Update fatigue level based on time worked.

        Args:
            dt: Time delta in seconds
        """
        current_time = time.time()
        time_since_rest = current_time - self.last_rest

        # Increase fatigue over time (fully fatigued after 8 hours)
        hours_worked = time_since_rest / 3600.0
        self.fatigue = min(1.0, hours_worked / 8.0)

        # Update time at station
        self.time_at_station = (current_time - self.last_shift_start) / 3600.0

    def rest(self, hours: float):
        """
        Rest for a period of time to reduce fatigue.

        Args:
            hours: Hours of rest
        """
        # Reduce fatigue (full rest after 8 hours)
        fatigue_reduction = hours / 8.0
        self.fatigue = max(0.0, self.fatigue - fatigue_reduction)

        # Reduce stress
        self.stress = max(0.0, self.stress - fatigue_reduction * 0.5)

        # Update timestamps
        self.last_rest = time.time()

    def improve_skill(self, skill: StationSkill, amount: float = 0.1):
        """
        Improve a skill through practice.

        Args:
            skill: Skill to improve
            amount: Amount to improve (partial levels allowed)
        """
        current = self.skills.get_skill(skill)
        # Skill improvement gets harder at higher levels
        improvement_rate = amount * (7 - current) / 6

        if improvement_rate >= 1.0:
            new_level = min(6, current + 1)
            self.skills.set_skill(skill, new_level)
            logger.info(f"Crew {self.name} improved {skill.value} to level {new_level}")

    def award_xp(self, skill_name: str, amount: int) -> bool:
        """Award XP to a skill and check for level advancement.

        Dead crew cannot gain XP. Zero or negative amounts are rejected.

        Args:
            skill_name: Skill to award XP for (e.g. "gunnery")
            amount: Integer XP to add

        Returns:
            True if the skill advanced a level, False otherwise.
        """
        from server.stations.crew_progression import InjuryState, try_advance_skill

        if amount <= 0:
            return False

        # Dead crew learn nothing
        if self.injury_state == InjuryState.DEAD:
            return False

        # Accumulate XP
        self.experience[skill_name] = self.experience.get(skill_name, 0) + amount

        # Check if this triggers a level-up
        return try_advance_skill(self, skill_name)

    def check_advancement(self) -> list:
        """Check all skills for possible level-ups from accumulated XP.

        Returns:
            List of skill names that advanced.
        """
        from server.stations.crew_progression import check_all_advancements
        return check_all_advancements(self)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        from server.stations.crew_progression import XP_THRESHOLDS

        # Build per-skill XP progress for the GUI progress bars
        xp_progress = {}
        for skill in StationSkill:
            skill_name = skill.value
            if skill_name in self.experience:
                current_level = self.skills.get_skill(skill)
                xp_progress[skill_name] = {
                    "xp": self.experience[skill_name],
                    "threshold": XP_THRESHOLDS.get(current_level),
                    "level": current_level,
                }

        return {
            "name": self.name,
            "crew_id": self.crew_id,
            "skills": {
                "piloting": self.skills.piloting,
                "navigation": self.skills.navigation,
                "gunnery": self.skills.gunnery,
                "targeting": self.skills.targeting,
                "sensors": self.skills.sensors,
                "electronic_warfare": self.skills.electronic_warfare,
                "engineering": self.skills.engineering,
                "damage_control": self.skills.damage_control,
                "communications": self.skills.communications,
                "command": self.skills.command,
                "fleet_tactics": self.skills.fleet_tactics,
            },
            "fatigue": round(self.fatigue, 2),
            "stress": round(self.stress, 2),
            "health": round(self.health, 2),
            "experience": dict(self.experience),
            "injury_state": self.injury_state,
            "xp_progress": xp_progress,
            "performance": {
                "commands_executed": self.commands_executed,
                "successful_commands": self.successful_commands,
                "failures": self.failures,
                "success_rate": round(self.get_success_rate(), 2),
            },
            "time_at_station_hours": round(self.time_at_station, 1),
        }


class CrewManager:
    """Manages crew members across all ships"""

    def __init__(self):
        # ship_id -> crew_id -> CrewMember
        self.crew: Dict[str, Dict[str, CrewMember]] = {}

        # client_id -> crew_id mapping
        self.client_to_crew: Dict[str, str] = {}

        # Counter for generating crew IDs
        self._next_crew_id = 1

    def generate_crew_id(self) -> str:
        """Generate a unique crew ID"""
        crew_id = f"crew_{self._next_crew_id}"
        self._next_crew_id += 1
        return crew_id

    def create_crew_member(
        self,
        ship_id: str,
        name: str,
        client_id: Optional[str] = None,
        skills: Optional[CrewSkills] = None
    ) -> CrewMember:
        """
        Create a new crew member.

        Args:
            ship_id: Ship the crew member is assigned to
            name: Crew member name
            client_id: Client controlling this crew member (if any)
            skills: Initial skill levels (default to COMPETENT)

        Returns:
            CrewMember instance
        """
        crew_id = self.generate_crew_id()

        crew_member = CrewMember(
            name=name,
            crew_id=crew_id,
            skills=skills or CrewSkills()
        )

        # Initialize ship's crew dict if needed
        if ship_id not in self.crew:
            self.crew[ship_id] = {}

        self.crew[ship_id][crew_id] = crew_member

        # Map client to crew if provided
        if client_id:
            self.client_to_crew[client_id] = crew_id

        logger.info(f"Created crew member {name} ({crew_id}) on ship {ship_id}")
        return crew_member

    def get_crew_member(self, ship_id: str, crew_id: str) -> Optional[CrewMember]:
        """
        Get a crew member.

        Args:
            ship_id: Ship ID
            crew_id: Crew member ID

        Returns:
            CrewMember if found, None otherwise
        """
        if ship_id not in self.crew:
            return None
        return self.crew[ship_id].get(crew_id)

    def get_crew_by_client(self, client_id: str, ship_id: str) -> Optional[CrewMember]:
        """
        Get crew member associated with a client.

        Args:
            client_id: Client ID
            ship_id: Ship ID

        Returns:
            CrewMember if found, None otherwise
        """
        crew_id = self.client_to_crew.get(client_id)
        if not crew_id:
            return None
        return self.get_crew_member(ship_id, crew_id)

    def get_ship_crew(self, ship_id: str) -> List[CrewMember]:
        """
        Get all crew members on a ship.

        Args:
            ship_id: Ship ID

        Returns:
            List of crew members
        """
        if ship_id not in self.crew:
            return []
        return list(self.crew[ship_id].values())

    def update_crew_fatigue(self, dt: float):
        """
        Update fatigue for all crew members.

        Args:
            dt: Time delta in seconds
        """
        for ship_crew in self.crew.values():
            for crew_member in ship_crew.values():
                crew_member.update_fatigue(dt)

    def get_station_efficiency(
        self,
        ship_id: str,
        client_id: str,
        skill: StationSkill
    ) -> float:
        """
        Get efficiency for a client at a specific skill.

        Args:
            ship_id: Ship ID
            client_id: Client ID
            skill: Skill to check

        Returns:
            Efficiency multiplier (0.1 to 1.0)
        """
        crew_member = self.get_crew_by_client(client_id, ship_id)

        if not crew_member:
            # No crew member assigned, use default competent efficiency
            return 0.5

        return crew_member.get_current_efficiency(skill)
