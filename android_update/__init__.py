"""Android Auto-Update System for Flaxos Spaceship Sim."""

from .updater import AutoUpdater, UpdateChecker
from .version import VersionManager

__all__ = ["AutoUpdater", "UpdateChecker", "VersionManager"]
