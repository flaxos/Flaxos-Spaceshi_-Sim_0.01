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
    }
    
    return system_map.get(system_type)

# Import system implementations
from hybrid.systems.power_system import PowerSystem
from hybrid.systems.propulsion_system import PropulsionSystem
from hybrid.systems.sensor_system import SensorSystem
from hybrid.systems.navigation_system import NavigationSystem
from hybrid.systems.helm_system import HelmSystem
from hybrid.systems.bio_monitor_system import BioMonitorSystem
from hybrid.systems.power_management_system import PowerManagementSystem
__all__ = [
    'PowerSystem',
    'SensorSystem',
    'HelmSystem',
    'NavigationSystem',
    'BioMonitorSystem',
    'PropulsionSystem',
    'PowerManagementSystem',
]
