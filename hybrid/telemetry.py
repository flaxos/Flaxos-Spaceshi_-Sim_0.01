# hybrid/telemetry.py
"""Unified telemetry snapshot system for consistent state export."""

import time
from typing import Dict, List, Any, Optional
from hybrid.utils.math_utils import magnitude, calculate_distance, calculate_bearing
from hybrid.utils.units import calculate_delta_v

def get_ship_telemetry(ship, sim_time: float = None) -> Dict[str, Any]:
    """Get comprehensive telemetry for a single ship.

    Args:
        ship: Ship object
        sim_time (float, optional): Current simulation time

    Returns:
        dict: Ship telemetry data
    """
    if sim_time is None:
        sim_time = time.time()

    # Get basic state
    state = ship.get_state()

    # Calculate derived metrics
    velocity_magnitude = magnitude(ship.velocity)
    acceleration_magnitude = magnitude(ship.acceleration)

    # Get propulsion data
    propulsion = ship.systems.get("propulsion")
    fuel_level = 0.0
    max_fuel = 0.0
    fuel_percent = 0.0
    delta_v_remaining = 0.0

    if propulsion and hasattr(propulsion, "get_state"):
        prop_state = propulsion.get_state()
        fuel_level = prop_state.get("fuel_level", 0.0)
        max_fuel = prop_state.get("max_fuel", 1.0)
        fuel_percent = prop_state.get("fuel_percent", 0.0)

        # Calculate delta-v if we have ISP data
        if hasattr(propulsion, "efficiency") and ship.mass > 0:
            dry_mass = max(0.0, ship.mass - fuel_level)  # Ensure non-negative
            isp = getattr(propulsion, "isp", 3000)  # Default ISP
            delta_v_remaining = calculate_delta_v(dry_mass, fuel_level, isp)

    # Get targeting data
    target_id = getattr(ship, "target_id", None)

    # Get navigation mode
    nav = ship.systems.get("navigation")
    nav_mode = "manual"
    autopilot_program = None

    if nav and hasattr(nav, "get_state"):
        nav_state = nav.get_state()
        nav_mode = "autopilot" if nav_state.get("autopilot_enabled", False) else "manual"
        autopilot_program = nav_state.get("current_program")

    # Get weapons status
    weapons_status = get_weapons_status(ship)

    # Get sensor contacts
    sensor_contacts = get_sensor_contacts(ship)

    return {
        "id": ship.id,
        "name": ship.name,
        "class": ship.class_type,
        "faction": ship.faction,
        "position": ship.position,
        "velocity": ship.velocity,
        "velocity_magnitude": velocity_magnitude,
        "acceleration": ship.acceleration,
        "acceleration_magnitude": acceleration_magnitude,
        "orientation": ship.orientation,
        "angular_velocity": ship.angular_velocity,
        "mass": ship.mass,
        "fuel": {
            "level": fuel_level,
            "max": max_fuel,
            "percent": fuel_percent
        },
        "delta_v_remaining": delta_v_remaining,
        "target_id": target_id,
        "nav_mode": nav_mode,
        "autopilot_program": autopilot_program,
        "weapons": weapons_status,
        "sensors": sensor_contacts,
        "systems": {
            system_name: system.get("status", "unknown") if isinstance(system, dict) else
                         system.get_state().get("status", "online") if hasattr(system, "get_state") else "online"
            for system_name, system in ship.systems.items()
        },
        "timestamp": sim_time
    }

def get_weapons_status(ship) -> Dict[str, Any]:
    """Get weapons system status.

    Args:
        ship: Ship object

    Returns:
        dict: Weapons status
    """
    weapons = ship.systems.get("weapons")

    if not weapons:
        return {
            "available": False,
            "armed": [],
            "status": "offline"
        }

    if hasattr(weapons, "get_state"):
        weapon_state = weapons.get_state()
        return {
            "available": True,
            "armed": weapon_state.get("armed_weapons", []),
            "status": weapon_state.get("status", "online"),
            "weapons": weapon_state.get("weapons", {})
        }

    return {
        "available": True,
        "status": "online"
    }

