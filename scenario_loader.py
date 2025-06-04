# scenario_loader.py — Loads scenario JSON and builds ship instances

import json
from ship_factory import build_ship_from_config

# Limit how far a ship can spawn from the origin to keep scenarios contained
MAX_START_DISTANCE = 10000.0

def _clamp_position(pos):
    """Clamp position components to the allowed maximum distance"""
    for axis in ("x", "y", "z"):
        if axis in pos:
            if pos[axis] > MAX_START_DISTANCE:
                pos[axis] = MAX_START_DISTANCE
            elif pos[axis] < -MAX_START_DISTANCE:
                pos[axis] = -MAX_START_DISTANCE
    return pos

def load_scenario(path, sector_manager=None):
    with open(path) as f:
        data = json.load(f)

    # Support either top-level list OR { "ships": [...] }
    if isinstance(data, list):
        ships_data = data
    elif isinstance(data, dict) and "ships" in data:
        ships_data = data["ships"]
    else:
        raise ValueError("Invalid scenario format. Expected list or {'ships': [...]}")

    ships = []
    for ship_cfg in ships_data:
        # Clamp starting position to avoid extremely far spawns
        if 'position' in ship_cfg:
            ship_cfg['position'] = _clamp_position(ship_cfg['position'])

        ship = build_ship_from_config(ship_cfg)
        ships.append(ship)
        if sector_manager:
            sector_manager.add_ship(ship)

    return ships
