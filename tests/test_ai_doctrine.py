"""Tests for AI doctrine system (Phase 3).

Validates:
  1. Salvo coordination: multi-ship fire timing
  2. Evasion jinking: heading changes keyed to railgun ToF
  3. Retreat conditions: subsystem-aware disengagement
  4. Smart target prioritization: spread fire
  5. Integration with AIController
"""

import pytest

from hybrid.fleet.ai_doctrine import (
    SalvoCoordinator,
    SalvoCoordination,
    EvasionState,
    RetreatAssessment,
    calculate_jink_interval,
    calculate_jink_angle,
    should_jink,
    assess_retreat,
    _get_ammo_fraction,
    RAILGUN_VELOCITY,
)
from hybrid.fleet.threat_assessment import AIThreatAssessment


# Minimal system configs for test ships
AI_SHIP_SYSTEMS = {
    "sensors": {"passive": {"range": 200000}},
    "targeting": {},
    "combat": {"railguns": 1, "pdcs": 1},
    "navigation": {},
    "propulsion": {"max_thrust": 50000, "fuel_level": 10000},
}


# ── Salvo Coordinator ─────────────────────────────────────────────

class TestSalvoCoordinator:
    """Tests for coordinated salvo timing."""

    def test_plan_salvo_requires_two_ships(self):
        """Salvo planning returns None for fewer than 2 ships."""
        coord = SalvoCoordinator()
        result = coord.plan_salvo("target1", [("ship1", 50_000)], sim_time=0.0)
        assert result is None

    def test_plan_salvo_two_ships(self):
        """Two ships produce a valid salvo plan with correct timing."""
        coord = SalvoCoordinator()
        # Ship A at 100km (5s ToF), Ship B at 50km (2.5s ToF)
        result = coord.plan_salvo(
            "target1",
            [("shipA", 100_000), ("shipB", 50_000)],
            sim_time=10.0,
        )
        assert result is not None
        assert len(result.slots) == 2

        # Ship A has longest ToF, should fire first (at sim_time=10)
        slot_a = next(s for s in result.slots if s.ship_id == "shipA")
        slot_b = next(s for s in result.slots if s.ship_id == "shipB")

        assert slot_a.scheduled_fire_time == pytest.approx(10.0, abs=0.1)
        # Ship B should delay by (5.0 - 2.5) = 2.5 seconds
        assert slot_b.scheduled_fire_time == pytest.approx(12.5, abs=0.1)

    def test_should_fire_now_no_plan(self):
        """Without a salvo plan, ships fire freely."""
        coord = SalvoCoordinator()
        assert coord.should_fire_now("ship1", "target1", 10.0) is True

    def test_should_fire_now_before_scheduled(self):
        """Ship should NOT fire before its scheduled time."""
        coord = SalvoCoordinator()
        coord.plan_salvo(
            "target1",
            [("shipA", 100_000), ("shipB", 50_000)],
            sim_time=10.0,
        )
        # Ship B is scheduled at ~12.5s, should not fire at 11.0
        assert coord.should_fire_now("shipB", "target1", 11.0) is False

    def test_should_fire_now_at_scheduled(self):
        """Ship fires when scheduled time arrives."""
        coord = SalvoCoordinator()
        coord.plan_salvo(
            "target1",
            [("shipA", 100_000), ("shipB", 50_000)],
            sim_time=10.0,
        )
        # Ship A fires immediately (longest ToF)
        assert coord.should_fire_now("shipA", "target1", 10.0) is True
        # Ship B fires after delay
        assert coord.should_fire_now("shipB", "target1", 13.0) is True

    def test_expired_plan_allows_fire(self):
        """Expired salvo plans are discarded, allowing free fire."""
        coord = SalvoCoordinator()
        coord.plan_salvo(
            "target1",
            [("shipA", 100_000), ("shipB", 50_000)],
            sim_time=0.0,
        )
        # 15 seconds later, plan should have expired (expiry=10s)
        assert coord.should_fire_now("shipB", "target1", 15.0) is True

    def test_clear_target(self):
        """clear_target removes the salvo plan."""
        coord = SalvoCoordinator()
        coord.plan_salvo(
            "target1",
            [("shipA", 100_000), ("shipB", 50_000)],
            sim_time=0.0,
        )
        coord.clear_target("target1")
        assert coord.should_fire_now("shipB", "target1", 0.0) is True

    def test_cleanup_removes_expired(self):
        """cleanup() removes all expired plans."""
        coord = SalvoCoordinator()
        coord.plan_salvo("t1", [("a", 50_000), ("b", 50_000)], sim_time=0.0)
        coord.plan_salvo("t2", [("c", 50_000), ("d", 50_000)], sim_time=5.0)
        coord.cleanup(sim_time=12.0)
        # t1 created at 0, expired at 10 -- should be gone
        assert "t1" not in coord._active
        # t2 created at 5, expires at 15 -- still active
        assert "t2" in coord._active


