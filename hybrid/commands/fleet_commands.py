# hybrid/commands/fleet_commands.py
"""Fleet coordination commands for FLEET_COMMANDER station.

Commands:
    fleet_create: Create a new fleet/squadron
    fleet_add_ship: Add a ship to an existing fleet
    fleet_form: Form fleet into a formation
    fleet_break_formation: Break current formation
    fleet_target: Designate target for entire fleet
    fleet_fire: Order fleet to fire on designated target
    fleet_cease_fire: Order fleet to cease fire
    fleet_maneuver: Execute coordinated fleet maneuver
    fleet_status: Get comprehensive fleet status
    fleet_tactical: Get fleet tactical summary
    share_contact: Share a sensor contact via data link
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)


def cmd_fleet_create(fleet_coord, ship, params):
    """Create a new fleet/squadron."""
    cmd_params = {
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
        "fleet_id": params.get("fleet_id"),
        "name": params.get("name"),
        "flagship": params.get("flagship"),
        "ships": params.get("ships"),
    }
    return fleet_coord._cmd_fleet_create(cmd_params)


def cmd_fleet_add_ship(fleet_coord, ship, params):
    """Add a ship to an existing fleet."""
    cmd_params = {
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
        "fleet_id": params.get("fleet_id"),
        "target_ship": params.get("target_ship"),
    }
    return fleet_coord._cmd_fleet_add_ship(cmd_params)


def cmd_fleet_form(fleet_coord, ship, params):
    """Form fleet into a formation."""
    cmd_params = {
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
        "fleet_id": params.get("fleet_id"),
        "formation": params.get("formation"),
        "spacing": params.get("spacing"),
    }
    # Pass through optional formation params
    for key in ("wall_columns", "echelon_angle", "sphere_radius"):
        if params.get(key) is not None:
            cmd_params[key] = params[key]
    return fleet_coord._cmd_fleet_form(cmd_params)


def cmd_fleet_break_formation(fleet_coord, ship, params):
    """Break fleet formation."""
    cmd_params = {
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
        "fleet_id": params.get("fleet_id"),
    }
    return fleet_coord._cmd_fleet_break_formation(cmd_params)


def cmd_fleet_target(fleet_coord, ship, params):
    """Designate target for entire fleet."""
    cmd_params = {
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
        "fleet_id": params.get("fleet_id"),
        "contact": params.get("contact"),
    }
    return fleet_coord._cmd_fleet_target(cmd_params)


def cmd_fleet_fire(fleet_coord, ship, params):
    """Order fleet to fire on designated target."""
    cmd_params = {
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
        "fleet_id": params.get("fleet_id"),
        "volley": params.get("volley"),
    }
    return fleet_coord._cmd_fleet_fire(cmd_params)


def cmd_fleet_cease_fire(fleet_coord, ship, params):
    """Order fleet to cease fire."""
    cmd_params = {
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
        "fleet_id": params.get("fleet_id"),
    }
    return fleet_coord._cmd_fleet_cease_fire(cmd_params)


def cmd_fleet_maneuver(fleet_coord, ship, params):
    """Execute coordinated fleet maneuver."""
    cmd_params = {
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
        "fleet_id": params.get("fleet_id"),
        "maneuver": params.get("maneuver"),
        "position": params.get("position"),
        "velocity": params.get("velocity"),
    }
    return fleet_coord._cmd_fleet_maneuver(cmd_params)


def cmd_fleet_status(fleet_coord, ship, params):
    """Get comprehensive fleet status."""
    cmd_params = {
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
        "fleet_id": params.get("fleet_id"),
    }
    return fleet_coord._cmd_fleet_status(cmd_params)


def cmd_fleet_tactical(fleet_coord, ship, params):
    """Get fleet tactical summary."""
    cmd_params = {
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
        "fleet_id": params.get("fleet_id"),
    }
    return fleet_coord._cmd_fleet_tactical(cmd_params)


def cmd_share_contact(fleet_coord, ship, params):
    """Share a sensor contact via tactical data link."""
    cmd_params = {
        "ship": ship,
        "_ship": ship,
        "event_bus": getattr(ship, "event_bus", None),
        "contact": params.get("contact"),
        "hostile": params.get("hostile"),
    }
    return fleet_coord._cmd_share_contact(cmd_params)


def register_commands(dispatcher):
    """Register all fleet coordination commands with the dispatcher."""

    dispatcher.register("fleet_create", CommandSpec(
        handler=cmd_fleet_create,
        args=[
            ArgSpec("fleet_id", "str", required=True,
                    description="Unique fleet identifier"),
            ArgSpec("name", "str", required=False,
                    description="Human-readable fleet name"),
            ArgSpec("flagship", "str", required=False,
                    description="Flagship ship ID (defaults to commanding ship)"),
            ArgSpec("ships", "str", required=False,
                    description="Comma-separated list of ship IDs to add"),
        ],
        help_text="Create a new fleet/squadron",
        system="fleet_coord",
    ))

    dispatcher.register("fleet_add_ship", CommandSpec(
        handler=cmd_fleet_add_ship,
        args=[
            ArgSpec("fleet_id", "str", required=True,
                    description="Fleet to add ship to"),
            ArgSpec("target_ship", "str", required=True,
                    description="Ship ID to add to fleet"),
        ],
        help_text="Add a ship to an existing fleet",
        system="fleet_coord",
    ))

    dispatcher.register("fleet_form", CommandSpec(
        handler=cmd_fleet_form,
        args=[
            ArgSpec("fleet_id", "str", required=False,
                    description="Fleet to form (uses current ship's fleet if omitted)"),
            ArgSpec("formation", "str", required=False,
                    description="Formation type (line, column, wall, sphere, wedge, echelon, diamond)"),
            ArgSpec("spacing", "float", required=False, min_val=100, max_val=50000,
                    description="Distance between ships in meters (default 2000)"),
            ArgSpec("wall_columns", "int", required=False,
                    description="Columns for wall formation"),
            ArgSpec("echelon_angle", "float", required=False,
                    description="Angle for echelon formation"),
            ArgSpec("sphere_radius", "float", required=False,
                    description="Radius for sphere formation"),
        ],
        help_text="Form fleet into a formation",
        system="fleet_coord",
    ))

    dispatcher.register("fleet_break_formation", CommandSpec(
        handler=cmd_fleet_break_formation,
        args=[
            ArgSpec("fleet_id", "str", required=False,
                    description="Fleet to break (uses current ship's fleet if omitted)"),
        ],
        help_text="Break current fleet formation",
        system="fleet_coord",
    ))

    dispatcher.register("fleet_target", CommandSpec(
        handler=cmd_fleet_target,
        args=[
            ArgSpec("fleet_id", "str", required=False,
                    description="Fleet to command (uses current ship's fleet if omitted)"),
            ArgSpec("contact", "str", required=True,
                    description="Contact ID to designate as fleet target"),
        ],
        help_text="Designate target for entire fleet",
        system="fleet_coord",
    ))

    dispatcher.register("fleet_fire", CommandSpec(
        handler=cmd_fleet_fire,
        args=[
            ArgSpec("fleet_id", "str", required=False,
                    description="Fleet to command (uses current ship's fleet if omitted)"),
            ArgSpec("volley", "bool", required=False,
                    description="True for coordinated volley, False for independent fire"),
        ],
        help_text="Order fleet to fire on designated target",
        system="fleet_coord",
    ))

    dispatcher.register("fleet_cease_fire", CommandSpec(
        handler=cmd_fleet_cease_fire,
        args=[
            ArgSpec("fleet_id", "str", required=False,
                    description="Fleet to command (uses current ship's fleet if omitted)"),
        ],
        help_text="Order fleet to cease fire",
        system="fleet_coord",
    ))

    dispatcher.register("fleet_maneuver", CommandSpec(
        handler=cmd_fleet_maneuver,
        args=[
            ArgSpec("fleet_id", "str", required=False,
                    description="Fleet to command (uses current ship's fleet if omitted)"),
            ArgSpec("maneuver", "str", required=False,
                    description="Maneuver type (intercept, match_velocity, hold, evasive)"),
            ArgSpec("position", "str", required=False,
                    description="Target position [x, y, z]"),
            ArgSpec("velocity", "str", required=False,
                    description="Target velocity [vx, vy, vz]"),
        ],
        help_text="Execute coordinated fleet maneuver",
        system="fleet_coord",
    ))

    dispatcher.register("fleet_status", CommandSpec(
        handler=cmd_fleet_status,
        args=[
            ArgSpec("fleet_id", "str", required=False,
                    description="Fleet to query (lists all fleets if omitted)"),
        ],
        help_text="Get comprehensive fleet status",
        system="fleet_coord",
    ))

    dispatcher.register("fleet_tactical", CommandSpec(
        handler=cmd_fleet_tactical,
        args=[
            ArgSpec("fleet_id", "str", required=False,
                    description="Fleet to query (uses current ship's fleet if omitted)"),
        ],
        help_text="Get fleet tactical summary",
        system="fleet_coord",
    ))

    dispatcher.register("share_contact", CommandSpec(
        handler=cmd_share_contact,
        args=[
            ArgSpec("contact", "str", required=True,
                    description="Contact ID to share with fleet"),
            ArgSpec("hostile", "bool", required=False,
                    description="Mark contact as hostile (default: False)"),
        ],
        help_text="Share a sensor contact via tactical data link",
        system="fleet_coord",
    ))
