# systems_schema.py — Default system loader for ships

def build_default_systems():
    return {
        "propulsion": {
            "main_drive": {
                "thrust": {"x": 0.0, "y": 0.0, "z": 0.0},
                "status": "online",
                "throttle": 0.0,
                "max_thrust": 100.0
            },
            "rcs": {
                "angular_velocity_target": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
                "current_angular_velocity": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
                "status": "online"
            }
        },
        "bio_monitor": {
            "crew_present": True,
            "g_limit": 6.0,
            "current_g": 0.0,
            "status": "nominal",
            "fail_timer": 0.0,
            "crew_health": 1.0,
            "override": False
        },
        "power": {
            "reactor_output_max": 1000,
            "battery_capacity": 500,
            "battery_charge_rate": 50,
            "primary": ["main_drive", "railgun", "active_sensors"],
            "secondary": ["rcs", "pdc", "comms", "passive_sensors", "drones"],
            "tertiary": ["life_support", "bio_monitor", "nav_computer"]
        },
        "sensors": {
            "passive": {
                "range": 3000.0,
                "fov": 120.0,  # ⬅️ New field added correctly here
                "signature_threshold": 0.1,
                "contacts": []
            },
            "active": {
                "scan_range": 5000.0,
                "cooldown": 0.0,
                "last_ping_time": 0.0,
                "contacts": []
            }
        },
        "weapons": {
            "railguns": [
                {"status": "online", "ammo": 20, "cooldown": 0.0, "barrel_heat": 0.0}
            ]
        },
        "point_defense": {
            "pdc_array": [
                {"arc": 180, "status": "online", "cooldown": 0.0, "tracking": None}
            ]
        }
    }
