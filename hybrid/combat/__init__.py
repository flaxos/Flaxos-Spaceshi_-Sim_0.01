# hybrid/combat/__init__.py
"""Combat physics modules — armor, penetration, and related models."""

from hybrid.combat.armor import ArmorModel, PenetrationResult, ArmorSection

__all__ = ["ArmorModel", "PenetrationResult", "ArmorSection"]
