# hybrid/commands/navigation_commands.py
"""Navigation and autopilot commands."""

from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec, validate_autopilot_program, validate_contact_id
from hybrid.utils.errors import success_dict, error_dict

def cmd_autopilot(navigation, ship, params):
    """Engage autopilot with a program."""
    program = params.get("program")
    target = params.get("target")

    # Validate program
    is_valid, validated_program, error_msg = validate_autopilot_program(program)
    if not is_valid:
        return error_dict("INVALID_PROGRAM", error_msg)

    if navigation and hasattr(navigation, "set_autopilot"):
        return navigation.set_autopilot({
            "program": validated_program,
            "target": target
        })

    return error_dict("NOT_IMPLEMENTED", "Autopilot not yet implemented")

def cmd_set_course(navigation, ship, params):
    """Set navigation course."""
    if navigation and hasattr(navigation, "set_course"):
        return navigation.set_course(params)

    return error_dict("NOT_IMPLEMENTED", "Course setting not yet implemented")

def cmd_set_plan(navigation, ship, params):
    """Set a queued flight plan."""
    if navigation and hasattr(navigation, "command"):
        return navigation.command("set_plan", params)

    return error_dict("NOT_IMPLEMENTED", "Flight plan setting not yet implemented")

def register_commands(dispatcher):
    """Register all navigation commands with the dispatcher."""

    dispatcher.register("autopilot", CommandSpec(
        handler=cmd_autopilot,
        args=[
            ArgSpec("program", "str", required=True,
                    choices=["match", "intercept", "approach", "hold", "off"],
                    description="Autopilot program to run"),
            ArgSpec("target", "str", required=False,
                    description="Target contact ID (required for match/intercept)")
        ],
        help_text="Engage autopilot (match|intercept|approach|hold|off)",
        system="navigation"
    ))

    dispatcher.register("set_course", CommandSpec(
        handler=cmd_set_course,
        args=[
            ArgSpec("x", "float", required=True, description="Destination X coordinate"),
            ArgSpec("y", "float", required=True, description="Destination Y coordinate"),
            ArgSpec("z", "float", required=True, description="Destination Z coordinate"),
            ArgSpec("stop", "bool", required=False, default=True,
                    description="Stop at destination (default true)"),
            ArgSpec("tolerance", "float", required=False,
                    description="Arrival tolerance in meters"),
            ArgSpec("max_thrust", "float", required=False,
                    description="Maximum thrust scalar (0..1)"),
            ArgSpec("coast_speed", "float", required=False,
                    description="Coast speed target for cruise"),
            ArgSpec("max_speed", "float", required=False,
                    description="Maximum speed during course"),
            ArgSpec("brake_buffer", "float", required=False,
                    description="Extra distance buffer for braking"),
        ],
        help_text="Set navigation course to destination",
        system="navigation"
    ))

    dispatcher.register("set_plan", CommandSpec(
        handler=cmd_set_plan,
        args=[
            ArgSpec("plan", "dict", required=True,
                    description="Flight plan payload"),
        ],
        help_text="Queue a navigation flight plan",
        system="navigation"
    ))
