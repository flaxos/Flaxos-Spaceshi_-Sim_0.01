# hybrid/navigation/autopilot/factory.py
"""Factory for creating autopilot instances."""

import logging
from typing import Dict, Optional
from hybrid.navigation.autopilot.base import BaseAutopilot
from hybrid.navigation.autopilot.match_velocity import MatchVelocityAutopilot
from hybrid.navigation.autopilot.intercept import InterceptAutopilot
from hybrid.navigation.autopilot.hold import HoldPositionAutopilot, HoldVelocityAutopilot
from hybrid.navigation.autopilot.formation import FormationAutopilot, EchelonFormationAutopilot

logger = logging.getLogger(__name__)

class AutopilotFactory:
    """Factory for creating autopilot program instances."""

    # Registry of available autopilot programs
    PROGRAMS = {
        "match": MatchVelocityAutopilot,
        "match_velocity": MatchVelocityAutopilot,
        "intercept": InterceptAutopilot,
        "approach": InterceptAutopilot,  # Alias for intercept
        "hold": HoldPositionAutopilot,
        "hold_position": HoldPositionAutopilot,
        "hold_velocity": HoldVelocityAutopilot,
        "cruise": HoldVelocityAutopilot,  # Alias
        "formation": FormationAutopilot,
        "formation_keeping": FormationAutopilot,  # Alias
        "echelon": EchelonFormationAutopilot,
        "off": None  # Disengage autopilot
    }

    @classmethod
    def create(cls, program_name: str, ship, target_id: Optional[str] = None,
               params: Dict = None) -> BaseAutopilot:
        """Create an autopilot instance.

        Args:
            program_name: Name of autopilot program
            ship: Ship to control
            target_id: Target contact ID (if required)
            params: Additional parameters

        Returns:
            BaseAutopilot: Autopilot instance

        Raises:
            ValueError: If program name is unknown
        """
        program_name_lower = program_name.lower()

        if program_name_lower not in cls.PROGRAMS:
            available = ", ".join(cls.PROGRAMS.keys())
            raise ValueError(
                f"Unknown autopilot program: '{program_name}'. "
                f"Available: {available}"
            )

        if program_name_lower == "off":
            # Special case: return None to disengage
            return None

        autopilot_class = cls.PROGRAMS[program_name_lower]

        # Create instance
        instance = autopilot_class(ship, target_id, params)

        logger.info(
            f"Created autopilot: {program_name} for ship {ship.id} "
            f"(target: {target_id})"
        )

        return instance

    @classmethod
    def list_programs(cls) -> list:
        """Get list of available autopilot programs.

        Returns:
            list: Program names
        """
        return list(cls.PROGRAMS.keys())

    @classmethod
    def get_help(cls, program_name: Optional[str] = None) -> str:
        """Get help text for autopilot programs.

        Args:
            program_name: Specific program or None for all

        Returns:
            str: Help text
        """
        help_text = {
            "match": "Match velocity with target (zero relative velocity)",
            "intercept": "Intercept moving target using lead pursuit",
            "hold": "Hold current position (station-keeping)",
            "hold_velocity": "Hold current velocity (cruise control)",
            "formation": "Maintain position in fleet formation",
            "echelon": "Formation keeping with collision avoidance",
            "off": "Disengage autopilot"
        }

        if program_name:
            return help_text.get(program_name.lower(), "Unknown program")

        lines = ["Available autopilot programs:"]
        for name in sorted(help_text.keys()):
            lines.append(f"  {name}: {help_text[name]}")

        return "\n".join(lines)
