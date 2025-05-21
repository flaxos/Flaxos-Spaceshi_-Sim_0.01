import yaml
import os

DEFAULT_STATE = {
    'position': {'x': 10.0, 'y': 10.0, 'z': 0.0},
    'velocity': {'x': 0.0, 'y': 0.0, 'z': 0.0},
    'orientation': {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0},
    'sector': {"x": 0, "y": 0, "z": 0},
    'mass': 250000.0,
    'throttle': 0.0,
    'acceleration': {'x': 0.0, 'y': 0.0, 'z': 0.0},
    'systems': {
        'impulse_drive': 'online',
        'reaction_control_system': 'online'
    },
    'event_log': []
}

os.makedirs("fleet", exist_ok=True)

for ship_id in ["test_ship_001", "enemy_probe"]:
    with open(f"fleet/{ship_id}.yaml", "w") as f:
        yaml.safe_dump(DEFAULT_STATE, f, default_flow_style=False)
    print(f"Created fleet/{ship_id}.yaml")
