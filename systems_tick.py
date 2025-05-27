# systems_tick.py — Ticks each modular system on every ship per frame
import math
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


def tick_all_systems(ship, dt):
    if "bio_monitor" in ship.systems:
        tick_bio_monitor(ship, dt)
    if "power" in ship.systems:
        tick_power(ship, dt)
    if "helm" in ship.systems:
        tick_helm(ship, dt)
    if "sensors" in ship.systems:
        tick_sensors(ship, dt)
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
def tick_helm(ship, dt):
    helm = ship.systems.get("helm", {})
    nav = ship.systems.get("navigation", {})
    thrust_out = {"x": 0.0, "y": 0.0, "z": 0.0}

    if helm.get("mode") == "manual":
        thrust_out = helm.get("manual_thrust", thrust_out)
    elif nav.get("autopilot") and nav.get("target"):
        # Let navigation tick determine thrust
        return

    ship.systems["propulsion"]["main_drive"]["thrust"] = thrust_out

def tick_power(ship, dt):
    power = ship.systems["power"]
    regen = power["generation"] * dt
    ship.systems["power"]["current"] = min(power["capacity"], power["current"] + regen)

def tick_sensors(ship, dt):
    sensors = ship.systems["sensors"]
    if sensors["cooldown"] > 0:
        sensors["cooldown"] -= dt
        sensors["cooldown"] = max(0, sensors["cooldown"])

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