"""Tests for FormationAutopilot: PD controller, dead zone, heading rotation.

Verifies that the formation autopilot:
  1. Converges to the desired offset position behind a constant-velocity flagship.
  2. Smoothly repositions when the flagship changes heading by 90 degrees.
  3. Applies the dead zone (no corrections when within tolerance).
  4. Matches the flagship heading (not pointing at the flagship).
  5. Rotates the formation offset into the flagship's heading frame.
"""

import math
import numpy as np
import pytest
from unittest.mock import MagicMock

from hybrid.navigation.autopilot.formation import (
    FormationAutopilot,
    _rotate_offset_by_heading,
)


# ---------------------------------------------------------------------------
# Mock helpers (same pattern as test_rendezvous.py)
# ---------------------------------------------------------------------------

class MockPropulsion:
    def __init__(self, max_thrust: float = 50_000.0):
        self.max_thrust = max_thrust


class SystemsDict:
    """dict-like container that supports .get() with system objects."""

    def __init__(self, mapping):
        self._d = mapping

    def get(self, key, default=None):
        return self._d.get(key, default)


class MockShip:
    """Minimal ship mock for autopilot tests."""

    def __init__(
        self,
        ship_id: str = "wing1",
        position=None,
        velocity=None,
        orientation=None,
        mass: float = 10_000.0,
        max_thrust: float = 50_000.0,
    ):
        self.id = ship_id
        self.mass = mass
        self.position = position or {"x": 0.0, "y": 0.0, "z": 0.0}
        self.velocity = velocity or {"x": 0.0, "y": 0.0, "z": 0.0}
        self.orientation = orientation or {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        self.systems = SystemsDict({"propulsion": MockPropulsion(max_thrust)})
        self._all_ships_ref = []


def _make_flagship(
    position=None, velocity=None, orientation=None, ship_id="flagship"
) -> MockShip:
    """Create a flagship mock."""
    return MockShip(
        ship_id=ship_id,
        position=position or {"x": 0.0, "y": 0.0, "z": 0.0},
        velocity=velocity or {"x": 0.0, "y": 0.0, "z": 0.0},
        orientation=orientation or {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
    )


def _make_wing(
    position=None, velocity=None, orientation=None, flagship=None
) -> MockShip:
    """Create a formation wing ship that knows about the flagship."""
    ship = MockShip(
        ship_id="wing1",
        position=position or {"x": 0.0, "y": 0.0, "z": 0.0},
        velocity=velocity or {"x": 0.0, "y": 0.0, "z": 0.0},
        orientation=orientation or {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
    )
    if flagship:
        ship._all_ships_ref = [flagship]
    return ship


def _apply_thrust_tick(ship: MockShip, cmd: dict, dt: float = 0.1) -> None:
    """Simulate one physics tick: apply thrust command and integrate position.

    This is a simplified Euler integration that approximates what the real
    physics engine does.  Thrust acts along the commanded heading, scaled
    by thrust fraction and max acceleration.
    """
    thrust = cmd.get("thrust", 0.0)
    heading = cmd.get("heading", ship.orientation)

    if thrust > 0.001:
        # Compute acceleration direction from heading
        yaw_rad = math.radians(heading.get("yaw", 0.0))
        pitch_rad = math.radians(heading.get("pitch", 0.0))

        dx = math.cos(pitch_rad) * math.cos(yaw_rad)
        dy = math.cos(pitch_rad) * math.sin(yaw_rad)
        dz = math.sin(pitch_rad)

        propulsion = ship.systems.get("propulsion")
        max_accel = propulsion.max_thrust / ship.mass if propulsion else 5.0
        accel = thrust * max_accel

        ship.velocity["x"] += dx * accel * dt
        ship.velocity["y"] += dy * accel * dt
        ship.velocity["z"] += dz * accel * dt

    # Integrate position
    ship.position["x"] += ship.velocity["x"] * dt
    ship.position["y"] += ship.velocity["y"] * dt
    ship.position["z"] += ship.velocity["z"] * dt

    # Update orientation to match commanded heading (instant rotation for tests)
    ship.orientation = dict(heading)


# ---------------------------------------------------------------------------
# Tests: offset rotation
# ---------------------------------------------------------------------------

class TestOffsetRotation:
    """Test that _rotate_offset_by_heading correctly transforms offsets."""

    def test_zero_yaw_identity(self):
        """At yaw=0, local frame == world frame."""
        offset = np.array([100.0, 200.0, 0.0])
        heading = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}
        result = _rotate_offset_by_heading(offset, heading)
        np.testing.assert_allclose(result, [100.0, 200.0, 0.0], atol=1e-6)

    def test_90_degree_yaw(self):
        """At yaw=90, +X local (forward) maps to +Y world."""
        offset = np.array([100.0, 0.0, 0.0])  # 100m forward
        heading = {"yaw": 90.0, "pitch": 0.0}
        result = _rotate_offset_by_heading(offset, heading)
        np.testing.assert_allclose(result, [0.0, 100.0, 0.0], atol=1e-6)

    def test_90_degree_yaw_port(self):
        """At yaw=90, +Y local (port) maps to -X world."""
        offset = np.array([0.0, 100.0, 0.0])  # 100m to port
        heading = {"yaw": 90.0, "pitch": 0.0}
        result = _rotate_offset_by_heading(offset, heading)
        np.testing.assert_allclose(result, [-100.0, 0.0, 0.0], atol=1e-6)

    def test_180_degree_yaw(self):
        """At yaw=180, forward maps to -X world."""
        offset = np.array([100.0, 0.0, 0.0])
        heading = {"yaw": 180.0, "pitch": 0.0}
        result = _rotate_offset_by_heading(offset, heading)
        np.testing.assert_allclose(result, [-100.0, 0.0, 0.0], atol=1e-6)

    def test_45_degree_yaw(self):
        """At yaw=45, 100m forward maps to (70.7, 70.7, 0)."""
        offset = np.array([100.0, 0.0, 0.0])
        heading = {"yaw": 45.0, "pitch": 0.0}
        result = _rotate_offset_by_heading(offset, heading)
        expected = np.array([100.0 * math.cos(math.radians(45)),
                             100.0 * math.sin(math.radians(45)),
                             0.0])
        np.testing.assert_allclose(result, expected, atol=1e-6)


# ---------------------------------------------------------------------------
# Tests: dead zone
# ---------------------------------------------------------------------------

class TestDeadZone:
    """The controller should produce zero thrust when inside the dead zone."""

    def test_in_formation_zero_thrust(self):
        """Ship within 50m and <0.5 m/s relative -> zero thrust."""
        flagship = _make_flagship(
            position={"x": 1000.0, "y": 0.0, "z": 0.0},
            velocity={"x": 100.0, "y": 0.0, "z": 0.0},
        )
        # Wing is at the exact offset position, matching velocity
        wing = _make_wing(
            position={"x": 800.0, "y": 0.0, "z": 0.0},
            velocity={"x": 100.0, "y": 0.0, "z": 0.0},
            flagship=flagship,
        )
        ap = FormationAutopilot(
            wing,
            target_id="flagship",
            params={"formation_position": [-200.0, 0.0, 0.0]},
        )
        cmd = ap.compute(dt=0.1, sim_time=0.0)
        assert cmd is not None
        assert cmd["thrust"] == 0.0
        assert ap.status == "in_formation"

    def test_just_outside_deadzone_applies_thrust(self):
        """Ship at 60m error should get a correction."""
        flagship = _make_flagship(
            position={"x": 1000.0, "y": 0.0, "z": 0.0},
            velocity={"x": 100.0, "y": 0.0, "z": 0.0},
        )
        wing = _make_wing(
            position={"x": 740.0, "y": 0.0, "z": 0.0},  # 60m behind desired
            velocity={"x": 100.0, "y": 0.0, "z": 0.0},
            flagship=flagship,
        )
        ap = FormationAutopilot(
            wing,
            target_id="flagship",
            params={"formation_position": [-200.0, 0.0, 0.0]},
        )
        cmd = ap.compute(dt=0.1, sim_time=0.0)
        assert cmd is not None
        assert cmd["thrust"] > 0.0, "Should apply correction outside dead zone"


# ---------------------------------------------------------------------------
# Tests: heading matching
# ---------------------------------------------------------------------------

class TestHeadingMatching:
    """Formation member should match flagship heading."""

    def test_matches_flagship_heading_in_formation(self):
        """When in dead zone, heading should match flagship.

        With flagship at yaw=45, the offset [-200, 0, 0] in local frame
        rotates to world-space (-141.4, -141.4, 0).  Place the wing
        there so it is inside the dead zone.
        """
        flagship = _make_flagship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            orientation={"yaw": 45.0, "pitch": 0.0, "roll": 0.0},
        )
        # Rotated offset for [-200, 0, 0] at yaw=45:
        cos45 = math.cos(math.radians(45.0))
        sin45 = math.sin(math.radians(45.0))
        wx = -200.0 * cos45  # ~ -141.4
        wy = -200.0 * sin45  # ~ -141.4
        wing = _make_wing(
            position={"x": wx, "y": wy, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            flagship=flagship,
        )
        ap = FormationAutopilot(
            wing,
            target_id="flagship",
            params={"formation_position": [-200.0, 0.0, 0.0]},
        )
        cmd = ap.compute(dt=0.1, sim_time=0.0)
        assert cmd is not None
        assert cmd["heading"]["yaw"] == pytest.approx(45.0)
        assert cmd["heading"]["pitch"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Tests: convergence with constant-velocity flagship
# ---------------------------------------------------------------------------

class TestConstantVelocityConvergence:
    """Wing ship should converge to formation position behind a moving flagship."""

    def test_converges_within_n_ticks(self):
        """Starting 500m off-position, should reach <50m error within 2000 ticks.

        Flagship moves at constant 100 m/s along +X.
        Wing starts 500m behind the desired position.
        """
        flagship = _make_flagship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 100.0, "y": 0.0, "z": 0.0},
        )
        # Desired position = flagship + offset (-200, 0, 0) = (-200, 0, 0)
        # Wing starts 500m further back at (-700, 0, 0)
        wing = _make_wing(
            position={"x": -700.0, "y": 0.0, "z": 0.0},
            velocity={"x": 100.0, "y": 0.0, "z": 0.0},  # matching velocity
            flagship=flagship,
        )

        ap = FormationAutopilot(
            wing,
            target_id="flagship",
            params={"formation_position": [-200.0, 0.0, 0.0]},
        )

        dt = 0.1
        max_ticks = 2000
        errors = []

        for tick in range(max_ticks):
            sim_time = tick * dt
            # Move flagship
            flagship.position["x"] += flagship.velocity["x"] * dt

            cmd = ap.compute(dt=dt, sim_time=sim_time)
            assert cmd is not None, f"Autopilot returned None at tick {tick}"
            _apply_thrust_tick(wing, cmd, dt)

            # Compute actual error
            desired_x = flagship.position["x"] - 200.0
            error = math.sqrt(
                (wing.position["x"] - desired_x) ** 2
                + wing.position["y"] ** 2
                + wing.position["z"] ** 2
            )
            errors.append(error)

        final_error = errors[-1]
        assert final_error < 50.0, (
            f"Formation did not converge: final error = {final_error:.1f}m "
            f"(min was {min(errors):.1f}m at tick {errors.index(min(errors))})"
        )

        # Also check relative velocity is small
        rel_vx = wing.velocity["x"] - flagship.velocity["x"]
        rel_vy = wing.velocity["y"] - flagship.velocity["y"]
        rel_vz = wing.velocity["z"] - flagship.velocity["z"]
        rel_speed = math.sqrt(rel_vx**2 + rel_vy**2 + rel_vz**2)
        assert rel_speed < 1.0, (
            f"Relative velocity too high: {rel_speed:.2f} m/s"
        )


# ---------------------------------------------------------------------------
# Tests: flagship heading change (repositioning)
# ---------------------------------------------------------------------------

class TestHeadingChangeReposition:
    """When flagship turns 90 degrees, the formation should reposition smoothly.

    The key test: position error should decrease monotonically after an
    initial transient, proving the PD controller does not oscillate.
    """

    def test_smooth_reposition_on_heading_change(self):
        """Flagship turns 90 degrees; wing repositions without oscillation.

        Setup:
          - Flagship at origin, stationary, heading yaw=0.
          - Wing at offset [-200, 0, 0] (200m behind).
          - At tick 0, flagship heading changes to yaw=90.
          - New desired position: offset rotated 90 degrees -> [0, -200, 0].
          - Wing must reposition from (-200, 0, 0) to (0, -200, 0).

        Acceptance:
          - Final error < 50m within 3000 ticks.
          - After the initial transient (first 200 ticks), the error trend
            should be generally decreasing (we allow some noise but no
            sustained oscillation).
        """
        flagship = _make_flagship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            orientation={"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
        )
        wing = _make_wing(
            position={"x": -200.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            flagship=flagship,
        )

        ap = FormationAutopilot(
            wing,
            target_id="flagship",
            params={"formation_position": [-200.0, 0.0, 0.0]},
        )

        # Change flagship heading to 90 degrees
        flagship.orientation = {"yaw": 90.0, "pitch": 0.0, "roll": 0.0}

        dt = 0.1
        max_ticks = 3000
        errors = []

        for tick in range(max_ticks):
            sim_time = tick * dt
            cmd = ap.compute(dt=dt, sim_time=sim_time)
            assert cmd is not None
            _apply_thrust_tick(wing, cmd, dt)

            # Desired position with rotated offset
            # At yaw=90, [-200, 0, 0] in local becomes [0, -200, 0] in world
            desired = np.array([0.0, -200.0, 0.0])
            pos = np.array([
                wing.position["x"],
                wing.position["y"],
                wing.position["z"],
            ])
            error = float(np.linalg.norm(pos - desired))
            errors.append(error)

        final_error = errors[-1]
        assert final_error < 50.0, (
            f"Reposition did not converge: final error = {final_error:.1f}m "
            f"(min was {min(errors):.1f}m)"
        )

        # Check no sustained oscillation after the transient.
        # We look at the error from tick 500 onward and verify it generally
        # decreases.  We use a sliding window: the average error in the
        # second half should be less than the average in the first half.
        late_errors = errors[500:]
        if len(late_errors) > 100:
            mid = len(late_errors) // 2
            first_half_avg = sum(late_errors[:mid]) / mid
            second_half_avg = sum(late_errors[mid:]) / (len(late_errors) - mid)
            assert second_half_avg <= first_half_avg + 5.0, (
                f"Oscillation detected: first-half avg={first_half_avg:.1f}m, "
                f"second-half avg={second_half_avg:.1f}m"
            )


# ---------------------------------------------------------------------------
# Tests: flagship not found
# ---------------------------------------------------------------------------

class TestFlagshipNotFound:
    """When flagship is not available, autopilot should return None."""

    def test_returns_none_when_no_flagship(self):
        wing = _make_wing()  # No flagship in _all_ships_ref
        ap = FormationAutopilot(
            wing,
            target_id="flagship",
            params={"formation_position": [-200.0, 0.0, 0.0]},
        )
        cmd = ap.compute(dt=0.1, sim_time=0.0)
        assert cmd is None
        assert ap.status == "no_flagship"


# ---------------------------------------------------------------------------
# Tests: get_state telemetry
# ---------------------------------------------------------------------------

class TestGetState:
    """Verify telemetry state includes expected fields."""

    def test_state_contains_formation_fields(self):
        flagship = _make_flagship(
            position={"x": 500.0, "y": 0.0, "z": 0.0},
            velocity={"x": 50.0, "y": 0.0, "z": 0.0},
        )
        wing = _make_wing(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 40.0, "y": 0.0, "z": 0.0},
            flagship=flagship,
        )
        ap = FormationAutopilot(
            wing,
            target_id="flagship",
            params={"formation_position": [-200.0, 0.0, 0.0]},
        )
        # Run one tick to populate target_position/target_velocity
        ap.compute(dt=0.1, sim_time=0.0)

        state = ap.get_state()
        assert "flagship_id" in state
        assert state["flagship_id"] == "flagship"
        assert "formation_position" in state
        assert "tolerance" in state
        assert "position_error" in state
        assert state["position_error"] is not None
        assert "velocity_error" in state
        assert state["velocity_error"] is not None
