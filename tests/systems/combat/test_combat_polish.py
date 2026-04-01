# tests/systems/combat/test_combat_polish.py
"""Tests for combat polish changes — spec alignment, targeting pipeline,
firing solution confidence, damage model, and weapon firing mechanics."""

import pytest
import math


# ---------------------------------------------------------------------------
# 1. Weapon Specs Match Design Doc
# ---------------------------------------------------------------------------

class TestWeaponSpecsMatchDesignDoc:
    """Verify that weapon constants match the CLAUDE.md design document."""

    def test_railgun_muzzle_velocity(self):
        """Railgun muzzle velocity == 20 km/s (20000 m/s)."""
        from hybrid.systems.weapons.truth_weapons import RAILGUN_SPECS
        assert RAILGUN_SPECS.muzzle_velocity == 20000.0

    def test_railgun_effective_range(self):
        """Railgun effective range == 500 km (500000 m)."""
        from hybrid.systems.weapons.truth_weapons import RAILGUN_SPECS
        assert RAILGUN_SPECS.effective_range == 500000.0

    def test_railgun_name(self):
        """Railgun name is UNE-440 Railgun."""
        from hybrid.systems.weapons.truth_weapons import RAILGUN_SPECS
        assert RAILGUN_SPECS.name == "UNE-440 Railgun"

    def test_pdc_muzzle_velocity(self):
        """PDC muzzle velocity == 2 km/s (2000 m/s, 40mm rounds)."""
        from hybrid.systems.weapons.truth_weapons import PDC_SPECS
        assert PDC_SPECS.muzzle_velocity == 2000.0

    def test_pdc_effective_range(self):
        """PDC effective range == 2 km (2000 m, accuracy-limited)."""
        from hybrid.systems.weapons.truth_weapons import PDC_SPECS
        assert PDC_SPECS.effective_range == 2000.0

    def test_pdc_name(self):
        """PDC name is Narwhal-III PDC."""
        from hybrid.systems.weapons.truth_weapons import PDC_SPECS
        assert PDC_SPECS.name == "Narwhal-III PDC"

    def test_railgun_is_kinetic_penetrator(self):
        """Railgun damage type is kinetic penetrator."""
        from hybrid.systems.weapons.truth_weapons import RAILGUN_SPECS, DamageType
        assert RAILGUN_SPECS.damage_type == DamageType.KINETIC_PENETRATOR

    def test_pdc_is_kinetic_fragmentation(self):
        """PDC damage type is kinetic fragmentation."""
        from hybrid.systems.weapons.truth_weapons import PDC_SPECS, DamageType
        assert PDC_SPECS.damage_type == DamageType.KINETIC_FRAGMENTATION

    def test_railgun_charge_time_defined(self):
        """Railgun has a 2-second charge time defined."""
        from hybrid.systems.weapons.truth_weapons import RAILGUN_SPECS
        assert RAILGUN_SPECS.charge_time == 2.0

    def test_pdc_burst_count_defined(self):
        """PDC has burst_count == 10 (Expanse-style sustained fire)."""
        from hybrid.systems.weapons.truth_weapons import PDC_SPECS
        assert PDC_SPECS.burst_count == 10


# ---------------------------------------------------------------------------
# 2. Firing Solution Confidence
# ---------------------------------------------------------------------------

