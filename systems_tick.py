# PHASE 4: SIGNATURE SPIKE ON THRUST
# Adds temporary visibility boost when ships apply thrust

import math
import logging
from datetime import datetime, timedelta

# Setup logging
logger = logging.getLogger(__name__)

def face_target(ship, target):
    """Turn ship to face the specified target position"""
    dx = target["x"] - ship.position["x"]
    dy = target["y"] - ship.position["y"]
    dz = target["z"] - ship.position["z"]
    dist = math.sqrt(dx**2 + dy**2 + dz**2)
    if dist == 0:
        return

    pitch = math.degrees(math.atan2(dy, math.sqrt(dx**2 + dz**2)))
    yaw = math.degrees(math.atan2(dx, dz)) % 360

    ship.orientation["pitch"] = pitch % 360
    ship.orientation["yaw"] = yaw

def tick_all_systems(ship, all_ships, dt):
    """Update all ship systems for the current time step"""
    if "bio_monitor" in ship.systems:
        tick_bio_monitor(ship, dt)
    if "power" in ship.systems:
        tick_power(ship, dt)
    if "helm" in ship.systems:
        tick_helm(ship, dt)
    if "sensors" in ship.systems:
        tick_sensors(ship, dt)
        tick_sensors_passive(ship, all_ships, dt)
        tick_sensors_active(ship, all_ships)
    if "navigation" in ship.systems:
        tick_navigation(ship, dt)

def tick_bio_monitor(ship, dt):
    """Update the bio monitoring system"""
    bm = ship.systems["bio_monitor"]
    a = ship.acceleration
    g_force = math.sqrt(a["x"]**2 + a["y"]**2 + a["z"]**2) / 9.81
    bm["current_g"] = g_force
    
    # Check for override
    if bm.get("override"):
        bm["status"] = "override"
        bm["fail_timer"] = 0
        return
    
    # Check g-force limits
    if g_force > bm["g_limit"]:
        bm["fail_timer"] += dt
        if bm["fail_timer"] > 3:
            bm["status"] = "fatal"
            bm["crew_health"] = 0.0
        else:
            bm["status"] = "warning"
    else:
        bm["status"] = "nominal"
        bm["fail_timer"] = 0

def tick_helm(ship, dt):
    """Update helm control system"""
    helm = ship.systems.get("helm", {})
    nav = ship.systems.get("navigation", {})
    thrust_out = {"x": 0.0, "y": 0.0, "z": 0.0}

    # Determine thrust based on control mode
    if helm.get("mode") == "manual":
        thrust_out = helm.get("manual_thrust", thrust_out)
    elif nav.get("autopilot") and nav.get("target"):
        return  # Autopilot is handling thrust

    # Check for signature spike from high thrust
    magnitude = math.sqrt(thrust_out["x"]**2 + thrust_out["y"]**2 + thrust_out["z"]**2)
    if magnitude > 10.0:
        sensors = ship.systems.setdefault("sensors", {})
        spike_duration = 3  # seconds
        sensors["spike_until"] = (datetime.utcnow() + timedelta(seconds=spike_duration)).isoformat()
        logger.debug(f"Signature spike triggered on {ship.id} until {sensors['spike_until']}")

    # Apply thrust to propulsion system
    ship.systems["propulsion"]["main_drive"]["thrust"] = thrust_out

def tick_power(ship, dt):
    """Update power system"""
    power = ship.systems["power"]
    regen = power["generation"] * dt
    ship.systems["power"]["current"] = min(power["capacity"], power["current"] + regen)

def tick_sensors(ship, dt):
    """Update sensor cooldown timers"""
    if "active" in ship.systems["sensors"]:
        sensors = ship.systems["sensors"]["active"]
        if sensors.get("cooldown", 0) > 0:
            sensors["cooldown"] -= dt
            sensors["cooldown"] = max(0, sensors["cooldown"])

