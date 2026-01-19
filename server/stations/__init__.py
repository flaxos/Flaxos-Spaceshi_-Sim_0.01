"""
Station-based control architecture for multi-crew spaceship operations.

This package enables multiple clients to control different stations on the same ship,
allowing for Expanse-style bridge crew gameplay.
"""

from .station_types import (
    StationType,
    PermissionLevel,
    StationDefinition,
    STATION_DEFINITIONS,
    get_station_commands,
    get_station_for_command,
    get_all_stations_for_command,
)

from .station_manager import (
    StationManager,
    StationClaim,
    ClientSession,
)

__all__ = [
    'StationType',
    'PermissionLevel',
    'StationDefinition',
    'STATION_DEFINITIONS',
    'get_station_commands',
    'get_station_for_command',
    'get_all_stations_for_command',
    'StationManager',
    'StationClaim',
    'ClientSession',
]
