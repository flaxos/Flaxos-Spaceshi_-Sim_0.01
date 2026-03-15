# hybrid/commands/crew_commands.py
"""Crew fatigue management commands.

Commands:
    crew_rest: Order crew to rest stations (accelerated fatigue recovery)
    cancel_rest: Cancel rest order, crew returns to duty
    crew_fatigue_status: Detailed crew fatigue and performance report
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)


def cmd_crew_rest(crew_fatigue, ship, params):
    """Order crew to rest stations for fatigue recovery.

    Args:
        crew_fatigue: CrewFatigueSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Rest order confirmation or error if under g-load
    """
    return crew_fatigue._cmd_crew_rest(params)


def cmd_cancel_rest(crew_fatigue, ship, params):
    """Cancel crew rest order, return to duty stations.

    Args:
        crew_fatigue: CrewFatigueSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Cancellation confirmation
    """
    return crew_fatigue._cmd_cancel_rest(params)


def cmd_crew_fatigue_status(crew_fatigue, ship, params):
    """Get detailed crew fatigue and performance report.

    Args:
        crew_fatigue: CrewFatigueSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Full crew fatigue status with per-station performance
    """
    return crew_fatigue._cmd_crew_status(params)


def register_commands(dispatcher):
    """Register all crew fatigue commands with the dispatcher."""

    dispatcher.register("crew_rest", CommandSpec(
        handler=cmd_crew_rest,
        args=[],
        help_text="Order crew to rest stations for accelerated fatigue recovery "
                  "(requires low-g conditions)",
        system="crew_fatigue",
    ))

    dispatcher.register("cancel_rest", CommandSpec(
        handler=cmd_cancel_rest,
        args=[],
        help_text="Cancel crew rest order, return crew to duty stations",
        system="crew_fatigue",
    ))

    dispatcher.register("crew_fatigue_status", CommandSpec(
        handler=cmd_crew_fatigue_status,
        args=[],
        help_text="Detailed crew fatigue report with per-station performance",
        system="crew_fatigue",
    ))
