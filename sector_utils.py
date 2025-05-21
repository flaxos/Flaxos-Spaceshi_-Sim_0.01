# sector_utils.py
SECTOR_SIZE_KM = 100_000

def get_sector(position, sector_size=SECTOR_SIZE_KM):
    return {
        "x": int(position["x"] // sector_size),
        "y": int(position["y"] // sector_size),
        "z": int(position["z"] // sector_size)
    }

def update_ship_sector(ship):
    pos = ship.get("position", {})
    if all(k in pos for k in ("x", "y", "z")):
        ship["sector"] = get_sector(pos)
