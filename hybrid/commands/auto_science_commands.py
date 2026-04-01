# hybrid/commands/auto_science_commands.py
"""Auto-science commands: enable/disable, mode selection, proposal approval.

Commands:
    enable_auto_science: Enable automated science analysis
    disable_auto_science: Disable auto-science system
    set_science_mode: Set auto/manual mode
    approve_science: Approve a pending science proposal
    deny_science: Deny a pending science proposal
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec

logger = logging.getLogger(__name__)


def cmd_enable(auto_science, ship, params):
    """Enable the auto-science system.

    Args:
        auto_science: AutoScienceSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Enable confirmation with mode
    """
    return auto_science._cmd_enable(params)


def cmd_disable(auto_science, ship, params):
    """Disable the auto-science system.

    Args:
        auto_science: AutoScienceSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Disable confirmation
    """
    return auto_science._cmd_disable(params)


def cmd_set_mode(auto_science, ship, params):
    """Set auto-science operating mode.

    Args:
        auto_science: AutoScienceSystem instance
        ship: Ship object
        params: Validated parameters with 'mode'

    Returns:
        dict: Updated mode
    """
    return auto_science._cmd_set_mode(params)


def cmd_approve(auto_science, ship, params):
    """Approve a pending science proposal.

    Args:
        auto_science: AutoScienceSystem instance
        ship: Ship object
        params: Validated parameters with optional 'proposal_id'

    Returns:
        dict: Execution result
    """
    params["_ship"] = ship
    params["event_bus"] = getattr(ship, "event_bus", None)
    return auto_science._cmd_approve(params)


def cmd_deny(auto_science, ship, params):
    """Deny a pending science proposal.

    Args:
        auto_science: AutoScienceSystem instance
        ship: Ship object
        params: Validated parameters with optional 'proposal_id'

    Returns:
        dict: Denial confirmation
    """
    return auto_science._cmd_deny(params)


def register_commands(dispatcher):
    """Register all auto-science commands with the dispatcher."""

    dispatcher.register("enable_auto_science", CommandSpec(
        handler=cmd_enable,
        args=[],
        help_text="Enable automated science analysis (CPU-ASSIST tier)",
        system="auto_science",
    ))

    dispatcher.register("disable_auto_science", CommandSpec(
        handler=cmd_disable,
        args=[],
        help_text="Disable auto-science system",
        system="auto_science",
    ))

    dispatcher.register("set_science_mode", CommandSpec(
        handler=cmd_set_mode,
        args=[
            ArgSpec(name="mode", arg_type="str", required=True,
                    description="Operating mode: auto or manual"),
        ],
        help_text="Set auto-science operating mode (auto=execute after timeout, manual=wait for approval)",
        system="auto_science",
    ))

    dispatcher.register("approve_science", CommandSpec(
        handler=cmd_approve,
        args=[
            ArgSpec(name="proposal_id", arg_type="str", required=False,
                    description="ID of proposal to approve (defaults to first pending)"),
        ],
        help_text="Approve a pending science proposal",
        system="auto_science",
    ))

    dispatcher.register("deny_science", CommandSpec(
        handler=cmd_deny,
        args=[
            ArgSpec(name="proposal_id", arg_type="str", required=False,
                    description="ID of proposal to deny (defaults to first pending)"),
        ],
        help_text="Deny a pending science proposal",
        system="auto_science",
    ))
