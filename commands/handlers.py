# handlers.py

import logging


logger = logging.getLogger(__name__)


def truncate(d, decimals=2):
    return {k: round(v, decimals) for k, v in d.items()}


def find_ship(ship_id, sectors):
    for sector_coords, sector in sectors.items():
        logger.debug("Checking sector %s", sector_coords)
        ships = sector.get("ships", {})
        if ship_id in ships:
            logger.debug("Found ship '%s' in sector %s", ship_id, sector_coords)
            return ships[ship_id]
    logger.debug("Ship '%s' not found in any sector", ship_id)
    return None

def handle_command(request: dict, sectors: dict) -> dict:
    cmd = request.get("command_type")
    payload = request.get("payload", {})
    ship_id = payload.get("ship")

    if not ship_id:
        return {"error": "Missing 'ship' in payload."}

    ship = find_ship(ship_id, sectors)
    if ship is None:
        return {"error": f"Ship '{ship_id}' not found in any sector."}

    if cmd == "throttle":
        value = payload.get("value", 0.0)
        ship["throttle"] = value
        return {"status": f"Throttle set to {value}"}

    elif cmd == "vector":
        x = payload.get("x", 0.0)
        y = payload.get("y", 0.0)
        z = payload.get("z", 0.0)
        ship["acceleration"] = {"x": x, "y": y, "z": z}
        return {"status": f"Applied vector ({x}, {y}, {z})"}

    elif cmd == "get_position":
        return {"position": truncate(ship.get("position", {}))}

    elif cmd == "get_velocity":
        return {"velocity": truncate(ship.get("velocity", {}))}

    elif cmd == "get_orientation":
        return {"orientation": truncate(ship.get("orientation", {}))}

    elif cmd == "get_state":
        return ship

    elif cmd == "get_sector":
        return {"sector": ship.get("sector", "unknown")}

    elif cmd == "status":
        return {"status": "Ship is online", "ship_id": ship_id}

    elif cmd == "events":
        return {"events": ship.get("event_log", [])}

    elif cmd == "reset":
        ship["position"] = {"x": 0.0, "y": 0.0, "z": 0.0}
        ship["velocity"] = {"x": 0.0, "y": 0.0, "z": 0.0}
        ship["acceleration"] = {"x": 0.0, "y": 0.0, "z": 0.0}
        ship["sector"] = {"x": 0, "y": 0, "z": 0}
        return {"status": f"{ship_id} reset to origin"}

    else:
        return {"error": f"Unknown command type: {cmd}"}
