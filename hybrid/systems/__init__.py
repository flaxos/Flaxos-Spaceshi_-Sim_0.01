# hybrid/systems/__init__.py
"""
System implementations for the hybrid architecture.
Each system is responsible for a specific aspect of ship functionality.
"""
# hybrid/systems/__init__.py
"""
Systems module for the hybrid architecture.
This module contains all the specific system implementations.

Sprint C: Added CombatSystem for truth weapons.
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
        "combat": CombatSystem,
        "rcs": RCSSystem,
        "docking": DockingSystem,
        "flight_computer": FlightComputer,
        "thermal": ThermalSystem,
        "ops": OpsSystem,
        "ecm": ECMSystem,
        "engineering": EngineeringSystem,
        "comms": CommsSystem,
        "crew_fatigue": CrewFatigueSystem,
        "science": ScienceSystem,
        "fleet_coord": FleetCoordSystem,
        "crew_binding": CrewBindingSystem,
        "auto_tactical": AutoTacticalSystem,
        "auto_ops": AutoOpsSystem,
        "auto_engineering": AutoEngineeringSystem,
        "auto_science": AutoScienceSystem,
        "auto_comms": AutoCommsSystem,
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
from hybrid.systems.combat.combat_system import CombatSystem
from hybrid.systems.rcs_system import RCSSystem
from hybrid.systems.docking_system import DockingSystem
from hybrid.systems.flight_computer.system import FlightComputer
from hybrid.systems.thermal_system import ThermalSystem
from hybrid.systems.ops_system import OpsSystem
from hybrid.systems.ecm_system import ECMSystem
from hybrid.systems.engineering_system import EngineeringSystem
from hybrid.systems.comms_system import CommsSystem
from hybrid.systems.crew_fatigue_system import CrewFatigueSystem
from hybrid.systems.science_system import ScienceSystem
from hybrid.systems.fleet_coord_system import FleetCoordSystem
from hybrid.systems.crew_binding_system import CrewBindingSystem
from hybrid.systems.auto_tactical import AutoTacticalSystem
from hybrid.systems.auto_ops import AutoOpsSystem
from hybrid.systems.auto_engineering import AutoEngineeringSystem
from hybrid.systems.auto_science import AutoScienceSystem
from hybrid.systems.auto_comms import AutoCommsSystem

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
    'CombatSystem',
    'RCSSystem',
    'DockingSystem',
    'FlightComputer',
    'ThermalSystem',
    'OpsSystem',
    'ECMSystem',
    'EngineeringSystem',
    'CommsSystem',
    'CrewFatigueSystem',
    'ScienceSystem',
    'FleetCoordSystem',
    'CrewBindingSystem',
    'AutoTacticalSystem',
    'AutoOpsSystem',
    'AutoEngineeringSystem',
    'AutoScienceSystem',
    'AutoCommsSystem',
]
