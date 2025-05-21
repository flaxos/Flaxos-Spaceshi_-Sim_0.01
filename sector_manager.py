import math

class SectorManager:
    def __init__(self, sector_size=1000):
        self.sector_size = sector_size
        self.sectors = {}  # (x, y, z) tuple -> list of ships

    def _get_sector_key(self, position):
        return (
            int(position["x"] // self.sector_size),
            int(position["y"] // self.sector_size),
            int(position["z"] // self.sector_size)
        )

    def add_ship(self, ship):
        key = self._get_sector_key(ship.position)
        self.sectors.setdefault(key, []).append(ship)

    def update_ship_position(self, ship, old_position):
        old_key = self._get_sector_key(old_position)
        new_key = self._get_sector_key(ship.position)
        if old_key != new_key:
            self.sectors[old_key].remove(ship)
            if not self.sectors[old_key]:
                del self.sectors[old_key]
            self.sectors.setdefault(new_key, []).append(ship)

    def get_nearby_ships(self, position, radius):
        keys = self._get_keys_in_radius(position, radius)
        nearby = []
        for key in keys:
            nearby.extend(self.sectors.get(key, []))
        return nearby

    def _get_keys_in_radius(self, position, radius):
        cx, cy, cz = self._get_sector_key(position)
        r = math.ceil(radius / self.sector_size)
        keys = []
        for dx in range(-r, r+1):
            for dy in range(-r, r+1):
                for dz in range(-r, r+1):
                    keys.append((cx + dx, cy + dy, cz + dz))
        return keys

print("[DEBUG] Simulation exited unexpectedly.")

