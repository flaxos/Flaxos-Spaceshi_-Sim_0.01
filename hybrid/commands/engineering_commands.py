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


def cmd_toggle_system(engineering, ship, params):
    """Toggle a ship system on or off.

    The GUI sends this from system-toggles.js when the player flips a
    system power switch.  We route through the engineering system but
    operate on the target system directly via BaseSystem.power_on/off.

    Args:
        engineering: EngineeringSystem instance (unused — we target the
            system specified in params)
        ship: Ship object
        params: Validated parameters with system id and state (1=on, 0=off)

    Returns:
        dict: Toggle result with new system state
    """
    system_id = params.get("system")
    state = params.get("state", 1)

    if not system_id:
        return {"ok": False, "error": "No system specified"}

    system = ship.systems.get(system_id)
    if not system:
        return {"ok": False, "error": f"Unknown system: {system_id}"}

    if state:
        result = system.power_on() if hasattr(system, "power_on") else {"status": "no power_on method"}
    else:
        result = system.power_off() if hasattr(system, "power_off") else {"status": "no power_off method"}

    logger.info("System %s toggled %s on ship %s", system_id, "ON" if state else "OFF", ship.id)
    return {
        "ok": True,
        "system": system_id,
        "enabled": bool(state),
        **(result if isinstance(result, dict) else {}),
    }


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

    dispatcher.register("toggle_system", CommandSpec(
        handler=cmd_toggle_system,
        args=[
            ArgSpec("system", "str", required=True,
                    description="System ID to toggle (e.g. 'propulsion', 'sensors')"),
            ArgSpec("state", "int", required=False,
                    description="1 to enable, 0 to disable (default: 1)"),
        ],
        help_text="Toggle a ship system on or off (power switch)",
        system="engineering",
    ))
