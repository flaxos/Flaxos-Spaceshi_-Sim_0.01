# hybrid/commands/sensor_commands.py
"""Sensor and targeting commands."""

from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec, validate_contact_id
from hybrid.utils.errors import success_dict, error_dict

def cmd_ping(sensors, ship, params):
    """Active sensor ping."""
    if sensors and hasattr(sensors, "ping"):
        # Get all_ships from sensor, or fall back to ship's reference
        all_ships = getattr(sensors, "all_ships", None)
        if not all_ships:
            # Fall back to ship's _all_ships_ref set by simulator/scenario loader
            all_ships = getattr(ship, "_all_ships_ref", [])
            # Update sensor's all_ships for future use
            if all_ships:
                sensors.all_ships = all_ships

        # Pass required parameters for ping
        ping_params = {
            "ship": ship,
            "all_ships": all_ships,
            "event_bus": ship.event_bus if hasattr(ship, "event_bus") else None
        }
        return sensors.ping(ping_params)

    return error_dict("NOT_IMPLEMENTED", "Active ping not yet implemented")

def cmd_contacts(sensors, ship, params):
    """List all sensor contacts."""
    # Ensure sensor has all_ships reference for proper operation
    if sensors and not getattr(sensors, "all_ships", None):
        all_ships = getattr(ship, "_all_ships_ref", [])
        if all_ships:
            sensors.all_ships = all_ships

    if sensors and hasattr(sensors, "get_contacts_list"):
        # Use the new API with proper parameters
        list_params = {
            "observer_position": ship.position,
            "observer_velocity": ship.velocity,
            "include_stale": params.get("include_stale", False)
        }
        return sensors.get_contacts_list(list_params)
    elif sensors and hasattr(sensors, "get_contacts"):
        contacts = sensors.get_contacts()
        return success_dict(
            f"{len(contacts)} contacts detected",
            contacts=list(contacts.values()) if isinstance(contacts, dict) else contacts
        )

    return error_dict("NOT_IMPLEMENTED", "Contact listing not yet implemented")

def cmd_target(ship, params):
    """Lock a target."""
    contact_id = params.get("contact_id")
    target_subsystem = params.get("target_subsystem")

    # Check if ship has targeting system
    targeting = ship.systems.get("targeting")
    if targeting and hasattr(targeting, "lock_target"):
        result = targeting.lock_target(contact_id)
        if target_subsystem is not None and hasattr(targeting, "set_target_subsystem"):
            subsystem_result = targeting.set_target_subsystem(target_subsystem, ship)
            result["target_subsystem"] = subsystem_result.get("target_subsystem")
            if not subsystem_result.get("ok"):
                result["target_subsystem_error"] = subsystem_result.get("error")
        return result

    # Fallback: store target on ship for now
    ship.target_id = contact_id
    if target_subsystem is not None:
        ship.target_subsystem = target_subsystem
    return success_dict(f"Target locked: {contact_id}", target=contact_id)

def cmd_target_subsystem(ship, params):
    """Set targeted subsystem."""
    target_subsystem = params.get("target_subsystem")
    targeting = ship.systems.get("targeting")
    if targeting and hasattr(targeting, "set_target_subsystem"):
        return targeting.set_target_subsystem(target_subsystem, ship)

    ship.target_subsystem = target_subsystem
    return success_dict("Target subsystem set", target_subsystem=target_subsystem)

def cmd_untarget(ship, params):
    """Unlock current target."""
    targeting = ship.systems.get("targeting")
    if targeting and hasattr(targeting, "unlock_target"):
        return targeting.unlock_target()

    # Fallback: clear ship target
    if hasattr(ship, "target_id"):
        ship.target_id = None

    return success_dict("Target unlocked")

def register_commands(dispatcher):
    """Register all sensor commands with the dispatcher."""

    dispatcher.register("ping", CommandSpec(
        handler=cmd_ping,
        args=[],
        help_text="Active sensor ping (reveals nearby contacts)",
        system="sensors"
    ))

    dispatcher.register("contacts", CommandSpec(
        handler=cmd_contacts,
        args=[],
        help_text="List all sensor contacts",
        system="sensors"
    ))

    dispatcher.register("target", CommandSpec(
        handler=cmd_target,
        args=[
            ArgSpec("contact_id", "str", required=True,
                    description="Contact ID to lock as target"),
            ArgSpec("target_subsystem", "str", required=False,
                    description="Subsystem to target (optional)")
        ],
        help_text="Lock a target by contact ID"
    ))

    dispatcher.register("target_subsystem", CommandSpec(
        handler=cmd_target_subsystem,
        args=[
            ArgSpec("target_subsystem", "str", required=True,
                    description="Subsystem to target")
        ],
        help_text="Set subsystem targeting for the locked target"
    ))

    dispatcher.register("set_target_subsystem", CommandSpec(
        handler=cmd_target_subsystem,
        args=[
            ArgSpec("target_subsystem", "str", required=True,
                    description="Subsystem to target")
        ],
        help_text="Set subsystem targeting for the locked target"
    ))

    dispatcher.register("untarget", CommandSpec(
        handler=cmd_untarget,
        args=[],
        help_text="Unlock current target"
    ))
