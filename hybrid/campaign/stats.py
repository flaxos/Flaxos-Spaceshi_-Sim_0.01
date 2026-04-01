# hybrid/campaign/stats.py
"""Combat statistics extraction from combat log events.

Walks the event list once and tallies hits, misses, damage dealt/taken
per weapon category. Also captures patterns needed for tip generation
(low-confidence fires, torpedo intercepts, early damage).
"""

from __future__ import annotations

from typing import Dict, List


def extract_combat_stats(events: List[Dict]) -> Dict:
    """Extract raw combat statistics from log events.

    Args:
        events: List of CombatLogEntry.to_dict() dicts.

    Returns:
        Dict with tallied combat stats.
    """
    stats = {
        "shots_fired": 0,
        "shots_hit": 0,
        "torpedoes_launched": 0,
        "torpedoes_hit": 0,
        "missiles_launched": 0,
        "missiles_hit": 0,
        "damage_dealt": 0.0,
        "damage_taken": 0.0,
        "target_destroyed": False,
        # For tip generation
        "low_confidence_fires": 0,
        "torpedoes_intercepted": 0,
        "early_damage_events": [],
        "shots_at_dead_targets": 0,
        "evasive_maneuvers_during_incoming": 0,
    }

    for ev in events:
        et = ev.get("event_type", "")
        details = ev.get("details", {})

        # -- Railgun projectile events --
        if et == "projectile_fired":
            stats["shots_fired"] += 1
            confidence = details.get("confidence_at_fire", 0)
            if confidence and confidence < 0.5:
                stats["low_confidence_fires"] += 1

        elif et == "projectile_hit":
            if details.get("hit"):
                stats["shots_hit"] += 1
                stats["damage_dealt"] += details.get("damage", 0)

        elif et == "projectile_miss":
            # Slug expired without hitting -- already counted as fired
            pass

        # -- Torpedo events --
        elif et == "torpedo_launch":
            stats["torpedoes_launched"] += 1

        elif et == "torpedo_hit":
            hull_dmg = details.get("hull_damage", 0)
            if hull_dmg > 0:
                stats["torpedoes_hit"] += 1
                stats["damage_dealt"] += hull_dmg

        elif et == "torpedo_miss":
            # Check if intercepted by PDC
            if details.get("intercepted_by"):
                stats["torpedoes_intercepted"] += 1

        # -- Missile events --
        elif et == "missile_launch":
            stats["missiles_launched"] += 1

        elif et in ("missile_hit", "missile_miss"):
            hull_dmg = details.get("hull_damage", 0)
            if hull_dmg > 0:
                stats["missiles_hit"] += 1
                stats["damage_dealt"] += hull_dmg

        # -- Damage taken by player --
        elif et == "ship_damage":
            dmg = details.get("damage", 0)
            stats["damage_taken"] += dmg
            stats["early_damage_events"].append({
                "sim_time": ev.get("sim_time", 0),
                "damage": dmg,
            })

        # -- Target destroyed --
        elif et == "ship_destroyed":
            stats["target_destroyed"] = True

        # -- PDC intercept of incoming (hit) events --
        elif et == "hit":
            if details.get("hit"):
                stats["damage_dealt"] += details.get("damage", 0)

        elif et == "miss":
            pass

    return stats