# ── Evasion Doctrine ───────────────────────────────────────────────

class TestEvasionDoctrine:
    """Tests for evasion jinking logic."""

    def test_jink_interval_at_100km(self):
        """At 100km range, jink interval = 5 seconds (100km / 20km/s)."""
        interval = calculate_jink_interval(100_000)
        assert interval == pytest.approx(5.0, abs=0.1)

    def test_jink_interval_floor(self):
        """Jink interval never goes below 1 second."""
        interval = calculate_jink_interval(100)  # 100m, ToF = 0.005s
        assert interval == 1.0

    def test_jink_interval_ceiling(self):
        """Jink interval capped at 15 seconds."""
        interval = calculate_jink_interval(500_000)  # 500km, ToF = 25s
        assert interval == 15.0

    def test_jink_angle_range(self):
        """Jink angle falls within 10-30 degree range."""
        for _ in range(50):
            angle = calculate_jink_angle(skill_level=0.5)
            assert 10.0 <= angle <= 30.0

    def test_jink_angle_skill_scaling(self):
        """Higher skill produces smaller (tighter) jink angles on average."""
        low_skill_angles = [calculate_jink_angle(skill_level=0.1) for _ in range(200)]
        high_skill_angles = [calculate_jink_angle(skill_level=0.9) for _ in range(200)]
        # Average of high-skill should be lower than low-skill
        assert sum(high_skill_angles) / len(high_skill_angles) < (
            sum(low_skill_angles) / len(low_skill_angles)
        )

    def test_should_jink_respects_interval(self):
        """should_jink returns None before the interval elapses."""
        state = EvasionState(last_jink_time=10.0)
        # At 100km range, interval is 5s. At sim_time=13, only 3s elapsed.
        result = should_jink(state, range_to_attacker_m=100_000, sim_time=13.0)
        assert result is None

    def test_should_jink_fires_after_interval(self):
        """should_jink returns an angle after the interval elapses."""
        state = EvasionState(last_jink_time=10.0)
        # At 100km range, interval is 5s. At sim_time=16, 6s elapsed.
        result = should_jink(state, range_to_attacker_m=100_000, sim_time=16.0)
        assert result is not None
        assert abs(result) >= 10.0

    def test_jink_alternates_direction(self):
        """Successive jinks alternate between clockwise and counterclockwise."""
        state = EvasionState(last_jink_time=0.0, jink_clockwise=True)

        angles = []
        for i in range(4):
            result = should_jink(state, 20_000, sim_time=float(i * 5 + 2))
            if result is not None:
                angles.append(result)

        # Should have alternating signs
        if len(angles) >= 2:
            for i in range(1, len(angles)):
                assert (angles[i] > 0) != (angles[i - 1] > 0), (
                    f"Jinks did not alternate: {angles}"
                )

    def test_jink_updates_state(self):
        """should_jink updates last_jink_time and count."""
        state = EvasionState(last_jink_time=0.0)
        should_jink(state, 20_000, sim_time=5.0)
        assert state.last_jink_time == 5.0
        assert state.jink_count == 1


# ── Retreat Conditions ─────────────────────────────────────────────

