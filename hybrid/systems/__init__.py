# hybrid/systems/__init__.py
"""
System implementations for the hybrid architecture.
Each system is responsible for a specific aspect of ship functionality.
"""
# hybrid/systems/__init__.py
"""
Systems module for the hybrid architecture.
This module contains all the specific system implementations.
"""

def get_system_class(system_type):
    """
    Get the appropriate system class for a given system type
    
    Args:
        system_type (str): Type of system to create
        
    Returns:
        class: The system class, or None if not found
    """
    system_map = {
        "power": PowerSystem,
        "propulsion": PropulsionSystem,
        "sensors": SensorSystem,
        "navigation": NavigationSystem,
        "helm": HelmSystem,
        "bio": BioMonitorSystem,
        "power_management": PowerManagementSystem,
        "targeting": TargetingSystem,
        "weapons": WeaponSystem,
        "rcs": RCSSystem,
    }
    
    return system_map.get(system_type)

# Import system implementations
from hybrid.systems.power_system import PowerSystem
from hybrid.systems.propulsion_system import PropulsionSystem
from hybrid.systems.sensors.sensor_system import SensorSystem
from hybrid.systems.navigation.navigation import NavigationSystem
from hybrid.systems.helm_system import HelmSystem
from hybrid.systems.bio_monitor_system import BioMonitorSystem
# Use the newer power management implementation that handles layered reactors
# and additional configuration like alert thresholds and system mapping.
from hybrid.systems.power.management import PowerManagementSystem
from hybrid.systems.targeting.targeting_system import TargetingSystem
from hybrid.systems.weapons.weapon_system import WeaponSystem
from hybrid.systems.rcs_system import RCSSystem

__all__ = [
    'PowerSystem',
    'SensorSystem',
    'HelmSystem',
    'NavigationSystem',
    'BioMonitorSystem',
    'PropulsionSystem',
    'PowerManagementSystem',
    'TargetingSystem',
    'WeaponSystem',
    'RCSSystem',
]
