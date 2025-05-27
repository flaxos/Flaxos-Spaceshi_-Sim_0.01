# scenario_loader.py — Loads scenario JSON and builds ship instances

import json
from ship_factory import build_ship_from_config

def load_scenario(path, sector_manager=None):
    with open(path) as f:
        data = json.load(f)

    ships = []
    for ship_cfg in data:
        ship = build_ship_from_config(ship_cfg)
        ships.append(ship)

        if sector_manager:
            sector_manager.add_ship(ship)

    return ships
