# hybrid/commands/auto_tactical_commands.py
"""Auto-tactical commands: enable/disable, engagement rules, proposal approval.

Commands:
    enable_auto_tactical: Enable automated targeting and fire proposals
    disable_auto_tactical: Disable auto-tactical system
    set_engagement_rules: Set engagement mode (weapons_free/hold/defensive_only)
    approve_tactical: Approve a pending fire proposal
    deny_tactical: Deny a pending fire proposal
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec

logger = logging.getLogger(__name__)


def cmd_enable(auto_tactical, ship, params):
    """Enable the auto-tactical system.

    Args:
        auto_tactical: AutoTacticalSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Enable confirmation with engagement mode
    """
    return auto_tactical._cmd_enable(params)


def cmd_disable(auto_tactical, ship, params):
    """Disable the auto-tactical system.

    Args:
        auto_tactical: AutoTacticalSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Disable confirmation
    """
    return auto_tactical._cmd_disable(params)


def cmd_set_engagement_rules(auto_tactical, ship, params):
    """Set engagement rules mode.

    Args:
        auto_tactical: AutoTacticalSystem instance
        ship: Ship object
        params: Validated parameters with 'mode'

    Returns:
        dict: Updated engagement mode
    """
    return auto_tactical._cmd_set_engagement_rules(params)


def cmd_approve(auto_tactical, ship, params):
    """Approve a pending tactical proposal.

    Args:
        auto_tactical: AutoTacticalSystem instance
        ship: Ship object
        params: Validated parameters with optional 'proposal_id'

    Returns:
        dict: Execution result
    """
    params["_ship"] = ship
    params["event_bus"] = getattr(ship, "event_bus", None)
    return auto_tactical._cmd_approve(params)


def cmd_deny(auto_tactical, ship, params):
    """Deny a pending tactical proposal.

    Args:
        auto_tactical: AutoTacticalSystem instance
        ship: Ship object
        params: Validated parameters with optional 'proposal_id'

    Returns:
        dict: Denial confirmation
    """
    return auto_tactical._cmd_deny(params)


def register_commands(dispatcher):
    """Register all auto-tactical commands with the dispatcher."""

    dispatcher.register("enable_auto_tactical", CommandSpec(
        handler=cmd_enable,
        args=[],
        help_text="Enable automated targeting and fire proposals (CPU-ASSIST tier)",
        system="auto_tactical",
    ))

    dispatcher.register("disable_auto_tactical", CommandSpec(
        handler=cmd_disable,
        args=[],
        help_text="Disable auto-tactical system",
        system="auto_tactical",
    ))

    dispatcher.register("set_engagement_rules", CommandSpec(
        handler=cmd_set_engagement_rules,
        args=[
            ArgSpec(name="mode", arg_type="str", required=True,
                    description="Engagement mode: weapons_free, weapons_hold, defensive_only"),
        ],
        help_text="Set rules of engagement for auto-tactical",
        system="auto_tactical",
    ))

    dispatcher.register("approve_tactical", CommandSpec(
        handler=cmd_approve,
        args=[
            ArgSpec(name="proposal_id", arg_type="str", required=False,
                    description="ID of proposal to approve (defaults to first pending)"),
        ],
        help_text="Approve a pending tactical fire proposal",
        system="auto_tactical",
    ))

    dispatcher.register("deny_tactical", CommandSpec(
        handler=cmd_deny,
        args=[
            ArgSpec(name="proposal_id", arg_type="str", required=False,
                    description="ID of proposal to deny (defaults to first pending)"),
        ],
        help_text="Deny a pending tactical fire proposal",
        system="auto_tactical",
    ))
