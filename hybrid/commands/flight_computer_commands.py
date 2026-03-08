# hybrid/commands/flight_computer_commands.py
"""Flight computer commands for the dispatch system."""

from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec
from hybrid.utils.errors import success_dict, error_dict


def cmd_flight_computer(flight_computer, ship, params):
    """Route a flight computer command to the system.

    The ``action`` parameter selects the sub-command:
    navigate_to, intercept, match_velocity, hold_position,
    orbit, evasive, manual, abort, status.
    """
    action = params.get("action")
    if not action:
        return error_dict("MISSING_ACTION", "Flight computer requires an action parameter")

    # Inject ship reference so the system can access it
    params["_ship"] = ship
    params["ship"] = ship

    return flight_computer.command(action, params)


def register_commands(dispatcher) -> None:
    """Register flight computer commands with the dispatcher.

    Args:
        dispatcher: CommandDispatcher instance.
    """
    dispatcher.register("flight_computer", CommandSpec(
        handler=cmd_flight_computer,
        args=[
            ArgSpec("action", "str", required=True,
                    choices=[
                        "navigate_to", "intercept", "match_velocity",
                        "hold_position", "orbit", "evasive",
                        "manual", "abort", "status",
                    ],
                    description="Flight computer action"),
            # navigate_to params
            ArgSpec("x", "float", required=False,
                    description="Target X coordinate (navigate_to)"),
            ArgSpec("y", "float", required=False,
                    description="Target Y coordinate (navigate_to)"),
            ArgSpec("z", "float", required=False,
                    description="Target Z coordinate (navigate_to)"),
            # intercept / match_velocity
            ArgSpec("target", "str", required=False,
                    description="Target contact ID (intercept/match_velocity)"),
            # orbit
            ArgSpec("center_x", "float", required=False,
                    description="Orbit center X"),
            ArgSpec("center_y", "float", required=False,
                    description="Orbit center Y"),
            ArgSpec("center_z", "float", required=False,
                    description="Orbit center Z"),
            ArgSpec("radius", "float", required=False,
                    description="Orbit radius in metres"),
            # evasive
            ArgSpec("duration", "float", required=False,
                    description="Evasive duration in seconds (0=indefinite)"),
            # common
            ArgSpec("max_thrust", "float", required=False,
                    description="Maximum thrust scalar (0..1)"),
        ],
        help_text="Unified flight computer interface (navigate_to|intercept|match_velocity|hold_position|orbit|evasive|manual|abort|status)",
        system="flight_computer",
    ))
