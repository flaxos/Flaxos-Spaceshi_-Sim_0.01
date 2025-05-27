# systems_tick.py — Ticks each modular system on every ship per frame
import math

def tick_all_systems(ship, dt):
    if "bio_monitor" in ship.systems:
        tick_bio_monitor(ship, dt)
    if "power" in ship.systems:
        tick_power(ship, dt)
    if "sensors" in ship.systems:
        tick_sensors(ship, dt)
    # Optional: weapons, PDC, nav, etc.

def tick_bio_monitor(ship, dt):
    bm = ship.systems["bio_monitor"]
    v = ship.velocity
    a = ship.acceleration if hasattr(ship, "acceleration") else {"x": 0, "y": 0, "z": 0}
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

def tick_power(ship, dt):
    power = ship.systems["power"]
    regen = power["generation"] * dt
    ship.systems["power"]["current"] = min(
        power["capacity"],
        power["current"] + regen
    )

def tick_sensors(ship, dt):
    sensors = ship.systems["sensors"]
    if sensors["cooldown"] > 0:
        sensors["cooldown"] -= dt
        if sensors["cooldown"] < 0:
            sensors["cooldown"] = 0
    # actual detection logic not yet implemented
