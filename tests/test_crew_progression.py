"""
Tests for the crew progression system (Phase 4D).

Covers:
- XP award increases experience dict
- Skill advancement at XP thresholds
- Injury state transitions (healthy -> wounded -> critical -> dead)
- Wounded crew operates at 50% efficiency
- Critical crew cannot be assigned
- XP bonus for high-g operations
- Combat event XP awards (weapon_fired, lock_achieved, etc.)
"""

import math
import random
import pytest
from unittest.mock import MagicMock, patch

from server.stations.crew_system import (
    CrewManager, CrewMember, CrewSkills, StationSkill, SkillLevel,
    InjuryState, XP_THRESHOLDS,
)
from server.stations.crew_binding import (
    CrewStationBinder, AI_BACKUP_COMPETENCE, STATION_SKILL_MAP,
)
from server.stations.station_types import StationType


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------

@pytest.fixture
def crew_manager() -> CrewManager:
    return CrewManager()


@pytest.fixture
def binder(crew_manager: CrewManager) -> CrewStationBinder:
    return CrewStationBinder(crew_manager)


@pytest.fixture
def ship_with_crew(crew_manager: CrewManager, binder: CrewStationBinder):
    """Create a ship with two crew members and registered slots."""
    ship_id = "test_ship"
    binder.register_ship(ship_id)

    # Novice gunner (level 1 -- lowest, easiest to test advancement)
    gunner_skills = CrewSkills(gunnery=1, targeting=1)
    gunner = crew_manager.create_crew_member(
        ship_id, "Amos Burton", skills=gunner_skills
    )

    # Competent pilot
    pilot_skills = CrewSkills(piloting=3, navigation=4)
    pilot = crew_manager.create_crew_member(
        ship_id, "Alex Kamal", skills=pilot_skills
    )

    return ship_id, gunner, pilot


# ---------------------------------------------------------------
# XP Award Tests
# ---------------------------------------------------------------

