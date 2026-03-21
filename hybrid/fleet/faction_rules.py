"""Faction hostility rules for NPC AI.

Determines which factions are hostile to each other. Used by the AI
controller to identify threats from sensor contacts. Hostility is
symmetric -- if A is hostile to B, then B is hostile to A.
"""

from typing import FrozenSet, Set

# Each frozenset pair represents mutual hostility between two factions.
# Add new pairs here when introducing new factions.
HOSTILE_PAIRS: Set[FrozenSet[str]] = {
    frozenset({"pirates", "unsa"}),
    frozenset({"pirates", "civilian"}),
    frozenset({"pirates", "mars"}),
    frozenset({"hostile", "unsa"}),
    frozenset({"hostile", "civilian"}),
    frozenset({"hostile", "mars"}),
    # MCRN vs UNE factions (scenario-driven hostility)
    frozenset({"mcrn", "unsa"}),
}


def are_hostile(faction_a: str, faction_b: str) -> bool:
    """Check if two factions are hostile to each other.

    Args:
        faction_a: First faction name (case-insensitive).
        faction_b: Second faction name (case-insensitive).

    Returns:
        True if the factions are hostile.
    """
    if not faction_a or not faction_b:
        return False
    if faction_a == faction_b:
        return False
    return frozenset({faction_a.lower(), faction_b.lower()}) in HOSTILE_PAIRS
