# hybrid/commands/thermal_commands.py
"""Thermal management commands: cold-drift stealth mode.

Commands:
    cold_drift: Enter emergency cold-drift mode (reactor shutdown, radiator
        retract, coast on battery — nearly invisible but defenseless)
    exit_cold_drift: Exit cold-drift and restart systems
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec

logger = logging.getLogger(__name__)


def cmd_cold_drift(thermal, ship, params):
    """Enter emergency cold-drift mode.

    Shuts down reactor, retracts radiators, kills drive. Ship becomes
    nearly invisible on IR but has no weapons, drive, or active sensors.

    Args:
        thermal: ThermalSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Cold-drift activation result
    """
    return thermal._cmd_cold_drift({
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    })


def cmd_exit_cold_drift(thermal, ship, params):
    """Exit cold-drift mode, restart systems.

    Args:
        thermal: ThermalSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Cold-drift deactivation result
    """
    return thermal._cmd_exit_cold_drift({
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    })


def register_commands(dispatcher):
    """Register thermal management commands with the dispatcher."""

    dispatcher.register("cold_drift", CommandSpec(
        handler=cmd_cold_drift,
        args=[],
        help_text=(
            "Enter emergency cold-drift: reactor scram, radiators retracted, "
            "coast on battery. Nearly invisible on IR but defenseless."
        ),
        system="thermal",
    ))

    dispatcher.register("exit_cold_drift", CommandSpec(
        handler=cmd_exit_cold_drift,
        args=[],
        help_text="Exit cold-drift mode, restart reactor and systems",
        system="thermal",
    ))
