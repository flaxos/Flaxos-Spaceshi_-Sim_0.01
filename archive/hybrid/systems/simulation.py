# hybrid/systems/simulation.py

import time
from hybrid.systems.power.management import PowerManagementSystem
from hybrid.systems.weapons.weapon_system import WeaponSystem
from hybrid.systems.navigation.navigation import NavigationSystem
from hybrid.systems.sensors.sensor_system import SensorSystem
from hybrid.core.event_bus import EventBus

class Simulation:
    def __init__(self, ship_configs):
        # ship_configs: dict mapping ship_id → config dict
        self.ships = {}
        for ship_id, config in ship_configs.items():
            power_mgr = PowerManagementSystem(config.get("power", {}))
            weapon_sys = WeaponSystem(config.get("weapons", {}))
            nav_sys = NavigationSystem(config.get("navigation", {}))
            sensor_sys = SensorSystem(config.get("sensors", {}))
            self.ships[ship_id] = {
                "power": power_mgr,
                "weapons": weapon_sys,
                "navigation": nav_sys,
                "sensors": sensor_sys
            }
        self.event_bus = EventBus.get_instance()

    def run(self, total_time, tick_rate=0.1):
        elapsed = 0.0
        while elapsed < total_time:
            for ship_id, systems in self.ships.items():
                dt = tick_rate
                # Tick subsystems in order
                systems["sensors"].tick(dt)
                systems["navigation"].tick(dt)
                systems["weapons"].tick(dt)
                systems["power"].tick(dt)
            time.sleep(tick_rate)
            elapsed += tick_rate
