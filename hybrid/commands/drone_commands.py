# hybrid/commands/drone_commands.py
"""Drone bay commands: launch, recall, behavior, status.

Commands:
    launch_drone:         Deploy a drone from bay into the simulator
    recall_drone:         Set drone autopilot to return to parent
    set_drone_behavior:   Change a drone's AI behavior profile
    drone_status:         Get bay inventory and active drone details
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)


def cmd_launch_drone(drone_bay, ship, params):
    """Launch a drone from the bay into the simulation.

    Args:
        drone_bay: DroneBaySystem instance
        ship: Ship object (parent ship)
        params: Validated parameters with drone_type

    Returns:
        dict: Launch result with drone_id
    """
    return drone_bay._cmd_launch_drone({
        "drone_type": params.get("drone_type"),
        "ship": ship,
        "_ship": ship,
        "_simulator": params.get("_simulator"),
    })


def cmd_recall_drone(drone_bay, ship, params):
    """Recall a deployed drone back to the parent ship.

    Args:
        drone_bay: DroneBaySystem instance
        ship: Ship object (parent ship)
        params: Validated parameters with drone_id

    Returns:
        dict: Recall result
    """
    return drone_bay._cmd_recall_drone({
        "drone_id": params.get("drone_id"),
        "ship": ship,
        "_ship": ship,
        "_simulator": params.get("_simulator"),
    })


def cmd_set_drone_behavior(drone_bay, ship, params):
    """Change a drone's AI behavior role.

    Args:
        drone_bay: DroneBaySystem instance
        ship: Ship object
        params: Validated parameters with drone_id and behavior

    Returns:
        dict: Behavior change result
    """
    return drone_bay._cmd_set_drone_behavior({
        "drone_id": params.get("drone_id"),
        "behavior": params.get("behavior"),
        "_simulator": params.get("_simulator"),
    })


def cmd_drone_status(drone_bay, ship, params):
    """Get drone bay inventory and active drone details.

    Args:
        drone_bay: DroneBaySystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Bay status with stored and active drone info
    """
    return drone_bay._cmd_drone_status({
        "ship": ship,
        "_ship": ship,
        "_simulator": params.get("_simulator"),
    })


def register_commands(dispatcher):
    """Register all drone commands with the dispatcher."""

    dispatcher.register("launch_drone", CommandSpec(
        handler=cmd_launch_drone,
        args=[
            ArgSpec("drone_type", "str", required=True,
                    choices=["drone_sensor", "drone_combat", "drone_decoy"],
                    description="Type of drone to launch"),
        ],
        help_text="Deploy a drone from bay storage into the simulation",
        system="drone_bay",
    ))

    dispatcher.register("recall_drone", CommandSpec(
        handler=cmd_recall_drone,
        args=[
            ArgSpec("drone_id", "str", required=True,
                    description="ID of the drone to recall"),
        ],
        help_text="Set a drone's autopilot to return to parent ship",
        system="drone_bay",
    ))

    dispatcher.register("set_drone_behavior", CommandSpec(
        handler=cmd_set_drone_behavior,
        args=[
            ArgSpec("drone_id", "str", required=True,
                    description="ID of the drone to modify"),
            ArgSpec("behavior", "str", required=True,
                    choices=["patrol", "defender", "decoy", "combat",
                             "escort", "swarm"],
                    description="AI behavior role to assign"),
        ],
        help_text="Change a drone's AI behavior profile",
        system="drone_bay",
    ))

    dispatcher.register("drone_status", CommandSpec(
        handler=cmd_drone_status,
        args=[],
        help_text="Get drone bay capacity, stored drones, and active drone status",
        system="drone_bay",
    ))
