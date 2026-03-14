# hybrid/telemetry.py
"""Unified telemetry snapshot system for consistent state export.

Includes delta-v budget and point-of-no-return (PONR) calculations for
hard-sci navigation — the player always knows whether they can still
stop, and how much velocity-change budget remains.
"""

import math
import time
from typing import Dict, List, Any, Optional
from hybrid.utils.math_utils import magnitude, calculate_distance, calculate_bearing
from hybrid.utils.units import calculate_delta_v

# Standard gravity (m/s²)
_G0 = 9.81


def _compute_ponr(velocity_magnitude: float, delta_v_remaining: float,
                  max_thrust: float, ship_mass: float, isp: float,
                  fuel_level: float, dry_mass: float) -> Dict[str, Any]:
    """Compute point-of-no-return data for deceleration.

    The PONR tells the player: at your current speed, can you still
    brake to a stop with remaining fuel? And how much delta-v margin
    do you have beyond the braking budget?

    Args:
        velocity_magnitude: Current speed in m/s
        delta_v_remaining: Total remaining delta-v in m/s
        max_thrust: Maximum thrust in Newtons
        ship_mass: Current total mass in kg
        isp: Specific impulse in seconds
        fuel_level: Current fuel in kg
        dry_mass: Structural mass without fuel in kg

    Returns:
        dict with PONR status and margins
    """
    if delta_v_remaining <= 0 or velocity_magnitude <= 0.01:
        return {
            "can_stop": delta_v_remaining > 0 or velocity_magnitude <= 0.01,
            "dv_to_stop": 0.0,
            "dv_margin": delta_v_remaining,
            "margin_percent": 100.0 if delta_v_remaining > 0 else 0.0,
            "stop_distance": 0.0,
            "stop_time": 0.0,
            "past_ponr": False,
        }

    # Delta-v needed to decelerate from current speed to zero
    dv_to_stop = velocity_magnitude

    # Margin: how much delta-v remains after a full stop burn
    dv_margin = delta_v_remaining - dv_to_stop
    margin_pct = (dv_margin / delta_v_remaining * 100.0) if delta_v_remaining > 0 else 0.0
    can_stop = dv_margin >= 0

    # Estimate stopping distance and time (constant-thrust approximation)
    # Uses average acceleration during deceleration burn
    stop_distance = 0.0
    stop_time = 0.0
    if max_thrust > 0 and ship_mass > 0:
        # Average acceleration during braking (mass decreases as fuel burns)
        # Use geometric mean of initial and final acceleration
        exhaust_vel = isp * _G0
        if exhaust_vel > 0 and can_stop:
            # Fuel consumed to stop = m0 * (1 - exp(-dv_to_stop / Ve))
            fuel_to_stop = ship_mass * (1.0 - math.exp(-dv_to_stop / exhaust_vel))
            final_mass = max(ship_mass - fuel_to_stop, dry_mass)
            avg_accel = max_thrust / ((ship_mass + final_mass) / 2.0)
            if avg_accel > 0:
                stop_time = dv_to_stop / avg_accel
                stop_distance = velocity_magnitude * stop_time - 0.5 * avg_accel * stop_time ** 2
                stop_distance = max(0.0, stop_distance)

    return {
        "can_stop": can_stop,
        "dv_to_stop": round(dv_to_stop, 1),
        "dv_margin": round(dv_margin, 1),
        "margin_percent": round(margin_pct, 1),
        "stop_distance": round(stop_distance, 1),
        "stop_time": round(stop_time, 1),
        "past_ponr": not can_stop,
    }


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
    isp = 3000.0
    max_thrust = 0.0

    if propulsion and hasattr(propulsion, "get_state"):
        prop_state = propulsion.get_state()
        fuel_level = prop_state.get("fuel_level", 0.0)
        max_fuel = prop_state.get("max_fuel", 1.0)
        fuel_percent = prop_state.get("fuel_percent", 0.0)
        isp = getattr(propulsion, "isp", 3000.0)
        max_thrust = getattr(propulsion, "max_thrust", 0.0)

        # Calculate delta-v using Tsiolkovsky equation
        dry_mass = getattr(ship, "dry_mass", max(0.0, ship.mass - fuel_level))
        delta_v_remaining = calculate_delta_v(dry_mass, fuel_level, isp)

    # Get targeting data
    target_id = getattr(ship, "target_id", None)
    target_subsystem = getattr(ship, "target_subsystem", None)
    targeting = ship.systems.get("targeting")
    if targeting:
        target_id = target_id or getattr(targeting, "locked_target", target_id)
        target_subsystem = getattr(targeting, "target_subsystem", target_subsystem)

    # Get navigation mode
    nav = ship.systems.get("navigation")
    nav_mode = "manual"
    autopilot_program = None

    autopilot_state = None
    course_info = None
    if nav and hasattr(nav, "get_state"):
        nav_state = nav.get_state()
        nav_mode = "autopilot" if nav_state.get("autopilot_enabled", False) else "manual"
        autopilot_program = nav_state.get("current_program")
        autopilot_state = nav_state.get("autopilot_state")
        course_info = nav_state.get("course")

    # Get helm queue status
    helm_queue = None
    helm = ship.systems.get("helm")
    if helm and hasattr(helm, "get_queue_state"):
        helm_queue = helm.get_queue_state()

    # Get weapons status
    weapons_status = get_weapons_status(ship)

    # Get sensor contacts and emissions
    sensor_contacts = get_sensor_contacts(ship)

    # Get own-ship emission data (what others can see)
    emissions = _get_ship_emissions(ship)

    # Drift state: moving with no thrust applied
    is_drifting = acceleration_magnitude < 0.001 and velocity_magnitude > 0.01

    # Point-of-no-return calculation
    dry_mass = getattr(ship, "dry_mass", max(0.0, ship.mass - fuel_level))
    ponr = _compute_ponr(
        velocity_magnitude=velocity_magnitude,
        delta_v_remaining=delta_v_remaining,
        max_thrust=max_thrust,
        ship_mass=ship.mass,
        isp=isp,
        fuel_level=fuel_level,
        dry_mass=dry_mass,
    )

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
        "dry_mass": getattr(ship, "dry_mass", ship.mass),
        "moment_of_inertia": getattr(ship, "moment_of_inertia", 0.0),
        "is_drifting": is_drifting,
        "fuel": {
            "level": fuel_level,
            "max": max_fuel,
            "percent": fuel_percent
        },
        "delta_v_remaining": delta_v_remaining,
        "ponr": ponr,
        "target_id": target_id,
        "target_subsystem": target_subsystem,
        "nav_mode": nav_mode,
        "autopilot_program": autopilot_program,
        "autopilot_state": autopilot_state,
        "course": course_info,
        "helm_queue": helm_queue,
        "weapons": weapons_status,
        "sensors": sensor_contacts,
        "emissions": emissions,
        "subsystem_health": ship.damage_model.get_report() if hasattr(ship, "damage_model") else {},
        "cascade_effects": ship.cascade_manager.get_report() if hasattr(ship, "cascade_manager") else {},
        "systems": {
            system_name: system.get("status", "unknown") if isinstance(system, dict) else
                         system.get_state().get("status", "online") if hasattr(system, "get_state") else "online"
            for system_name, system in ship.systems.items()
        },
        "timestamp": sim_time
    }

