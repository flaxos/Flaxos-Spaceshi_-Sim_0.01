# hybrid/commands/helm_commands.py
"""Helm navigation commands for ship control.

Commands:
- execute_burn: Timed burn with specified thrust/direction
- plot_intercept: Calculate burn sequence to reach target position/velocity
- flip_and_burn: Rotate 180 degrees and decelerate
- emergency_burn: Maximum thrust override (safety limits bypassed)
"""

import math
import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec
from hybrid.utils.errors import success_dict, error_dict
from hybrid.utils.math_utils import magnitude, subtract_vectors

logger = logging.getLogger(__name__)


def cmd_execute_burn(helm, ship, params):
    """Execute a timed burn with specified parameters.

    Queues a rotate-then-thrust sequence on the helm command queue.
    The burn runs for 'duration' seconds at the given throttle or G-force,
    optionally in a specified direction (heading).

    Args:
        helm: HelmSystem instance
        ship: Ship object
        params: Validated parameters (duration, throttle/g, pitch, yaw)

    Returns:
        dict: Burn plan with estimated delta-v and fuel cost
    """
    duration = params.get("duration", 10.0)
    throttle = params.get("throttle")
    g_force = params.get("g")

    # Determine thrust level
    if g_force is not None:
        thrust_param = {"g": g_force}
        thrust_desc = f"{g_force}G"
    elif throttle is not None:
        thrust_param = {"thrust": throttle}
        thrust_desc = f"{throttle * 100:.0f}%"
    else:
        thrust_param = {"thrust": 1.0}
        thrust_desc = "100%"

    # Get propulsion for burn estimates
    propulsion = ship.systems.get("propulsion")
    if not propulsion:
        return error_dict("NO_PROPULSION", "Propulsion system not available")

    if propulsion.fuel_level <= 0:
        return error_dict("NO_FUEL", "No fuel remaining")

    # Calculate estimated delta-v for this burn
    max_thrust = getattr(propulsion, "max_thrust", 0)
    if g_force is not None:
        actual_force = min(g_force * 9.81 * ship.mass, max_thrust)
    elif throttle is not None:
        actual_force = throttle * max_thrust
    else:
        actual_force = max_thrust

    accel = actual_force / ship.mass if ship.mass > 0 else 0
    estimated_dv = accel * duration
    exhaust_vel = getattr(propulsion, "exhaust_velocity", 29430)
    fuel_estimate = ship.mass * (1.0 - math.exp(-estimated_dv / exhaust_vel)) if exhaust_vel > 0 else 0

    # Build helm queue commands
    commands = []

    # Optional heading change before burn
    pitch = params.get("pitch")
    yaw = params.get("yaw")
    if pitch is not None or yaw is not None:
        current = ship.orientation
        rotate_target = {
            "pitch": pitch if pitch is not None else current.get("pitch", 0),
            "yaw": yaw if yaw is not None else current.get("yaw", 0),
            "roll": current.get("roll", 0),
        }
        # Set orientation first
        helm_params = dict(rotate_target)
        helm_params["_ship"] = ship
        helm_params["ship"] = ship
        helm_params["_from_autopilot"] = True
        helm._cmd_set_orientation_target(helm_params)

    # Queue the timed thrust command
    thrust_cmd = dict(thrust_param)
    thrust_cmd["duration"] = duration
    normalized = helm._normalize_queue_command("thrust", thrust_cmd)
    if "error" in normalized:
        return normalized

    entry = helm._enqueue_command(normalized["command"], normalized["params"])

    # Warn if insufficient fuel
    warnings = []
    if fuel_estimate > propulsion.fuel_level:
        warnings.append(f"Burn may exhaust fuel (need ~{fuel_estimate:.1f}kg, have {propulsion.fuel_level:.1f}kg)")

    return success_dict(
        f"Burn queued: {thrust_desc} for {duration:.1f}s",
        burn={
            "duration": duration,
            "thrust_desc": thrust_desc,
            "estimated_delta_v": round(estimated_dv, 1),
            "estimated_fuel": round(fuel_estimate, 1),
            "estimated_accel_g": round(accel / 9.81, 2),
        },
        queued=entry,
        queue_depth=len(helm.command_queue),
        warnings=warnings,
    )


