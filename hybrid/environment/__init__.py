# hybrid/environment/__init__.py
"""Environmental hazards package.

Provides asteroid fields, hazard zones, and an environment manager
that integrates with the simulator tick loop.
"""

from hybrid.environment.asteroid_field import AsteroidField, Asteroid
from hybrid.environment.hazard_zone import HazardZone, HazardType
from hybrid.environment.environment_manager import EnvironmentManager

__all__ = [
    "AsteroidField",
    "Asteroid",
    "HazardZone",
    "HazardType",
    "EnvironmentManager",
]