class TestRetreatConditions:
    """Tests for subsystem-aware retreat assessment."""

    def test_healthy_ship_no_retreat(self):
        """Fully healthy ship has no retreat condition."""
        from hybrid.ship import Ship

        ship = Ship("warship", {
            "mass": 5000,
            "faction": "hostile",
            "max_hull_integrity": 100.0,
            "hull_integrity": 100.0,
            "systems": AI_SHIP_SYSTEMS,
        })

        result = assess_retreat(ship)
        assert result.should_retreat is False
        assert result.conservative_fire is False

    def test_weapons_destroyed_triggers_retreat(self):
        """Ship with destroyed weapons should retreat."""
        from hybrid.ship import Ship

        ship = Ship("warship", {
            "mass": 5000,
            "faction": "hostile",
            "systems": AI_SHIP_SYSTEMS,
        })

        # Destroy weapons subsystem
        if hasattr(ship, "damage_model") and "weapons" in ship.damage_model.subsystems:
            ship.damage_model.subsystems["weapons"].health = 0.0

        result = assess_retreat(ship)
        assert result.should_retreat is True
        assert "weapons_destroyed" in result.reason

    def test_propulsion_degraded_triggers_retreat(self):
        """Ship with badly degraded propulsion should retreat."""
        from hybrid.ship import Ship

        ship = Ship("warship", {
            "mass": 5000,
            "faction": "hostile",
            "systems": AI_SHIP_SYSTEMS,
        })

        if hasattr(ship, "damage_model") and "propulsion" in ship.damage_model.subsystems:
            # Set health to 30% of max
            sub = ship.damage_model.subsystems["propulsion"]
            sub.health = sub.max_health * 0.3

        result = assess_retreat(ship)
        assert result.should_retreat is True
        assert "propulsion" in result.reason

    def test_low_ammo_triggers_conservative_fire(self):
        """Low ammo activates conservative fire mode (not full retreat)."""
        from hybrid.ship import Ship

        ship = Ship("warship", {
            "mass": 5000,
            "faction": "hostile",
            "systems": AI_SHIP_SYSTEMS,
        })

        # Drain ammo to 10% on all weapons
        combat = ship.systems.get("combat")
        if combat:
            for weapon in combat.truth_weapons.values():
                if weapon.ammo is not None:
                    weapon.ammo = max(1, int(weapon.specs.ammo_capacity * 0.10))

        result = assess_retreat(ship)
        assert result.conservative_fire is True
        assert "low_ammo" in result.reason


# ── Smart Target Prioritization ────────────────────────────────────

