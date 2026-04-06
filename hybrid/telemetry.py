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

    fuel_burn_rate = 0.0
    fuel_time_remaining = None

    if propulsion and hasattr(propulsion, "get_state"):
        prop_state = propulsion.get_state()
        fuel_level = prop_state.get("fuel_level", 0.0)
        max_fuel = prop_state.get("max_fuel", 1.0)
        fuel_percent = prop_state.get("fuel_percent", 0.0)
        fuel_burn_rate = prop_state.get("fuel_burn_rate", 0.0)
        fuel_time_remaining = prop_state.get("fuel_time_remaining")
        isp = getattr(propulsion, "isp", 3000.0)
        max_thrust = getattr(propulsion, "max_thrust", 0.0)

        # Calculate delta-v using Tsiolkovsky equation
        dry_mass = getattr(ship, "dry_mass", max(0.0, ship.mass - fuel_level))
        delta_v_remaining = calculate_delta_v(dry_mass, fuel_level, isp)

    # Get targeting data — expose the full pipeline state so the GUI
    # can render each stage: contact → track → lock → solution → fire.
    target_id = getattr(ship, "target_id", None)
    target_subsystem = getattr(ship, "target_subsystem", None)
    targeting = ship.systems.get("targeting")
    targeting_state = None
    if targeting:
        target_id = target_id or getattr(targeting, "locked_target", target_id)
        target_subsystem = getattr(targeting, "target_subsystem", target_subsystem)
        if hasattr(targeting, "get_state"):
            targeting_state = targeting.get_state()

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

    # Get thermal system state
    thermal_state = _get_thermal_state(ship)

    # Get ops system state (power allocation, repair teams, priorities)
    ops_state = _get_ops_state(ship)

    # Get ECM system state (jamming, chaff, flares, EMCON)
    ecm_state = _get_ecm_state(ship)

    # Get ECCM system state (frequency hop, burn-through, multi-spectral, HoJ)
    eccm_state = _get_eccm_state(ship)

    # Get engineering system state (reactor output, drive limit, radiators, fuel, vent)
    engineering_state = _get_engineering_state(ship)

    # Get comms system state (transponder, radio, distress)
    comms_state = _get_comms_state(ship)

    # Get docking system state
    docking_state = _get_docking_state(ship)

    # Get crew fatigue system state
    crew_fatigue_state = _get_crew_fatigue_state(ship)

    # Get crew progression data (XP, injury states, skill levels)
    crew_progression_state = _get_crew_progression_state(ship)

    # Get auto-system states (CPU-ASSIST tier)
    auto_tactical_state = _get_auto_system_state(ship, "auto_tactical")
    auto_ops_state = _get_auto_system_state(ship, "auto_ops")
    auto_engineering_state = _get_auto_system_state(ship, "auto_engineering")
    auto_science_state = _get_auto_system_state(ship, "auto_science")
    auto_comms_state = _get_auto_system_state(ship, "auto_comms")

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

    # Trajectory projection for navigation displays
    trajectory = _compute_trajectory_projection(
        ship, velocity_magnitude, acceleration_magnitude,
        max_thrust, delta_v_remaining,
    )

    # Flight computer status
    flight_computer_status = _get_flight_computer_status(ship)

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
            "percent": fuel_percent,
            "burn_rate": fuel_burn_rate,
            "time_remaining": fuel_time_remaining,
        },
        "delta_v_remaining": delta_v_remaining,
        "ponr": ponr,
        "target_id": target_id,
        "target_subsystem": target_subsystem,
        "targeting": targeting_state,
        "nav_mode": nav_mode,
        "autopilot_program": autopilot_program,
        "autopilot_state": autopilot_state,
        "course": course_info,
        "helm_queue": helm_queue,
        "trajectory": trajectory,
        "flight_computer": flight_computer_status,
        "weapons": weapons_status,
        "ammo_mass": weapons_status.get("total_ammo_mass", 0.0),
        "sensors": sensor_contacts,
        "emissions": emissions,
        "thermal": thermal_state,
        "ops": ops_state,
        "ecm": ecm_state,
        "eccm": eccm_state,
        "engineering": engineering_state,
        "comms": comms_state,
        "docking": docking_state,
        "crew_fatigue": crew_fatigue_state,
        "crew_progression": crew_progression_state,
        "auto_tactical": auto_tactical_state,
        "auto_ops": auto_ops_state,
        "auto_engineering": auto_engineering_state,
        "auto_science": auto_science_state,
        "auto_comms": auto_comms_state,
        "hull_integrity": getattr(ship, "hull_integrity", 0.0),
        "max_hull_integrity": getattr(ship, "max_hull_integrity", 0.0),
        "hull_percent": (
            round(ship.hull_integrity / ship.max_hull_integrity * 100.0, 1)
            if getattr(ship, "max_hull_integrity", 0) > 0 else 0.0
        ),
        "subsystem_health": ship.damage_model.get_report() if hasattr(ship, "damage_model") else {},
        "cascade_effects": ship.cascade_manager.get_report() if hasattr(ship, "cascade_manager") else {},
        "systems": {
            system_name: system.get("status", "unknown") if isinstance(system, dict) else
                         system.get_state().get("status", "online") if hasattr(system, "get_state") else "online"
            for system_name, system in ship.systems.items()
        },
        # Ship class metadata (from modular ship definitions)
        "dimensions": getattr(ship, "dimensions", None),
        "armor": getattr(ship, "armor", None),
        # Live armor state with ablation tracking (None if no armor model)
        "armor_status": (
            ship.armor_model.get_status()
            if hasattr(ship, "armor_model") and ship.armor_model is not None
            else None
        ),
        "crew_complement": getattr(ship, "crew_complement", None),
        "weapon_mounts": getattr(ship, "weapon_mounts", None),
        "timestamp": sim_time
    }

