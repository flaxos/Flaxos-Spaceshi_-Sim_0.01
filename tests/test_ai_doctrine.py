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

    def test_retreat_propulsion_degraded_triggers_flee(self):
        """AI FLEEs when propulsion is degraded but still functional."""
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

        # Cripple propulsion to 30% -- degraded but not destroyed
        if hasattr(ship, "damage_model") and "propulsion" in ship.damage_model.subsystems:
            sub = ship.damage_model.subsystems["propulsion"]
            sub.health = sub.max_health * 0.3

        ship.ai_controller.set_behavior(AIBehavior.ATTACK)
        ship.ai_controller.update(0.1, 3.0)

        # Propulsion still > 0%, so the ship can flee
        assert ship.ai_controller.behavior == AIBehavior.FLEE

    def test_retreat_propulsion_destroyed_triggers_hold(self):
        """AI HOLDs position when propulsion is completely destroyed."""
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

        # Destroy propulsion completely
        if hasattr(ship, "damage_model") and "propulsion" in ship.damage_model.subsystems:
            sub = ship.damage_model.subsystems["propulsion"]
            sub.health = 0.0

        ship.ai_controller.set_behavior(AIBehavior.ATTACK)
        ship.ai_controller.update(0.1, 3.0)

        # Propulsion at 0% -- cannot flee, must hold
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


# ── Phase 2A: Doctrine Wiring Integration Tests ──────────────────