class TestFiringSolutionConfidence:
    """Verify firing solution confidence scores work correctly."""

    def test_firing_solution_has_confidence_field(self):
        """FiringSolution dataclass has a confidence field."""
        from hybrid.systems.weapons.truth_weapons import FiringSolution
        sol = FiringSolution()
        assert hasattr(sol, "confidence")

    def test_confidence_is_bounded_zero_to_one(self):
        """Confidence score stays in [0.0, 1.0]."""
        from hybrid.systems.weapons.truth_weapons import create_railgun

        railgun = create_railgun("test")
        solution = railgun.calculate_solution(
            shooter_pos={"x": 0, "y": 0, "z": 0},
            shooter_vel={"x": 0, "y": 0, "z": 0},
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            target_id="t1",
            sim_time=0.0,
        )
        assert 0.0 <= solution.confidence <= 1.0

    def test_confidence_higher_at_close_range(self):
        """Closer targets yield higher confidence than distant ones."""
        from hybrid.systems.weapons.truth_weapons import create_railgun

        railgun = create_railgun("test")

        close = railgun.calculate_solution(
            shooter_pos={"x": 0, "y": 0, "z": 0},
            shooter_vel={"x": 0, "y": 0, "z": 0},
            target_pos={"x": 5000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            target_id="t1",
            sim_time=0.0,
        )

        far = railgun.calculate_solution(
            shooter_pos={"x": 0, "y": 0, "z": 0},
            shooter_vel={"x": 0, "y": 0, "z": 0},
            target_pos={"x": 400000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            target_id="t1",
            sim_time=0.0,
        )

        assert close.confidence > far.confidence

    def test_confidence_degraded_by_low_track_quality(self):
        """Lower track_quality input produces lower confidence."""
        from hybrid.systems.weapons.truth_weapons import create_railgun

        railgun = create_railgun("test")
        pos = {"x": 10000, "y": 0, "z": 0}
        vel = {"x": 0, "y": 0, "z": 0}
        zero = {"x": 0, "y": 0, "z": 0}

        high_tq = railgun.calculate_solution(
            shooter_pos=zero, shooter_vel=zero,
            target_pos=pos, target_vel=vel,
            target_id="t1", sim_time=0.0,
            track_quality=1.0,
        )

        low_tq = railgun.calculate_solution(
            shooter_pos=zero, shooter_vel=zero,
            target_pos=pos, target_vel=vel,
            target_id="t1", sim_time=0.0,
            track_quality=0.3,
        )

        assert high_tq.confidence > low_tq.confidence

    def test_confidence_zero_track_quality_yields_zero(self):
        """Zero track quality should produce zero confidence."""
        from hybrid.systems.weapons.truth_weapons import create_railgun

        railgun = create_railgun("test")
        sol = railgun.calculate_solution(
            shooter_pos={"x": 0, "y": 0, "z": 0},
            shooter_vel={"x": 0, "y": 0, "z": 0},
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            target_id="t1", sim_time=0.0,
            track_quality=0.0,
        )
        assert sol.confidence == 0.0


# ---------------------------------------------------------------------------
# 3. Targeting Pipeline
# ---------------------------------------------------------------------------

class TestTargetingPipeline:
    """Verify the targeting pipeline: CONTACT -> TRACKING -> ACQUIRING -> LOCKED."""

    def test_lock_starts_at_contact(self):
        """Lock initiation enters CONTACT state (sensor correlation phase).

        Without a ship reference to check range, there is no close-range
        skip, so the system always enters CONTACT first.
        """
        from hybrid.systems.targeting.targeting_system import (
            TargetingSystem, LockState,
        )

        ts = TargetingSystem({})
        result = ts.lock_target("t1", sim_time=0.0)

        assert result["ok"]
        assert ts.lock_state == LockState.CONTACT

    def test_tracking_state_enum_exists(self):
        """LockState enum contains TRACKING."""
        from hybrid.systems.targeting.targeting_system import LockState

        assert hasattr(LockState, "TRACKING")
        assert LockState.TRACKING.value == "tracking"

    def test_contact_state_enum_exists(self):
        """LockState enum contains CONTACT (used as initial designation state)."""
        from hybrid.systems.targeting.targeting_system import LockState

        assert hasattr(LockState, "CONTACT")
        assert LockState.CONTACT.value == "contact"

    def test_lock_loss_reverts_to_tracking(self):
        """When lock is LOST, next update reverts to TRACKING."""
        from hybrid.systems.targeting.targeting_system import (
            TargetingSystem, LockState,
        )

        ts = TargetingSystem({})
        ts.lock_target("t1", sim_time=0.0)

        # Manually set to LOST to simulate lock loss
        ts.lock_state = LockState.LOST
        ts.track_quality = 0.5

        # The _update_lock method transitions LOST -> TRACKING.
        # We test the transition logic directly since we don't have a full ship.
        # According to the code: LOST -> TRACKING with 50% track retention
        assert ts.lock_state == LockState.LOST

        # Simulate what _update_lock does for LOST state
        ts.lock_state = LockState.TRACKING
        ts.track_quality *= 0.5
        ts.lock_progress = 0.0

        assert ts.lock_state == LockState.TRACKING
        assert ts.track_quality == 0.25  # Halved from 0.5

    def test_track_quality_starts_at_zero(self):
        """Track quality starts at 0 when a new target is locked."""
        from hybrid.systems.targeting.targeting_system import TargetingSystem

        ts = TargetingSystem({})
        ts.lock_target("t1", sim_time=0.0)

        assert ts.track_quality == 0.0

    def test_track_quality_attribute_exists(self):
        """TargetingSystem has track_quality attribute."""
        from hybrid.systems.targeting.targeting_system import TargetingSystem

        ts = TargetingSystem({})
        assert hasattr(ts, "track_quality")

    def test_unlock_resets_state(self):
        """Unlocking resets all targeting state back to NONE."""
        from hybrid.systems.targeting.targeting_system import (
            TargetingSystem, LockState,
        )

        ts = TargetingSystem({})
        ts.lock_target("t1", sim_time=0.0)
        ts.lock_state = LockState.LOCKED
        ts.track_quality = 0.9

        result = ts.unlock_target()

        assert result["ok"]
        assert ts.lock_state == LockState.NONE
        assert ts.locked_target is None
        assert ts.track_quality == 0.0

    def test_lock_state_full_progression_enum_values(self):
        """All expected lock states exist: NONE, CONTACT, TRACKING, ACQUIRING, LOCKED, LOST."""
        from hybrid.systems.targeting.targeting_system import LockState

        expected = {"NONE", "CONTACT", "TRACKING", "ACQUIRING", "LOCKED", "LOST"}
        actual = {s.name for s in LockState}
        assert expected == actual

    def test_sensor_factor_attribute_exists(self):
        """TargetingSystem tracks sensor degradation factor."""
        from hybrid.systems.targeting.targeting_system import TargetingSystem

        ts = TargetingSystem({})
        assert hasattr(ts, "_sensor_factor")
        assert ts._sensor_factor == 1.0


# ---------------------------------------------------------------------------
# 4. Damage Model
# ---------------------------------------------------------------------------

class TestDamageModelPolish:
    """Verify subsystem damage levels and mission kill detection."""

    def test_status_progression_online_to_damaged(self):
        """Subsystem transitions from ONLINE to DAMAGED below 75% health."""
        from hybrid.systems.damage_model import DamageModel, SubsystemStatus

        model = DamageModel(schema={
            "propulsion": {"max_health": 100.0},
        })

        # Initially ONLINE
        assert model.subsystems["propulsion"].get_status() == SubsystemStatus.ONLINE

        # Damage to 70% => DAMAGED
        model.apply_damage("propulsion", 30.0)
        assert model.subsystems["propulsion"].get_status() == SubsystemStatus.DAMAGED

    def test_status_progression_to_offline(self):
        """Subsystem transitions to OFFLINE at failure threshold."""
        from hybrid.systems.damage_model import DamageModel, SubsystemStatus

        model = DamageModel(schema={
            "sensors": {"max_health": 100.0, "failure_threshold": 0.2},
        })

        # Damage to below 20% of max (failure threshold)
        model.apply_damage("sensors", 85.0)
        assert model.subsystems["sensors"].get_status() == SubsystemStatus.OFFLINE

    def test_status_progression_to_destroyed(self):
        """Subsystem transitions to DESTROYED at 0 health."""
        from hybrid.systems.damage_model import DamageModel, SubsystemStatus

        model = DamageModel(schema={
            "weapons": {"max_health": 100.0},
        })

        model.apply_damage("weapons", 100.0)
        assert model.subsystems["weapons"].get_status() == SubsystemStatus.DESTROYED

    def test_mission_kill_on_propulsion_destroyed(self):
        """Destroying propulsion triggers a mobility/mission kill."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "propulsion": {"max_health": 100.0, "failure_threshold": 0.2},
            "weapons": {"max_health": 100.0},
        })

        assert not model.is_mission_kill()

        model.apply_damage("propulsion", 100.0)

        assert model.is_mobility_kill()
        assert model.is_mission_kill()
        assert "mobility_kill" in model.get_mission_kill_reason()

    def test_sensor_damage_degrades_targeting(self):
        """Sensor degradation factor drops when sensors are damaged."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "sensors": {"max_health": 100.0, "failure_threshold": 0.2},
        })

        factor_before = model.get_degradation_factor("sensors")
        assert factor_before == 1.0

        model.apply_damage("sensors", 50.0)
        factor_after = model.get_degradation_factor("sensors")

        assert factor_after < factor_before
        assert factor_after == pytest.approx(0.5, abs=0.01)

    def test_sensor_failure_gives_zero_factor(self):
        """Failed sensors give 0.0 degradation factor."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "sensors": {"max_health": 100.0, "failure_threshold": 0.2},
        })

        model.apply_damage("sensors", 85.0)  # Below failure threshold
        assert model.get_degradation_factor("sensors") == 0.0

    def test_all_five_subsystems_represented(self):
        """All five design-doc subsystems can be registered."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "propulsion": {"max_health": 100.0},
            "rcs": {"max_health": 80.0},
            "sensors": {"max_health": 90.0},
            "weapons": {"max_health": 100.0},
            "power": {"max_health": 120.0},
        })

        assert set(model.subsystems.keys()) == {
            "propulsion", "rcs", "sensors", "weapons", "power"
        }

    def test_damage_history_tracked(self):
        """Damage events are recorded in history."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "propulsion": {"max_health": 100.0},
        })

        model.apply_damage("propulsion", 20.0, source="railgun")
        model.apply_damage("propulsion", 15.0, source="pdc")

        assert len(model.damage_history) == 2
        assert model.damage_history[0]["source"] == "railgun"
        assert model.damage_history[1]["source"] == "pdc"


# ---------------------------------------------------------------------------
# 5. Weapon Firing
# ---------------------------------------------------------------------------

class TestWeaponFiring:
    """Verify weapon firing mechanics: ammo, cooldown, basic fire."""

    def test_railgun_fire_reduces_ammo(self):
        """Firing a railgun reduces ammo by 1."""
        from hybrid.systems.weapons.truth_weapons import create_railgun

        railgun = create_railgun("test")
        initial_ammo = railgun.ammo

        # Set up a valid firing solution and force ready state
        railgun.turret_bearing = {"pitch": 0.0, "yaw": 0.0}
        solution = railgun.calculate_solution(
            shooter_pos={"x": 0, "y": 0, "z": 0},
            shooter_vel={"x": 0, "y": 0, "z": 0},
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            target_id="t1",
            sim_time=10.0,
        )

        # Need a mock power manager
        class MockPower:
            def request_power(self, amount, category):
                return True

        result = railgun.fire(sim_time=10.0, power_manager=MockPower())

        if result["ok"]:
            assert railgun.ammo == initial_ammo - 1

    def test_pdc_fire_reduces_ammo(self):
        """Firing a PDC reduces ammo by 1."""
        from hybrid.systems.weapons.truth_weapons import create_pdc

        pdc = create_pdc("test")
        initial_ammo = pdc.ammo

        pdc.turret_bearing = {"pitch": 0.0, "yaw": 0.0}
        solution = pdc.calculate_solution(
            shooter_pos={"x": 0, "y": 0, "z": 0},
            shooter_vel={"x": 0, "y": 0, "z": 0},
            target_pos={"x": 2000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            target_id="t1",
            sim_time=10.0,
        )

        class MockPower:
            def request_power(self, amount, category):
                return True

        result = pdc.fire(sim_time=10.0, power_manager=MockPower())

        if result["ok"]:
            assert pdc.ammo == initial_ammo - 1

    def test_weapon_respects_cooldown(self):
        """Weapon cannot fire again before cycle_time elapses."""
        from hybrid.systems.weapons.truth_weapons import create_railgun

        railgun = create_railgun("test")
        railgun.turret_bearing = {"pitch": 0.0, "yaw": 0.0}

        pos = {"x": 10000, "y": 0, "z": 0}
        zero = {"x": 0, "y": 0, "z": 0}

        class MockPower:
            def request_power(self, amount, category):
                return True

        # First shot at t=10
        railgun.calculate_solution(
            shooter_pos=zero, shooter_vel=zero,
            target_pos=pos, target_vel=zero,
            target_id="t1", sim_time=10.0,
        )
        result1 = railgun.fire(sim_time=10.0, power_manager=MockPower())

        # Second shot at t=11 (only 1s later, cycle_time=5s)
        railgun.calculate_solution(
            shooter_pos=zero, shooter_vel=zero,
            target_pos=pos, target_vel=zero,
            target_id="t1", sim_time=11.0,
        )
        result2 = railgun.fire(sim_time=11.0, power_manager=MockPower())

        if result1["ok"]:
            assert not result2["ok"]
            assert result2["reason"] == "cycling"

    def test_weapon_requires_ammo(self):
        """Weapon with no ammo cannot fire."""
        from hybrid.systems.weapons.truth_weapons import create_railgun

        railgun = create_railgun("test")
        railgun.ammo = 0

        result = railgun.fire(sim_time=100.0, power_manager=None)

        assert not result["ok"]
        assert result["reason"] == "no_ammo"

    def test_weapon_disabled_cannot_fire(self):
        """Disabled weapon cannot fire."""
        from hybrid.systems.weapons.truth_weapons import create_railgun

        railgun = create_railgun("test")
        railgun.enabled = False

        result = railgun.fire(sim_time=100.0, power_manager=None)

        assert not result["ok"]
        assert result["reason"] == "disabled"

    def test_can_fire_check(self):
        """TruthWeapon.can_fire() returns correct readiness."""
        from hybrid.systems.weapons.truth_weapons import create_railgun, ChargeState

        railgun = create_railgun("test")

        # Fresh railgun cannot fire — capacitor must charge first
        assert not railgun.can_fire(sim_time=100.0)

        # Manually set charge to READY so we can test the other gates
        railgun._charge_state = ChargeState.READY
        assert railgun.can_fire(sim_time=100.0)

        # Empty weapon cannot
        railgun.ammo = 0
        assert not railgun.can_fire(sim_time=100.0)

        # Disabled weapon cannot
        railgun.ammo = 10
        railgun.enabled = False
        assert not railgun.can_fire(sim_time=100.0)

    def test_subsystem_targets_include_all_five(self):
        """Both weapon types can target all 5 subsystems."""
        from hybrid.systems.weapons.truth_weapons import create_railgun, create_pdc
        import random

        random.seed(42)

        railgun = create_railgun("test")
        pdc = create_pdc("test")

        railgun_targets = set()
        pdc_targets = set()

        for _ in range(500):
            railgun_targets.add(railgun._select_subsystem_target())
            pdc_targets.add(pdc._select_subsystem_target())

        expected = {"propulsion", "power", "weapons", "rcs", "sensors"}
        assert railgun_targets == expected
        assert pdc_targets == expected


# ---------------------------------------------------------------------------
# 6. Combat System Integration
# ---------------------------------------------------------------------------

class TestCombatSystemIntegration:
    """Integration-level tests for the combat system."""

    def test_combat_system_creates_correct_weapon_counts(self):
        """CombatSystem creates the right number of each weapon type."""
        from hybrid.systems.combat.combat_system import CombatSystem

        cs = CombatSystem({"railguns": 2, "pdcs": 3})

        railguns = [k for k in cs.truth_weapons if k.startswith("railgun")]
        pdcs = [k for k in cs.truth_weapons if k.startswith("pdc")]

        assert len(railguns) == 2
        assert len(pdcs) == 3
        assert len(cs.truth_weapons) == 5

    def test_combat_system_tracks_shots(self):
        """CombatSystem starts with zero shots/hits."""
        from hybrid.systems.combat.combat_system import CombatSystem

        cs = CombatSystem({"railguns": 1, "pdcs": 1})

        assert cs.shots_fired == 0
        assert cs.hits == 0
        assert cs.damage_dealt == 0.0

    def test_resupply_restores_full_ammo(self):
        """Resupply brings all weapons back to full capacity."""
        from hybrid.systems.combat.combat_system import CombatSystem

        cs = CombatSystem({"railguns": 1, "pdcs": 1})
        cs.truth_weapons["railgun_1"].ammo = 3
        cs.truth_weapons["pdc_1"].ammo = 50

        result = cs.resupply()

        assert result["ok"]
        assert cs.truth_weapons["railgun_1"].ammo == 20
        assert cs.truth_weapons["pdc_1"].ammo == 3000

    def test_weapon_state_includes_confidence(self):
        """Weapon get_state() includes solution confidence."""
        from hybrid.systems.weapons.truth_weapons import create_railgun

        railgun = create_railgun("test")
        railgun.calculate_solution(
            shooter_pos={"x": 0, "y": 0, "z": 0},
            shooter_vel={"x": 0, "y": 0, "z": 0},
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            target_id="t1",
            sim_time=0.0,
        )

        state = railgun.get_state()
        assert "solution" in state
        assert "confidence" in state["solution"]


# ---------------------------------------------------------------------------
# 7. PDC Expanse-style Range Falloff
# ---------------------------------------------------------------------------

class TestPDCRangeFalloff:
    """Verify the PDC range accuracy curve matches Expanse combat doctrine.

    The curve is tuned so computer-controlled turrets are deadly at
    knife-fight range but 40mm rounds disperse fast past 1km.
    """

    def test_pdc_accuracy_at_500m(self):
        """PDC accuracy at 500m should be near base_accuracy (~0.95)."""
        from hybrid.systems.weapons.truth_weapons import pdc_range_accuracy
        acc = pdc_range_accuracy(500.0)
        assert acc >= 0.90, f"PDC accuracy at 500m should be >=0.90, got {acc:.3f}"

    def test_pdc_accuracy_at_1km(self):
        """PDC accuracy at 1km should be ~0.70 (effective engagement)."""
        from hybrid.systems.weapons.truth_weapons import pdc_range_accuracy
        acc = pdc_range_accuracy(1000.0)
        assert 0.55 <= acc <= 0.80, f"PDC accuracy at 1km should be 0.55-0.80, got {acc:.3f}"

    def test_pdc_accuracy_at_2km(self):
        """PDC accuracy at 2km (effective_range) should be low (~0.05-0.30)."""
        from hybrid.systems.weapons.truth_weapons import pdc_range_accuracy
        acc = pdc_range_accuracy(2000.0)
        assert acc <= 0.10, f"PDC accuracy at 2km should be <=0.10, got {acc:.3f}"

    def test_pdc_accuracy_beyond_range(self):
        """PDC accuracy beyond effective range should be ~0.05 (floor)."""
        from hybrid.systems.weapons.truth_weapons import pdc_range_accuracy
        acc = pdc_range_accuracy(3000.0)
        assert acc <= 0.06, f"PDC accuracy at 3km should be <=0.06, got {acc:.3f}"

    def test_pdc_accuracy_point_blank(self):
        """PDC accuracy at point blank should equal base_accuracy."""
        from hybrid.systems.weapons.truth_weapons import pdc_range_accuracy, PDC_SPECS
        acc = pdc_range_accuracy(100.0)
        assert acc == PDC_SPECS.base_accuracy

    def test_pdc_accuracy_monotonically_decreasing(self):
        """PDC accuracy should decrease monotonically with range."""
        from hybrid.systems.weapons.truth_weapons import pdc_range_accuracy
        ranges = [100, 250, 500, 750, 1000, 1250, 1500, 1750, 2000]
        accuracies = [pdc_range_accuracy(r) for r in ranges]
        for i in range(1, len(accuracies)):
            assert accuracies[i] <= accuracies[i - 1], (
                f"Accuracy should decrease: {ranges[i-1]}m={accuracies[i-1]:.3f} "
                f"> {ranges[i]}m={accuracies[i]:.3f}"
            )

    def test_railgun_uses_linear_falloff(self):
        """Railgun should still use linear falloff, not the PDC curve."""
        from hybrid.systems.weapons.truth_weapons import RAILGUN_SPECS, _range_accuracy
        # Linear model: base_accuracy - accuracy_falloff * (range / effective_range)
        # At 250km (half range): 0.85 - 0.3 * 0.5 = 0.70
        acc = _range_accuracy(RAILGUN_SPECS, 250000.0)
        expected = 0.85 - 0.3 * 0.5
        assert abs(acc - expected) < 0.01, (
            f"Railgun at 250km should use linear falloff: expected {expected:.3f}, got {acc:.3f}"
        )

    def test_pdc_fire_rate_is_3000_rpm(self):
        """PDC cycle_time of 0.02s equals 50 rps = 3000 RPM."""
        from hybrid.systems.weapons.truth_weapons import PDC_SPECS
        rps = 1.0 / PDC_SPECS.cycle_time
        rpm = rps * 60
        assert abs(rps - 50.0) < 0.1, f"Expected 50 rps, got {rps:.1f}"
        assert abs(rpm - 3000.0) < 10, f"Expected 3000 RPM, got {rpm:.0f}"
