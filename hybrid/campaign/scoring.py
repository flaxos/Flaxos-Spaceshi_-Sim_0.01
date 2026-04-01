# hybrid/campaign/scoring.py
"""Mission scoring and after-action report generation.

Computes a comprehensive score from combat log events, objective
completion, and ship state snapshots. The score breaks down into
measurable axes so the player understands exactly where they
excelled or struggled.

Design principle: every number traces back to a concrete player
action. "Accuracy 0.35" means "you hit 7 of 20 shots" -- not a
vague abstract rating.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from hybrid.campaign.stats import extract_combat_stats
from hybrid.campaign.tips import generate_tips

logger = logging.getLogger(__name__)

# Grade thresholds (total_score out of 1000)
GRADE_THRESHOLDS = [
    (900, "S"),
    (750, "A"),
    (600, "B"),
    (450, "C"),
    (300, "D"),
]
# Below 300 -> "F"

# Weights for the weighted sum (must sum to 1.0)
METRIC_WEIGHTS = {
    "efficiency": 0.15,
    "accuracy": 0.25,
    "preservation": 0.25,
    "crew_safety": 0.10,
    "objectives": 0.25,
}

# Style bonus point values (added on top of weighted base)
STYLE_BONUS_POINTS = {
    "surgical": 40,
    "untouchable": 50,
    "knife_edge": 20,
    "ammo_miser": 15,
}


@dataclass
class MissionScore:
    """Comprehensive mission score with breakdown and tips.

    Each metric is 0.0-1.0, higher is better. Style bonuses are
    boolean flags worth flat point bonuses. total_score is 0-1000.
    """

    # Core metrics (0.0 to 1.0)
    efficiency: float = 0.0
    accuracy: float = 0.0
    preservation: float = 0.0
    crew_safety: float = 1.0
    objectives: float = 0.0

    # Style bonuses
    surgical: bool = False
    untouchable: bool = False
    knife_edge: bool = False
    ammo_miser: bool = False

    # Computed
    total_score: int = 0
    grade: str = "F"

    # Debrief tips derived from combat log analysis
    improvement_tips: List[str] = field(default_factory=list)

    # Raw stats for the after-action timeline
    shots_fired: int = 0
    shots_hit: int = 0
    damage_taken: float = 0.0
    damage_dealt: float = 0.0
    torpedoes_launched: int = 0
    torpedoes_hit: int = 0
    missiles_launched: int = 0
    missiles_hit: int = 0
    mission_result: str = "failure"

    # Timeline events (for the GUI after-action report)
    timeline: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Serialize for transport to the GUI."""
        return {
            "efficiency": round(self.efficiency, 3),
            "accuracy": round(self.accuracy, 3),
            "preservation": round(self.preservation, 3),
            "crew_safety": round(self.crew_safety, 3),
            "objectives": round(self.objectives, 3),
            "surgical": self.surgical,
            "untouchable": self.untouchable,
            "knife_edge": self.knife_edge,
            "ammo_miser": self.ammo_miser,
            "total_score": self.total_score,
            "grade": self.grade,
            "improvement_tips": self.improvement_tips,
            "shots_fired": self.shots_fired,
            "shots_hit": self.shots_hit,
            "damage_taken": round(self.damage_taken, 1),
            "damage_dealt": round(self.damage_dealt, 1),
            "torpedoes_launched": self.torpedoes_launched,
            "torpedoes_hit": self.torpedoes_hit,
            "missiles_launched": self.missiles_launched,
            "missiles_hit": self.missiles_hit,
            "mission_result": self.mission_result,
            "timeline": self.timeline,
        }