def _compute_trajectory_projection(ship, velocity_magnitude: float,
                                     acceleration_magnitude: float,
                                     max_thrust: float,
                                     delta_v_remaining: float) -> Dict[str, Any]:
    """Compute trajectory projection data for navigation displays.

    Projects the ship's future position based on current velocity and
    acceleration, and calculates useful navigation metrics.

    Args:
        ship: Ship object
        velocity_magnitude: Current speed (m/s)
        acceleration_magnitude: Current acceleration magnitude (m/s^2)
        max_thrust: Maximum thrust (N)
        delta_v_remaining: Remaining delta-v budget (m/s)

    Returns:
        dict: Trajectory projection data
    """
    max_accel = max_thrust / ship.mass if ship.mass > 0 and max_thrust > 0 else 0

    # Velocity heading (prograde direction)
    vel_heading = {"pitch": 0.0, "yaw": 0.0}
    if velocity_magnitude > 0.01:
        vx = ship.velocity.get("x", 0)
        vy = ship.velocity.get("y", 0)
        vz = ship.velocity.get("z", 0)
        yaw = math.degrees(math.atan2(vy, vx))
        horiz = math.sqrt(vx**2 + vy**2)
        pitch = math.degrees(math.atan2(vz, horiz)) if horiz > 0.001 else 0.0
        vel_heading = {"pitch": round(pitch, 1), "yaw": round(yaw, 1)}

    # Projected position at t+10s, t+30s, t+60s (linear extrapolation)
    projections = []
    for dt in (10, 30, 60):
        proj_pos = {
            "x": round(ship.position["x"] + ship.velocity["x"] * dt + 0.5 * ship.acceleration["x"] * dt**2, 1),
            "y": round(ship.position["y"] + ship.velocity["y"] * dt + 0.5 * ship.acceleration["y"] * dt**2, 1),
            "z": round(ship.position["z"] + ship.velocity["z"] * dt + 0.5 * ship.acceleration["z"] * dt**2, 1),
        }
        projections.append({"t": dt, "position": proj_pos})

    # Ship heading vs velocity heading drift angle
    drift_angle = 0.0
    if velocity_magnitude > 0.1:
        # Angle between ship forward and velocity vector
        ship_yaw = ship.orientation.get("yaw", 0)
        drift_angle = abs(((vel_heading["yaw"] - ship_yaw + 180) % 360) - 180)

    return {
        "velocity_heading": vel_heading,
        "drift_angle": round(drift_angle, 1),
        "max_accel_g": round(max_accel / 9.81, 2) if max_accel > 0 else 0,
        "projected_positions": projections,
        "time_to_zero": round(velocity_magnitude / max_accel, 1) if max_accel > 0 and velocity_magnitude > 0.1 else None,
    }


