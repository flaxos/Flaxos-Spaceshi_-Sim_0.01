# hybrid/commands/comms_commands.py
"""Comms station commands: IFF transponder, hailing, broadcast, distress.

Commands:
    set_transponder: Enable/disable transponder, set IFF code (spoof)
    hail_contact: Hail a specific contact with optional message
    broadcast_message: Broadcast on a radio channel
    set_distress: Activate/deactivate distress beacon
    comms_status: Full comms system readout
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)


def cmd_set_transponder(comms, ship, params):
    """Set IFF transponder state, code, and spoofing.

    Args:
        comms: CommsSystem instance
        ship: Ship object
        params: Validated parameters (enabled, code, spoofed,
                declared_class, declared_faction)

    Returns:
        dict: Transponder state change result
    """
    cmd_params = {
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    }
    for key in ("enabled", "code", "spoofed", "declared_class", "declared_faction"):
        if key in params:
            cmd_params[key] = params[key]
    return comms._cmd_set_transponder(cmd_params)


def cmd_hail_contact(comms, ship, params):
    """Hail a specific contact.

    Args:
        comms: CommsSystem instance
        ship: Ship object
        params: Validated parameters (target, message)

    Returns:
        dict: Hail result with propagation delay
    """
    cmd_params = {
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    }
    if "target" in params:
        cmd_params["target"] = params["target"]
    if "message" in params:
        cmd_params["message"] = params["message"]
    return comms._cmd_hail_contact(cmd_params)


def cmd_broadcast_message(comms, ship, params):
    """Broadcast a radio message.

    Args:
        comms: CommsSystem instance
        ship: Ship object
        params: Validated parameters (message, channel)

    Returns:
        dict: Broadcast result
    """
    cmd_params = {
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    }
    if "message" in params:
        cmd_params["message"] = params["message"]
    if "channel" in params:
        cmd_params["channel"] = params["channel"]
    return comms._cmd_broadcast_message(cmd_params)


def cmd_set_distress(comms, ship, params):
    """Activate or deactivate distress beacon.

    Args:
        comms: CommsSystem instance
        ship: Ship object
        params: Validated parameters (enabled)

    Returns:
        dict: Distress beacon state change result
    """
    cmd_params = {
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    }
    if "enabled" in params:
        cmd_params["enabled"] = params["enabled"]
    return comms._cmd_set_distress(cmd_params)


def cmd_comms_status(comms, ship, params):
    """Full comms system readout.

    Args:
        comms: CommsSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Complete comms status
    """
    state = comms.get_state()
    state["ok"] = True
    return state


def register_commands(dispatcher):
    """Register all comms commands with the dispatcher."""

    dispatcher.register("set_transponder", CommandSpec(
        handler=cmd_set_transponder,
        args=[
            ArgSpec("enabled", "bool", required=False,
                    description="True to enable transponder, False to disable"),
            ArgSpec("code", "str", required=False,
                    description="IFF code to broadcast (can be spoofed)"),
            ArgSpec("spoofed", "bool", required=False,
                    description="True to broadcast false identity"),
            ArgSpec("declared_class", "str", required=False,
                    description="False ship class to broadcast when spoofed"),
            ArgSpec("declared_faction", "str", required=False,
                    description="False faction to broadcast when spoofed"),
        ],
        help_text="Set IFF transponder state, identity code, and spoofing",
        system="comms",
    ))

    dispatcher.register("hail_contact", CommandSpec(
        handler=cmd_hail_contact,
        args=[
            ArgSpec("target", "str", required=True,
                    description="Contact ID or ship name to hail"),
            ArgSpec("message", "str", required=False,
                    description="Message to include in hail"),
        ],
        help_text="Hail a specific contact (speed-of-light delay applies)",
        system="comms",
    ))

    dispatcher.register("broadcast_message", CommandSpec(
        handler=cmd_broadcast_message,
        args=[
            ArgSpec("message", "str", required=True,
                    description="Message to broadcast"),
            ArgSpec("channel", "str", required=False,
                    description="Radio channel (default: GUARD)"),
        ],
        help_text="Broadcast a radio message on a channel",
        system="comms",
    ))

    dispatcher.register("set_distress", CommandSpec(
        handler=cmd_set_distress,
        args=[
            ArgSpec("enabled", "bool", required=False,
                    description="True to activate distress, False to cancel (toggles if omitted)"),
        ],
        help_text="Activate or deactivate emergency distress beacon",
        system="comms",
    ))

    dispatcher.register("comms_status", CommandSpec(
        handler=cmd_comms_status,
        args=[],
        help_text="Full communications system status readout",
        system="comms",
    ))
