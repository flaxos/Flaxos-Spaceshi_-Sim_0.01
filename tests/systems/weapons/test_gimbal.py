# tests/systems/weapons/test_gimbal.py
"""Tests for gimbal weapon mount tracking.

Verifies that gimballed weapons slew toward the target at the correct
rate, clamp to arc limits, report tracking only within threshold, and
that non-gimballed weapons are unchanged.
"""

import math
import pytest
from hybrid.systems.weapons.truth_weapons import (
    TruthWeapon, FiringSolution, RAILGUN_SPECS, PDC_SPECS,
    create_railgun, create_pdc, DamageType,
)
from hybrid.systems.weapons.hardpoint import Hardpoint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gimballed_railgun(
    max_rate: float = 15.0,
    az_limits: tuple = (-25.0, 25.0),
    el_limits: tuple = (-15.0, 30.0),
) -> TruthWeapon:
    """Create a railgun with gimbal enabled and configured limits."""
    w = create_railgun("railgun_test")
    w.gimbal_enabled = True
    w._gimbal_max_rate = max_rate
    w._gimbal_az_limits = az_limits
    w._gimbal_el_limits = el_limits
    w.firing_arc = {
        "azimuth_min": az_limits[0],
        "azimuth_max": az_limits[1],
        "elevation_min": el_limits[0],
        "elevation_max": el_limits[1],
    }
    return w


def _make_gimballed_pdc(
    max_rate: float = 180.0,
    az_limits: tuple = (-90.0, 90.0),
    el_limits: tuple = (-90.0, 90.0),
) -> TruthWeapon:
    """Create a PDC with gimbal enabled and configured limits."""
    w = create_pdc("pdc_test")
    w.gimbal_enabled = True
    w._gimbal_max_rate = max_rate
    w._gimbal_az_limits = az_limits
    w._gimbal_el_limits = el_limits
    w.firing_arc = {
        "azimuth_min": az_limits[0],
        "azimuth_max": az_limits[1],
        "elevation_min": el_limits[0],
        "elevation_max": el_limits[1],
    }
    return w


def _set_solution(weapon: TruthWeapon, yaw: float, pitch: float) -> None:
    """Set a fake firing solution with the given lead angle."""
    sol = FiringSolution(
        valid=True,
        target_id="target_1",
        lead_angle={"yaw": yaw, "pitch": pitch},
        in_range=True,
    )
    weapon.current_solution = sol


# ---------------------------------------------------------------------------
# Test: gimbal slews toward target over time
# ---------------------------------------------------------------------------

class TestGimbalSlew:
    """Gimbal azimuth/elevation should approach desired angle at max_rate."""

    def test_slew_from_zero_to_positive(self):
        w = _make_gimballed_railgun(max_rate=15.0)
        _set_solution(w, yaw=10.0, pitch=5.0)

        # One second at 15 deg/s should reach the target (only 10 deg away)
        w.tick(1.0, 0.0)
        assert abs(w.current_azimuth - 10.0) < 0.01
        assert abs(w.current_elevation - 5.0) < 0.01

    def test_slew_rate_limited(self):
        w = _make_gimballed_railgun(max_rate=15.0)
        _set_solution(w, yaw=20.0, pitch=0.0)

        # 0.5s at 15 deg/s = max 7.5 deg movement
        w.tick(0.5, 0.0)
        assert abs(w.current_azimuth - 7.5) < 0.01
        assert w._gimbal_error > 0.5  # Still not there

    def test_pdc_slews_fast(self):
        w = _make_gimballed_pdc(max_rate=180.0)
        _set_solution(w, yaw=45.0, pitch=-30.0)

        # 0.5s at 180 deg/s = 90 deg max, target only 45 away
        w.tick(0.5, 0.0)
        assert abs(w.current_azimuth - 45.0) < 0.01
        assert abs(w.current_elevation - (-30.0)) < 0.01

    def test_slew_converges_over_multiple_ticks(self):
        w = _make_gimballed_railgun(max_rate=15.0)
        _set_solution(w, yaw=20.0, pitch=10.0)

        # Tick many small steps
        for _ in range(100):
            w.tick(0.1, 0.0)

        assert abs(w.current_azimuth - 20.0) < 0.01
        assert abs(w.current_elevation - 10.0) < 0.01
        assert w._gimbal_error < 0.1


# ---------------------------------------------------------------------------
# Test: tracking flag based on error threshold
# ---------------------------------------------------------------------------