def _get_flight_computer_status(ship) -> Optional[Dict[str, Any]]:
    """Get flight computer status for telemetry.

    Args:
        ship: Ship object

    Returns:
        dict or None: Flight computer status
    """
    fc = ship.systems.get("flight_computer")
    if fc and hasattr(fc, "get_flight_status"):
        try:
            status = fc.get_flight_status(ship)
            if hasattr(status, "to_dict"):
                return status.to_dict()
            return status
        except Exception:
            pass
    return None


def _get_thermal_state(ship) -> Dict[str, Any]:
    """Get thermal system state for telemetry.

    Args:
        ship: Ship object

    Returns:
        dict: Thermal state (hull_temperature, radiator status, etc.)
    """
    thermal = ship.systems.get("thermal")
    if thermal and hasattr(thermal, "get_state"):
        try:
            return thermal.get_state()
        except Exception:
            pass
    return {
        "enabled": False,
        "hull_temperature": 300.0,
        "status": "unavailable",
    }


def _get_ops_state(ship) -> Dict[str, Any]:
    """Get ops system state for telemetry.

    Args:
        ship: Ship object

    Returns:
        dict: Ops state (power allocation, repair teams, priorities, shutdowns)
    """
    ops = ship.systems.get("ops")
    if ops and hasattr(ops, "get_state"):
        try:
            return ops.get_state()
        except Exception:
            pass
    return {
        "enabled": False,
        "status": "unavailable",
    }


def _get_ecm_state(ship) -> Dict[str, Any]:
    """Get ECM system state for telemetry.

    Args:
        ship: Ship object

    Returns:
        dict: ECM state (jamming, chaff, flares, EMCON)
    """
    ecm = ship.systems.get("ecm")
    if ecm and hasattr(ecm, "get_state"):
        try:
            return ecm.get_state()
        except Exception:
            pass
    return {
        "enabled": False,
        "status": "unavailable",
    }


def _get_eccm_state(ship) -> Dict[str, Any]:
    """Get ECCM system state for telemetry.

    ECCM is a capability of the sensor system, not a standalone system.
    It lives at ship.systems["sensors"].eccm and provides counter-
    countermeasure state (frequency hop, burn-through, multi-spectral, HoJ).

    Args:
        ship: Ship object

    Returns:
        dict: ECCM state (mode, toggles, sensor health, power draw)
    """
    sensors = ship.systems.get("sensors")
    if sensors and hasattr(sensors, "eccm") and hasattr(sensors.eccm, "get_state"):
        try:
            return sensors.eccm.get_state()
        except Exception:
            pass
    return {
        "mode": "off",
        "multispectral_active": False,
        "hoj_active": False,
        "sensor_health": 1.0,
        "power_multiplier": 1.0,
        "status": "unavailable",
    }


def _get_comms_state(ship) -> Dict[str, Any]:
    """Get comms system state for telemetry.

    Args:
        ship: Ship object

    Returns:
        dict: Comms state (transponder, radio, distress, messages)
    """
    comms = ship.systems.get("comms")
    if comms and hasattr(comms, "get_state"):
        try:
            return comms.get_state()
        except Exception:
            pass
    return {
        "enabled": False,
        "status": "unavailable",
    }


def _get_docking_state(ship) -> Dict[str, Any]:
    """Get docking system state for telemetry.

    Args:
        ship: Ship object

    Returns:
        dict: Docking state (status, target, range, relative velocity)
    """
    docking = ship.systems.get("docking")
    if docking and hasattr(docking, "get_state"):
        try:
            return docking.get_state()
        except Exception:
            pass
    return {
        "enabled": False,
        "status": "unavailable",
    }