class TestSmartTargetPrioritization:
    """Tests for tactical threat scoring."""

    def test_spread_fire_penalty(self):
        """Targets already engaged by friendlies score lower."""
        from hybrid.ship import Ship
        from hybrid.systems.sensors.contact import ContactData

        ship = Ship("own", {"mass": 5000, "position": {"x": 0, "y": 0, "z": 0}})

        contact = ContactData(
            id="C001",
            position={"x": 10_000, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            confidence=0.9,
            last_update=0.0,
            detection_method="ir",
            faction="hostile",
        )

        # Score without friendly engagement
        score_solo = AIThreatAssessment.assess_threat_tactical(
            "C001", contact, ship, friendly_targets=None,
        )

        # Score with 2 friendlies already targeting
        score_engaged = AIThreatAssessment.assess_threat_tactical(
            "C001", contact, ship, friendly_targets={"C001": 2},
        )

        assert score_engaged < score_solo
        # Each engaged friendly subtracts 2.0
        assert score_solo - score_engaged == pytest.approx(4.0)

    def test_tactical_prioritization_spreads_fire(self):
        """prioritize_targets_tactical ranks un-engaged targets higher."""
        from hybrid.ship import Ship
        from hybrid.systems.sensors.contact import ContactData

        ship = Ship("own", {"mass": 5000, "position": {"x": 0, "y": 0, "z": 0}})

        contacts = [
            ("C001", ContactData(
                id="C001",
                position={"x": 5_000, "y": 0, "z": 0},
                velocity={"x": 0, "y": 0, "z": 0},
                confidence=0.9, last_update=0.0,
                detection_method="ir", faction="hostile",
                classification="destroyer",
            )),
            ("C002", ContactData(
                id="C002",
                position={"x": 8_000, "y": 0, "z": 0},
                velocity={"x": 0, "y": 0, "z": 0},
                confidence=0.9, last_update=0.0,
                detection_method="ir", faction="hostile",
                classification="destroyer",
            )),
        ]

        # C001 is closer, but 3 friendlies already target it
        friendly_targets = {"C001": 3}

        ranked = AIThreatAssessment.prioritize_targets_tactical(
            contacts, ship, friendly_targets,
        )

        # C002 should rank higher because C001 has -6.0 penalty
        assert ranked[0][0] == "C002"


# ── AIController Doctrine Integration ──────────────────────────────

class TestControllerDoctrine:
    """Tests for doctrine integration in AIController."""

    def test_get_state_includes_doctrine(self):
        """get_state includes doctrine sub-dict."""
        from hybrid.ship import Ship

        ship = Ship("ai_ship", {
            "mass": 5000,
            "faction": "unsa",
            "ai_enabled": True,
            "systems": AI_SHIP_SYSTEMS,
        })

        state = ship.ai_controller.get_state()
        assert "doctrine" in state
        assert "conservative_fire" in state["doctrine"]
        assert "jink_count" in state["doctrine"]

    def test_set_salvo_coordinator(self):
        """Salvo coordinator can be attached to AIController."""
        from hybrid.ship import Ship

        ship = Ship("ai_ship", {
            "mass": 5000,
            "faction": "unsa",
            "ai_enabled": True,
            "systems": AI_SHIP_SYSTEMS,
        })

        coord = SalvoCoordinator()
        ship.ai_controller.set_salvo_coordinator(coord)
        assert ship.ai_controller._salvo_coordinator is coord

        state = ship.ai_controller.get_state()
        assert state["doctrine"]["salvo_coordinated"] is True

    def test_retreat_propulsion_triggers_hold(self):
        """AI disengages to HOLD when propulsion is badly damaged."""
        from hybrid.ship import Ship
        from hybrid.fleet.ai_controller import AIBehavior
        from hybrid.systems.sensors.contact import ContactData

        ship = Ship("warship", {
            "mass": 5000,
            "faction": "hostile",
            "ai_enabled": True,
            "max_hull_integrity": 100.0,
            "hull_integrity": 100.0,
            "systems": AI_SHIP_SYSTEMS,
        })

        # Inject a threat
        sensors = ship.systems.get("sensors")
        enemy = ContactData(
            id="enemy",
            position={"x": 10_000, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            confidence=0.9, last_update=0.0,
            detection_method="ir", faction="unsa",
        )
        sensors.contact_tracker.update_contact("enemy", enemy, 0.0)

        # Cripple propulsion
        if hasattr(ship, "damage_model") and "propulsion" in ship.damage_model.subsystems:
            sub = ship.damage_model.subsystems["propulsion"]
            sub.health = sub.max_health * 0.3

        ship.ai_controller.set_behavior(AIBehavior.ATTACK)
        ship.ai_controller.update(0.1, 3.0)

        assert ship.ai_controller.behavior == AIBehavior.HOLD_POSITION

    def test_backward_compat_base_prioritization(self):
        """Base prioritize_targets still works (not broken by tactical)."""
        from hybrid.ship import Ship
        from hybrid.systems.sensors.contact import ContactData

        ship = Ship("own", {"mass": 5000, "position": {"x": 0, "y": 0, "z": 0}})

        contacts = [
            ("C002", ContactData(
                id="C002", position={"x": 200_000, "y": 0, "z": 0},
                velocity={"x": 0, "y": 0, "z": 0},
                confidence=0.5, last_update=0.0,
                detection_method="ir", faction="hostile",
            )),
            ("C001", ContactData(
                id="C001", position={"x": 5_000, "y": 0, "z": 0},
                velocity={"x": -100, "y": 0, "z": 0},
                confidence=0.9, last_update=0.0,
                detection_method="ir", classification="destroyer",
                faction="hostile",
            )),
        ]

        sorted_contacts = AIThreatAssessment.prioritize_targets(contacts, ship)
        assert sorted_contacts[0][0] == "C001"