def cmd_plot_intercept(helm, ship, params):
    """Calculate burn sequence to reach a target position/velocity.

    Uses the flight computer's planning module to compute delta-v
    requirements and fuel consumption, then returns the plan without
    executing it. The player can then decide whether to commit.

    Args:
        helm: HelmSystem instance
        ship: Ship object
        params: target (contact ID) or target_position {x,y,z}

    Returns:
        dict: Intercept plan with delta-v, fuel cost, estimated time, phases
    """
    from hybrid.systems.flight_computer.planning import (
        plan_intercept, plan_goto, _max_accel, _fuel_available,
    )

    target_id = params.get("target")
    target_position = params.get("target_position")
    execute = params.get("execute", False)

    if target_id:
        # Intercept a sensor contact
        plan = plan_intercept(ship, target_id, params)

        if plan.confidence <= 0:
            return error_dict(
                "CANNOT_INTERCEPT",
                plan.warnings[0] if plan.warnings else "Cannot compute intercept",
            )

        result = success_dict(
            f"Intercept solution for {target_id}",
            plan={
                "command": plan.command,
                "estimated_time": round(plan.estimated_time, 1),
                "delta_v": round(plan.delta_v, 1),
                "fuel_cost": round(plan.fuel_cost, 1),
                "confidence": round(plan.confidence, 2),
                "phases": plan.phases,
                "warnings": plan.warnings,
            },
            fuel_remaining=round(_fuel_available(ship), 1),
            max_accel_g=round(_max_accel(ship) / 9.81, 2),
        )

        # Optionally execute the intercept
        if execute:
            nav = ship.systems.get("navigation")
            if nav:
                ap_result = nav.set_autopilot({
                    "program": "intercept",
                    "target": target_id,
                })
                result["autopilot_engaged"] = ap_result.get("ok", False)
                result["status"] = f"Intercept course set for {target_id}"
            else:
                result["warnings"] = result.get("warnings", []) + ["Navigation system unavailable - plan only"]

        return result

    elif target_position:
        # Go-to-position plan
        pos = target_position
        if isinstance(pos, dict):
            position = {
                "x": float(pos.get("x", 0)),
                "y": float(pos.get("y", 0)),
                "z": float(pos.get("z", 0)),
            }
        else:
            return error_dict("INVALID_POSITION", "target_position must be {x, y, z}")

        plan = plan_goto(ship, position, params)

        if plan.confidence <= 0:
            return error_dict(
                "CANNOT_REACH",
                plan.warnings[0] if plan.warnings else "Cannot reach position",
            )

        distance = magnitude(subtract_vectors(position, ship.position))

        result = success_dict(
            f"Course plotted to ({position['x']:.0f}, {position['y']:.0f}, {position['z']:.0f})",
            plan={
                "command": plan.command,
                "estimated_time": round(plan.estimated_time, 1),
                "delta_v": round(plan.delta_v, 1),
                "fuel_cost": round(plan.fuel_cost, 1),
                "confidence": round(plan.confidence, 2),
                "phases": plan.phases,
                "warnings": plan.warnings,
                "distance": round(distance, 1),
            },
            fuel_remaining=round(_fuel_available(ship), 1),
            max_accel_g=round(_max_accel(ship) / 9.81, 2),
        )

        # Optionally execute
        if execute:
            nav = ship.systems.get("navigation")
            if nav:
                course_params = dict(position)
                course_params["stop"] = True
                ap_result = nav.set_course(course_params)
                result["course_set"] = ap_result.get("ok", False)
                result["status"] = "Course set and autopilot engaged"

        return result

    return error_dict("MISSING_TARGET", "Provide 'target' (contact ID) or 'target_position' {x, y, z}")


