# tests/test_mission_scoring.py
"""Tests for mission scoring and after-action report generation.

Validates:
- Score calculation from combat log events
- Grade thresholds (S >= 900, A >= 750, B >= 600, C >= 450, D >= 300)
- Style bonuses (surgical, untouchable, knife_edge, ammo_miser)
- Tip generation from combat log patterns
- Edge cases: no weapons fired, perfect play, total failure
"""

import pytest
from hybrid.campaign.scoring import MissionScorer, MissionScore


@pytest.fixture
def scorer():
    return MissionScorer()


# ── Helper Factories ─────────────────────────────────────────

def make_ship_state(
    hull: float = 100.0,
    max_hull: float = 100.0,
    fuel: float = 5000.0,
    max_fuel: float = 10000.0,
    total_ammo: int = 20,
    crew_count: int = 0,
    crew_injured: int = 0,
) -> dict:
    return {
        "hull_integrity": hull,
        "max_hull_integrity": max_hull,
        "fuel_level": fuel,
        "max_fuel": max_fuel,
        "total_ammo": total_ammo,
        "crew_count": crew_count,
        "crew_injured": crew_injured,
    }


def make_objectives(
    required_completed: int = 2,
    required_total: int = 2,
    optional_completed: int = 0,
    optional_total: int = 0,
) -> dict:
    """Build a dict of objective status dicts."""
    objs = {}
    for i in range(required_total):
        status = "completed" if i < required_completed else "in_progress"
        objs[f"req_{i}"] = {
            "id": f"req_{i}",
            "status": status,
            "required": True,
        }
    for i in range(optional_total):
        status = "completed" if i < optional_completed else "in_progress"
        objs[f"opt_{i}"] = {
            "id": f"opt_{i}",
            "status": status,
            "required": False,
        }
    return objs


def make_projectile_fired_event(confidence: float = 0.7, sim_time: float = 50.0) -> dict:
    return {
        "event_type": "projectile_fired",
        "sim_time": sim_time,
        "details": {"confidence_at_fire": confidence},
        "weapon": "UNE-440 Railgun",
        "severity": "info",
        "summary": "Railgun fired",
    }


def make_projectile_hit_event(
    hit: bool = True, damage: float = 30.0, sim_time: float = 52.0
) -> dict:
    return {
        "event_type": "projectile_hit",
        "sim_time": sim_time,
        "details": {"hit": hit, "damage": damage if hit else 0},
        "weapon": "UNE-440 Railgun",
        "severity": "hit" if hit else "miss",
        "summary": "Railgun hit" if hit else "Railgun miss",
    }


def make_torpedo_launch_event(sim_time: float = 100.0) -> dict:
    return {
        "event_type": "torpedo_launch",
        "sim_time": sim_time,
        "details": {"profile": "direct"},
        "weapon": "Torpedo",
        "severity": "info",
        "summary": "Torpedo launched",
    }


def make_torpedo_hit_event(hull_damage: float = 60.0, sim_time: float = 120.0) -> dict:
    return {
        "event_type": "torpedo_hit",
        "sim_time": sim_time,
        "details": {"hull_damage": hull_damage},
        "weapon": "Torpedo",
        "severity": "hit",
        "summary": "Torpedo impact",
    }


def make_torpedo_intercepted_event(sim_time: float = 115.0) -> dict:
    return {
        "event_type": "torpedo_miss",
        "sim_time": sim_time,
        "details": {"intercepted_by": "PDC"},
        "weapon": "Torpedo",
        "severity": "info",
        "summary": "Torpedo intercepted by PDC",
    }


def make_ship_damage_event(damage: float = 20.0, sim_time: float = 30.0) -> dict:
    return {
        "event_type": "ship_damage",
        "sim_time": sim_time,
        "details": {"damage": damage},
        "severity": "damage",
        "summary": f"Ship took {damage} damage",
    }


def make_missile_launch_event(sim_time: float = 80.0) -> dict:
    return {
        "event_type": "missile_launch",
        "sim_time": sim_time,
        "details": {"profile": "evasive"},
        "weapon": "Missile",
        "severity": "info",
        "summary": "Missile launched",
    }