def tick_sensors_passive(ship, all_ships, dt):
    """Update passive sensor detections for the ship."""
    sensors = ship.systems.get("sensors", {})
    passive = sensors.get("passive")

    # Exit early if ship has no passive sensors configured
    if passive is None:
        return

    passive_range = passive.get("range", 3000.0)
    fov = passive.get("fov", 120.0)
    threshold = passive.get("signature_threshold", 0.1)

    ship_yaw = ship.orientation.get("yaw", 0.0)
    now = datetime.utcnow().isoformat()
    contacts = []

    for other in all_ships:
        if other.id == ship.id:
            continue

        dx = other.position["x"] - ship.position["x"]
        dy = other.position["y"] - ship.position["y"]
        dz = other.position["z"] - ship.position["z"]

        dist = math.sqrt(dx**2 + dy**2 + dz**2)
        if dist > passive_range:
            continue

        angle_to_target = math.degrees(math.atan2(dx, dz)) % 360
        delta = abs((angle_to_target - ship_yaw + 180) % 360 - 180)
        if delta > fov / 2:
            continue

        target_signature = calc_signature(other)
        strength = target_signature / (dist ** 2 if dist > 0 else 1)

        if strength < threshold:
            continue

        contacts.append({
            "id": other.id,
            "distance": round(dist, 1),
            "bearing": round(angle_to_target, 1),
            "signature": round(target_signature, 2),
            "detection_method": "passive",
            "last_updated": now,
        })

    passive["contacts"] = contacts
    # Merge active and passive contacts for convenience
    active_contacts = sensors.get("active", {}).get("contacts", [])
    sensors["contacts"] = contacts + active_contacts

def tick_sensors_active(ship, all_ships):
    """Process active sensor ping results"""
    active = ship.systems["sensors"].get("active", {})
    
    # Return if no ping is pending
    if not active.get("last_ping_time"):
        return
    
    # Return if this ping has already been processed
    if active.get("processed"):
        return

    # Get sensor parameters
    active_range = active.get("scan_range", 5000.0)
    fov = active.get("scan_fov", 120.0)
    ship_yaw = ship.orientation.get("yaw", 0.0)
    now = datetime.utcnow().isoformat()
    contacts = []

    # Scan for other ships
    for other in all_ships:
        # Skip self
        if other.id == ship.id:
            continue

        # Calculate distance
        dx = other.position["x"] - ship.position["x"]
        dz = other.position["z"] - ship.position["z"]
        dy = other.position["y"] - ship.position["y"]
        dist = math.sqrt(dx**2 + dy**2 + dz**2)
        
        # Skip if out of range
        if dist > active_range:
            continue

        # Check if in field of view
        angle_to_target = math.degrees(math.atan2(dx, dz)) % 360
        delta = abs((angle_to_target - ship_yaw + 180) % 360 - 180)
        if delta > fov / 2:
            continue

        # Add to contacts
        contacts.append({
            "target_id": other.id,
            "distance": round(dist, 1),
            "method": "active",
            "detected_at": now
        })

    # Update sensor state
    active["contacts"] = contacts
    active["cooldown"] = 10.0
    active["processed"] = True
    active["last_ping_time"] = None

def calc_signature(ship):
    """Calculate ship's sensor signature"""
    # Base signature from propulsion
    thrust_values = ship.systems.get("propulsion", {}).get("main_drive", {}).get("thrust", {}).values()
    thrust_sum_squares = sum(v**2 for v in thrust_values)
    base = math.sqrt(thrust_sum_squares) if thrust_sum_squares > 0 else 0
    
    # Check for signature spike
    spike_until = ship.systems.get("sensors", {}).get("spike_until")
    if spike_until:
        try:
            if datetime.utcnow() < datetime.fromisoformat(spike_until):
                return base + 100.0
        except (ValueError, TypeError):
            # Handle invalid datetime format
            logger.warning(f"Invalid spike_until format for ship {ship.id}: {spike_until}")
    
    # Base signature plus mass component
    return base + ship.mass * 0.001

def tick_navigation(ship, dt):
    """Update navigation system and autopilot"""
    nav = ship.systems["navigation"]
    
    # Check if autopilot is enabled
    if not nav.get("autopilot"):
        return
    
    # Check if target is set
    tgt = nav.get("target")
    if not tgt:
        return
    
    # Calculate vector to target
    pos = ship.position
    dx = tgt["x"] - pos["x"]
    dy = tgt["y"] - pos["y"]
    dz = tgt["z"] - pos["z"]
    dist = math.sqrt(dx**2 + dy**2 + dz**2)
    
    # Check if we've reached the target
    if dist < 1:
        nav["autopilot"] = False
        nav["target"] = None
        return
    
    # Calculate normalized direction and apply thrust
    thrust_mag = nav.get("thrust", 1.0)
    norm = (dx / dist, dy / dist, dz / dist)
    thrust = {
        "x": norm[0] * thrust_mag,
        "y": norm[1] * thrust_mag,
        "z": norm[2] * thrust_mag
    }
    
    # Apply thrust to propulsion
    ship.systems["propulsion"]["main_drive"]["thrust"] = thrust
