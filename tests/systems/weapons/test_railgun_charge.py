# tests/systems/weapons/test_railgun_charge.py
"""Tests for railgun charge-time enforcement (Phase 1A).

The UNE-440 railgun has charge_time=2.0 seconds. Before this feature,
fire() only checked cycle_time (cooldown after firing) and never gated
on charge_time — so the railgun fired instantly. These tests verify
that the charge state machine works correctly:

  1. A freshly-created railgun cannot fire until charged.
  2. Advancing time with a valid solution brings it to READY.
  3. Losing the solution mid-charge resets to IDLE.
  4. PDCs (charge_time=0) are unaffected.
  5. After firing, the railgun must charge again.
"""

import pytest

from hybrid.systems.weapons.truth_weapons import (
    ChargeState,
    TruthWeapon,
    create_railgun,
    create_pdc,
    RAILGUN_SPECS,
    PDC_SPECS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _give_valid_solution(weapon: TruthWeapon, sim_time: float = 0.0) -> None:
    """Compute a firing solution against a stationary target at 10 km.

    The target is well within railgun range (500 km) so the solution
    will be valid and in-range.
    """
    weapon.calculate_solution(
        shooter_pos={"x": 0, "y": 0, "z": 0},
        shooter_vel={"x": 0, "y": 0, "z": 0},
        target_pos={"x": 10_000, "y": 0, "z": 0},
        target_vel={"x": 0, "y": 0, "z": 0},
        target_id="target_1",
        sim_time=sim_time,
    )


def _tick_weapon(weapon: TruthWeapon, dt: float, sim_time: float) -> None:
    """Advance the weapon by one tick."""
    weapon.tick(dt, sim_time)


class _FakePowerManager:
    """Stub that always grants power requests."""
    def request_power(self, amount: float, category: str) -> bool:
        return True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRailgunChargeState:
    """Railgun charge-time enforcement tests."""

    def test_fresh_railgun_starts_idle(self):
        """A new railgun has charge state IDLE and zero progress."""
        rg = create_railgun("test_rg")
        assert rg._charge_state == ChargeState.IDLE
        assert rg._charge_progress == 0.0

    def test_railgun_cannot_fire_immediately(self):
        """Railgun must NOT fire at t=0 even with a valid solution.

        Before the fix, fire() only checked cycle_time, not charge_time,
        so this would succeed immediately.
        """
        rg = create_railgun("test_rg")
        _give_valid_solution(rg, sim_time=10.0)

        # Tick once so the charge state machine sees the valid solution
        _tick_weapon(rg, dt=0.1, sim_time=10.1)

        assert rg._charge_state == ChargeState.CHARGING
        assert rg._charge_progress < 1.0

        # Attempt to fire
        result = rg.fire(
            sim_time=10.1,
            power_manager=_FakePowerManager(),
        )
        assert result["ok"] is False
        assert result["reason"] == "charging"
        assert "charge_progress" in result

    def test_railgun_charges_to_ready_over_time(self):
        """Ticking for >= charge_time seconds transitions to READY."""
        rg = create_railgun("test_rg")
        charge_time = RAILGUN_SPECS.charge_time  # 2.0 seconds

        sim_time = 10.0
        _give_valid_solution(rg, sim_time=sim_time)

        # Tick in 0.5s increments (4 ticks to reach 2.0 seconds)
        dt = 0.5
        for _ in range(4):
            sim_time += dt
            _give_valid_solution(rg, sim_time=sim_time)
            _tick_weapon(rg, dt=dt, sim_time=sim_time)

        assert rg._charge_state == ChargeState.READY
        assert rg._charge_progress == 1.0

    def test_railgun_can_fire_when_charged(self):
        """After charging for >= charge_time, fire() succeeds."""
        rg = create_railgun("test_rg")
        sim_time = 10.0
        _give_valid_solution(rg, sim_time=sim_time)

        # Charge fully
        dt = 0.5
        for _ in range(5):  # 2.5s > 2.0s charge_time
            sim_time += dt
            _give_valid_solution(rg, sim_time=sim_time)
            _tick_weapon(rg, dt=dt, sim_time=sim_time)

        assert rg._charge_state == ChargeState.READY

        # Fire (no projectile manager, so it will try instant path;
        # but the charge gate passes, and we get to the solution check
        # which should also pass).
        result = rg.fire(
            sim_time=sim_time,
            power_manager=_FakePowerManager(),
        )
        assert result["ok"] is True

    def test_charge_resets_on_lock_loss(self):
        """If the solution is lost mid-charge, state resets to IDLE."""
        rg = create_railgun("test_rg")
        sim_time = 10.0
        _give_valid_solution(rg, sim_time=sim_time)

        # Tick partway through charge
        sim_time += 1.0
        _give_valid_solution(rg, sim_time=sim_time)
        _tick_weapon(rg, dt=1.0, sim_time=sim_time)

        assert rg._charge_state == ChargeState.CHARGING
        assert rg._charge_progress > 0.0

        # Clear the solution (simulate lock lost)
        rg.current_solution = None

        # Next tick should dump the capacitor
        sim_time += 0.1
        _tick_weapon(rg, dt=0.1, sim_time=sim_time)

        assert rg._charge_state == ChargeState.IDLE
        assert rg._charge_progress == 0.0

    def test_charge_resets_after_fire(self):
        """After firing, charge state resets to IDLE for the next shot."""
        rg = create_railgun("test_rg")
        sim_time = 10.0
        _give_valid_solution(rg, sim_time=sim_time)

        # Charge fully
        dt = 0.5
        for _ in range(5):
            sim_time += dt
            _give_valid_solution(rg, sim_time=sim_time)
            _tick_weapon(rg, dt=dt, sim_time=sim_time)

        assert rg._charge_state == ChargeState.READY

        # Fire
        rg.fire(sim_time=sim_time, power_manager=_FakePowerManager())

        # Charge should be reset
        assert rg._charge_state == ChargeState.IDLE
        assert rg._charge_progress == 0.0

    def test_pdc_has_no_charge_delay(self):
        """PDC (charge_time=0) fires instantly with no charge gate."""
        pdc = create_pdc("test_pdc")
        assert PDC_SPECS.charge_time == 0.0

        # Charge state should be IDLE but the gate should not block
        assert pdc._charge_state == ChargeState.IDLE

        sim_time = 10.0
        # Give PDC a valid solution at close range
        pdc.calculate_solution(
            shooter_pos={"x": 0, "y": 0, "z": 0},
            shooter_vel={"x": 0, "y": 0, "z": 0},
            target_pos={"x": 500, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            target_id="target_pdc",
            sim_time=sim_time,
        )

        # Tick once to let tracking converge
        _tick_weapon(pdc, dt=0.1, sim_time=sim_time + 0.1)

        # PDC should be able to fire without any charge wait
        result = pdc.fire(
            sim_time=sim_time + 0.1,
            power_manager=_FakePowerManager(),
        )
        assert result["ok"] is True

    def test_pdc_charge_state_unchanged_after_tick(self):
        """Ticking a PDC does not advance charge state (no-op path)."""
        pdc = create_pdc("test_pdc")
        _tick_weapon(pdc, dt=1.0, sim_time=1.0)
        assert pdc._charge_state == ChargeState.IDLE
        assert pdc._charge_progress == 0.0

    def test_charge_progress_in_telemetry(self):
        """get_state() exposes charge_state and charge_progress."""
        rg = create_railgun("test_rg")
        state = rg.get_state()

        assert "charge_state" in state
        assert "charge_progress" in state
        assert "charge_time" in state
        assert state["charge_state"] == "idle"
        assert state["charge_progress"] == 0.0
        assert state["charge_time"] == 2.0

    def test_charging_telemetry_during_charge(self):
        """Telemetry shows CHARGING state while capacitor energises."""
        rg = create_railgun("test_rg")
        sim_time = 10.0
        _give_valid_solution(rg, sim_time=sim_time)

        sim_time += 1.0
        _give_valid_solution(rg, sim_time=sim_time)
        _tick_weapon(rg, dt=1.0, sim_time=sim_time)

        state = rg.get_state()
        assert state["charge_state"] == "charging"
        assert 0.4 < state["charge_progress"] < 0.6  # ~50% through 2s charge

    def test_ready_to_fire_includes_charge_check(self):
        """Firing solution's ready_to_fire is False while charging."""
        rg = create_railgun("test_rg")
        sim_time = 10.0
        _give_valid_solution(rg, sim_time=sim_time)

        # One tick to start charging
        sim_time += 0.5
        _give_valid_solution(rg, sim_time=sim_time)
        _tick_weapon(rg, dt=0.5, sim_time=sim_time)

        assert rg.current_solution is not None
        # Solution should not be ready yet because charge is not complete
        assert rg._charge_state == ChargeState.CHARGING
        assert not rg.current_solution.ready_to_fire
        assert "Charging" in rg.current_solution.reason

    def test_can_fire_returns_false_while_charging(self):
        """can_fire() quick check blocks while charging."""
        rg = create_railgun("test_rg")
        sim_time = 10.0
        _give_valid_solution(rg, sim_time=sim_time)

        sim_time += 0.5
        _give_valid_solution(rg, sim_time=sim_time)
        _tick_weapon(rg, dt=0.5, sim_time=sim_time)

        assert rg._charge_state == ChargeState.CHARGING
        assert rg.can_fire(sim_time) is False

    def test_can_fire_returns_true_when_ready(self):
        """can_fire() passes once charge is complete."""
        rg = create_railgun("test_rg")
        sim_time = 10.0
        _give_valid_solution(rg, sim_time=sim_time)

        for _ in range(5):
            sim_time += 0.5
            _give_valid_solution(rg, sim_time=sim_time)
            _tick_weapon(rg, dt=0.5, sim_time=sim_time)

        assert rg._charge_state == ChargeState.READY
        assert rg.can_fire(sim_time) is True

    def test_target_switch_resets_charge(self):
        """Switching targets mid-charge dumps the capacitor."""
        rg = create_railgun("test_rg")
        sim_time = 10.0
        _give_valid_solution(rg, sim_time=sim_time)
        _tick_weapon(rg, dt=1.0, sim_time=sim_time + 1.0)

        # Mid-charge — should be ~50%
        assert rg._charge_state == ChargeState.CHARGING
        assert rg._charge_progress > 0.4

        # Switch to a different target
        rg.calculate_solution(
            shooter_pos={"x": 0, "y": 0, "z": 0},
            shooter_vel={"x": 0, "y": 0, "z": 0},
            target_pos={"x": 20_000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            target_id="target_2",
            sim_time=sim_time + 1.0,
        )
        _tick_weapon(rg, dt=0.1, sim_time=sim_time + 1.1)

        # Charge should have reset for the new target
        assert rg._charge_target_id == "target_2"
        assert rg._charge_progress < 0.2  # Starting over

    def test_large_dt_clamps_progress(self):
        """A very large dt must not push charge_progress above 1.0."""
        rg = create_railgun("test_rg")
        sim_time = 10.0
        _give_valid_solution(rg, sim_time=sim_time)
        _tick_weapon(rg, dt=10.0, sim_time=sim_time + 10.0)

        assert rg._charge_progress == 1.0
        assert rg._charge_state == ChargeState.READY
        # Telemetry must also be clamped
        state = rg.get_state()
        assert state.get("charge_progress", 0) <= 1.0