class MissionScorer:
    """Computes mission score from combat log and mission result.

    Stateless -- call score_mission() with the data from one completed
    mission and get a MissionScore back. No side effects.
    """

    def score_mission(
        self,
        mission_result: str,
        combat_log_events: List[Dict],
        ship_state_start: Dict,
        ship_state_end: Dict,
        sim_time_elapsed: float,
        par_time: float = 300.0,
        objectives_status: Optional[Dict] = None,
    ) -> MissionScore:
        """Compute comprehensive mission score.

        Args:
            mission_result: "success" or "failure".
            combat_log_events: List of CombatLogEntry.to_dict() dicts.
            ship_state_start: Snapshot of player ship state at mission start.
            ship_state_end: Snapshot of player ship state at mission end.
            sim_time_elapsed: Total sim seconds from start to completion.
            par_time: Scenario-defined par time (seconds). Default 300s.
            objectives_status: Dict of objective dicts from ObjectiveTracker.

        Returns:
            Fully computed MissionScore.
        """
        score = MissionScore()
        score.mission_result = mission_result

        # -- Extract raw stats from combat log events --
        stats = self._extract_combat_stats(combat_log_events)
        score.shots_fired = stats["shots_fired"]
        score.shots_hit = stats["shots_hit"]
        score.torpedoes_launched = stats["torpedoes_launched"]
        score.torpedoes_hit = stats["torpedoes_hit"]
        score.missiles_launched = stats["missiles_launched"]
        score.missiles_hit = stats["missiles_hit"]
        score.damage_dealt = stats["damage_dealt"]
        score.damage_taken = stats["damage_taken"]

        # -- Core metrics --
        score.efficiency = self._calc_efficiency(sim_time_elapsed, par_time)
        score.accuracy = self._calc_accuracy(stats)
        score.preservation = self._calc_preservation(
            ship_state_start, ship_state_end
        )
        score.crew_safety = self._calc_crew_safety(
            ship_state_start, ship_state_end
        )
        score.objectives = self._calc_objectives(objectives_status)

        # -- Style bonuses --
        score.surgical = self._check_surgical(
            mission_result, ship_state_end, stats
        )
        score.untouchable = self._check_untouchable(stats)
        score.knife_edge = self._check_knife_edge(ship_state_end)
        score.ammo_miser = self._check_ammo_miser(ship_state_start, ship_state_end)

        # -- Compute total score --
        score.total_score = self._calc_total_score(score)
        score.grade = self._calc_grade(score.total_score)

        # -- Generate improvement tips from combat log --
        score.improvement_tips = self._generate_tips(
            stats, combat_log_events, sim_time_elapsed, score
        )

        # -- Build timeline of key events --
        score.timeline = self._build_timeline(combat_log_events)

        return score

    # ── Metric Calculators ────────────────────────────────────

    def _calc_efficiency(
        self, elapsed: float, par_time: float
    ) -> float:
        """Efficiency = par_time / actual_time, capped at 1.5.

        Faster completion scores higher, but diminishing returns
        past 1.0 prevent speed-running cheese from dominating.
        """
        if elapsed <= 0:
            return 1.0
        if par_time <= 0:
            return 1.0
        ratio = par_time / elapsed
        return min(ratio, 1.5)

    def _calc_accuracy(self, stats: Dict) -> float:
        """Accuracy = total hits / total shots across all weapons.

        Includes railgun, torpedo, and missile fire. PDC bursts
        are excluded because PDC is suppression fire by design
        and shouldn't penalize the accuracy score.
        """
        total_fired = (
            stats["shots_fired"]
            + stats["torpedoes_launched"]
            + stats["missiles_launched"]
        )
        total_hit = (
            stats["shots_hit"]
            + stats["torpedoes_hit"]
            + stats["missiles_hit"]
        )
        if total_fired == 0:
            # No weapons fired -- score neutral (tutorial missions etc)
            return 1.0
        return total_hit / total_fired

    def _calc_preservation(
        self, start: Dict, end: Dict
    ) -> float:
        """Preservation = 1.0 - (damage_taken / max_hull).

        Measures how well the player protected their ship.
        """
        max_hull = start.get("hull_integrity", 100.0)
        if max_hull <= 0:
            return 0.0
        end_hull = end.get("hull_integrity", max_hull)
        damage_fraction = max(0.0, (max_hull - end_hull) / max_hull)
        return max(0.0, 1.0 - damage_fraction)

    def _calc_crew_safety(
        self, start: Dict, end: Dict
    ) -> float:
        """Crew safety = 1.0 - (injured_crew / total_crew).

        Falls back to 1.0 if no crew data exists (most scenarios
        don't track individual crew yet).
        """
        total = start.get("crew_count", 0)
        if total <= 0:
            return 1.0
        injured = end.get("crew_injured", 0)
        return max(0.0, 1.0 - (injured / total))

    def _calc_objectives(
        self, objectives_status: Optional[Dict]
    ) -> float:
        """Objectives = completed_count / total_count.

        Includes both required and optional objectives so players
        who go above and beyond get rewarded.
        """
        if not objectives_status:
            return 0.0

        total = 0
        completed = 0
        for obj in objectives_status.values():
            # Handle both raw dicts and Objective-like objects
            obj_dict = obj if isinstance(obj, dict) else getattr(obj, "__dict__", {})
            total += 1
            status = obj_dict.get("status", "")
            if status == "completed" or status == "COMPLETED":
                completed += 1

        if total == 0:
            return 0.0
        return completed / total

    # ── Style Bonus Checks ────────────────────────────────────

    def _check_surgical(
        self, result: str, end_state: Dict, stats: Dict
    ) -> bool:
        """Surgical: mission kill without hull destruction.

        The player disabled the target's critical systems without
        reducing hull to zero. Rewards precision over brute force.
        """
        if result != "success":
            return False
        # If the player dealt damage but the target was not "destroyed"
        # (hull > 0 at mission end), it was a surgical mission kill
        target_destroyed = stats.get("target_destroyed", False)
        return not target_destroyed and stats["damage_dealt"] > 0

    def _check_untouchable(self, stats: Dict) -> bool:
        """Untouchable: zero damage taken."""
        return stats["damage_taken"] <= 0.0

    def _check_knife_edge(self, end_state: Dict) -> bool:
        """Knife edge: completed with < 25% fuel remaining."""
        max_fuel = end_state.get("max_fuel", 0)
        if max_fuel <= 0:
            return False
        fuel = end_state.get("fuel_level", max_fuel)
        return (fuel / max_fuel) < 0.25

    def _check_ammo_miser(
        self, start_state: Dict, end_state: Dict
    ) -> bool:
        """Ammo miser: completed with > 75% ammo remaining."""
        start_ammo = start_state.get("total_ammo", 0)
        if start_ammo <= 0:
            return False
        end_ammo = end_state.get("total_ammo", 0)
        return (end_ammo / start_ammo) > 0.75

    # ── Score Computation ─────────────────────────────────────

    def _calc_total_score(self, score: MissionScore) -> int:
        """Weighted sum of metrics (0-1000) plus style bonuses.

        Failure missions get a 50% penalty on the base score so
        there's still differentiation between "died immediately"
        and "almost won."
        """
        # Base score from weighted metrics
        base = 0.0
        for metric, weight in METRIC_WEIGHTS.items():
            val = getattr(score, metric, 0.0)
            # Clamp to 0-1 range (efficiency can exceed 1.0)
            clamped = max(0.0, min(1.0, val))
            base += clamped * weight

        # Scale to 0-1000
        base_score = base * 1000

        # Apply failure penalty
        if score.mission_result != "success":
            base_score *= 0.5

        # Add style bonuses (only if mission succeeded)
        bonus = 0
        if score.mission_result == "success":
            for bonus_name, points in STYLE_BONUS_POINTS.items():
                if getattr(score, bonus_name, False):
                    bonus += points

        return min(1000, int(base_score + bonus))

    def _calc_grade(self, total_score: int) -> str:
        """Map total score to letter grade."""
        for threshold, grade in GRADE_THRESHOLDS:
            if total_score >= threshold:
                return grade
        return "F"

    # ── Combat Stats Extraction ───────────────────────────────

    def _extract_combat_stats(self, events: List[Dict]) -> Dict:
        """Delegate to stats module for event extraction."""
        return extract_combat_stats(events)

    # ── Tip Generation ────────────────────────────────────────

    def _generate_tips(
        self,
        stats: Dict,
        events: List[Dict],
        elapsed: float,
        score: MissionScore,
    ) -> List[str]:
        """Delegate to tips module for combat log analysis."""
        return generate_tips(stats, events, elapsed, score)

    # ── Timeline Builder ──────────────────────────────────────

    def _build_timeline(
        self, events: List[Dict]
    ) -> List[Dict]:
        """Extract key events for the after-action timeline.

        Filters out routine events (reloads, info-level) and keeps
        the high-signal events: hits, misses, damage, kills, locks.
        Limits to 20 entries to keep the report focused.
        """
        KEY_TYPES = {
            "projectile_hit", "projectile_miss",
            "torpedo_hit", "torpedo_miss", "torpedo_launch",
            "missile_hit", "missile_miss", "missile_launch",
            "ship_damage", "ship_destroyed",
            "hit", "miss", "damage",
            "lock", "lock_lost",
        }

        timeline = []
        for ev in events:
            if ev.get("event_type") in KEY_TYPES:
                timeline.append({
                    "time": ev.get("sim_time", 0),
                    "type": ev.get("event_type"),
                    "summary": ev.get("summary", ""),
                    "severity": ev.get("severity", "info"),
                })

        # Keep at most 20 entries, preferring later events
        if len(timeline) > 20:
            timeline = timeline[-20:]

        return timeline