def make_missile_hit_event(hull_damage: float = 25.0, sim_time: float = 90.0) -> dict:
    return {
        "event_type": "missile_hit",
        "sim_time": sim_time,
        "details": {"hull_damage": hull_damage},
        "weapon": "Missile",
        "severity": "hit",
        "summary": "Missile impact",
    }


# ── Grade Threshold Tests ────────────────────────────────────


class TestGradeThresholds:
    """Verify grade boundaries map correctly."""

    def test_s_grade(self, scorer):
        """Perfect play: all metrics at 1.0, success => S grade."""
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=[
                make_projectile_fired_event(),
                make_projectile_hit_event(hit=True),
            ],
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=200.0,
            par_time=300.0,
            objectives_status=make_objectives(2, 2),
        )
        assert score.grade == "S"
        assert score.total_score >= 900

    def test_failure_halves_score(self, scorer):
        """Same metrics but failure result => score halved."""
        score = scorer.score_mission(
            mission_result="failure",
            combat_log_events=[
                make_projectile_fired_event(),
                make_projectile_hit_event(hit=True),
            ],
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=200.0,
            par_time=300.0,
            objectives_status=make_objectives(2, 2),
        )
        # No style bonuses on failure, base halved
        assert score.total_score < 600

    def test_f_grade_on_total_failure(self, scorer):
        """Zero metrics + failure => F grade."""
        score = scorer.score_mission(
            mission_result="failure",
            combat_log_events=[],
            ship_state_start=make_ship_state(hull=100),
            ship_state_end=make_ship_state(hull=0),
            sim_time_elapsed=600.0,
            par_time=300.0,
            objectives_status=make_objectives(0, 2),
        )
        assert score.grade == "F"
        assert score.total_score < 300


class TestCoreMetrics:
    """Verify individual metric calculations."""

    def test_efficiency_under_par(self, scorer):
        """Completing faster than par => efficiency > 1.0 (capped at 1.5)."""
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=[],
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=100.0,
            par_time=300.0,
            objectives_status=make_objectives(),
        )
        # 300/100 = 3.0, capped at 1.5
        assert score.efficiency == 1.5

    def test_efficiency_over_par(self, scorer):
        """Completing slower than par => efficiency < 1.0."""
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=[],
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=600.0,
            par_time=300.0,
            objectives_status=make_objectives(),
        )
        assert score.efficiency == pytest.approx(0.5, abs=0.01)

    def test_accuracy_100_percent(self, scorer):
        """All shots hit => accuracy 1.0."""
        events = [
            make_projectile_fired_event(),
            make_projectile_hit_event(hit=True),
            make_torpedo_launch_event(),
            make_torpedo_hit_event(),
        ]
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=events,
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(),
        )
        assert score.accuracy == pytest.approx(1.0, abs=0.01)

    def test_accuracy_50_percent(self, scorer):
        """Half shots hit => accuracy 0.5."""
        events = [
            make_projectile_fired_event(sim_time=10),
            make_projectile_hit_event(hit=True, sim_time=12),
            make_projectile_fired_event(sim_time=20),
            make_projectile_hit_event(hit=False, sim_time=22),
        ]
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=events,
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(),
        )
        assert score.accuracy == pytest.approx(0.5, abs=0.01)

    def test_accuracy_no_weapons_fired(self, scorer):
        """No weapons fired (tutorial) => accuracy defaults to 1.0."""
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=[],
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(),
        )
        assert score.accuracy == 1.0

    def test_preservation_no_damage(self, scorer):
        """No damage taken => preservation 1.0."""
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=[],
            ship_state_start=make_ship_state(hull=100),
            ship_state_end=make_ship_state(hull=100),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(),
        )
        assert score.preservation == 1.0

    def test_preservation_half_hull(self, scorer):
        """Lost 50% hull => preservation 0.5."""
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=[],
            ship_state_start=make_ship_state(hull=100),
            ship_state_end=make_ship_state(hull=50),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(),
        )
        assert score.preservation == pytest.approx(0.5, abs=0.01)

    def test_objectives_partial(self, scorer):
        """2 of 3 objectives completed => objectives ~0.67."""
        score = scorer.score_mission(
            mission_result="failure",
            combat_log_events=[],
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(2, 3),
        )
        assert score.objectives == pytest.approx(2 / 3, abs=0.01)


