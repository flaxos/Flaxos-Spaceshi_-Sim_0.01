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
            "generation": 100.0,
            "capacity": 1000.0,
            "current": 800.0,
            "distribution": {
                "propulsion": 0.4,
                "sensors": 0.2,
                "weapons": 0.3,
                "pdc": 0.1
            }
        },
        "sensors": {
            "range": 3000.0,
            "fov": 120.0,
            "cooldown": 0.0,
            "detected_contacts": []
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
