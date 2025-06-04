# sensors.py — Sensor system using BaseSystem and sector proximity

from hybrid.core.base_system import BaseSystem

class SensorArray(BaseSystem):
    def __init__(self, range):
        self.range = range
        self.detected = []
        self.scan_cooldown = 0
        self.scan_interval = 1.0  # seconds between scans

    def tick(self, delta_time, ship):
        self.scan_cooldown -= delta_time
        if self.scan_cooldown <= 0:
            self.scan_cooldown = self.scan_interval

            # Must be injected into ship before sim
            if hasattr(ship, "sector_manager"):
                nearby = ship.sector_manager.get_nearby_ships(ship.position, self.range)
                self.detected = [s.id for s in nearby if s.id != ship.id]
            else:
                self.detected = []

    def get_state(self):
        return {
            "range": self.range,
            "detected_ships": self.detected
        }

    def command(self, action, params):
        if action == "set_range":
            self.range = params.get("value", self.range)
