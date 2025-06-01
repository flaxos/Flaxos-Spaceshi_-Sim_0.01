# PHASE 4: SIGNATURE SPIKE ON THRUST
# Adds temporary visibility boost when ships apply thrust

import math
from datetime import datetime, timedelta

def face_target(ship, target):
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
    bm = ship.systems["bio_monitor"]
    a = ship.acceleration
    g_force = math.sqrt(a["x"]**2 + a["y"]**2 + a["z"]**2) / 9.81
    bm["current_g"] = g_force
    if bm.get("override"):
        bm["status"] = "override"
        bm["fail_timer"] = 0
        return
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


def tick_bio_monitor(ship, dt):
    bm = ship.systems["bio_monitor"]
    a = ship.acceleration
    g_force = math.sqrt(a["x"]**2 + a["y"]**2 + a["z"]**2) / 9.81
    bm["current_g"] = g_force
    if bm.get("override"):
        bm["status"] = "override"
        bm["fail_timer"] = 0
        return
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
    helm = ship.systems.get("helm", {})
    nav = ship.systems.get("navigation", {})
    thrust_out = {"x": 0.0, "y": 0.0, "z": 0.0}

    if helm.get("mode") == "manual":
        thrust_out = helm.get("manual_thrust", thrust_out)
    elif nav.get("autopilot") and nav.get("target"):
        return

    magnitude = math.sqrt(thrust_out["x"]**2 + thrust_out["y"]**2 + thrust_out["z"]**2)
    if magnitude > 10.0:
        sensors = ship.systems.setdefault("sensors", {})
        sensors["spike_until"] = (datetime.utcnow() + timedelta(seconds=3)).isoformat()
        print(f"[DEBUG] Signature spike triggered on {ship.id} until {sensors['spike_until']}")

    ship.systems["propulsion"]["main_drive"]["thrust"] = thrust_out


def tick_power(ship, dt):
    power = ship.systems["power"]
    regen = power["generation"] * dt
    ship.systems["power"]["current"] = min(power["capacity"], power["current"] + regen)

def tick_sensors(ship, dt):
    if "active" in ship.systems["sensors"]:
        sensors = ship.systems["sensors"]["active"]
        if sensors.get("cooldown", 0) > 0:
            sensors["cooldown"] -= dt
            sensors["cooldown"] = max(0, sensors["cooldown"])

def tick_sensors_passive(ship, all_ships, dt):
    pass  # assumed already implemented elsewhere

def tick_sensors_active(ship, all_ships):
    active = ship.systems["sensors"].get("active", {})
    if not active.get("last_ping_time"):
        return
    if active.get("processed"):
        return

    active_range = active.get("scan_range", 5000.0)
    fov = active.get("scan_fov", 120.0)
    ship_yaw = ship.orientation.get("yaw", 0.0)
    now = datetime.utcnow().isoformat()
    contacts = []

    for other in all_ships:
        if other.id == ship.id:
            continue

        dx = other.position["x"] - ship.position["x"]
        dz = other.position["z"] - ship.position["z"]
        dy = other.position["y"] - ship.position["y"]
        dist = math.sqrt(dx**2 + dy**2 + dz**2)
        if dist > active_range:
            continue

        angle_to_target = math.degrees(math.atan2(dx, dz)) % 360
        delta = abs((angle_to_target - ship_yaw + 180) % 360 - 180)
        if delta > fov / 2:
            continue

        contacts.append({
            "target_id": other.id,
            "distance": round(dist, 1),
            "method": "active",
            "detected_at": now
        })

    active["contacts"] = contacts
    active["cooldown"] = 10.0
    active["processed"] = True
    active["last_ping_time"] = None

def calc_signature(ship):
    base = math.sqrt(sum(v**2 for v in ship.systems.get("propulsion", {}).get("main_drive", {}).get("thrust", {}).values()))
    spike_until = ship.systems.get("sensors", {}).get("spike_until")
    if spike_until:
        try:
            if datetime.utcnow() < datetime.fromisoformat(spike_until):
                return base + 100.0
        except:
            pass
    return base + ship.mass * 0.001

def tick_navigation(ship, dt):
    nav = ship.systems["navigation"]
    if not nav.get("autopilot"):
        return
    tgt = nav.get("target")
    if not tgt:
        return
    pos = ship.position
    dx = tgt["x"] - pos["x"]
    dy = tgt["y"] - pos["y"]
    dz = tgt["z"] - pos["z"]
    dist = math.sqrt(dx**2 + dy**2 + dz**2)
    if dist < 1:
        nav["autopilot"] = False
        nav["target"] = None
        return
    thrust_mag = nav.get("thrust", 1.0)
    norm = (dx / dist, dy / dist, dz / dist)
    thrust = {
        "x": norm[0] * thrust_mag,
        "y": norm[1] * thrust_mag,
        "z": norm[2] * thrust_mag
    }
    ship.systems["propulsion"]["main_drive"]["thrust"] = thrust