def _get_ship_emissions(ship) -> Dict[str, Any]:
    """Get own-ship emission data for telemetry.

    Shows the player what emissions their ship is producing —
    how visible they are to enemy sensors.

    Args:
        ship: Ship object

    Returns:
        dict: Emission data (ir_watts, rcs_m2, ir_detection_range, is_thrusting)
    """
    try:
        from hybrid.systems.sensors.emission_model import get_ship_emissions
        return get_ship_emissions(ship)
    except Exception:
        return {
            "ir_watts": 0.0,
            "rcs_m2": 0.0,
            "ir_detection_range": 0.0,
            "is_thrusting": False,
            "thrust_magnitude": 0.0,
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

    Reads from SensorSystem.contact_tracker (the single source of truth for
    merged, de-duplicated contacts with stable IDs like C001).  Falls back to
    reading raw passive/active contact dicts only for legacy dict-based sensor
    systems that lack a ContactTracker.

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

    # Prefer ContactTracker — it holds merged contacts with stable IDs (C001)
    # and already de-duplicates passive + active detections.
    if hasattr(sensors, "contact_tracker"):
        sim_time = getattr(sensors, "sim_time", 0.0)
        all_contacts = sensors.contact_tracker.get_all_contacts(sim_time)

        for contact_id, contact in all_contacts.items():
            position = getattr(contact, "position", ship.position)
            distance = calculate_distance(ship.position, position)
            bearing = calculate_bearing(ship.position, position)

            pos_dict = _serialize_vector(position)
            vel_dict = _serialize_vector(getattr(contact, "velocity", None))

            contacts_list.append({
                "id": contact_id,
                "position": pos_dict,
                "velocity": vel_dict,
                "distance": distance,
                "bearing": bearing,
                "confidence": getattr(contact, "confidence", 0.5),
                "last_update": getattr(contact, "last_update", 0),
                "detection_method": getattr(contact, "detection_method", "passive"),
                "name": getattr(contact, "name", None),
                "classification": getattr(contact, "classification", None),
            })
    else:
        # Legacy fallback for dict-based sensors without ContactTracker
        contacts_list = _get_contacts_from_raw_sensors(sensors, ship)

    # Sort by distance
    contacts_list.sort(key=lambda c: c["distance"])

    return {
        "available": True,
        "contacts": contacts_list,
        "count": len(contacts_list)
    }


def _serialize_vector(vec) -> Optional[Dict[str, float]]:
    """Serialize a position/velocity to a plain dict for JSON transport."""
    if vec is None:
        return None
    if hasattr(vec, "x"):
        return {"x": vec.x, "y": vec.y, "z": getattr(vec, "z", 0)}
    if isinstance(vec, dict):
        return {"x": vec.get("x", 0), "y": vec.get("y", 0), "z": vec.get("z", 0)}
    return None


def _get_contacts_from_raw_sensors(sensors, ship) -> List[Dict[str, Any]]:
    """Legacy fallback: read contacts directly from passive/active subsystems.

    Used only when the sensor system has no ContactTracker (old dict-based
    sensors).  New code should always use ContactTracker.
    """
    contacts_list = []

    def contact_value(contact: Any, key: str, default: Any = None) -> Any:
        if isinstance(contact, dict):
            if key == "last_update":
                return contact.get("last_update", contact.get("last_updated", default))
            return contact.get(key, default)
        return getattr(contact, key, default)

    if hasattr(sensors, "passive") and hasattr(sensors.passive, "contacts"):
        for contact_id, contact in sensors.passive.contacts.items():
            position = contact_value(contact, "position", ship.position)
            distance = calculate_distance(ship.position, position)
            bearing = calculate_bearing(ship.position, position)

            contacts_list.append({
                "id": contact_id,
                "position": _serialize_vector(position),
                "velocity": _serialize_vector(contact_value(contact, "velocity", None)),
                "distance": distance,
                "bearing": bearing,
                "confidence": contact_value(contact, "confidence", 0.5),
                "last_update": contact_value(contact, "last_update", 0),
                "detection_method": contact_value(contact, "detection_method", "passive"),
                "name": contact_value(contact, "name", None),
                "classification": contact_value(contact, "classification", None),
            })

    if hasattr(sensors, "active") and hasattr(sensors.active, "contacts"):
        for contact_id, contact in sensors.active.contacts.items():
            if any(c["id"] == contact_id for c in contacts_list):
                continue
            position = contact_value(contact, "position", ship.position)
            distance = calculate_distance(ship.position, position)
            bearing = calculate_bearing(ship.position, position)

            contacts_list.append({
                "id": contact_id,
                "position": _serialize_vector(position),
                "velocity": _serialize_vector(contact_value(contact, "velocity", None)),
                "distance": distance,
                "bearing": bearing,
                "confidence": contact_value(contact, "confidence", 0.9),
                "last_update": contact_value(contact, "last_update", 0),
                "detection_method": contact_value(contact, "detection_method", "active"),
                "name": contact_value(contact, "name", None),
                "classification": contact_value(contact, "classification", None),
            })

    return contacts_list

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

    # Get active projectiles from ProjectileManager
    projectiles = []
    if hasattr(sim, "projectile_manager"):
        projectiles = sim.projectile_manager.get_state()
    elif hasattr(sim, "projectiles"):
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

    # Get tick metrics
    tick_metrics = {}
    if hasattr(sim, "get_tick_metrics"):
        tick_metrics = sim.get_tick_metrics()

    return {
        "tick": tick,
        "sim_time": sim_time,
        "dt": dt,
        "ships": ships_telemetry,
        "projectiles": projectiles,
        "events": events,
        "tick_metrics": tick_metrics,
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