def cmd_flip_and_burn(helm, ship, params):
    """Rotate 180 degrees and decelerate (Expanse-style flip-and-burn).

    Computes the retrograde heading (opposite to current velocity vector),
    sets the attitude target, and optionally starts a deceleration burn.

    Args:
        helm: HelmSystem instance
        ship: Ship object
        params: Optional g (G-force), throttle, auto_burn (bool)

    Returns:
        dict: Maneuver status with retrograde heading and burn estimate
    """
    from hybrid.navigation.relative_motion import vector_to_heading

    vel_mag = magnitude(ship.velocity)

    if vel_mag < 0.01:
        return error_dict("NO_VELOCITY", "Ship has negligible velocity - flip-and-burn not needed")

    # Calculate retrograde direction (opposite of velocity)
    retrograde_vec = {
        "x": -ship.velocity["x"] / vel_mag,
        "y": -ship.velocity["y"] / vel_mag,
        "z": -ship.velocity["z"] / vel_mag,
    }
    retrograde_heading = vector_to_heading(retrograde_vec)

    # Set attitude target to retrograde
    attitude_target = {
        "pitch": retrograde_heading.get("pitch", 0),
        "yaw": retrograde_heading.get("yaw", 0),
        "roll": ship.orientation.get("roll", 0),
    }

    # Apply through helm system
    orient_params = dict(attitude_target)
    orient_params["_ship"] = ship
    orient_params["ship"] = ship
    orient_params["_from_autopilot"] = True
    helm._cmd_set_orientation_target(orient_params)

    # Calculate braking estimates
    propulsion = ship.systems.get("propulsion")
    burn_estimate = {}
    if propulsion:
        max_thrust = getattr(propulsion, "max_thrust", 0)
        max_accel = max_thrust / ship.mass if ship.mass > 0 else 0
        exhaust_vel = getattr(propulsion, "exhaust_velocity", 29430)

        g_force = params.get("g")
        throttle = params.get("throttle")

        if g_force is not None:
            accel = min(g_force * 9.81, max_accel)
        elif throttle is not None:
            accel = throttle * max_accel
        else:
            accel = max_accel

        if accel > 0:
            burn_time = vel_mag / accel
            fuel_needed = ship.mass * (1.0 - math.exp(-vel_mag / exhaust_vel)) if exhaust_vel > 0 else 0
            burn_estimate = {
                "accel_g": round(accel / 9.81, 2),
                "burn_time": round(burn_time, 1),
                "delta_v_to_stop": round(vel_mag, 1),
                "fuel_needed": round(fuel_needed, 1),
                "fuel_available": round(propulsion.fuel_level, 1),
                "can_stop": fuel_needed <= propulsion.fuel_level,
            }

    # Optionally engage the deceleration burn automatically
    auto_burn = params.get("auto_burn", False)
    if auto_burn:
        # Use navigation autopilot for velocity matching to zero
        nav = ship.systems.get("navigation")
        if nav:
            nav.set_autopilot({"program": "hold_velocity", "target": None})

    return success_dict(
        "Flip-and-burn initiated" + (" (auto-brake engaged)" if auto_burn else ""),
        retrograde_heading=attitude_target,
        current_velocity=round(vel_mag, 1),
        burn_estimate=burn_estimate,
        auto_burn=auto_burn,
    )


