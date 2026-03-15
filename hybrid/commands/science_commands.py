# hybrid/commands/science_commands.py
"""Science station commands: contact analysis, spectral analysis, mass estimation,
threat assessment.

Commands:
    analyze_contact: Deep sensor analysis of a tracked contact
    spectral_analysis: Emission signature breakdown (IR, RCS, drive type)
    estimate_mass: Mass estimation from RCS and observed acceleration
    assess_threat: Tactical threat evaluation
    science_status: Science system status readout
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)


def cmd_analyze_contact(science, ship, params):
    """Deep sensor analysis of a tracked contact.

    Args:
        science: ScienceSystem instance
        ship: Ship object
        params: Validated parameters with 'contact_id'

    Returns:
        dict: Contact analysis result
    """
    return science._cmd_analyze_contact({
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
        "contact_id": params.get("contact_id"),
        "all_ships": getattr(ship, "_all_ships_ref", None),
    })


def cmd_spectral_analysis(science, ship, params):
    """Analyze emission signature to identify drive type and thermal state.

    Args:
        science: ScienceSystem instance
        ship: Ship object
        params: Validated parameters with 'contact_id'

    Returns:
        dict: Spectral analysis result
    """
    return science._cmd_spectral_analysis({
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
        "contact_id": params.get("contact_id"),
        "all_ships": getattr(ship, "_all_ships_ref", None),
    })


def cmd_estimate_mass(science, ship, params):
    """Estimate target mass from RCS and observed acceleration.

    Args:
        science: ScienceSystem instance
        ship: Ship object
        params: Validated parameters with 'contact_id'

    Returns:
        dict: Mass estimation result
    """
    return science._cmd_estimate_mass({
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
        "contact_id": params.get("contact_id"),
        "all_ships": getattr(ship, "_all_ships_ref", None),
    })


def cmd_assess_threat(science, ship, params):
    """Evaluate target as tactical threat.

    Args:
        science: ScienceSystem instance
        ship: Ship object
        params: Validated parameters with 'contact_id'

    Returns:
        dict: Threat assessment result
    """
    return science._cmd_assess_threat({
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
        "contact_id": params.get("contact_id"),
        "all_ships": getattr(ship, "_all_ships_ref", None),
    })


def cmd_science_status(science, ship, params):
    """Science system status readout.

    Args:
        science: ScienceSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Science system status
    """
    return science._cmd_science_status({
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    })


def register_commands(dispatcher):
    """Register all science commands with the dispatcher."""

    dispatcher.register("analyze_contact", CommandSpec(
        handler=cmd_analyze_contact,
        args=[
            ArgSpec("contact_id", "str", required=True,
                    description="Contact ID to analyze (e.g. C001)"),
        ],
        help_text="Deep sensor analysis of a tracked contact",
        system="science",
    ))

    dispatcher.register("spectral_analysis", CommandSpec(
        handler=cmd_spectral_analysis,
        args=[
            ArgSpec("contact_id", "str", required=True,
                    description="Contact ID for spectral analysis"),
        ],
        help_text="Analyze emission signature to identify drive type and thermal state",
        system="science",
    ))

    dispatcher.register("estimate_mass", CommandSpec(
        handler=cmd_estimate_mass,
        args=[
            ArgSpec("contact_id", "str", required=True,
                    description="Contact ID to estimate mass for"),
        ],
        help_text="Estimate target mass from RCS and observed acceleration (F=ma)",
        system="science",
    ))

    dispatcher.register("assess_threat", CommandSpec(
        handler=cmd_assess_threat,
        args=[
            ArgSpec("contact_id", "str", required=True,
                    description="Contact ID to assess threat level"),
        ],
        help_text="Evaluate target as tactical threat based on weapons, armor, and geometry",
        system="science",
    ))

    dispatcher.register("science_status", CommandSpec(
        handler=cmd_science_status,
        args=[],
        help_text="Science system status readout",
        system="science",
    ))
