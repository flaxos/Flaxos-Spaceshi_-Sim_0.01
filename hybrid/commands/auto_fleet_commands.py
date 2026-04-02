# hybrid/commands/auto_fleet_commands.py
"""Auto-fleet commands: enable/disable, mode, proposal approval.

Commands:
    enable_auto_fleet: Enable automated fleet management proposals
    disable_auto_fleet: Disable auto-fleet system
    set_fleet_auto_mode: Set operating mode (auto/manual)
    approve_fleet: Approve a pending fleet proposal
    deny_fleet: Deny a pending fleet proposal
    auto_fleet_status: Get auto-fleet system status
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec

logger = logging.getLogger(__name__)


def cmd_enable(auto_fleet, ship, params):
    """Enable the auto-fleet system.

    Args:
        auto_fleet: AutoFleetSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Enable confirmation with operating mode
    """
    return auto_fleet._cmd_enable(params)


def cmd_disable(auto_fleet, ship, params):
    """Disable the auto-fleet system.

    Args:
        auto_fleet: AutoFleetSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Disable confirmation
    """
    return auto_fleet._cmd_disable(params)


def cmd_set_mode(auto_fleet, ship, params):
    """Set auto-fleet operating mode.

    Args:
        auto_fleet: AutoFleetSystem instance
        ship: Ship object
        params: Validated parameters with 'mode'

    Returns:
        dict: Updated operating mode
    """
    return auto_fleet._cmd_set_mode(params)


def cmd_approve(auto_fleet, ship, params):
    """Approve a pending fleet proposal.

    Args:
        auto_fleet: AutoFleetSystem instance
        ship: Ship object
        params: Validated parameters with optional 'proposal_id'

    Returns:
        dict: Execution result
    """
    params["_ship"] = ship
    params["event_bus"] = getattr(ship, "event_bus", None)
    return auto_fleet._cmd_approve(params)


def cmd_deny(auto_fleet, ship, params):
    """Deny a pending fleet proposal.

    Args:
        auto_fleet: AutoFleetSystem instance
        ship: Ship object
        params: Validated parameters with optional 'proposal_id'

    Returns:
        dict: Denial confirmation
    """
    return auto_fleet._cmd_deny(params)


def cmd_status(auto_fleet, ship, params):
    """Get auto-fleet system status.

    Args:
        auto_fleet: AutoFleetSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Current status and proposals
    """
    return auto_fleet._cmd_status(params)


def register_commands(dispatcher):
    """Register all auto-fleet commands with the dispatcher."""

    dispatcher.register("enable_auto_fleet", CommandSpec(
        handler=cmd_enable,
        args=[],
        help_text="Enable automated fleet management proposals (CPU-ASSIST tier)",
        system="auto_fleet",
    ))

    dispatcher.register("disable_auto_fleet", CommandSpec(
        handler=cmd_disable,
        args=[],
        help_text="Disable auto-fleet system",
        system="auto_fleet",
    ))

    dispatcher.register("set_fleet_auto_mode", CommandSpec(
        handler=cmd_set_mode,
        args=[
            ArgSpec(name="mode", arg_type="str", required=True,
                    description="Operating mode: auto, manual"),
        ],
        help_text="Set auto-fleet operating mode (auto proposals execute after timeout, manual waits for approval)",
        system="auto_fleet",
    ))

    dispatcher.register("approve_fleet", CommandSpec(
        handler=cmd_approve,
        args=[
            ArgSpec(name="proposal_id", arg_type="str", required=False,
                    description="ID of proposal to approve (defaults to first pending)"),
        ],
        help_text="Approve a pending fleet management proposal",
        system="auto_fleet",
    ))

    dispatcher.register("deny_fleet", CommandSpec(
        handler=cmd_deny,
        args=[
            ArgSpec(name="proposal_id", arg_type="str", required=False,
                    description="ID of proposal to deny (defaults to first pending)"),
        ],
        help_text="Deny a pending fleet management proposal",
        system="auto_fleet",
    ))

    dispatcher.register("auto_fleet_status", CommandSpec(
        handler=cmd_status,
        args=[],
        help_text="Get auto-fleet system status and pending proposals",
        system="auto_fleet",
    ))
