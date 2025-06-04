# hybrid/__init__.py
"""
Hybrid architecture implementation for ship simulation.
Combines object-oriented and event-driven approaches.
"""

from hybrid.core.base_system import BaseSystem
from hybrid.core.event_bus import EventBus
from hybrid.ship import Ship

__all__ = ['BaseSystem', 'EventBus', 'Ship']