def _get_crew_fatigue_state(ship) -> Dict[str, Any]:
    """Get crew fatigue system state for telemetry.

    Exposes fatigue level, g-load, performance factor, and rest status
    so the OPS station can monitor crew readiness.

    Args:
        ship: Ship object

    Returns:
        dict: Crew fatigue state (fatigue, g_load, performance, rest, status)
    """
    crew_fatigue = ship.systems.get("crew_fatigue")
    if crew_fatigue and hasattr(crew_fatigue, "get_state"):
        try:
            return crew_fatigue.get_state()
        except Exception:
            pass
    return {
        "enabled": False,
        "status": "unavailable",
    }


def _get_crew_progression_state(ship) -> Dict[str, Any]:
    """Get crew progression data (XP, injuries, skill levels) for telemetry.

    Reads from the shared CrewStationBinder to build a per-crew-member
    snapshot including experience, injury state, and XP progress bars.
    Falls back gracefully when crew binding is not initialized.

    Args:
        ship: Ship object

    Returns:
        dict: Crew progression data with roster, injuries, and XP.
    """
    try:
        from hybrid.systems.crew_binding_system import CrewBindingSystem
        binder = CrewBindingSystem._shared_binder
        crew_manager = CrewBindingSystem._shared_crew_manager
        if binder is None or crew_manager is None:
            return {"available": False, "roster": []}

        ship_crew = crew_manager.get_ship_crew(ship.id)
        if not ship_crew:
            return {"available": False, "roster": []}

        roster = []
        for crew in ship_crew:
            entry = crew.to_dict()
            # Add current station assignment
            assignment = binder._find_assignment(ship.id, crew.crew_id)
            entry["station_assignment"] = assignment.value if assignment else None
            roster.append(entry)

        return {
            "available": True,
            "roster": roster,
            "count": len(roster),
        }
    except Exception:
        return {"available": False, "roster": []}


def _get_auto_system_state(ship, system_name: str) -> Dict[str, Any]:
    """Get auto-system state (auto_tactical or auto_ops) for telemetry.

    Args:
        ship: Ship object
        system_name: System key ('auto_tactical' or 'auto_ops')

    Returns:
        dict: System state with proposals
    """
    system = ship.systems.get(system_name)
    if system and hasattr(system, "get_state"):
        try:
            return system.get_state()
        except Exception:
            pass
    return {
        "enabled": False,
        "status": "unavailable",
    }


