# ship_factory.py
from ship import Ship

def build_ship_from_config(ship_cfg, sector_manager=None):
    ship_id = ship_cfg["id"]
    position = ship_cfg["position"]
    mass = ship_cfg.get("mass", 1.0)
    systems = ship_cfg.get("systems", {})
    ship = Ship(ship_id, position, systems=systems, mass=mass)

    if sector_manager:
        sector_manager.add_ship(ship)

    return ship
