# hybrid/commands/ecm_commands.py
"""ECM station commands: jamming, chaff, flares, EMCON.

Commands:
    activate_jammer: Enable radar noise jamming
    deactivate_jammer: Disable radar jammer
    deploy_chaff: Launch radar-reflective chaff bundle
    deploy_flare: Launch IR decoy flare
    set_emcon: Toggle emissions control mode
    ecm_status: Full ECM system readout
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)


def cmd_activate_jammer(ecm, ship, params):
    """Enable radar noise jammer.

    Args:
        ecm: ECMSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Jammer activation result
    """
    return ecm._cmd_activate_jammer({
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    })


def cmd_deactivate_jammer(ecm, ship, params):
    """Disable radar noise jammer.

    Args:
        ecm: ECMSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Jammer deactivation result
    """
    return ecm._cmd_deactivate_jammer({
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    })


def cmd_deploy_chaff(ecm, ship, params):
    """Deploy radar-reflective chaff bundle.

    Args:
        ecm: ECMSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Chaff deployment result
    """
    return ecm._cmd_deploy_chaff({
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    })


def cmd_deploy_flare(ecm, ship, params):
    """Deploy IR decoy flare.

    Args:
        ecm: ECMSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Flare deployment result
    """
    return ecm._cmd_deploy_flare({
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    })


def cmd_set_emcon(ecm, ship, params):
    """Toggle emissions control mode.

    Args:
        ecm: ECMSystem instance
        ship: Ship object
        params: Validated parameters with optional 'enabled' bool

    Returns:
        dict: EMCON state change result
    """
    cmd_params = {
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    }
    if "enabled" in params:
        cmd_params["enabled"] = params["enabled"]
    return ecm._cmd_set_emcon(cmd_params)


def cmd_ecm_status(ecm, ship, params):
    """Full ECM system readout.

    Args:
        ecm: ECMSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Complete ECM status
    """
    state = ecm.get_state()
    state["ok"] = True
    return state


def register_commands(dispatcher):
    """Register all ECM commands with the dispatcher."""

    dispatcher.register("activate_jammer", CommandSpec(
        handler=cmd_activate_jammer,
        args=[],
        help_text="Enable radar noise jammer to degrade enemy radar detection",
        system="ecm",
    ))

    dispatcher.register("deactivate_jammer", CommandSpec(
        handler=cmd_deactivate_jammer,
        args=[],
        help_text="Disable radar noise jammer",
        system="ecm",
    ))

    dispatcher.register("deploy_chaff", CommandSpec(
        handler=cmd_deploy_chaff,
        args=[],
        help_text="Launch radar-reflective chaff bundle (creates false radar returns)",
        system="ecm",
    ))

    dispatcher.register("deploy_flare", CommandSpec(
        handler=cmd_deploy_flare,
        args=[],
        help_text="Launch IR decoy flare (diverts passive IR tracking)",
        system="ecm",
    ))

    dispatcher.register("set_emcon", CommandSpec(
        handler=cmd_set_emcon,
        args=[
            ArgSpec("enabled", "bool", required=False,
                    description="True to enable EMCON, False to disable (toggles if omitted)"),
        ],
        help_text="Toggle emissions control mode (reduce own signature, disable active sensors)",
        system="ecm",
    ))

    dispatcher.register("ecm_status", CommandSpec(
        handler=cmd_ecm_status,
        args=[],
        help_text="Full ECM system status readout",
        system="ecm",
    ))
