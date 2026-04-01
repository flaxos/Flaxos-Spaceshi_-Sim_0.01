# hybrid/campaign/tips.py
"""Combat log analysis for after-action improvement tips.

Analyzes combat log events to detect patterns of suboptimal play
and produces 3 actionable tips ranked by severity. Each tip traces
back to a specific player action so the feedback is concrete:
"You fired 12 rounds at confidence below 50%" -- not vague advice.
"""

from __future__ import annotations

from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from hybrid.campaign.scoring import MissionScore


def generate_tips(
    stats: Dict,
    events: List[Dict],
    elapsed: float,
    score: MissionScore,
) -> List[str]:
    """Analyze combat log to produce 3 actionable improvement tips.

    Each tip pattern has a severity score (higher = more impactful).
    We pick the top 3 by severity so the player gets the most
    useful feedback first.

    Args:
        stats: Extracted combat statistics dict.
        events: Raw combat log event dicts.
        elapsed: Total mission time in seconds.
        score: Partially computed MissionScore (metrics filled in).

    Returns:
        List of up to 3 tip strings.
    """
    candidates: List[tuple] = []  # (severity, tip_text)

    # 1. Low-confidence firing
    low_conf = stats["low_confidence_fires"]
    if low_conf >= 2:
        candidates.append((
            low_conf * 10,
            f"You fired {low_conf} railgun round(s) at confidence below "
            f"50% -- wait for 60%+ for roughly 2x hit rate."
        ))

    # 2. Torpedoes intercepted by enemy PDC
    intercepted = stats["torpedoes_intercepted"]
    if intercepted >= 1:
        candidates.append((
            intercepted * 15,
            f"{intercepted} torpedo(es) were intercepted by enemy PDC -- "
            f"try the 'evasive' flight profile to complicate intercepts."
        ))

    # 3. Early damage: damage taken in first 25% of mission
    if elapsed > 0:
        quarter_time = elapsed * 0.25
        early_dmg = sum(
            e["damage"]
            for e in stats["early_damage_events"]
            if e["sim_time"] <= quarter_time
        )
        if early_dmg > 0:
            candidates.append((
                early_dmg * 2,
                f"You took {early_dmg:.0f} damage in the first 25% of "
                f"the mission -- consider evasive maneuvers on approach."
            ))

    # 4. Low accuracy overall
    if score.shots_fired > 0 and score.accuracy < 0.3:
        candidates.append((
            20,
            f"Overall accuracy was {score.accuracy:.0%} "
            f"({score.shots_hit}/{score.shots_fired} shots). "
            f"Close range and higher lock confidence improve hit rate."
        ))

    # 5. Torpedoes launched but none hit
    if stats["torpedoes_launched"] > 2 and stats["torpedoes_hit"] == 0:
        candidates.append((
            25,
            f"Launched {stats['torpedoes_launched']} torpedoes with 0 hits. "
            f"Torpedoes work best against large/slow targets at close range."
        ))

    # 6. Missiles launched but none hit
    if stats["missiles_launched"] > 2 and stats["missiles_hit"] == 0:
        candidates.append((
            25,
            f"Launched {stats['missiles_launched']} missiles with 0 hits. "
            f"Try 'evasive' or 'bracket' flight profiles against maneuvering targets."
        ))

    # 7. Took heavy damage (preservation < 50%)
    if score.preservation < 0.5 and score.preservation > 0.0:
        pct_lost = (1.0 - score.preservation) * 100
        candidates.append((
            15,
            f"Lost {pct_lost:.0f}% hull integrity. Closing distance "
            f"under fire is risky -- consider stand-off torpedo attacks."
        ))

    # 8. Time ran out or very slow completion
    if score.efficiency < 0.5:
        candidates.append((
            12,
            f"Mission took {score.efficiency:.0%} of the par time "
            f"efficiency. Use intercept autopilot and higher G to "
            f"close distance faster."
        ))

    # 9. No weapons fired at all (in a combat mission)
    total_fired = (
        stats["shots_fired"]
        + stats["torpedoes_launched"]
        + stats["missiles_launched"]
    )
    if total_fired == 0 and score.mission_result == "failure":
        candidates.append((
            30,
            "No weapons were fired. Lock a target first with the "
            "targeting panel, then select a weapon and fire."
        ))

    # Sort by severity (highest first) and take top 3
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [tip for _, tip in candidates[:3]]