class TestStyleBonuses:
    """Verify style bonus detection."""

    def test_untouchable(self, scorer):
        """Zero damage taken => untouchable bonus."""
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=[
                make_projectile_fired_event(),
                make_projectile_hit_event(hit=True),
            ],
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(),
        )
        assert score.untouchable is True

    def test_not_untouchable_with_damage(self, scorer):
        """Damage taken => no untouchable bonus."""
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=[make_ship_damage_event(damage=10.0)],
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(hull=90),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(),
        )
        assert score.untouchable is False

    def test_knife_edge(self, scorer):
        """< 25% fuel remaining => knife edge bonus."""
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=[],
            ship_state_start=make_ship_state(fuel=10000, max_fuel=10000),
            ship_state_end=make_ship_state(fuel=2000, max_fuel=10000),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(),
        )
        assert score.knife_edge is True

    def test_not_knife_edge_with_fuel(self, scorer):
        """Plenty of fuel => no knife edge."""
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=[],
            ship_state_start=make_ship_state(fuel=10000, max_fuel=10000),
            ship_state_end=make_ship_state(fuel=8000, max_fuel=10000),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(),
        )
        assert score.knife_edge is False

    def test_ammo_miser(self, scorer):
        """Used < 25% ammo => ammo miser bonus."""
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=[],
            ship_state_start=make_ship_state(total_ammo=20),
            ship_state_end=make_ship_state(total_ammo=18),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(),
        )
        assert score.ammo_miser is True

    def test_no_bonuses_on_failure(self, scorer):
        """Style bonuses don't contribute points on failure."""
        score = scorer.score_mission(
            mission_result="failure",
            combat_log_events=[],
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(0, 2),
        )
        # Even if untouchable is True (no damage), failure should not
        # get style bonus points
        assert score.mission_result == "failure"


class TestTipGeneration:
    """Verify combat log analysis produces actionable tips."""

    def test_low_confidence_firing_tip(self, scorer):
        """Firing at < 50% confidence generates a tip."""
        events = [
            make_projectile_fired_event(confidence=0.3, sim_time=10),
            make_projectile_hit_event(hit=False, sim_time=12),
            make_projectile_fired_event(confidence=0.2, sim_time=20),
            make_projectile_hit_event(hit=False, sim_time=22),
        ]
        score = scorer.score_mission(
            mission_result="failure",
            combat_log_events=events,
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(0, 1),
        )
        tips = score.improvement_tips
        assert len(tips) > 0
        assert any("confidence" in t.lower() for t in tips)

    def test_torpedo_intercepted_tip(self, scorer):
        """Torpedoes intercepted by PDC generates a tip."""
        events = [
            make_torpedo_launch_event(sim_time=50),
            make_torpedo_intercepted_event(sim_time=65),
            make_torpedo_launch_event(sim_time=70),
            make_torpedo_intercepted_event(sim_time=85),
        ]
        score = scorer.score_mission(
            mission_result="failure",
            combat_log_events=events,
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(0, 1),
        )
        tips = score.improvement_tips
        assert any("intercept" in t.lower() or "evasive" in t.lower() for t in tips)

    def test_early_damage_tip(self, scorer):
        """Damage in first 25% of mission generates a tip."""
        events = [
            make_ship_damage_event(damage=30.0, sim_time=20.0),
            make_ship_damage_event(damage=20.0, sim_time=40.0),
        ]
        score = scorer.score_mission(
            mission_result="failure",
            combat_log_events=events,
            ship_state_start=make_ship_state(hull=100),
            ship_state_end=make_ship_state(hull=50),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(0, 1),
        )
        tips = score.improvement_tips
        assert any("first 25%" in t or "evasive" in t.lower() for t in tips)

    def test_max_three_tips(self, scorer):
        """Never more than 3 tips regardless of how many patterns match."""
        events = [
            make_projectile_fired_event(confidence=0.2, sim_time=10),
            make_projectile_hit_event(hit=False, sim_time=12),
            make_projectile_fired_event(confidence=0.1, sim_time=20),
            make_projectile_hit_event(hit=False, sim_time=22),
            make_torpedo_launch_event(sim_time=30),
            make_torpedo_intercepted_event(sim_time=45),
            make_torpedo_launch_event(sim_time=50),
            make_torpedo_intercepted_event(sim_time=65),
            make_ship_damage_event(damage=40.0, sim_time=15.0),
        ]
        score = scorer.score_mission(
            mission_result="failure",
            combat_log_events=events,
            ship_state_start=make_ship_state(hull=100),
            ship_state_end=make_ship_state(hull=30),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(0, 1),
        )
        assert len(score.improvement_tips) <= 3

    def test_no_weapons_fired_tip(self, scorer):
        """No weapons fired on failure => tip about targeting."""
        score = scorer.score_mission(
            mission_result="failure",
            combat_log_events=[],
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(0, 1),
        )
        tips = score.improvement_tips
        assert any("lock" in t.lower() or "target" in t.lower() for t in tips)


