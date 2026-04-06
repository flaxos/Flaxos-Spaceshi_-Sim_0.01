"""
Crew progression constants and XP advancement logic.

Extracted from crew_system.py to keep module sizes manageable.
These types and functions are the core of the Phase 4D progression
system: injury states, XP thresholds, and skill advancement.

Imported by crew_system.py (CrewMember uses these) and crew_damage.py.
"""

from __future__ import annotations

import logging
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class InjuryState:
    """Crew injury states with defined severity ladder.

    The progression is one-way under fire: each subsequent hit while
    already injured escalates the state. Recovery only happens between
    missions (WOUNDED) or at a medical facility (CRITICAL).
    """
    HEALTHY = "healthy"
    WOUNDED = "wounded"    # 50% efficiency penalty
    CRITICAL = "critical"  # Cannot be assigned to stations
    DEAD = "dead"          # Permanently removed from roster


# XP thresholds for each skill level transition.
# Key = current SkillLevel value, value = XP needed to advance.
XP_THRESHOLDS: Dict[int, int] = {
    1: 100,    # NOVICE -> TRAINEE
    2: 300,    # TRAINEE -> COMPETENT
    3: 600,    # COMPETENT -> SKILLED
    4: 1000,   # SKILLED -> EXPERT
    5: 2000,   # EXPERT -> MASTER
}


def try_advance_skill(
    crew_member,
    skill_name: str,
) -> bool:
    """Check if accumulated XP crosses the threshold for level-up.

    Operates on a CrewMember instance (duck-typed to avoid circular
    imports). Reads crew_member.skills, crew_member.experience.

    Args:
        crew_member: CrewMember-like object with skills and experience attrs.
        skill_name: Name of the skill to check.

    Returns:
        True if the skill advanced.
    """
    from .crew_system import StationSkill, SkillLevel

    try:
        skill_enum = StationSkill(skill_name)
    except ValueError:
        return False

    current_level = crew_member.skills.get_skill(skill_enum)
    if current_level >= 6:
        return False

    threshold = XP_THRESHOLDS.get(current_level)
    if threshold is None:
        return False

    xp = crew_member.experience.get(skill_name, 0)
    if xp >= threshold:
        new_level = current_level + 1
        crew_member.skills.set_skill(skill_enum, new_level)
        level_name = SkillLevel(new_level).name
        logger.info(
            f"{crew_member.name} advanced {skill_name} to {level_name} "
            f"(level {new_level}, XP={xp}/{threshold})"
        )
        return True
    return False


def check_all_advancements(crew_member) -> List[str]:
    """Check all skills for possible level-ups from accumulated XP.

    Args:
        crew_member: CrewMember-like object.

    Returns:
        List of skill names that advanced.
    """
    from .crew_system import StationSkill

    advanced = []
    for skill in StationSkill:
        skill_name = skill.value
        if skill_name in crew_member.experience:
            if try_advance_skill(crew_member, skill_name):
                advanced.append(skill_name)
    return advanced