class TestGimbalTracking:
    """Tracking should be True only when gimbal error < threshold."""

    def test_railgun_tracking_tight_threshold(self):
        """Railgun requires < 1 deg error for tracking."""
        w = _make_gimballed_railgun(max_rate=15.0, az_limits=(-50.0, 50.0))
        # Place gimbal 2 deg away from target -- should NOT track
        w.current_azimuth = 8.0
        w.current_elevation = 0.0
        _set_solution(w, yaw=10.0, pitch=0.0)

        # Run a single tick to update gimbal error
        w.tick(0.01, 0.0)  # tiny dt, barely moves

        # Compute solution to check tracking flag
        sol = w.calculate_solution(
            shooter_pos={"x": 0, "y": 0, "z": 0},
            shooter_vel={"x": 0, "y": 0, "z": 0},
            target_pos={"x": 100000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            target_id="t1",
            sim_time=10.0,
        )
        # Gimbal hasn't reached target yet (only moved ~0.15 deg in 0.01s)
        # Error is still > 1 deg
        assert w._gimbal_error > 1.0
        assert not sol.tracking

    def test_pdc_tracking_permissive_threshold(self):
        """PDC allows up to 5 deg error for tracking."""
        w = _make_gimballed_pdc(max_rate=180.0)
        # Place gimbal 3 deg from target -- should track (< 5 threshold)
        _set_solution(w, yaw=3.0, pitch=0.0)
        # Several ticks at 180 deg/s to converge
        for _ in range(10):
            w.tick(0.1, 0.0)

        assert w._gimbal_error < 5.0  # PDC threshold

        sol = w.calculate_solution(
            shooter_pos={"x": 0, "y": 0, "z": 0},
            shooter_vel={"x": 0, "y": 0, "z": 0},
            target_pos={"x": 1000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            target_id="t1",
            sim_time=10.0,
        )
        assert sol.tracking


# ---------------------------------------------------------------------------
# Test: non-gimballed weapons unchanged
# ---------------------------------------------------------------------------

class TestNonGimballed:
    """Non-gimballed weapons should use legacy turret tracking."""

    def test_default_weapon_has_no_gimbal(self):
        w = create_railgun("rg1")
        assert not w.gimbal_enabled
        assert w._gimbal_max_rate == 0.0
        assert w.current_azimuth == 0.0
        assert w.current_elevation == 0.0

    def test_non_gimballed_uses_turret_bearing(self):
        """Non-gimballed weapon uses turret_bearing, not gimbal angles."""
        w = create_railgun("rg1")
        _set_solution(w, yaw=5.0, pitch=2.0)
        w.tick(1.0, 0.0)

        # Gimbal angles should not move
        assert w.current_azimuth == 0.0
        assert w.current_elevation == 0.0
        # Turret bearing should have moved toward target
        assert w.turret_bearing["yaw"] != 0.0


# ---------------------------------------------------------------------------
# Test: gimbal respects arc limits
# ---------------------------------------------------------------------------

class TestGimbalLimits:
    """Gimbal should clamp to azimuth/elevation arc limits."""

    def test_clamp_azimuth_positive(self):
        w = _make_gimballed_railgun(max_rate=100.0, az_limits=(-25.0, 25.0))
        _set_solution(w, yaw=50.0, pitch=0.0)

        # Fast slew rate, should reach limit in one tick
        w.tick(1.0, 0.0)
        assert w.current_azimuth <= 25.0 + 0.01

    def test_clamp_azimuth_negative(self):
        w = _make_gimballed_railgun(max_rate=100.0, az_limits=(-25.0, 25.0))
        _set_solution(w, yaw=-50.0, pitch=0.0)

        w.tick(1.0, 0.0)
        assert w.current_azimuth >= -25.0 - 0.01

    def test_clamp_elevation(self):
        w = _make_gimballed_railgun(max_rate=100.0, el_limits=(-15.0, 30.0))
        _set_solution(w, yaw=0.0, pitch=60.0)

        w.tick(1.0, 0.0)
        assert w.current_elevation <= 30.0 + 0.01

    def test_clamp_preserves_valid_position(self):
        """If target is within limits, no clamping should occur."""
        w = _make_gimballed_railgun(max_rate=100.0, az_limits=(-25.0, 25.0))
        _set_solution(w, yaw=10.0, pitch=5.0)

        w.tick(1.0, 0.0)
        assert abs(w.current_azimuth - 10.0) < 0.01
        assert abs(w.current_elevation - 5.0) < 0.01


# ---------------------------------------------------------------------------
# Test: fast-crossing target temporarily loses tracking
# ---------------------------------------------------------------------------

class TestFastCrossingTarget:
    """A target that sweeps rapidly across the gimbal arc should cause
    the weapon to lose and re-acquire tracking."""

    def test_target_sweep_loses_tracking(self):
        w = _make_gimballed_railgun(max_rate=15.0, az_limits=(-25.0, 25.0))

        # Start with gimbal on target
        _set_solution(w, yaw=0.0, pitch=0.0)
        for _ in range(10):
            w.tick(0.1, 0.0)
        assert w._gimbal_error < 1.0  # Tracking

        # Target jumps to far side -- gimbal can't keep up instantly
        _set_solution(w, yaw=20.0, pitch=0.0)
        w.tick(0.1, 0.0)  # Single tick at 15 deg/s = 1.5 deg movement

        # Should have large error -- railgun threshold is 1 deg
        assert w._gimbal_error > 1.0

    def test_target_sweep_reacquires(self):
        w = _make_gimballed_railgun(max_rate=15.0, az_limits=(-25.0, 25.0))
        _set_solution(w, yaw=0.0, pitch=0.0)
        for _ in range(10):
            w.tick(0.1, 0.0)

        # Target jumps
        _set_solution(w, yaw=10.0, pitch=0.0)

        # Give it time to catch up: 10 deg / 15 deg/s < 1 second
        for _ in range(20):
            w.tick(0.1, 0.0)

        assert w._gimbal_error < 1.0  # Re-acquired


# ---------------------------------------------------------------------------
# Test: gimbal telemetry in get_state()
# ---------------------------------------------------------------------------

class TestGimbalTelemetry:
    """get_state() should expose gimbal fields."""

    def test_gimballed_weapon_state(self):
        w = _make_gimballed_pdc()
        _set_solution(w, yaw=10.0, pitch=-5.0)
        w.tick(1.0, 0.0)

        state = w.get_state()
        assert state["gimbal_enabled"] is True
        assert "gimbal_azimuth" in state
        assert "gimbal_elevation" in state
        assert "gimbal_error" in state
        assert isinstance(state["gimbal_azimuth"], float)

    def test_non_gimballed_weapon_state(self):
        w = create_railgun("rg1")
        state = w.get_state()
        assert state["gimbal_enabled"] is False
        assert state["gimbal_azimuth"] == 0.0
        assert state["gimbal_elevation"] == 0.0
        assert state["gimbal_error"] == 0.0


# ---------------------------------------------------------------------------
# Test: Hardpoint gimbal field
# ---------------------------------------------------------------------------

class TestHardpointGimbal:
    """Hardpoint dataclass should carry the gimbal flag."""

    def test_default_no_gimbal(self):
        hp = Hardpoint(id="hp1", mount_type="turret")
        assert hp.gimbal is False

    def test_gimbal_set(self):
        hp = Hardpoint(id="hp1", mount_type="turret", gimbal=True)
        assert hp.gimbal is True


# ---------------------------------------------------------------------------
# Test: CombatSystem applies gimbal config from weapon_mounts
# ---------------------------------------------------------------------------

class TestCombatSystemGimbalConfig:
    """CombatSystem._apply_gimbal_config should transfer settings."""

    def test_apply_gimbal_config(self):
        from hybrid.systems.combat.combat_system import CombatSystem

        w = create_railgun("railgun_1")
        lookup = {
            "railgun_1": {"gimbal": True, "max_rotation_rate": 15.0}
        }
        w.firing_arc = {
            "azimuth_min": -25, "azimuth_max": 25,
            "elevation_min": -15, "elevation_max": 30,
        }
        CombatSystem._apply_gimbal_config(w, "railgun_1", lookup)

        assert w.gimbal_enabled is True
        assert w._gimbal_max_rate == 15.0
        assert w._gimbal_az_limits == (-25, 25)
        assert w._gimbal_el_limits == (-15, 30)

    def test_no_gimbal_config_leaves_weapon_unchanged(self):
        from hybrid.systems.combat.combat_system import CombatSystem

        w = create_railgun("railgun_1")
        CombatSystem._apply_gimbal_config(w, "railgun_1", {})

        assert w.gimbal_enabled is False
        assert w._gimbal_max_rate == 0.0


# ---------------------------------------------------------------------------
# Test: gimbal holds position when solution drops
# ---------------------------------------------------------------------------

class TestGimbalHoldsPosition:
    """When the firing solution becomes invalid, the gimbal should
    hold its last position rather than snapping to boresight."""

    def test_holds_on_solution_loss(self):
        w = _make_gimballed_railgun(max_rate=100.0)
        _set_solution(w, yaw=15.0, pitch=10.0)

        # Converge
        for _ in range(10):
            w.tick(0.1, 0.0)
        assert abs(w.current_azimuth - 15.0) < 0.1
        assert abs(w.current_elevation - 10.0) < 0.1

        # Drop solution
        w.current_solution = None
        w.tick(1.0, 0.0)

        # Should still be at 15, 10
        assert abs(w.current_azimuth - 15.0) < 0.1
        assert abs(w.current_elevation - 10.0) < 0.1
        # Error should be large (no valid solution)
        assert w._gimbal_error == 999.0
