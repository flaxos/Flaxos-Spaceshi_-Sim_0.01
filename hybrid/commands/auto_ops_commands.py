# hybrid/commands/auto_ops_commands.py
"""Auto-ops commands: enable/disable, mode selection, proposal approval.

Commands:
    enable_auto_ops: Enable automated ops management
    disable_auto_ops: Disable auto-ops system
    set_ops_mode: Set auto/manual mode
    approve_ops: Approve a pending ops proposal
    deny_ops: Deny a pending ops proposal
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec

logger = logging.getLogger(__name__)


def cmd_enable(auto_ops, ship, params):
    """Enable the auto-ops system.

    Args:
        auto_ops: AutoOpsSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Enable confirmation with mode
    """
    return auto_ops._cmd_enable(params)


def cmd_disable(auto_ops, ship, params):
    """Disable the auto-ops system.

    Args:
        auto_ops: AutoOpsSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Disable confirmation
    """
    return auto_ops._cmd_disable(params)


def cmd_set_mode(auto_ops, ship, params):
    """Set auto-ops operating mode.

    Args:
        auto_ops: AutoOpsSystem instance
        ship: Ship object
        params: Validated parameters with 'mode'

    Returns:
        dict: Updated mode
    """
    return auto_ops._cmd_set_mode(params)


def cmd_approve(auto_ops, ship, params):
    """Approve a pending ops proposal.

    Args:
        auto_ops: AutoOpsSystem instance
        ship: Ship object
        params: Validated parameters with optional 'proposal_id'

    Returns:
        dict: Execution result
    """
    params["_ship"] = ship
    params["event_bus"] = getattr(ship, "event_bus", None)
    return auto_ops._cmd_approve(params)


def cmd_deny(auto_ops, ship, params):
    """Deny a pending ops proposal.

    Args:
        auto_ops: AutoOpsSystem instance
        ship: Ship object
        params: Validated parameters with optional 'proposal_id'

    Returns:
        dict: Denial confirmation
    """
    return auto_ops._cmd_deny(params)


def register_commands(dispatcher):
    """Register all auto-ops commands with the dispatcher."""

    dispatcher.register("enable_auto_ops", CommandSpec(
        handler=cmd_enable,
        args=[],
        help_text="Enable automated ops management (CPU-ASSIST tier)",
        system="auto_ops",
    ))

    dispatcher.register("disable_auto_ops", CommandSpec(
        handler=cmd_disable,
        args=[],
        help_text="Disable auto-ops system",
        system="auto_ops",
    ))

    dispatcher.register("set_ops_mode", CommandSpec(
        handler=cmd_set_mode,
        args=[
            ArgSpec(name="mode", arg_type="str", required=True,
                    description="Operating mode: auto or manual"),
        ],
        help_text="Set auto-ops operating mode (auto=execute after timeout, manual=wait for approval)",
        system="auto_ops",
    ))

    dispatcher.register("approve_ops", CommandSpec(
        handler=cmd_approve,
        args=[
            ArgSpec(name="proposal_id", arg_type="str", required=False,
                    description="ID of proposal to approve (defaults to first pending)"),
        ],
        help_text="Approve a pending ops proposal",
        system="auto_ops",
    ))

    dispatcher.register("deny_ops", CommandSpec(
        handler=cmd_deny,
        args=[
            ArgSpec(name="proposal_id", arg_type="str", required=False,
                    description="ID of proposal to deny (defaults to first pending)"),
        ],
        help_text="Deny a pending ops proposal",
        system="auto_ops",
    ))
