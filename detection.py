# detection.py
import math
import time




def update_sensor_signature(ship):
    # Basic formula: base + throttle × scaling factor
    base_emission = 100.0
    thrust_factor = 400.0
    throttle = ship.get("throttle", 0.0)
    ship["sensor_signature"] = base_emission + (throttle * thrust_factor)

def is_within_fov(observer_orientation, vector_to_target, fov_angle_deg):
    # Placeholder: assumes FOV is forward-only (yaw only) and 2D for now
    import math
    yaw_rad = math.radians(observer_orientation.get("yaw", 0.0))
    fwd_vector = (math.cos(yaw_rad), math.sin(yaw_rad))
    target_vector = (
        vector_to_target["x"],
        vector_to_target["y"]
    )
    dot = fwd_vector[0]*target_vector[0] + fwd_vector[1]*target_vector[1]
    mag_fwd = math.hypot(*fwd_vector)
    mag_tgt = math.hypot(*target_vector)
    if mag_fwd == 0 or mag_tgt == 0:
        return False
    angle_rad = math.acos(dot / (mag_fwd * mag_tgt))
    return angle_rad <= math.radians(fov_angle_deg / 2)

def update_visibility(ship_id, ship, sectors, fov_angle_deg=120, passive_range_km=500000.0, threshold=0.001):
    ship["visibility_state"] = []
    position = ship.get("position", {})
    orientation = ship.get("orientation", {})
    sector_coords = tuple(ship.get("sector", {}).values())
    now = time.time()

    def dist(a, b):
        return math.sqrt(
            (a["x"] - b["x"])**2 +
            (a["y"] - b["y"])**2 +
            (a["z"] - b["z"])**2
        )

    for other_sector_coords, sector in sectors.items():
        for target_id, target in sector.get("ships", {}).items():
            if target_id == ship_id:
                continue
            target_pos = target.get("position")
            if not target_pos or any(k not in target_pos for k in ("x", "y", "z")):
                print(f"[WARN] Skipping target '{target_id}' due to invalid position: {target_pos}")
                continue

            distance = dist(position, target_pos)

            if distance > passive_range_km:
                continue

            # Check FOV
            direction = {
                "x": target_pos["x"] - position["x"],
                "y": target_pos["y"] - position["y"]
            }
            if not is_within_fov(orientation, direction, fov_angle_deg):
                continue

            sig = target.get("sensor_signature", 0.0)
            strength = sig / (distance ** 2 if distance > 0 else 1)

            if strength > threshold:
                contact = {
                    "target_id": target_id,
                    "method": "passive",
                    "distance": round(distance, 2),
                    "signature": round(sig, 1)
                }
                ship["visibility_state"].append(contact)
                ship.setdefault("last_seen_state", {})[target_id] = {
                    "last_seen_at": now,
                    "last_method": "passive"
                }
