# hybrid/commands/auto_comms_commands.py
"""Auto-comms commands: enable/disable, policy selection, proposal approval.

Commands:
    enable_auto_comms: Enable automated communications management
    disable_auto_comms: Disable auto-comms system
    set_comms_policy: Set communication policy (open_comms/radio_silence/diplomatic_mode)
    approve_comms: Approve a pending comms proposal
    deny_comms: Deny a pending comms proposal
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec

logger = logging.getLogger(__name__)


def cmd_enable(auto_comms, ship, params):
    """Enable the auto-comms system.

    Args:
        auto_comms: AutoCommsSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Enable confirmation with policy
    """
    return auto_comms._cmd_enable(params)


def cmd_disable(auto_comms, ship, params):
    """Disable the auto-comms system.

    Args:
        auto_comms: AutoCommsSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Disable confirmation
    """
    return auto_comms._cmd_disable(params)


def cmd_set_policy(auto_comms, ship, params):
    """Set communication policy.

    Args:
        auto_comms: AutoCommsSystem instance
        ship: Ship object
        params: Validated parameters with 'policy'

    Returns:
        dict: Updated policy
    """
    return auto_comms._cmd_set_policy(params)


def cmd_approve(auto_comms, ship, params):
    """Approve a pending comms proposal.

    Args:
        auto_comms: AutoCommsSystem instance
        ship: Ship object
        params: Validated parameters with optional 'proposal_id'

    Returns:
        dict: Execution result
    """
    params["_ship"] = ship
    params["event_bus"] = getattr(ship, "event_bus", None)
    return auto_comms._cmd_approve(params)


def cmd_deny(auto_comms, ship, params):
    """Deny a pending comms proposal.

    Args:
        auto_comms: AutoCommsSystem instance
        ship: Ship object
        params: Validated parameters with optional 'proposal_id'

    Returns:
        dict: Denial confirmation
    """
    return auto_comms._cmd_deny(params)


def register_commands(dispatcher):
    """Register all auto-comms commands with the dispatcher."""

    dispatcher.register("enable_auto_comms", CommandSpec(
        handler=cmd_enable,
        args=[],
        help_text="Enable automated communications management (CPU-ASSIST tier)",
        system="auto_comms",
    ))

    dispatcher.register("disable_auto_comms", CommandSpec(
        handler=cmd_disable,
        args=[],
        help_text="Disable auto-comms system",
        system="auto_comms",
    ))

    dispatcher.register("set_comms_policy", CommandSpec(
        handler=cmd_set_policy,
        args=[
            ArgSpec(name="policy", arg_type="str", required=True,
                    description="Communication policy: open_comms, radio_silence, diplomatic_mode"),
        ],
        help_text="Set communication policy for auto-comms",
        system="auto_comms",
    ))

    dispatcher.register("approve_comms", CommandSpec(
        handler=cmd_approve,
        args=[
            ArgSpec(name="proposal_id", arg_type="str", required=False,
                    description="ID of proposal to approve (defaults to first pending)"),
        ],
        help_text="Approve a pending comms proposal",
        system="auto_comms",
    ))

    dispatcher.register("deny_comms", CommandSpec(
        handler=cmd_deny,
        args=[
            ArgSpec(name="proposal_id", arg_type="str", required=False,
                    description="ID of proposal to deny (defaults to first pending)"),
        ],
        help_text="Deny a pending comms proposal",
        system="auto_comms",
    ))
