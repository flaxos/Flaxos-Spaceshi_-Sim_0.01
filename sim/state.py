# spaceship_sim/sim/state.py
import yaml
import os
from sector_utils import get_sector


DEFAULT_STATE = {
    'position': {'x': 0.0, 'y': 0.0, 'z': 0.0},
    'velocity': {'x': 0.0, 'y': 0.0, 'z': 0.0},
    'orientation': {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0},
    'sector': {"x": 0, "y": 0, "z": 0},
    'mass': 250000.0,
    'throttle': 0.0,
    'systems': {
        'impulse_drive': 'online',
        'reaction_control_system': 'online'
    },
    'event_log': []
}
# sim/state.py


from sector_utils import get_sector
import os, yaml
def calculate_sector(pos):
    return (
        int(pos["x"] // SECTOR_SIZE),
        int(pos["y"] // SECTOR_SIZE),
        int(pos["z"] // SECTOR_SIZE),
    )

def load_fleet():
    fleet = {}
    for file in os.listdir("fleet"):
        if file.endswith(".json"):
            with open(os.path.join("fleet", file)) as f:
                ship = json.load(f)

                # Make sure sector is set based on position
                pos = ship.get("position")
                if pos:
                    sector = calculate_sector(pos)
                    ship["sector"] = sector
                    print(f"[INFO] Ship '{ship['id']}' loaded into sector {sector}.")
                else:
                    ship["sector"] = None
                    print(f"[WARN] Ship '{ship['id']}' has no valid position on load.")

                fleet[ship["id"]] = ship
    return fleet



def load_ship_state(filepath):
    if not os.path.exists(filepath):
        print("[WARN] State file not found. Using default state.")
        return DEFAULT_STATE.copy()

    with open(filepath, 'r') as f:
        state = yaml.safe_load(f) or {}

    # Fill in missing defaults
    full_state = DEFAULT_STATE.copy()
    for key, value in DEFAULT_STATE.items():
        if key not in state:
            state[key] = value
    return state

def save_ship_state(filepath, state):
    with open(filepath, 'w') as f:
        yaml.safe_dump(state, f, default_flow_style=False)
    print("[INFO] Ship state saved to config.")