def get_sensor_contacts(ship) -> Dict[str, Any]:
    """Get sensor contacts for a ship.

    Args:
        ship: Ship object

    Returns:
        dict: Sensor contacts data
    """
    sensors = ship.systems.get("sensors")

    if not sensors:
        return {
            "available": False,
            "contacts": [],
            "count": 0
        }

    contacts_list = []

    def contact_value(contact: Any, key: str, default: Any = None) -> Any:
        if isinstance(contact, dict):
            if key == "last_update":
                return contact.get("last_update", contact.get("last_updated", default))
            return contact.get(key, default)
        return getattr(contact, key, default)

    # Get passive contacts
    if hasattr(sensors, "passive") and hasattr(sensors.passive, "contacts"):
        for contact_id, contact in sensors.passive.contacts.items():
            position = contact_value(contact, "position", ship.position)
            distance = calculate_distance(ship.position, position)
            bearing = calculate_bearing(ship.position, position)

            contacts_list.append({
                "id": contact_id,
                "distance": distance,
                "bearing": bearing,
                "confidence": contact_value(contact, "confidence", 0.5),
                "last_update": contact_value(contact, "last_update", 0),
                "detection_method": contact_value(contact, "detection_method", "passive")
            })

    # Get active contacts
    if hasattr(sensors, "active") and hasattr(sensors.active, "contacts"):
        for contact_id, contact in sensors.active.contacts.items():
            # Skip if already in passive contacts
            if any(c["id"] == contact_id for c in contacts_list):
                continue

            position = contact_value(contact, "position", ship.position)
            distance = calculate_distance(ship.position, position)
            bearing = calculate_bearing(ship.position, position)

            contacts_list.append({
                "id": contact_id,
                "distance": distance,
                "bearing": bearing,
                "confidence": contact_value(contact, "confidence", 0.9),
                "last_update": contact_value(contact, "last_update", 0),
                "detection_method": contact_value(contact, "detection_method", "active")
            })

    # Sort by distance
    contacts_list.sort(key=lambda c: c["distance"])

    return {
        "available": True,
        "contacts": contacts_list,
        "count": len(contacts_list)
    }

def get_telemetry_snapshot(sim, recent_events_limit: int = 50) -> Dict[str, Any]:
    """Get complete telemetry snapshot of the simulation.

    Args:
        sim: Simulator object
        recent_events_limit (int): Number of recent events to include

    Returns:
        dict: Complete telemetry snapshot
    """
    sim_time = getattr(sim, "time", time.time())
    tick = getattr(sim, "tick", 0)
    dt = getattr(sim, "dt", 0.1)

    ships_telemetry = {}
    if hasattr(sim, "ships"):
        for ship_id, ship in sim.ships.items():
            ships_telemetry[ship_id] = get_ship_telemetry(ship, sim_time)

    # Get projectiles/missiles
    projectiles = []
    if hasattr(sim, "projectiles"):
        for proj in sim.projectiles:
            projectiles.append({
                "id": getattr(proj, "id", "unknown"),
                "type": getattr(proj, "type", "unknown"),
                "position": getattr(proj, "position", {"x": 0, "y": 0, "z": 0}),
                "velocity": getattr(proj, "velocity", {"x": 0, "y": 0, "z": 0}),
                "source": getattr(proj, "source_id", None),
                "target": getattr(proj, "target_id", None),
            })

    # Get recent events
    events = []
    if hasattr(sim, "event_log"):
        events = sim.event_log[-recent_events_limit:]
    elif hasattr(sim, "recent_events"):
        events = sim.recent_events[-recent_events_limit:]

    return {
        "tick": tick,
        "sim_time": sim_time,
        "dt": dt,
        "ships": ships_telemetry,
        "projectiles": projectiles,
        "events": events,
        "timestamp": time.time()
    }

def format_telemetry_for_display(telemetry: Dict[str, Any], ship_id: str = None) -> str:
    """Format telemetry snapshot for human-readable display.

    Args:
        telemetry (dict): Telemetry snapshot
        ship_id (str, optional): Specific ship to format (None for all)

    Returns:
        str: Formatted telemetry
    """
    from hybrid.utils.units import format_distance, format_velocity, format_heading, format_vector

    output = []
    output.append(f"=== TELEMETRY SNAPSHOT ===")
    output.append(f"Tick: {telemetry['tick']}")
    output.append(f"Sim Time: {telemetry['sim_time']:.2f}s")
    output.append(f"dt: {telemetry['dt']}s")
    output.append("")

    ships = telemetry["ships"]
    if ship_id:
        ships = {ship_id: ships[ship_id]} if ship_id in ships else {}

    for sid, ship in ships.items():
        output.append(f"--- {ship['name']} ({sid}) ---")
        output.append(f"  Position: {format_vector(ship['position'])}")
        output.append(f"  Velocity: {format_velocity(ship['velocity_magnitude'])}")
        output.append(f"  Heading: {format_heading(ship['orientation'])}")
        output.append(f"  Fuel: {ship['fuel']['percent']:.1f}%")
        output.append(f"  Δv: {ship['delta_v_remaining']:.0f} m/s")
        output.append(f"  Nav Mode: {ship['nav_mode']}")

        if ship['target_id']:
            output.append(f"  Target: {ship['target_id']}")

        output.append(f"  Contacts: {ship['sensors']['count']}")
        output.append("")

    output.append(f"Projectiles: {len(telemetry['projectiles'])}")
    output.append(f"Recent Events: {len(telemetry['events'])}")

    return "\n".join(output)