def _get_engineering_state(ship) -> Dict[str, Any]:
    """Get engineering system state for telemetry.

    Args:
        ship: Ship object

    Returns:
        dict: Engineering state (reactor output, drive limit, radiators, vent)
    """
    engineering = ship.systems.get("engineering")
    if engineering and hasattr(engineering, "get_state"):
        try:
            return engineering.get_state()
        except Exception:
            pass
    return {
        "enabled": False,
        "status": "unavailable",
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
    """Get weapons system status including truth weapons and ammo mass.

    Args:
        ship: Ship object

    Returns:
        dict: Weapons status with ammunition tracking data
    """
    weapons = ship.systems.get("weapons")
    combat = ship.systems.get("combat")

    if not weapons and not combat:
        return {
            "available": False,
            "armed": [],
            "status": "offline"
        }

    result: Dict[str, Any] = {
        "available": True,
        "status": "online",
        "armed": [],
        "weapons": {},
        "total_ammo_mass": 0.0,
    }

    # Legacy weapon system state
    if weapons and hasattr(weapons, "get_state"):
        weapon_state = weapons.get_state()
        result["armed"] = weapon_state.get("armed_weapons", [])
        result["status"] = weapon_state.get("status", "online")
        result["weapons"] = weapon_state.get("weapons", {})

    # Truth weapons from combat system (railguns, PDCs)
    if combat and hasattr(combat, "get_state"):
        combat_state = combat.get_state()
        truth_weapons = combat_state.get("truth_weapons", {})
        result["truth_weapons"] = truth_weapons
        result["total_ammo_mass"] = combat_state.get("total_ammo_mass", 0.0)
        result["ready_weapons"] = combat_state.get("ready_weapons", [])
        result["torpedoes"] = combat_state.get("torpedoes", {})
        result["missiles"] = combat_state.get("missiles", {})
        result["pdc_mode"] = combat_state.get("pdc_mode", "auto")
        result["pdc_priority_targets"] = combat_state.get("pdc_priority_targets", [])
        result["pdc_engagements"] = combat_state.get("pdc_engagements", {})
        result["pdc_stats"] = combat_state.get("pdc_stats", {})

        # Merge status: if combat system has a damage factor
        if combat_state.get("damage_factor", 1.0) <= 0.0:
            result["status"] = "failed"
        elif combat_state.get("damage_factor", 1.0) < 1.0:
            result["status"] = "degraded"

    return result

def _mask_contact_by_state(contact_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Mask contact fields based on contact_state.

    Enforces information degradation at the telemetry layer so the GUI
    only receives what the ship's sensors can actually resolve. This is
    the hard-sci rule: you can't know what you can't measure.

    - GHOST (confidence < 0.3): IR hit on the sensor but no resolved
      track. Bearing is solid (it's a point source), distance is a rough
      estimate (inverse-square law gives you order-of-magnitude), but
      there's no velocity vector, no classification, no name.

    - UNCONFIRMED (0.3 <= confidence < 0.6): Resolved position and size
      class (thermal cross-section gives Small/Medium/Large) but not
      enough integration time for a velocity track or positive ID.

    - LOST: Last-known position preserved with growing uncertainty,
      velocity and identity data stale. Marked for the GUI to render
      as a fading marker.

    - CONFIRMED (>= 0.6): Full track, no masking.

    Args:
        contact_dict: Fully populated contact telemetry dict.

    Returns:
        The same dict with fields nulled/noised per state rules.
    """
    import random

    state = contact_dict.get("contact_state", "confirmed")

    if state == "ghost":
        # Bearing is reliable (point-source direction is easy).
        # Distance gets +/- 30% noise — inverse-square flux gives a
        # rough range but not a precise one.
        raw_distance = contact_dict.get("distance", 0)
        if raw_distance > 0:
            noise_factor = 1.0 + random.uniform(-0.3, 0.3)
            contact_dict["distance"] = raw_distance * noise_factor
        # Null out everything we can't resolve from a single IR return
        contact_dict["position"] = None
        contact_dict["velocity"] = None
        contact_dict["classification"] = None
        contact_dict["name"] = None
        contact_dict["faction"] = None
        contact_dict["diplomatic_state"] = "unknown"

    elif state == "unconfirmed":
        # Position is available (multi-scan triangulation).
        # Classification is coarse size class only — thermal cross-section
        # tells you big/medium/small, not "Donnager-class battleship".
        classification = contact_dict.get("classification")
        if classification and classification not in ("Small", "Medium", "Large", "Unknown"):
            # Downgrade detailed class to size bucket.
            # The passive sensor already does this at low accuracy,
            # but active sensors or re-acquired contacts might have
            # a stale full classification from a higher-confidence moment.
            contact_dict["classification"] = _coarsen_classification(classification)
        # Velocity has extra noise — not enough integration time for
        # a clean velocity track, so add 50% additional scatter.
        vel = contact_dict.get("velocity")
        if vel and isinstance(vel, dict):
            for axis in ("x", "y", "z"):
                if axis in vel and vel[axis] is not None:
                    vel[axis] += random.gauss(0, abs(vel[axis]) * 0.5 + 5.0)
        # No positive ID at unconfirmed confidence
        contact_dict["name"] = None

    elif state == "lost":
        # Preserve last-known position but null out live tracking data.
        # The GUI will show a fading marker at the last-known spot.
        contact_dict["velocity"] = None
        contact_dict["name"] = None

    # "confirmed" — no masking needed, full track data

    return contact_dict


def _coarsen_classification(classification: str) -> str:
    """Downgrade a detailed ship classification to a size bucket.

    At unconfirmed confidence the sensor can estimate thermal
    cross-section (which correlates with mass/size) but can't
    resolve fine structural details for a class identification.

    Args:
        classification: Detailed class string (e.g. "Corvette")

    Returns:
        Size bucket: "Small", "Medium", or "Large"
    """
    # Map known class types to size buckets based on typical mass ranges.
    # This is intentionally coarse — the point is information loss.
    large_classes = {"battleship", "carrier", "cruiser", "station", "freighter"}
    medium_classes = {"destroyer", "frigate", "corvette", "transport"}
    # Everything else (shuttle, fighter, drone, unknown) -> Small

    lower = classification.lower()
    if lower in large_classes:
        return "Large"
    if lower in medium_classes:
        return "Medium"
    return "Small"


def get_sensor_contacts(ship) -> Dict[str, Any]:
    """Get sensor contacts for a ship.

    Reads from SensorSystem.contact_tracker (the single source of truth for
    merged, de-duplicated contacts with stable IDs like C001).  Falls back to
    reading raw passive/active contact dicts only for legacy dict-based sensor
    systems that lack a ContactTracker.

    Contact data is masked based on contact_state before serialization:
    ghost contacts only expose bearing + rough distance, unconfirmed
    contacts expose position + size class, and confirmed contacts get
    full data. This enforces hard-sci sensor rules at the telemetry layer.

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

        # Compute diplomatic state for each contact relative to our faction
        our_faction = getattr(ship, "faction", "")

        for contact_id, contact in all_contacts.items():
            position = getattr(contact, "position", ship.position)
            distance = calculate_distance(ship.position, position)
            bearing = calculate_bearing(ship.position, position)

            pos_dict = _serialize_vector(position)
            vel_dict = _serialize_vector(getattr(contact, "velocity", None))

            contact_faction = getattr(contact, "faction", None)
            diplo_state = _get_contact_diplomatic_state(our_faction, contact_faction)

            contact_dict = {
                "id": contact_id,
                "position": pos_dict,
                "velocity": vel_dict,
                "distance": distance,
                "bearing": bearing,
                "confidence": getattr(contact, "confidence", 0.5),
                "contact_state": getattr(contact, "contact_state", "confirmed"),
                "last_update": getattr(contact, "last_update", 0),
                "detection_method": getattr(contact, "detection_method", "passive"),
                "name": getattr(contact, "name", None),
                "classification": getattr(contact, "classification", None),
                "faction": contact_faction,
                "diplomatic_state": diplo_state,
            }

            # Mask fields the sensor can't actually resolve at this state
            contacts_list.append(_mask_contact_by_state(contact_dict))
    else:
        # Legacy fallback for dict-based sensors without ContactTracker
        contacts_list = _get_contacts_from_raw_sensors(sensors, ship)

    # Sort by distance
    contacts_list.sort(key=lambda c: c.get("distance") or float("inf"))

    return {
        "available": True,
        "contacts": contacts_list,
        "count": len(contacts_list)
    }


def _get_contact_diplomatic_state(our_faction: str, contact_faction: Optional[str]) -> str:
    """Get the diplomatic state string for a contact.

    Args:
        our_faction: Our ship's faction.
        contact_faction: The contact's faction (may be None).

    Returns:
        Diplomatic state string: "allied", "neutral", "hostile", or "unknown".
    """
    if not contact_faction:
        return "unknown"
    try:
        from hybrid.fleet.faction_rules import get_diplomatic_state
        return get_diplomatic_state(our_faction, contact_faction).value
    except Exception:
        return "unknown"


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

    # Get active torpedoes from TorpedoManager
    torpedoes = []
    if hasattr(sim, "torpedo_manager"):
        torpedoes = sim.torpedo_manager.get_state()

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

    # Get environment state (asteroid fields, hazard zones) for GUI rendering
    environment = {}
    if hasattr(sim, "environment_manager"):
        environment = sim.environment_manager.get_state()

    return {
        "tick": tick,
        "sim_time": sim_time,
        "dt": dt,
        "ships": ships_telemetry,
        "projectiles": projectiles,
        "torpedoes": torpedoes,
        "environment": environment,
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