def cmd_emergency_burn(helm, ship, params):
    """Maximum thrust override - full power emergency burn.

    Immediately sets throttle to 100% (or specified direction at max thrust).
    Bypasses normal throttle ramping. Use for collision avoidance or escape.

    Args:
        helm: HelmSystem instance
        ship: Ship object
        params: Optional direction (pitch, yaw), duration

    Returns:
        dict: Emergency burn status
    """
    propulsion = ship.systems.get("propulsion")
    if not propulsion:
        return error_dict("NO_PROPULSION", "Propulsion system not available")

    if propulsion.fuel_level <= 0:
        return error_dict("NO_FUEL", "No fuel remaining for emergency burn")

    # Optional heading change
    pitch = params.get("pitch")
    yaw = params.get("yaw")
    if pitch is not None or yaw is not None:
        current = ship.orientation
        orient_params = {
            "pitch": pitch if pitch is not None else current.get("pitch", 0),
            "yaw": yaw if yaw is not None else current.get("yaw", 0),
            "roll": current.get("roll", 0),
            "_ship": ship,
            "ship": ship,
            "_from_autopilot": True,
        }
        helm._cmd_set_orientation_target(orient_params)

    # Maximum thrust immediately
    propulsion.set_throttle({"thrust": 1.0, "_ship": ship, "ship": ship})
    helm.manual_throttle = 1.0

    # Take manual control (disables autopilot)
    helm.manual_override = True
    helm.mode = "manual"
    helm.control_authority = "manual"
    helm.resume_autopilot_after_override = False

    # Disengage autopilot
    nav = ship.systems.get("navigation")
    if nav and hasattr(nav, "controller") and nav.controller:
        nav.controller.disengage_autopilot()

    # If duration specified, queue a thrust stop
    duration = params.get("duration")
    if duration is not None and duration > 0:
        # Queue the burn with a stop at the end
        thrust_cmd = {"thrust": 1.0, "duration": duration}
        normalized = helm._normalize_queue_command("thrust", thrust_cmd)
        if "error" not in normalized:
            helm._enqueue_command(normalized["command"], normalized["params"])

    max_thrust = getattr(propulsion, "max_thrust", 0)
    max_accel = max_thrust / ship.mass if ship.mass > 0 else 0

    # Publish event for combat log / alerts
    if hasattr(ship, "event_bus"):
        ship.event_bus.publish("emergency_burn", {
            "ship_id": ship.id,
            "max_thrust": max_thrust,
            "max_accel_g": round(max_accel / 9.81, 2),
            "duration": duration,
        })

    return success_dict(
        "EMERGENCY BURN - Maximum thrust engaged",
        max_thrust=max_thrust,
        max_accel_g=round(max_accel / 9.81, 2),
        fuel_remaining=round(propulsion.fuel_level, 1),
        duration=duration,
        manual_control=True,
    )


def register_commands(dispatcher):
    """Register all helm navigation commands with the dispatcher."""

    dispatcher.register("execute_burn", CommandSpec(
        handler=cmd_execute_burn,
        args=[
            ArgSpec("duration", "float", required=True, min_val=0.1, max_val=3600.0,
                    description="Burn duration in seconds"),
            ArgSpec("throttle", "float", required=False, min_val=0.0, max_val=1.0,
                    description="Throttle level (0-1)"),
            ArgSpec("g", "float", required=False, min_val=0.0, max_val=20.0,
                    description="Burn G-force (alternative to throttle)"),
            ArgSpec("pitch", "float", required=False, min_val=-90.0, max_val=90.0,
                    description="Heading pitch for burn direction"),
            ArgSpec("yaw", "float", required=False, min_val=-360.0, max_val=360.0,
                    description="Heading yaw for burn direction"),
        ],
        help_text="Execute a timed burn with specified thrust and optional heading",
        system="helm"
    ))

    dispatcher.register("plot_intercept", CommandSpec(
        handler=cmd_plot_intercept,
        args=[
            ArgSpec("target", "str", required=False,
                    description="Target contact ID to intercept"),
            ArgSpec("target_position", "dict", required=False,
                    description="Target position {x, y, z} (alternative to contact)"),
            ArgSpec("execute", "bool", required=False, default=False,
                    description="Execute the intercept plan immediately"),
        ],
        help_text="Calculate intercept/goto burn plan (delta-v, fuel, time)",
        system="helm"
    ))

    dispatcher.register("flip_and_burn", CommandSpec(
        handler=cmd_flip_and_burn,
        args=[
            ArgSpec("g", "float", required=False, min_val=0.0, max_val=20.0,
                    description="Deceleration G-force"),
            ArgSpec("throttle", "float", required=False, min_val=0.0, max_val=1.0,
                    description="Deceleration throttle (0-1)"),
            ArgSpec("auto_burn", "bool", required=False, default=False,
                    description="Automatically engage deceleration burn after flip"),
        ],
        help_text="Flip 180 degrees and decelerate (retrograde burn)",
        system="helm"
    ))

    dispatcher.register("emergency_burn", CommandSpec(
        handler=cmd_emergency_burn,
        args=[
            ArgSpec("pitch", "float", required=False, min_val=-90.0, max_val=90.0,
                    description="Emergency burn heading pitch"),
            ArgSpec("yaw", "float", required=False, min_val=-360.0, max_val=360.0,
                    description="Emergency burn heading yaw"),
            ArgSpec("duration", "float", required=False, min_val=0.1, max_val=300.0,
                    description="Burn duration (omit for continuous)"),
        ],
        help_text="Maximum thrust emergency burn (collision avoidance / escape)",
        system="helm"
    ))
