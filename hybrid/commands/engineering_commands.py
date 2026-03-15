# hybrid/commands/engineering_commands.py
"""Engineering station commands: reactor control, drive management, radiators, fuel, emergency vent.

Commands:
    set_reactor_output: Adjust reactor power generation level (0-100%)
    throttle_drive: Set drive output percentage (cap on helm throttle)
    manage_radiators: Extend/retract radiator panels, set dissipation priority
    monitor_fuel: Track reaction mass remaining, burn rate, delta-v budget
    emergency_vent: Dump heat rapidly by venting coolant (one-time use)
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec

logger = logging.getLogger(__name__)


def cmd_set_reactor_output(engineering, ship, params):
    """Adjust reactor power generation level.

    Args:
        engineering: EngineeringSystem instance
        ship: Ship object
        params: Validated parameters with output value

    Returns:
        dict: Updated reactor output status
    """
    return engineering._cmd_set_reactor_output({
        "output": params.get("output"),
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    })


def cmd_throttle_drive(engineering, ship, params):
    """Set drive output percentage (cap on helm throttle).

    Args:
        engineering: EngineeringSystem instance
        ship: Ship object
        params: Validated parameters with limit value

    Returns:
        dict: Updated drive limit status
    """
    return engineering._cmd_throttle_drive({
        "limit": params.get("limit"),
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    })


def cmd_manage_radiators(engineering, ship, params):
    """Manage radiator panels: deploy/retract and set priority.

    Args:
        engineering: EngineeringSystem instance
        ship: Ship object
        params: Validated parameters with deployed and/or priority

    Returns:
        dict: Updated radiator state
    """
    cmd_params = {
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    }
    if "deployed" in params and params["deployed"] is not None:
        cmd_params["deployed"] = params["deployed"]
    if "priority" in params and params["priority"] is not None:
        cmd_params["priority"] = params["priority"]

    return engineering._cmd_manage_radiators(cmd_params)


def cmd_monitor_fuel(engineering, ship, params):
    """Track reaction mass remaining, burn rate, delta-v budget.

    Args:
        engineering: EngineeringSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Comprehensive fuel status
    """
    return engineering._cmd_monitor_fuel({"_ship": ship})


def cmd_emergency_vent(engineering, ship, params):
    """Dump heat rapidly by venting coolant (one-time use).

    Args:
        engineering: EngineeringSystem instance
        ship: Ship object
        params: Validated parameters with confirm flag

    Returns:
        dict: Vent activation result
    """
    confirm = params.get("confirm", False)
    if not confirm:
        return {
            "ok": False,
            "error": "Emergency vent is irreversible. Pass confirm=true to activate.",
            "warning": "This will permanently deplete coolant reserves.",
        }

    return engineering._cmd_emergency_vent({
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    })


def register_commands(dispatcher):
    """Register all engineering commands with the dispatcher."""

    dispatcher.register("set_reactor_output", CommandSpec(
        handler=cmd_set_reactor_output,
        args=[
            ArgSpec("output", "float", required=True,
                    min_val=0.0, max_val=100.0,
                    description="Reactor output (0-1 fraction or 0-100 percentage)"),
        ],
        help_text="Adjust reactor power generation level (higher = more heat)",
        system="engineering",
    ))

    dispatcher.register("throttle_drive", CommandSpec(
        handler=cmd_throttle_drive,
        args=[
            ArgSpec("limit", "float", required=True,
                    min_val=0.0, max_val=100.0,
                    description="Drive throttle limit (0-1 fraction or 0-100 percentage)"),
        ],
        help_text="Set maximum drive output (engineering safety limit on helm throttle)",
        system="engineering",
    ))

    dispatcher.register("manage_radiators", CommandSpec(
        handler=cmd_manage_radiators,
        args=[
            ArgSpec("deployed", "bool", required=False,
                    description="Deploy (true) or retract (false) radiator panels"),
            ArgSpec("priority", "str", required=False,
                    choices=["balanced", "cooling", "stealth"],
                    description="Radiator priority mode: balanced, cooling, or stealth"),
        ],
        help_text="Manage radiator panels — deploy/retract and set heat dissipation priority",
        system="engineering",
    ))

    dispatcher.register("monitor_fuel", CommandSpec(
        handler=cmd_monitor_fuel,
        args=[],
        help_text="Track reaction mass remaining, burn rate, and delta-v budget",
        system="engineering",
    ))

    dispatcher.register("emergency_vent", CommandSpec(
        handler=cmd_emergency_vent,
        args=[
            ArgSpec("confirm", "bool", required=True,
                    description="Confirm irreversible emergency coolant vent (true to activate)"),
        ],
        help_text="Dump heat rapidly by venting coolant — ONE-TIME USE, irreversible",
        system="engineering",
    ))
