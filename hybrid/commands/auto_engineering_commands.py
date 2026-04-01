# hybrid/commands/auto_engineering_commands.py
"""Auto-engineering commands: enable/disable, mode selection, proposal approval.

Commands:
    enable_auto_engineering: Enable automated engineering management
    disable_auto_engineering: Disable auto-engineering system
    set_engineering_mode: Set auto/manual mode
    approve_engineering: Approve a pending engineering proposal
    deny_engineering: Deny a pending engineering proposal
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec

logger = logging.getLogger(__name__)


def cmd_enable(auto_engineering, ship, params):
    """Enable the auto-engineering system.

    Args:
        auto_engineering: AutoEngineeringSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Enable confirmation with mode
    """
    return auto_engineering._cmd_enable(params)


def cmd_disable(auto_engineering, ship, params):
    """Disable the auto-engineering system.

    Args:
        auto_engineering: AutoEngineeringSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Disable confirmation
    """
    return auto_engineering._cmd_disable(params)


def cmd_set_mode(auto_engineering, ship, params):
    """Set auto-engineering operating mode.

    Args:
        auto_engineering: AutoEngineeringSystem instance
        ship: Ship object
        params: Validated parameters with 'mode'

    Returns:
        dict: Updated mode
    """
    return auto_engineering._cmd_set_mode(params)


def cmd_approve(auto_engineering, ship, params):
    """Approve a pending engineering proposal.

    Args:
        auto_engineering: AutoEngineeringSystem instance
        ship: Ship object
        params: Validated parameters with optional 'proposal_id'

    Returns:
        dict: Execution result
    """
    params["_ship"] = ship
    params["event_bus"] = getattr(ship, "event_bus", None)
    return auto_engineering._cmd_approve(params)


def cmd_deny(auto_engineering, ship, params):
    """Deny a pending engineering proposal.

    Args:
        auto_engineering: AutoEngineeringSystem instance
        ship: Ship object
        params: Validated parameters with optional 'proposal_id'

    Returns:
        dict: Denial confirmation
    """
    return auto_engineering._cmd_deny(params)


def register_commands(dispatcher):
    """Register all auto-engineering commands with the dispatcher."""

    dispatcher.register("enable_auto_engineering", CommandSpec(
        handler=cmd_enable,
        args=[],
        help_text="Enable automated engineering management (CPU-ASSIST tier)",
        system="auto_engineering",
    ))

    dispatcher.register("disable_auto_engineering", CommandSpec(
        handler=cmd_disable,
        args=[],
        help_text="Disable auto-engineering system",
        system="auto_engineering",
    ))

    dispatcher.register("set_engineering_mode", CommandSpec(
        handler=cmd_set_mode,
        args=[
            ArgSpec(name="mode", arg_type="str", required=True,
                    description="Operating mode: auto or manual"),
        ],
        help_text="Set auto-engineering operating mode (auto=execute after timeout, manual=wait for approval)",
        system="auto_engineering",
    ))

    dispatcher.register("approve_engineering", CommandSpec(
        handler=cmd_approve,
        args=[
            ArgSpec(name="proposal_id", arg_type="str", required=False,
                    description="ID of proposal to approve (defaults to first pending)"),
        ],
        help_text="Approve a pending engineering proposal",
        system="auto_engineering",
    ))

    dispatcher.register("deny_engineering", CommandSpec(
        handler=cmd_deny,
        args=[
            ArgSpec(name="proposal_id", arg_type="str", required=False,
                    description="ID of proposal to deny (defaults to first pending)"),
        ],
        help_text="Deny a pending engineering proposal",
        system="auto_engineering",
    ))
