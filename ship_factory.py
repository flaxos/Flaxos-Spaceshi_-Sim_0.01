# ship_factory.py — builds Ship objects from templates + systems

from ship import Ship
from impulse_drive import ImpulseDrive
from rcs_controller import RCSController
from sensors import SensorArray

SYSTEM_REGISTRY = {
    "impulse": lambda config: ImpulseDrive(config.get("max_thrust", 100)),
    "sensor": lambda config: SensorArray(config.get("range", 2000)),
    "rcs": lambda config: RCSController(config.get("torque_rating", 10))
}

def build_ship_from_config(ship_id, config, sector_manager=None):
    position = config.get("position", {"x": 0.0, "y": 0.0, "z": 0.0})
    systems_cfg = config.get("systems", {})

    systems = {}
    for name, sys_cfg in systems_cfg.items():
        sys_type = sys_cfg.get("type")
        if sys_type in SYSTEM_REGISTRY:
            systems[name] = SYSTEM_REGISTRY[sys_type](sys_cfg)
        else:
            print(f"[WARN] Unknown system type: {sys_type} on {ship_id}")

    mass = config.get("mass", 1000)
    ship = Ship(ship_id, position, systems, mass=mass)

    if sector_manager:
        ship.sector_manager = sector_manager

    return ship