class TestSerialization:
    """Verify score serializes correctly for transport."""

    def test_to_dict_keys(self, scorer):
        """to_dict() includes all expected keys."""
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=[],
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(),
        )
        d = score.to_dict()
        expected_keys = {
            "efficiency", "accuracy", "preservation", "crew_safety",
            "objectives", "surgical", "untouchable", "knife_edge",
            "ammo_miser", "total_score", "grade", "improvement_tips",
            "shots_fired", "shots_hit", "damage_taken", "damage_dealt",
            "torpedoes_launched", "torpedoes_hit",
            "missiles_launched", "missiles_hit",
            "mission_result", "timeline",
        }
        assert expected_keys.issubset(set(d.keys()))

    def test_to_dict_types(self, scorer):
        """Serialized values have correct types."""
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=[],
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(),
        )
        d = score.to_dict()
        assert isinstance(d["total_score"], int)
        assert isinstance(d["grade"], str)
        assert isinstance(d["improvement_tips"], list)
        assert isinstance(d["timeline"], list)
        assert isinstance(d["surgical"], bool)


class TestTimeline:
    """Verify timeline extraction from combat log."""

    def test_timeline_captures_key_events(self, scorer):
        """Timeline includes hits, misses, damage."""
        events = [
            make_projectile_fired_event(sim_time=10),
            make_projectile_hit_event(hit=True, sim_time=12),
            make_ship_damage_event(damage=15, sim_time=30),
        ]
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=events,
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(),
        )
        # projectile_fired is NOT a key type, but projectile_hit and
        # ship_damage are
        types = [e["type"] for e in score.timeline]
        assert "projectile_hit" in types
        assert "ship_damage" in types

    def test_timeline_max_20(self, scorer):
        """Timeline capped at 20 entries."""
        events = []
        for i in range(30):
            events.append(make_projectile_fired_event(sim_time=i * 10))
            events.append(make_projectile_hit_event(hit=True, sim_time=i * 10 + 2))
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=events,
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(),
        )
        assert len(score.timeline) <= 20


class TestMissileScoring:
    """Verify missile events are correctly counted."""

    def test_missile_accuracy(self, scorer):
        """Missile hits and launches tracked separately."""
        events = [
            make_missile_launch_event(sim_time=10),
            make_missile_hit_event(hull_damage=25, sim_time=20),
            make_missile_launch_event(sim_time=30),
            make_missile_hit_event(hull_damage=0, sim_time=40),  # miss
        ]
        score = scorer.score_mission(
            mission_result="success",
            combat_log_events=events,
            ship_state_start=make_ship_state(),
            ship_state_end=make_ship_state(),
            sim_time_elapsed=300.0,
            par_time=300.0,
            objectives_status=make_objectives(),
        )
        assert score.missiles_launched == 2
        assert score.missiles_hit == 1
        assert score.damage_dealt >= 25.0