class TestSalvoWiring:
    """Test that salvo coordination is wired into the AI tick loop."""

    def test_salvo_plan_two_ships_same_target(self):
        """Two AI ships targeting the same enemy plan a coordinated salvo."""
        from hybrid.ship import Ship
        from hybrid.fleet.ai_controller import AIBehavior
        from hybrid.systems.sensors.contact import ContactData

        # Create two AI ships in the same faction
        ship_a = Ship("shipA", {
            "mass": 5000,
            "faction": "unsa",
            "ai_enabled": True,
            "position": {"x": 0, "y": 0, "z": 0},
            "systems": AI_SHIP_SYSTEMS,
        })
        ship_b = Ship("shipB", {
            "mass": 5000,
            "faction": "unsa",
            "ai_enabled": True,
            "position": {"x": 20_000, "y": 0, "z": 0},
            "systems": AI_SHIP_SYSTEMS,
        })

        all_ships = [ship_a, ship_b]
        ship_a._all_ships_ref = all_ships
        ship_b._all_ships_ref = all_ships

        # Shared salvo coordinator
        coord = SalvoCoordinator()
        ship_a.ai_controller.set_salvo_coordinator(coord)
        ship_b.ai_controller.set_salvo_coordinator(coord)

        # Inject the same hostile contact into both ships' sensors
        enemy = ContactData(
            id="enemy01",
            position={"x": 100_000, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            confidence=0.9, last_update=0.0,
            detection_method="ir", faction="pirates",
        )
        for ship in all_ships:
            sensors = ship.systems.get("sensors")
            sensors.contact_tracker.update_contact("enemy01", enemy, 0.0)

        ship_a.ai_controller.set_behavior(AIBehavior.ATTACK)
        ship_b.ai_controller.set_behavior(AIBehavior.ATTACK)

        # Trigger decision cycles
        ship_a.ai_controller.update(0.1, 3.0)
        ship_b.ai_controller.update(0.1, 3.0)

        # Both should have acquired a target
        assert ship_a.ai_controller.current_target is not None
        assert ship_b.ai_controller.current_target is not None

        # The salvo coordinator should now have an active plan
        # (if both target the same contact)
        target_a = ship_a.ai_controller.current_target[0]
        target_b = ship_b.ai_controller.current_target[0]

        if target_a == target_b:
            assert target_a in coord._active
            plan = coord._active[target_a]
            assert len(plan.slots) == 2
            # Arrival spread should be small (within SALVO_ARRIVAL_WINDOW)
            arrival_times = sorted(
                s.scheduled_fire_time + s.time_of_flight for s in plan.slots
            )
            assert arrival_times[-1] - arrival_times[0] < 2.5

    def test_salvo_hold_fire_before_scheduled(self):
        """AI ship holds fire when salvo coordinator says wait."""
        from hybrid.ship import Ship

        ship = Ship("shipA", {
            "mass": 5000,
            "faction": "unsa",
            "ai_enabled": True,
            "systems": AI_SHIP_SYSTEMS,
        })

        coord = SalvoCoordinator()
        ship.ai_controller.set_salvo_coordinator(coord)

        # Plan a salvo: shipA at 100km (5s ToF), shipB at 50km (2.5s ToF)
        # shipA fires first (longest range), shipB waits 2.5s
        coord.plan_salvo(
            "C001",
            [("shipA", 100_000), ("shipB", 50_000)],
            sim_time=10.0,
        )

        # shipA fires immediately (longest ToF)
        assert coord.should_fire_now("shipA", "C001", 10.0) is True
        # shipB should hold fire at 11.0 (scheduled at 12.5)
        assert coord.should_fire_now("shipB", "C001", 11.0) is False


class TestRetreatWiring:
    """Test retreat condition wiring into the AI tick loop."""

    def test_ammo_depleted_triggers_retreat(self):
        """AI retreats when all ammo is depleted."""
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

        # Deplete all ammo
        combat = ship.systems.get("combat")
        if combat:
            for weapon in combat.truth_weapons.values():
                if weapon.ammo is not None:
                    weapon.ammo = 0
            combat.torpedoes_loaded = 0
            combat.missiles_loaded = 0

        ship.ai_controller.set_behavior(AIBehavior.ATTACK)
        ship.ai_controller.update(0.1, 3.0)

        # Should retreat (FLEE because propulsion still works)
        assert ship.ai_controller.behavior == AIBehavior.FLEE


class TestAmmoConservation:
    """Test ammo conservation doctrine in AI fire logic."""

    def test_low_railgun_ammo_fraction(self):
        """_get_railgun_ammo_fraction returns correct fraction."""
        from hybrid.ship import Ship

        ship = Ship("warship", {
            "mass": 5000,
            "faction": "unsa",
            "ai_enabled": True,
            "systems": AI_SHIP_SYSTEMS,
        })

        combat = ship.systems.get("combat")
        if not combat:
            pytest.skip("No combat system")

        # Get initial fraction (should be 1.0)
        frac = ship.ai_controller._get_railgun_ammo_fraction(combat)
        assert frac == pytest.approx(1.0)

        # Drain railgun ammo to 20%
        for weapon in combat.truth_weapons.values():
            if weapon.mount_id.startswith("railgun") and weapon.ammo is not None:
                weapon.ammo = int(weapon.specs.ammo_capacity * 0.20)

        frac = ship.ai_controller._get_railgun_ammo_fraction(combat)
        assert frac == pytest.approx(0.20, abs=0.05)

    def test_ammo_conservation_detects_low_railgun(self):
        """AI detects low railgun ammo and still has guided ordnance."""
        from hybrid.ship import Ship

        ship = Ship("warship", {
            "mass": 5000,
            "faction": "unsa",
            "ai_enabled": True,
            "systems": {
                **AI_SHIP_SYSTEMS,
                "combat": {"railguns": 1, "pdcs": 1, "torpedoes": 2, "torpedo_capacity": 4},
            },
        })

        combat = ship.systems.get("combat")
        if not combat:
            pytest.skip("No combat system")

        # Drain railgun ammo to 10%
        for weapon in combat.truth_weapons.values():
            if weapon.mount_id.startswith("railgun") and weapon.ammo is not None:
                weapon.ammo = max(1, int(weapon.specs.ammo_capacity * 0.10))

        frac = ship.ai_controller._get_railgun_ammo_fraction(combat)
        assert frac < 0.25, f"Expected < 25% railgun ammo, got {frac:.0%}"

        # is_ammo_depleted should be False (still have torpedoes)
        assert not ship.ai_controller._is_ammo_depleted(combat)

    def test_ammo_fully_depleted_detection(self):
        """_is_ammo_depleted returns True when everything is at zero."""
        from hybrid.ship import Ship

        ship = Ship("warship", {
            "mass": 5000,
            "faction": "unsa",
            "ai_enabled": True,
            "systems": AI_SHIP_SYSTEMS,
        })

        combat = ship.systems.get("combat")
        if not combat:
            pytest.skip("No combat system")

        # Deplete everything
        for weapon in combat.truth_weapons.values():
            if weapon.ammo is not None:
                weapon.ammo = 0
        combat.torpedoes_loaded = 0
        combat.missiles_loaded = 0

        assert ship.ai_controller._is_ammo_depleted(combat) is True


class TestTargetPrioritizationWiring:
    """Test tactical scoring bonuses are correctly applied."""

    def test_railgun_target_scores_higher(self):
        """Ship with active railguns gets +3.0 tactical threat bonus."""
        from hybrid.ship import Ship
        from hybrid.systems.sensors.contact import ContactData

        own_ship = Ship("own", {
            "mass": 5000,
            "position": {"x": 0, "y": 0, "z": 0},
            "systems": AI_SHIP_SYSTEMS,
        })

        # Create armed enemy ship
        armed_enemy = Ship("armed", {
            "mass": 5000,
            "faction": "pirates",
            "position": {"x": 20_000, "y": 0, "z": 0},
            "systems": AI_SHIP_SYSTEMS,
        })

        # Create unarmed enemy ship (same distance)
        unarmed_enemy = Ship("unarmed", {
            "mass": 5000,
            "faction": "pirates",
            "position": {"x": 20_000, "y": 5_000, "z": 0},
        })

        own_ship._all_ships_ref = [own_ship, armed_enemy, unarmed_enemy]

        # Create contacts at similar distances
        armed_contact = ContactData(
            id="armed",
            position={"x": 20_000, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            confidence=0.9, last_update=0.0,
            detection_method="ir", faction="pirates",
        )
        unarmed_contact = ContactData(
            id="unarmed",
            position={"x": 20_000, "y": 5_000, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            confidence=0.9, last_update=0.0,
            detection_method="ir", faction="pirates",
        )

        score_armed = AIThreatAssessment.assess_threat_tactical(
            "armed", armed_contact, own_ship,
        )
        score_unarmed = AIThreatAssessment.assess_threat_tactical(
            "unarmed", unarmed_contact, own_ship,
        )

        # Armed ship should score higher (has railguns = +3.0)
        assert score_armed > score_unarmed

    def test_impaired_sensors_bonus(self):
        """Target with damaged sensors gets +1.5 tactical bonus."""
        from hybrid.ship import Ship
        from hybrid.systems.sensors.contact import ContactData

        own_ship = Ship("own", {
            "mass": 5000,
            "position": {"x": 0, "y": 0, "z": 0},
            "systems": AI_SHIP_SYSTEMS,
        })

        enemy = Ship("enemy", {
            "mass": 5000,
            "faction": "pirates",
            "position": {"x": 30_000, "y": 0, "z": 0},
            "systems": AI_SHIP_SYSTEMS,
        })

        own_ship._all_ships_ref = [own_ship, enemy]

        contact = ContactData(
            id="enemy",
            position={"x": 30_000, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            confidence=0.9, last_update=0.0,
            detection_method="ir", faction="pirates",
        )

        # Score with healthy sensors
        score_healthy = AIThreatAssessment.assess_threat_tactical(
            "enemy", contact, own_ship,
        )

        # Damage enemy sensors
        if hasattr(enemy, "damage_model") and "sensors" in enemy.damage_model.subsystems:
            sub = enemy.damage_model.subsystems["sensors"]
            sub.health = sub.max_health * 0.3  # 30% = impaired

        score_impaired = AIThreatAssessment.assess_threat_tactical(
            "enemy", contact, own_ship,
        )

        # Impaired sensors should score +1.5
        assert score_impaired > score_healthy
        assert score_impaired - score_healthy == pytest.approx(1.5, abs=0.1)

    def test_impaired_propulsion_bonus(self):
        """Target with damaged propulsion gets +1.0 tactical bonus."""
        from hybrid.ship import Ship
        from hybrid.systems.sensors.contact import ContactData

        own_ship = Ship("own", {
            "mass": 5000,
            "position": {"x": 0, "y": 0, "z": 0},
            "systems": AI_SHIP_SYSTEMS,
        })

        enemy = Ship("enemy", {
            "mass": 5000,
            "faction": "pirates",
            "position": {"x": 30_000, "y": 0, "z": 0},
            "systems": AI_SHIP_SYSTEMS,
        })

        own_ship._all_ships_ref = [own_ship, enemy]

        contact = ContactData(
            id="enemy",
            position={"x": 30_000, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            confidence=0.9, last_update=0.0,
            detection_method="ir", faction="pirates",
        )

        # Score with healthy propulsion
        score_healthy = AIThreatAssessment.assess_threat_tactical(
            "enemy", contact, own_ship,
        )

        # Damage enemy propulsion
        if hasattr(enemy, "damage_model") and "propulsion" in enemy.damage_model.subsystems:
            sub = enemy.damage_model.subsystems["propulsion"]
            sub.health = sub.max_health * 0.3

        score_impaired = AIThreatAssessment.assess_threat_tactical(
            "enemy", contact, own_ship,
        )

        # Impaired propulsion should score +1.0
        assert score_impaired > score_healthy
        assert score_impaired - score_healthy == pytest.approx(1.0, abs=0.1)


class TestFleetManagerSalvoDistribution:
    """Test that FleetManager creates and distributes salvo coordinators."""

    def test_create_fleet_attaches_coordinator(self):
        """Creating a fleet distributes salvo coordinator to AI ships."""
        from hybrid.ship import Ship
        from hybrid.fleet.fleet_manager import FleetManager

        class MockSimulator:
            def __init__(self):
                self.ships = {}

        sim = MockSimulator()
        ship_a = Ship("shipA", {
            "mass": 5000, "faction": "unsa", "ai_enabled": True,
            "systems": AI_SHIP_SYSTEMS,
        })
        ship_b = Ship("shipB", {
            "mass": 5000, "faction": "unsa", "ai_enabled": True,
            "systems": AI_SHIP_SYSTEMS,
        })
        sim.ships = {"shipA": ship_a, "shipB": ship_b}

        fm = FleetManager(simulator=sim)
        fm.create_fleet("fleet1", "Alpha Fleet", "shipA", ["shipA", "shipB"])

        # Both ships should have the same salvo coordinator
        assert ship_a.ai_controller._salvo_coordinator is not None
        assert ship_b.ai_controller._salvo_coordinator is not None
        assert (
            ship_a.ai_controller._salvo_coordinator
            is ship_b.ai_controller._salvo_coordinator
        )

    def test_add_ship_to_fleet_attaches_coordinator(self):
        """Adding a ship to an existing fleet attaches the coordinator."""
        from hybrid.ship import Ship
        from hybrid.fleet.fleet_manager import FleetManager

        class MockSimulator:
            def __init__(self):
                self.ships = {}

        sim = MockSimulator()
        ship_a = Ship("shipA", {
            "mass": 5000, "faction": "unsa", "ai_enabled": True,
            "systems": AI_SHIP_SYSTEMS,
        })
        ship_c = Ship("shipC", {
            "mass": 5000, "faction": "unsa", "ai_enabled": True,
            "systems": AI_SHIP_SYSTEMS,
        })
        sim.ships = {"shipA": ship_a, "shipC": ship_c}

        fm = FleetManager(simulator=sim)
        fm.create_fleet("fleet1", "Alpha Fleet", "shipA", ["shipA"])

        # ship_c not in fleet yet
        assert ship_c.ai_controller._salvo_coordinator is None

        fm.add_ship_to_fleet("shipC", "fleet1")

        # Now ship_c should share the coordinator
        assert ship_c.ai_controller._salvo_coordinator is not None
        assert (
            ship_c.ai_controller._salvo_coordinator
            is ship_a.ai_controller._salvo_coordinator
        )
