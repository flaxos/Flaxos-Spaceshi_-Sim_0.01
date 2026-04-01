# hybrid/commands/boarding_commands.py
"""Boarding commands: begin, cancel, and query boarding actions.

Commands:
    begin_boarding:   Initiate boarding of a docked, mission-killed target
    cancel_boarding:  Abort an in-progress boarding action
    boarding_status:  Query current boarding state and progress
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)


def cmd_begin_boarding(boarding, ship, params: dict) -> dict:
    """Start a boarding action against a docked target.

    Preconditions validated inside BoardingSystem.begin_boarding:
    - Must be docked with target
    - Target must be mission-killed
    - Target hull must be > 0

    Args:
        boarding: BoardingSystem instance
        ship: Attacker ship object
        params: Validated params with target_ship_id

    Returns:
        dict: Success or error with reason
    """
    target_id = params.get("target_ship_id")

    # Resolve all_ships from the ship's live reference (CLAUDE.md rule)
    all_ships_ref = getattr(ship, "_all_ships_ref", None)
    if all_ships_ref:
        all_ships = {s.id: s for s in all_ships_ref}
    else:
        all_ships = {}

    return boarding.begin_boarding(target_id, ship, all_ships)


def cmd_cancel_boarding(boarding, ship, params: dict) -> dict:
    """Cancel an in-progress boarding action.

    Args:
        boarding: BoardingSystem instance
        ship: Attacker ship object
        params: Validated params (none required)

    Returns:
        dict: Cancellation result
    """
    return boarding.cancel_boarding()


def cmd_boarding_status(boarding, ship, params: dict) -> dict:
    """Query current boarding system state.

    Args:
        boarding: BoardingSystem instance
        ship: Attacker ship object
        params: Validated params (none required)

    Returns:
        dict: Full boarding state telemetry
    """
    return boarding.get_state()


def register_commands(dispatcher) -> None:
    """Register all boarding commands with the dispatcher."""

    dispatcher.register("begin_boarding", CommandSpec(
        handler=cmd_begin_boarding,
        args=[
            ArgSpec(
                "target_ship_id", "str", required=True,
                description="ID of the ship to board (must be docked and mission-killed)",
            ),
        ],
        help_text="Initiate boarding of a docked, mission-killed target ship",
        system="boarding",
    ))

    dispatcher.register("cancel_boarding", CommandSpec(
        handler=cmd_cancel_boarding,
        args=[],
        help_text="Abort the current boarding action",
        system="boarding",
    ))

    dispatcher.register("boarding_status", CommandSpec(
        handler=cmd_boarding_status,
        args=[],
        help_text="Query boarding system state, progress, and resistance info",
        system="boarding",
    ))
