# hybrid/systems/simulation.py
import time
from hybrid.systems.power.management import PowerManagementSystem
from hybrid.systems.weapons.weapon_system import WeaponSystem
from hybrid.systems.navigation.navigation import NavigationSystem
from hybrid.systems.sensors.sensor_system import SensorSystem
from hybrid.core.event_bus import EventBus

class Simulation:
    def __init__(self, ship_configs):
        self.ships = {}
        for ship_id, config in ship_configs.items():
            power_manager = PowerManagementSystem(config.get("power", {}))
            weapon_system = WeaponSystem(config.get("weapons", {}))
            nav_system = NavigationSystem(config.get("navigation", {}))
            sensor_system = SensorSystem(config.get("sensors", {}))
            self.ships[ship_id] = {
                "power": power_manager,
                "weapons": weapon_system,
                "navigation": nav_system,
                "sensors": sensor_system
            }
        self.event_bus = EventBus.get_instance()

    def run(self, total_time, tick_rate=0.1):
        t = 0.0
        while t < total_time:
            for ship_id, systems in self.ships.items():
                dt = tick_rate
                systems["sensors"].tick(dt)
                systems["navigation"].tick(dt)
                systems["weapons"].tick(dt)
                systems["power"].tick(dt)
            time.sleep(tick_rate)
            t += tick_rate
