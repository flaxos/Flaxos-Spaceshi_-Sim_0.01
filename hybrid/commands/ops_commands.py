# hybrid/commands/ops_commands.py
"""Ops station commands: power allocation, damage control, system triage.

Commands:
    allocate_power: Distribute reactor output among subsystems by priority
    dispatch_repair: Send a damage control team to a specific subsystem
    set_system_priority: Triage which systems get power when reactor is impaired
    report_status: Full subsystem integrity readout
    emergency_shutdown: Scram a system to prevent cascade failure
    restart_system: Restart a previously scrammed system
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)


def cmd_allocate_power(ops, ship, params):
    """Distribute reactor output among subsystems.

    Args:
        ops: OpsSystem instance
        ship: Ship object
        params: Validated parameters with allocation dict

    Returns:
        dict: Updated power allocation
    """
    allocation = params.get("allocation")
    if not allocation:
        return error_dict(
            "MISSING_ALLOCATION",
            "Provide 'allocation' dict mapping subsystem names to fractions",
        )
    return ops._cmd_allocate_power({"allocation": allocation})


def cmd_dispatch_repair(ops, ship, params):
    """Send a damage control team to repair a subsystem.

    Args:
        ops: OpsSystem instance
        ship: Ship object
        params: Validated parameters with subsystem and optional team

    Returns:
        dict: Dispatch result with team status and ETA
    """
    subsystem = params.get("subsystem")
    team = params.get("team")

    cmd_params = {
        "subsystem": subsystem,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    }
    if team:
        cmd_params["team"] = team

    return ops._cmd_dispatch_repair(cmd_params)


def cmd_set_system_priority(ops, ship, params):
    """Set priority level for a subsystem.

    Args:
        ops: OpsSystem instance
        ship: Ship object
        params: Validated parameters with subsystem and priority

    Returns:
        dict: Updated priority ordering
    """
    return ops._cmd_set_system_priority({
        "subsystem": params.get("subsystem"),
        "priority": params.get("priority"),
    })


def cmd_report_status(ops, ship, params):
    """Full subsystem integrity readout.

    Args:
        ops: OpsSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Complete subsystem status with repair teams and power allocation
    """
    return ops._cmd_report_status({"_ship": ship})


def cmd_emergency_shutdown(ops, ship, params):
    """Scram a system to prevent cascade failure.

    Args:
        ops: OpsSystem instance
        ship: Ship object
        params: Validated parameters with subsystem name

    Returns:
        dict: Shutdown confirmation
    """
    return ops._cmd_emergency_shutdown({
        "subsystem": params.get("subsystem"),
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    })


def cmd_restart_system(ops, ship, params):
    """Restart a previously scrammed system.

    Args:
        ops: OpsSystem instance
        ship: Ship object
        params: Validated parameters with subsystem name

    Returns:
        dict: Restart confirmation
    """
    return ops._cmd_restart_system({
        "subsystem": params.get("subsystem"),
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
    })


def register_commands(dispatcher):
    """Register all ops commands with the dispatcher."""

    dispatcher.register("allocate_power", CommandSpec(
        handler=cmd_allocate_power,
        args=[
            ArgSpec("allocation", "dict", required=True,
                    description="Subsystem power fractions, e.g. "
                                '{"propulsion": 0.4, "weapons": 0.3}'),
        ],
        help_text="Distribute reactor output among subsystems by priority",
        system="ops",
    ))

    dispatcher.register("dispatch_repair", CommandSpec(
        handler=cmd_dispatch_repair,
        args=[
            ArgSpec("subsystem", "str", required=True,
                    description="Target subsystem to repair"),
            ArgSpec("team", "str", required=False,
                    description="Specific team ID (e.g. DC-1)"),
        ],
        help_text="Send a damage control team to repair a specific subsystem",
        system="ops",
    ))

    dispatcher.register("set_system_priority", CommandSpec(
        handler=cmd_set_system_priority,
        args=[
            ArgSpec("subsystem", "str", required=True,
                    description="Subsystem to set priority for"),
            ArgSpec("priority", "int", required=True,
                    min_val=0, max_val=10,
                    description="Priority level (0-10, higher = more important)"),
        ],
        help_text="Set which systems get power first when reactor is impaired",
        system="ops",
    ))

    dispatcher.register("report_status", CommandSpec(
        handler=cmd_report_status,
        args=[],
        help_text="Full subsystem integrity readout with repair teams and power",
        system="ops",
    ))

    dispatcher.register("emergency_shutdown", CommandSpec(
        handler=cmd_emergency_shutdown,
        args=[
            ArgSpec("subsystem", "str", required=True,
                    description="Subsystem to scram (emergency shutdown)"),
        ],
        help_text="Scram a system to prevent cascade failure",
        system="ops",
    ))

    dispatcher.register("restart_system", CommandSpec(
        handler=cmd_restart_system,
        args=[
            ArgSpec("subsystem", "str", required=True,
                    description="Subsystem to restart after emergency shutdown"),
        ],
        help_text="Restart a previously scrammed system",
        system="ops",
    ))
