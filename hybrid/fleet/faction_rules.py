"""Faction hostility and diplomatic rules for NPC AI.

Determines faction relationships using a four-level diplomatic state
model: ALLIED, NEUTRAL, HOSTILE, UNKNOWN.  The legacy ``are_hostile``
helper is preserved for backward compatibility — it delegates to the
diplomatic state system.

Diplomatic state is symmetric: if A→B is HOSTILE, then B→A is HOSTILE.
"""

from enum import Enum
from typing import Dict, FrozenSet, Set, Optional


class DiplomaticState(Enum):
    """Four-level diplomatic relationship between factions.

    ALLIED   — shares sensor contacts, won't target each other.
    NEUTRAL  — responds to hails, won't fire first.
    HOSTILE  — may ignore hails, will engage on sight.
    UNKNOWN  — default for unidentified contacts; must hail/scan.
    """
    ALLIED = "allied"
    NEUTRAL = "neutral"
    HOSTILE = "hostile"
    UNKNOWN = "unknown"


# ── Explicit faction pair relationships ──────────────────────────────
# Key: frozenset of two lowercase faction names → DiplomaticState.
# Any pair NOT listed here defaults to UNKNOWN.

_FACTION_RELATIONS: Dict[FrozenSet[str], DiplomaticState] = {
    # Pirates are hostile to everyone
    frozenset({"pirates", "unsa"}): DiplomaticState.HOSTILE,
    frozenset({"pirates", "civilian"}): DiplomaticState.HOSTILE,
    frozenset({"pirates", "mars"}): DiplomaticState.HOSTILE,
    frozenset({"pirates", "neutral"}): DiplomaticState.HOSTILE,
    # Generic "hostile" faction
    frozenset({"hostile", "unsa"}): DiplomaticState.HOSTILE,
    frozenset({"hostile", "civilian"}): DiplomaticState.HOSTILE,
    frozenset({"hostile", "mars"}): DiplomaticState.HOSTILE,
    frozenset({"hostile", "neutral"}): DiplomaticState.HOSTILE,
    # MCRN vs UNE (scenario-driven)
    frozenset({"mcrn", "unsa"}): DiplomaticState.HOSTILE,
    # Allied pairs
    frozenset({"unsa", "civilian"}): DiplomaticState.ALLIED,
    frozenset({"mars", "civilian"}): DiplomaticState.NEUTRAL,
    frozenset({"unsa", "neutral"}): DiplomaticState.NEUTRAL,
    frozenset({"mars", "neutral"}): DiplomaticState.NEUTRAL,
}

# Legacy compatibility set — derived from _FACTION_RELATIONS at import time.
HOSTILE_PAIRS: Set[FrozenSet[str]] = {
    pair for pair, state in _FACTION_RELATIONS.items()
    if state == DiplomaticState.HOSTILE
}


def get_diplomatic_state(faction_a: str, faction_b: str) -> DiplomaticState:
    """Get the diplomatic relationship between two factions.

    Same-faction is always ALLIED.  Unknown pairs default to UNKNOWN.

    Args:
        faction_a: First faction name (case-insensitive).
        faction_b: Second faction name (case-insensitive).

    Returns:
        DiplomaticState for the pair.
    """
    if not faction_a or not faction_b:
        return DiplomaticState.UNKNOWN
    a, b = faction_a.lower(), faction_b.lower()
    if a == b:
        return DiplomaticState.ALLIED
    return _FACTION_RELATIONS.get(frozenset({a, b}), DiplomaticState.UNKNOWN)


def are_hostile(faction_a: str, faction_b: str) -> bool:
    """Check if two factions are hostile to each other.

    Backward-compatible helper — delegates to ``get_diplomatic_state``.

    Args:
        faction_a: First faction name (case-insensitive).
        faction_b: Second faction name (case-insensitive).

    Returns:
        True if the factions are hostile.
    """
    return get_diplomatic_state(faction_a, faction_b) == DiplomaticState.HOSTILE


def are_allied(faction_a: str, faction_b: str) -> bool:
    """Check if two factions are allied.

    Args:
        faction_a: First faction name (case-insensitive).
        faction_b: Second faction name (case-insensitive).

    Returns:
        True if the factions are allied (including same faction).
    """
    return get_diplomatic_state(faction_a, faction_b) == DiplomaticState.ALLIED
