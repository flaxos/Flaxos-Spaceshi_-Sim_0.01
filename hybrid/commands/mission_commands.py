# hybrid/commands/mission_commands.py
"""Mission branching commands: comms choices and mission branch status.

Commands:
    comms_respond: Respond to an active comms choice during a branching mission.
    get_comms_choices: List currently active comms choices awaiting player response.
    get_branch_status: Get the current branch state of the active mission.
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)


def _get_branching_mission(ship):
    """Try to get the BranchingMission from the runner attached to the ship.

    The hybrid runner stores the active mission on itself, and the ship
    has a back-reference to the runner.  This is the only way to reach
    mission state from a command handler without global singletons.

    Returns:
        BranchingMission or None.
    """
    runner = getattr(ship, "_runner_ref", None)
    if not runner:
        return None
    mission = getattr(runner, "mission", None)
    if mission is None:
        return None
    # Only BranchingMission has the comms_choices attribute
    from hybrid.missions.branching import BranchingMission
    if isinstance(mission, BranchingMission):
        return mission
    return None


def cmd_comms_respond(comms, ship, params):
    """Respond to an active comms choice.

    The player selects one of the presented options.  The response
    is recorded on the BranchingMission and will be picked up by
    branch point condition evaluation on the next tick.

    Args:
        comms: CommsSystem instance (used for logging the response).
        ship: Ship object.
        params: Validated parameters (choice_id, option_id).

    Returns:
        dict: Result of the response.
    """
    choice_id = params.get("choice_id")
    option_id = params.get("option_id")

    mission = _get_branching_mission(ship)
    if not mission:
        return error_dict("NO_BRANCHING_MISSION",
                          "No active branching mission to respond to")

    manager = getattr(mission, "comms_choice_manager", None)
    if not manager:
        return error_dict("NO_CHOICE_MANAGER",
                          "Mission has no comms choice system")

    # Resolve through the manager (validates choice/option exist)
    result = manager.resolve_choice(choice_id, option_id)
    if result is None:
        active = [c["choice_id"] for c in manager.get_active_choices()]
        return error_dict(
            "INVALID_CHOICE",
            f"Cannot resolve choice '{choice_id}' with option '{option_id}'. "
            f"Active choices: {active}",
        )

    # Record on the mission for branch condition evaluation
    mission.record_comms_choice(choice_id, option_id)

    # Log in the comms system message log
    event_bus = getattr(ship, "event_bus", None)
    if event_bus:
        event_bus.publish("comms_choice_made", {
            "ship_id": ship.id,
            "choice_id": choice_id,
            "option_id": option_id,
        })

    return success_dict(
        f"Response recorded: {option_id}",
        choice_id=choice_id,
        option_id=option_id,
    )


def cmd_get_comms_choices(comms, ship, params):
    """List active comms choices awaiting response.

    Args:
        comms: CommsSystem instance.
        ship: Ship object.
        params: Validated parameters (none required).

    Returns:
        dict: Active choices and resolved history.
    """
    mission = _get_branching_mission(ship)
    if not mission:
        return success_dict("No branching mission active", choices=[], resolved={})

    manager = getattr(mission, "comms_choice_manager", None)
    if not manager:
        return success_dict("No choice system", choices=[], resolved={})

    state = manager.get_state()
    return success_dict(
        f"{len(state['active_choices'])} active choice(s)",
        choices=state["active_choices"],
        resolved=state["resolved_choices"],
    )


def cmd_get_branch_status(comms, ship, params):
    """Get the current branch state of the active mission.

    Args:
        comms: CommsSystem instance.
        ship: Ship object.
        params: Validated parameters (none required).

    Returns:
        dict: Branch history, active branches, pending choices.
    """
    mission = _get_branching_mission(ship)
    if not mission:
        return success_dict(
            "No branching mission active",
            active_branches=[],
            branch_history=[],
            pending_comms_choices=[],
        )

    return success_dict(
        f"{len(mission.active_branches)} active branch(es)",
        active_branches=mission.active_branches,
        branch_history=mission.branch_history,
        pending_comms_choices=mission.pending_comms_choices,
    )


def register_commands(dispatcher):
    """Register mission branching commands with the dispatcher."""

    dispatcher.register("comms_respond", CommandSpec(
        handler=cmd_comms_respond,
        args=[
            ArgSpec("choice_id", "str", required=True,
                    description="ID of the comms choice to respond to"),
            ArgSpec("option_id", "str", required=True,
                    description="ID of the selected option"),
        ],
        help_text="Respond to a comms choice during a branching mission",
        system="comms",
    ))

    dispatcher.register("get_comms_choices", CommandSpec(
        handler=cmd_get_comms_choices,
        args=[],
        help_text="List active comms choices awaiting player response",
        system="comms",
    ))

    dispatcher.register("get_branch_status", CommandSpec(
        handler=cmd_get_branch_status,
        args=[],
        help_text="Get current mission branch state and history",
        system="comms",
    ))
