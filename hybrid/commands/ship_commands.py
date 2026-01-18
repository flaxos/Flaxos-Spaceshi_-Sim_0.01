# hybrid/commands/ship_commands.py
"""Ship-level commands (status, position, etc.)."""

from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec
from hybrid.utils.errors import success_dict, error_dict
from hybrid.utils.units import (
    format_vector, format_heading, format_velocity,
    format_mass
)
from hybrid.utils.math_utils import magnitude
import math

def cmd_status(ship, params):
    """Get comprehensive ship status."""
    state = ship.get_state()

    # Calculate additional metrics
    speed = math.sqrt(
        ship.velocity["x"]**2 +
        ship.velocity["y"]**2 +
        ship.velocity["z"]**2
    )

    return success_dict(
        "Ship status retrieved",
        ship_id=ship.id,
        name=ship.name,
        class_type=ship.class_type,
        position=format_vector(ship.position),
        velocity=format_velocity(speed),
        heading=format_heading(ship.orientation),
        mass=format_mass(ship.mass),
        systems={k: v.get("status", "unknown") if isinstance(v, dict) else "unknown"
                 for k, v in state["systems"].items()}
    )

def cmd_get_position(ship, params):
    """Get ship position."""
    return success_dict(
        "Position retrieved",
        position=ship.position,
        formatted=format_vector(ship.position)
    )

def cmd_get_velocity(ship, params):
    """Get ship velocity."""
    speed = math.sqrt(
        ship.velocity["x"]**2 +
        ship.velocity["y"]**2 +
        ship.velocity["z"]**2
    )

    return success_dict(
        "Velocity retrieved",
        velocity=ship.velocity,
        speed=speed,
        formatted=f"{format_vector(ship.velocity)} ({format_velocity(speed)})"
    )

def cmd_get_orientation(ship, params):
    """Get ship orientation."""
    return success_dict(
        "Orientation retrieved",
        orientation=ship.orientation,
        formatted=format_heading(ship.orientation)
    )

def cmd_thrust(propulsion, ship, params):
    """Set thrust."""
    thrust_vector = params.get("thrust_vector")

    if thrust_vector:
        # Vector thrust command
        return propulsion.set_thrust({
            "x": thrust_vector["x"],
            "y": thrust_vector["y"],
            "z": thrust_vector["z"]
        })
    else:
        # Scalar thrust command (main drive only)
        magnitude = params.get("magnitude", 0.0)
        return propulsion.set_thrust({
            "x": magnitude,
            "y": 0.0,
            "z": 0.0
        })

def cmd_heading(helm, ship, params):
    """Set heading."""
    pitch = params.get("pitch")
    yaw = params.get("yaw")
    roll = params.get("roll", 0.0)

    if helm and hasattr(helm, "set_orientation"):
        return helm.set_orientation({
            "pitch": pitch,
            "yaw": yaw,
            "roll": roll
        })

    # Direct orientation set if no helm
    ship.orientation = {
        "pitch": pitch,
        "yaw": yaw,
        "roll": roll
    }

    return success_dict(
        "Heading set",
        orientation=ship.orientation,
        formatted=format_heading(ship.orientation)
    )

def cmd_rotate(ship, params):
    """Rotate ship."""
    axis = params.get("axis", "yaw")
    amount = params.get("amount", 0.0)

    if axis not in ["pitch", "yaw", "roll"]:
        return error_dict("INVALID_AXIS", f"Invalid axis: {axis}")

    ship.orientation[axis] += amount

    # Normalize
    while ship.orientation[axis] >= 180:
        ship.orientation[axis] -= 360
    while ship.orientation[axis] < -180:
        ship.orientation[axis] += 360

    return success_dict(
        f"Rotated {amount}° on {axis}",
        orientation=ship.orientation,
        formatted=format_heading(ship.orientation)
    )

def cmd_refuel(propulsion, ship, params):
    """Refuel ship."""
    amount = params.get("amount")

    if amount is None:
        # Refuel to max
        return propulsion.refuel({})

    return propulsion.refuel({"amount": amount})