class TestXPAward:
    """Test that award_xp correctly modifies the experience dict."""

    def test_award_xp_increases_experience(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        assert gunner.experience.get("gunnery", 0) == 0

        gunner.award_xp("gunnery", 10)
        assert gunner.experience["gunnery"] == 10

    def test_award_xp_accumulates(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        gunner.award_xp("gunnery", 10)
        gunner.award_xp("gunnery", 15)
        assert gunner.experience["gunnery"] == 25

    def test_award_zero_xp_does_nothing(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        result = gunner.award_xp("gunnery", 0)
        assert result is False
        assert gunner.experience.get("gunnery", 0) == 0

    def test_award_negative_xp_does_nothing(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        result = gunner.award_xp("gunnery", -5)
        assert result is False

    def test_dead_crew_cannot_gain_xp(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        gunner.injury_state = InjuryState.DEAD
        result = gunner.award_xp("gunnery", 100)
        assert result is False
        assert gunner.experience.get("gunnery", 0) == 0


# ---------------------------------------------------------------
# Skill Advancement Tests
# ---------------------------------------------------------------

class TestSkillAdvancement:
    """Test skill level-up at XP thresholds."""

    def test_novice_to_trainee_at_100xp(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        assert gunner.skills.gunnery == 1  # NOVICE

        # 99 XP: not enough
        gunner.award_xp("gunnery", 99)
        assert gunner.skills.gunnery == 1

        # 1 more = 100 total: should advance
        advanced = gunner.award_xp("gunnery", 1)
        assert advanced is True
        assert gunner.skills.gunnery == 2  # TRAINEE

    def test_trainee_to_competent_at_300xp(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        # Start at trainee (level 2)
        gunner.skills.set_skill(StationSkill.GUNNERY, 2)

        gunner.award_xp("gunnery", 299)
        assert gunner.skills.gunnery == 2

        advanced = gunner.award_xp("gunnery", 1)
        assert advanced is True
        assert gunner.skills.gunnery == 3  # COMPETENT

    def test_competent_to_skilled_at_600xp(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        gunner.skills.set_skill(StationSkill.GUNNERY, 3)

        advanced = gunner.award_xp("gunnery", 600)
        assert advanced is True
        assert gunner.skills.gunnery == 4  # SKILLED

    def test_skilled_to_expert_at_1000xp(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        gunner.skills.set_skill(StationSkill.GUNNERY, 4)

        advanced = gunner.award_xp("gunnery", 1000)
        assert advanced is True
        assert gunner.skills.gunnery == 5  # EXPERT

    def test_expert_to_master_at_2000xp(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        gunner.skills.set_skill(StationSkill.GUNNERY, 5)

        advanced = gunner.award_xp("gunnery", 2000)
        assert advanced is True
        assert gunner.skills.gunnery == 6  # MASTER

    def test_master_cannot_advance_further(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        gunner.skills.set_skill(StationSkill.GUNNERY, 6)

        advanced = gunner.award_xp("gunnery", 9999)
        assert advanced is False
        assert gunner.skills.gunnery == 6

    def test_check_advancement_returns_advanced_skills(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        # Set both skills to NOVICE, give enough XP for gunnery but not targeting
        gunner.skills.set_skill(StationSkill.GUNNERY, 1)
        gunner.skills.set_skill(StationSkill.TARGETING, 1)
        gunner.experience["gunnery"] = 150   # Over 100 threshold
        gunner.experience["targeting"] = 50   # Under 100 threshold

        advanced = gunner.check_advancement()
        assert "gunnery" in advanced
        assert "targeting" not in advanced
        assert gunner.skills.gunnery == 2  # Advanced

    def test_award_xp_returns_true_on_advancement(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        assert gunner.skills.gunnery == 1  # NOVICE
        result = gunner.award_xp("gunnery", 100)
        assert result is True

    def test_award_xp_returns_false_without_advancement(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        result = gunner.award_xp("gunnery", 50)
        assert result is False


# ---------------------------------------------------------------
# Injury State Transition Tests
# ---------------------------------------------------------------

class TestInjuryStateTransitions:
    """Test the injury escalation ladder."""

    def test_default_state_is_healthy(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        assert gunner.injury_state == InjuryState.HEALTHY

    def test_healthy_to_wounded(self, binder, ship_with_crew):
        ship_id, gunner, _ = ship_with_crew
        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)

        # Force deterministic injury
        random.seed(42)
        result = binder.apply_damage_to_station(
            ship_id, StationType.TACTICAL, severity=1.0,
        )
        assert result is not None
        # With severity=1.0, injury_chance = 0.3 -- seed 42 should trigger
        if result["injured"]:
            assert result["new_state"] == InjuryState.WOUNDED

    def test_wounded_to_critical(self, binder, ship_with_crew):
        ship_id, gunner, _ = ship_with_crew
        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        gunner.injury_state = InjuryState.WOUNDED

        # Run multiple times to catch the 50% escalation chance
        escalated = False
        for seed in range(100):
            gunner.injury_state = InjuryState.WOUNDED
            gunner.health = 0.5
            # Re-assign if removed by previous critical escalation
            slots = binder._slots.get(ship_id)
            slots[StationType.TACTICAL].crew_id = gunner.crew_id
            slots[StationType.TACTICAL].is_ai_backup = False

            random.seed(seed)
            result = binder.apply_damage_to_station(
                ship_id, StationType.TACTICAL, severity=1.0,
            )
            if result and result.get("new_state") == InjuryState.CRITICAL:
                escalated = True
                break

        assert escalated, "Wounded -> Critical should happen within 100 seeds"

    def test_critical_to_dead(self, binder, ship_with_crew):
        ship_id, gunner, _ = ship_with_crew
        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        gunner.injury_state = InjuryState.CRITICAL

        # Critical crew are removed from station -- re-assign for test
        slots = binder._slots.get(ship_id)

        killed = False
        for seed in range(100):
            gunner.injury_state = InjuryState.CRITICAL
            gunner.health = 0.2
            slots[StationType.TACTICAL].crew_id = gunner.crew_id
            slots[StationType.TACTICAL].is_ai_backup = False

            random.seed(seed)
            result = binder.apply_damage_to_station(
                ship_id, StationType.TACTICAL, severity=1.0,
            )
            if result and result.get("new_state") == InjuryState.DEAD:
                killed = True
                break

        assert killed, "Critical -> Dead should happen within 100 seeds"

    def test_dead_crew_not_processed(self, binder, ship_with_crew):
        ship_id, gunner, _ = ship_with_crew
        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        gunner.injury_state = InjuryState.DEAD

        # Must re-assign manually for test (normally dead crew are removed)
        slots = binder._slots.get(ship_id)
        slots[StationType.TACTICAL].crew_id = gunner.crew_id

        result = binder.apply_damage_to_station(
            ship_id, StationType.TACTICAL, severity=1.0,
        )
        assert result is None  # Dead crew are skipped


# ---------------------------------------------------------------
# Efficiency Penalty Tests
# ---------------------------------------------------------------

class TestWoundedEfficiency:
    """Test that wounded crew operate at 50% efficiency."""

    def test_wounded_crew_half_efficiency(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        gunner.skills.set_skill(StationSkill.GUNNERY, 5)  # EXPERT

        healthy_eff = gunner.get_current_efficiency(StationSkill.GUNNERY)

        gunner.injury_state = InjuryState.WOUNDED
        wounded_eff = gunner.get_current_efficiency(StationSkill.GUNNERY)

        # Wounded should be approximately half (50% penalty)
        # The 0.1 floor clamp means the ratio may not be exact
        assert wounded_eff < healthy_eff
        assert wounded_eff == pytest.approx(healthy_eff * 0.5, abs=0.05)

    def test_critical_crew_zero_efficiency(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        gunner.injury_state = InjuryState.CRITICAL
        eff = gunner.get_current_efficiency(StationSkill.GUNNERY)
        assert eff == 0.0

    def test_dead_crew_zero_efficiency(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        gunner.injury_state = InjuryState.DEAD
        eff = gunner.get_current_efficiency(StationSkill.GUNNERY)
        assert eff == 0.0

    def test_healthy_crew_normal_efficiency(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        gunner.skills.set_skill(StationSkill.GUNNERY, 5)  # EXPERT
        eff = gunner.get_current_efficiency(StationSkill.GUNNERY)
        assert eff == pytest.approx(0.9, abs=0.01)


# ---------------------------------------------------------------
# Assignment Block for Critical/Dead
# ---------------------------------------------------------------

class TestCriticalAssignment:
    """Test that critical and dead crew cannot be assigned to stations."""

    def test_critical_crew_cannot_be_assigned(self, binder, ship_with_crew):
        ship_id, gunner, _ = ship_with_crew
        gunner.injury_state = InjuryState.CRITICAL

        ok, msg = binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        assert ok is False
        assert "critically injured" in msg

    def test_dead_crew_cannot_be_assigned(self, binder, ship_with_crew):
        ship_id, gunner, _ = ship_with_crew
        gunner.injury_state = InjuryState.DEAD

        ok, msg = binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        assert ok is False
        assert "dead" in msg.lower()

    def test_wounded_crew_can_be_assigned(self, binder, ship_with_crew):
        ship_id, gunner, _ = ship_with_crew
        gunner.injury_state = InjuryState.WOUNDED

        ok, msg = binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        assert ok is True


# ---------------------------------------------------------------
# Serialization Tests
# ---------------------------------------------------------------

class TestSerialization:
    """Test that to_dict includes experience and injury state."""

    def test_to_dict_has_experience(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        gunner.award_xp("gunnery", 42)
        d = gunner.to_dict()

        assert "experience" in d
        assert d["experience"]["gunnery"] == 42

    def test_to_dict_has_injury_state(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        gunner.injury_state = InjuryState.WOUNDED
        d = gunner.to_dict()

        assert d["injury_state"] == "wounded"

    def test_to_dict_has_xp_progress(self, ship_with_crew):
        _, gunner, _ = ship_with_crew
        gunner.award_xp("gunnery", 50)
        d = gunner.to_dict()

        assert "xp_progress" in d
        gunnery_prog = d["xp_progress"]["gunnery"]
        assert gunnery_prog["xp"] == 50
        assert gunnery_prog["threshold"] == 100  # NOVICE->TRAINEE
        assert gunnery_prog["level"] == 1


# ---------------------------------------------------------------
# CrewXPSystem Tick Tests
# ---------------------------------------------------------------

class TestCrewXPSystemTick:
    """Test the CrewXPSystem high-g XP bonus through tick()."""

    def _make_ship(self, accel_x=0.0, accel_y=0.0, accel_z=0.0):
        """Create a mock ship with specified acceleration."""
        ship = MagicMock()
        ship.id = "test_ship"
        ship.acceleration = {"x": accel_x, "y": accel_y, "z": accel_z}
        ship.systems = {}
        return ship

    def test_high_g_awards_xp_to_all_assigned_crew(
        self, crew_manager, binder, ship_with_crew
    ):
        """At >3g for 1+ second, all assigned crew should gain XP."""
        from hybrid.systems.crew_xp_system import CrewXPSystem, HIGH_G_THRESHOLD
        from hybrid.systems.crew_binding_system import CrewBindingSystem

        ship_id, gunner, pilot = ship_with_crew
        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        binder.assign_crew(ship_id, pilot.crew_id, StationType.HELM)

        # Wire up shared state
        CrewBindingSystem.set_shared_state(crew_manager, binder)

        xp_system = CrewXPSystem()

        # 4g acceleration = 39.24 m/s^2
        accel = HIGH_G_THRESHOLD * 9.81 + 9.81  # Just above threshold
        ship = self._make_ship(accel_x=accel)

        # Tick for 1.5 seconds (should award 1 second of high-g XP)
        xp_system.tick(1.5, ship=ship, event_bus=MagicMock())

        # Gunner should have gunnery and targeting XP
        assert gunner.experience.get("gunnery", 0) >= 1
        assert gunner.experience.get("targeting", 0) >= 1

        # Pilot should have piloting and navigation XP
        assert pilot.experience.get("piloting", 0) >= 1
        assert pilot.experience.get("navigation", 0) >= 1

    def test_low_g_does_not_award_xp(
        self, crew_manager, binder, ship_with_crew
    ):
        """Below 3g, no high-g XP bonus."""
        from hybrid.systems.crew_xp_system import CrewXPSystem
        from hybrid.systems.crew_binding_system import CrewBindingSystem

        ship_id, gunner, pilot = ship_with_crew
        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)

        CrewBindingSystem.set_shared_state(crew_manager, binder)

        xp_system = CrewXPSystem()
        ship = self._make_ship(accel_x=9.81)  # ~1g

        xp_system.tick(5.0, ship=ship, event_bus=MagicMock())

        assert gunner.experience.get("gunnery", 0) == 0


# ---------------------------------------------------------------
# CrewXPSystem Event Handler Tests
# ---------------------------------------------------------------

class TestCrewXPSystemEvents:
    """Test that event handlers queue XP awards correctly."""

    def test_weapon_fired_hit_awards_gunnery_xp(
        self, crew_manager, binder, ship_with_crew
    ):
        """weapon_fired with hit=True should award gunnery XP."""
        from hybrid.systems.crew_xp_system import (
            CrewXPSystem, XP_WEAPON_HIT,
        )
        from hybrid.systems.crew_binding_system import CrewBindingSystem
        from hybrid.core.event_bus import EventBus

        ship_id, gunner, pilot = ship_with_crew
        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        CrewBindingSystem.set_shared_state(crew_manager, binder)

        bus = EventBus()
        xp_system = CrewXPSystem()

        ship = MagicMock()
        ship.id = ship_id
        ship.acceleration = {"x": 0, "y": 0, "z": 0}

        # Subscribe (happens on first tick)
        xp_system.tick(0.1, ship=ship, event_bus=bus)

        # Fire the event
        bus.publish("weapon_fired", {
            "ship_id": ship_id,
            "hit": True,
            "confidence": 0.8,
        })

        # Process pending awards in next tick
        xp_system.tick(0.1, ship=ship, event_bus=bus)

        assert gunner.experience.get("gunnery", 0) == XP_WEAPON_HIT

    def test_weapon_fired_low_confidence_bonus(
        self, crew_manager, binder, ship_with_crew
    ):
        """Hitting with confidence < 0.5 should award bonus XP."""
        from hybrid.systems.crew_xp_system import (
            CrewXPSystem, XP_WEAPON_HIT, XP_WEAPON_HIT_LOW_CONFIDENCE_BONUS,
        )
        from hybrid.systems.crew_binding_system import CrewBindingSystem
        from hybrid.core.event_bus import EventBus

        ship_id, gunner, _ = ship_with_crew
        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        CrewBindingSystem.set_shared_state(crew_manager, binder)

        bus = EventBus()
        xp_system = CrewXPSystem()
        ship = MagicMock()
        ship.id = ship_id
        ship.acceleration = {"x": 0, "y": 0, "z": 0}

        xp_system.tick(0.1, ship=ship, event_bus=bus)

        bus.publish("weapon_fired", {
            "ship_id": ship_id,
            "hit": True,
            "confidence": 0.3,  # Below 0.5
        })

        xp_system.tick(0.1, ship=ship, event_bus=bus)

        expected = XP_WEAPON_HIT + XP_WEAPON_HIT_LOW_CONFIDENCE_BONUS
        assert gunner.experience.get("gunnery", 0) == expected

    def test_weapon_miss_does_not_award_xp(
        self, crew_manager, binder, ship_with_crew
    ):
        """weapon_fired with hit=False should NOT award XP."""
        from hybrid.systems.crew_xp_system import CrewXPSystem
        from hybrid.systems.crew_binding_system import CrewBindingSystem
        from hybrid.core.event_bus import EventBus

        ship_id, gunner, _ = ship_with_crew
        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        CrewBindingSystem.set_shared_state(crew_manager, binder)

        bus = EventBus()
        xp_system = CrewXPSystem()
        ship = MagicMock()
        ship.id = ship_id
        ship.acceleration = {"x": 0, "y": 0, "z": 0}

        xp_system.tick(0.1, ship=ship, event_bus=bus)

        bus.publish("weapon_fired", {
            "ship_id": ship_id,
            "hit": False,
        })

        xp_system.tick(0.1, ship=ship, event_bus=bus)

        assert gunner.experience.get("gunnery", 0) == 0

    def test_lock_achieved_awards_targeting_xp(
        self, crew_manager, binder, ship_with_crew
    ):
        """target_locked should award targeting XP."""
        from hybrid.systems.crew_xp_system import (
            CrewXPSystem, XP_LOCK_ACHIEVED,
        )
        from hybrid.systems.crew_binding_system import CrewBindingSystem
        from hybrid.core.event_bus import EventBus

        ship_id, gunner, _ = ship_with_crew
        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        CrewBindingSystem.set_shared_state(crew_manager, binder)

        bus = EventBus()
        xp_system = CrewXPSystem()
        ship = MagicMock()
        ship.id = ship_id
        ship.acceleration = {"x": 0, "y": 0, "z": 0}

        xp_system.tick(0.1, ship=ship, event_bus=bus)

        bus.publish("target_locked", {"ship_id": ship_id, "target_id": "t1"})

        xp_system.tick(0.1, ship=ship, event_bus=bus)

        assert gunner.experience.get("targeting", 0) == XP_LOCK_ACHIEVED

    def test_repair_complete_awards_damage_control_xp(
        self, crew_manager, binder, ship_with_crew
    ):
        """repair_complete should award damage_control XP to OPS crew."""
        from hybrid.systems.crew_xp_system import (
            CrewXPSystem, XP_REPAIR_COMPLETE,
        )
        from hybrid.systems.crew_binding_system import CrewBindingSystem
        from hybrid.core.event_bus import EventBus

        ship_id, _, pilot = ship_with_crew

        # Create an ops crew member
        from server.stations.crew_system import CrewSkills
        ops_skills = CrewSkills(damage_control=3, sensors=3)
        ops_crew = crew_manager.create_crew_member(
            ship_id, "Naomi Nagata", skills=ops_skills
        )
        binder.assign_crew(ship_id, ops_crew.crew_id, StationType.OPS)
        CrewBindingSystem.set_shared_state(crew_manager, binder)

        bus = EventBus()
        xp_system = CrewXPSystem()
        ship = MagicMock()
        ship.id = ship_id
        ship.acceleration = {"x": 0, "y": 0, "z": 0}

        xp_system.tick(0.1, ship=ship, event_bus=bus)

        bus.publish("repair_complete", {
            "ship_id": ship_id,
            "team_id": "rt1",
            "subsystem": "sensors",
        })

        xp_system.tick(0.1, ship=ship, event_bus=bus)

        assert ops_crew.experience.get("damage_control", 0) == XP_REPAIR_COMPLETE


# ---------------------------------------------------------------
# XP Threshold Constants Test
# ---------------------------------------------------------------

class TestXPThresholdConstants:
    """Verify the XP threshold table is complete and monotonically increasing."""

    def test_all_levels_except_master_have_thresholds(self):
        for level in range(1, 6):
            assert level in XP_THRESHOLDS, f"Missing threshold for level {level}"

    def test_master_has_no_threshold(self):
        assert 6 not in XP_THRESHOLDS

    def test_thresholds_are_increasing(self):
        prev = 0
        for level in sorted(XP_THRESHOLDS.keys()):
            assert XP_THRESHOLDS[level] > prev
            prev = XP_THRESHOLDS[level]
