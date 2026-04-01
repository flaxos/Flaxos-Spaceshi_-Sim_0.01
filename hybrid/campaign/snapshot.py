"""Snapshot application helpers for campaign state updates.

These functions handle the detailed merging of post-mission ship and crew
snapshots into the campaign's persistent state. Separated from the main
CampaignState class to keep modules under 300 lines.
"""

from __future__ import annotations

from typing import Any, Dict, List


def apply_ship_snapshot(ship_state: Dict[str, Any], snapshot: dict) -> None:
    """Merge post-mission ship state into the campaign ship_state dict.

    Mutates ship_state in place with hull, subsystem, ammo, and fuel
    values from the mission snapshot.

    Args:
        ship_state: The campaign's persistent ship_state dict.
        snapshot: Post-mission ship snapshot from the sim.
    """
    # Hull
    hull_pct = snapshot.get("hull_percent")
    if hull_pct is not None:
        ship_state["hull_percent"] = max(0.0, min(100.0, hull_pct))

    # Subsystem health
    subsys = snapshot.get("subsystems")
    if subsys:
        if "subsystems" not in ship_state:
            ship_state["subsystems"] = {}
        for name, health in subsys.items():
            ship_state["subsystems"][name] = max(0.0, min(100.0, health))

    # Ammo
    ammo = snapshot.get("ammo")
    if ammo:
        ship_state["ammo"] = dict(ammo)

    # Fuel
    fuel = snapshot.get("fuel")
    if fuel is not None:
        ship_state["fuel"] = max(0.0, fuel)


def apply_crew_snapshot(
    crew_roster: List[Dict[str, Any]],
    crew_snapshot: list,
    outcome: str,
) -> None:
    """Merge post-mission crew state and award XP.

    Fatigue and stress carry forward from the snapshot. On success,
    each crew member gets a skill improvement in their two strongest
    skills (capped at level 6).

    Args:
        crew_roster: The campaign's persistent crew roster list (mutated).
        crew_snapshot: Post-mission crew dicts from the sim.
        outcome: Mission outcome ("success", "failure", "partial").
    """
    # Build lookup by crew_id for merging
    roster_by_id = {c["crew_id"]: c for c in crew_roster}

    for snap in crew_snapshot:
        cid = snap.get("crew_id")
        if cid and cid in roster_by_id:
            member = roster_by_id[cid]
            # Carry forward fatigue, stress, health
            if "fatigue" in snap:
                member["fatigue"] = snap["fatigue"]
            if "stress" in snap:
                member["stress"] = snap["stress"]
            if "health" in snap:
                member["health"] = snap["health"]
            # Carry forward skill changes if present
            if "skills" in snap:
                member["skills"] = snap["skills"]

    # XP reward on success: bump two primary skills by 1 level (capped at 6)
    if outcome == "success":
        for member in crew_roster:
            skills = member.get("skills", {})
            if skills:
                sorted_skills = sorted(
                    skills.items(), key=lambda x: x[1], reverse=True,
                )
                for skill_name, level in sorted_skills[:2]:
                    if level < 6:
                        skills[skill_name] = level + 1