def cmd_emergency_stop(propulsion, ship, params):
    """Emergency stop all thrust."""
    return propulsion.emergency_stop()

def cmd_power_on(ship, params):
    """Power on a system."""
    system_name = params.get("system")

    if system_name not in ship.systems:
        return error_dict("SYSTEM_NOT_FOUND", f"Unknown system: {system_name}")

    system = ship.systems[system_name]

    if hasattr(system, "power_on"):
        return system.power_on()
    elif hasattr(system, "enabled"):
        system.enabled = True
        return success_dict(f"System {system_name} powered on")

    return error_dict("NOT_SUPPORTED", f"System {system_name} does not support power_on")

def cmd_power_off(ship, params):
    """Power off a system."""
    system_name = params.get("system")

    if system_name not in ship.systems:
        return error_dict("SYSTEM_NOT_FOUND", f"Unknown system: {system_name}")

    system = ship.systems[system_name]

    if hasattr(system, "power_off"):
        return system.power_off()
    elif hasattr(system, "enabled"):
        system.enabled = False
        return success_dict(f"System {system_name} powered off")

    return error_dict("NOT_SUPPORTED", f"System {system_name} does not support power_off")

def register_commands(dispatcher):
    """Register all ship commands with the dispatcher."""

    # Status commands
    dispatcher.register("status", CommandSpec(
        handler=cmd_status,
        args=[],
        help_text="Show comprehensive ship status"
    ))

    dispatcher.register("position", CommandSpec(
        handler=cmd_get_position,
        args=[],
        help_text="Get current position"
    ))

    dispatcher.register("velocity", CommandSpec(
        handler=cmd_get_velocity,
        args=[],
        help_text="Get current velocity"
    ))

    dispatcher.register("orientation", CommandSpec(
        handler=cmd_get_orientation,
        args=[],
        help_text="Get current orientation"
    ))

    # Movement commands
    dispatcher.register("thrust", CommandSpec(
        handler=cmd_thrust,
        args=[
            ArgSpec("magnitude", "float", required=False, min_val=0.0, max_val=1.0,
                    default=0.0, description="Thrust magnitude (0-1)"),
            ArgSpec("thrust_vector", "vector3", required=False,
                    description="3D thrust vector (alternative to magnitude)")
        ],
        help_text="Set thrust (0-1)",
        system="propulsion"
    ))

    dispatcher.register("heading", CommandSpec(
        handler=cmd_heading,
        args=[
            ArgSpec("pitch", "angle", required=True, description="Pitch angle in degrees"),
            ArgSpec("yaw", "angle", required=True, description="Yaw angle in degrees"),
            ArgSpec("roll", "angle", required=False, default=0.0, description="Roll angle in degrees")
        ],
        help_text="Set heading (pitch, yaw, roll in degrees)",
        system="helm"
    ))

    dispatcher.register("rotate", CommandSpec(
        handler=cmd_rotate,
        args=[
            ArgSpec("axis", "str", required=True, choices=["pitch", "yaw", "roll"],
                    description="Axis to rotate on"),
            ArgSpec("amount", "angle", required=True, description="Amount to rotate in degrees")
        ],
        help_text="Rotate ship on an axis"
    ))

    dispatcher.register("refuel", CommandSpec(
        handler=cmd_refuel,
        args=[
            ArgSpec("amount", "float", required=False, min_val=0.0,
                    description="Amount to refuel (omit for full tank)")
        ],
        help_text="Refuel ship",
        system="propulsion"
    ))

    dispatcher.register("emergency_stop", CommandSpec(
        handler=cmd_emergency_stop,
        args=[],
        help_text="Emergency stop all thrust",
        system="propulsion"
    ))

    # System power commands
    dispatcher.register("power_on", CommandSpec(
        handler=cmd_power_on,
        args=[
            ArgSpec("system", "str", required=True, description="System to power on")
        ],
        help_text="Power on a system"
    ))

    dispatcher.register("power_off", CommandSpec(
        handler=cmd_power_off,
        args=[
            ArgSpec("system", "str", required=True, description="System to power off")
        ],
        help_text="Power off a system"
    ))
