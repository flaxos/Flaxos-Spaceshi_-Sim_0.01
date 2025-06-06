from collections import defaultdict

def assign_ships_to_sectors(fleet):
    sectors = defaultdict(lambda: {"ships": {}})
    for ship_id, ship in fleet.items():
        sector = ship.get("sector")
        if sector:
            sectors[sector]["ships"][ship_id] = ship
        else:
            print(f"[WARN] Ship '{ship_id}' has invalid sector: {sector}. Skipping.")
    return dict(sectors)
