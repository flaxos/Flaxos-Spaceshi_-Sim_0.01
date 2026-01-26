# hybrid/ship_factory.py
"""Factory helpers for creating ships with systems."""
from hybrid.systems.weapons.hardpoint import Hardpoint
from hybrid.systems.weapons.weapon_system import WeaponSystem
from hybrid.systems.power.management import PowerManagementSystem
from hybrid.systems.navigation.navigation import NavigationSystem
from hybrid.systems.sensors.sensor_system import SensorSystem


def build_ship_systems(config):
    power_management = PowerManagementSystem(
        config.get("power_management", config.get("power", {}))
    )
    weapon_cfg = config.get("weapons", {})
    weapon_system = WeaponSystem(weapon_cfg)
    hardpoints = []
    for hcfg in weapon_cfg.get("hardpoints", []):
        hp = Hardpoint(
            id=hcfg["id"],
            mount_type=hcfg.get("mount_type", "fixed"),
            position_offset=hcfg.get("position_offset", {"x": 0.0, "y": 0.0, "z": 0.0}),
            orientation=hcfg.get("orientation", {"azimuth": 0.0, "elevation": 0.0}),
            max_rotation_rate=hcfg.get("max_rotation_rate", 30.0 if hcfg.get("mount_type") == "turret" else 0.0),
            azimuth_limits=tuple(hcfg["azimuth_limits"]) if "azimuth_limits" in hcfg else None,
            elevation_limits=tuple(hcfg["elevation_limits"]) if "elevation_limits" in hcfg else None
        )
        wname = hcfg.get("weapon")
        if wname and wname in weapon_system.weapons:
            hp.mount_weapon(weapon_system.weapons[wname])
        hardpoints.append(hp)
    navigation = NavigationSystem(config.get("navigation", {}))
    sensors = SensorSystem(config.get("sensors", {}))
    return {
        "power_management": power_management,
        "weapons": weapon_system,
        "hardpoints": hardpoints,
        "navigation": navigation,
        "sensors": sensors,
    }


def create_ship(config):
    """Create ship systems dict from configuration."""
    return build_ship_systems(config)
