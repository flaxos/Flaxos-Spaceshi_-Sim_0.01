# scenario_loader.py — Loads scenario JSON and builds ship instances

import json
import sys
from ship_factory import build_ship_from_config

def load_scenario(path, sector_manager=None):
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Scenario file not found: {path}", file=sys.stderr)
        sys.exit(1)

    # Support either top-level list OR { "ships": [...] }
    if isinstance(data, list):
        ships_data = data
    elif isinstance(data, dict) and "ships" in data:
        ships_data = data["ships"]
    else:
        raise ValueError("Invalid scenario format. Expected list or {'ships': [...]}")

    ships = []
    for ship_cfg in ships_data:
        ship = build_ship_from_config(ship_cfg)
        ships.append(ship)
        if sector_manager:
            sector_manager.add_ship(ship)

    return ships
