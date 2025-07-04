# ship_factory.py
from ship import Ship
from power_management import (
    PowerManagementSystem,
    ShipSystem,
)

# Define default systems structure
DEFAULT_SYSTEMS = {
    "bio_monitor": {
        "g_limit": 8.0,
        "fail_timer": 0.0,
        "current_g": 0.0,
        "status": "nominal",
        "crew_health": 1.0,
    },
    "power": {
        "generation": 5.0,
        "capacity": 100.0,
        "current": 100.0
    },
    "sensors": {
        "range": 1000.0,
        "cooldown": 0.0
    },
    "propulsion": {
        "main_drive": {
            "thrust": {"x": 0.0, "y": 0.0, "z": 0.0}
        }
    },
    "helm": {
        "manual_thrust": {"x": 0.0, "y": 0.0, "z": 0.0},
        "mode": "autopilot"  # or "manual"
    }

}


def build_ship_from_config(cfg):
    ship_id = cfg["id"]
    position = cfg.get("position", {"x": 0.0, "y": 0.0, "z": 0.0})
    velocity = cfg.get("velocity", {"x": 0.0, "y": 0.0, "z": 0.0})
    orientation = cfg.get("orientation", {"pitch": 0.0, "yaw": 0.0, "roll": 0.0})
    angular_velocity = cfg.get("angular_velocity", {"pitch": 0.0, "yaw": 0.0, "roll": 0.0})
    mass = cfg.get("mass", 1.0)

    # Start with default systems, then override/extend with provided ones
    user_systems = cfg.get("systems", {})
    systems = {**DEFAULT_SYSTEMS, **user_systems}

    ship = Ship(
        ship_id=ship_id,
        position=position,
        velocity=velocity,
        orientation=orientation,
        angular_velocity=angular_velocity,
        mass=mass,
        systems=systems,
    )

    power_cfg = systems.get("power", {})
    pm = PowerManagementSystem(power_cfg)

    for bus in ["primary", "secondary", "tertiary"]:
        for sys_name in power_cfg.get(bus, []):
            draw = systems.get(sys_name, {}).get("power_draw", 0)
            pm.add_system(bus, ShipSystem(sys_name, draw))

    ship.power_system = pm
    return ship
