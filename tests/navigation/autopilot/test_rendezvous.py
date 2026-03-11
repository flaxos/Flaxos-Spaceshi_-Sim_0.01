"""Tests for RendezvousAutopilot: nav profiles, flip/brake math, phase transitions."""

import pytest
import math
from unittest.mock import MagicMock
from hybrid.navigation.autopilot.rendezvous import RendezvousAutopilot, NAV_PROFILES


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

class MockPropulsion:
    def __init__(self, max_thrust=50000.0):
        self.max_thrust = max_thrust


class MockRCS:
    """RCS stub with controllable estimate_rotation_time."""

    def __init__(self, flip_time=10.0):
        self._flip_time = flip_time

    def estimate_rotation_time(self, angle_degrees: float, ship) -> float:
        return self._flip_time


class SystemsDict:
    """dict-like container that supports .get() with system objects as values."""

    def __init__(self, mapping):
        self._d = mapping

    def get(self, key, default=None):
        return self._d.get(key, default)

    def __getitem__(self, key):
        return self._d[key]

    def __setitem__(self, key, value):
        self._d[key] = value


class MockShip:
    def __init__(
        self,
        position=None,
        velocity=None,
        orientation=None,
        mass=10000.0,
        moment_of_inertia=None,
        max_thrust=50000.0,
        rcs_flip_time=10.0,
        target=None,
    ):
        self.id = "player_ship"
        self.mass = mass
        self.moment_of_inertia = moment_of_inertia or (mass * 10.0)
        self.position = position or {"x": 0.0, "y": 0.0, "z": 0.0}
        self.velocity = velocity or {"x": 0.0, "y": 0.0, "z": 0.0}
        self.orientation = orientation or {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        self.angular_velocity = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}

        propulsion = MockPropulsion(max_thrust)
        rcs = MockRCS(rcs_flip_time)

        sensors = MagicMock()
        sensors.get_contact = MagicMock(return_value=target)

        self.systems = SystemsDict({
            "propulsion": propulsion,
            "rcs": rcs,
            "sensors": sensors,
        })
        self._all_ships_ref = []


def _make_ship(**kwargs):
    return MockShip(**kwargs)


def _make_target(position, velocity=None):
    t = MagicMock()
    t.position = position
    t.velocity = velocity or {"x": 0.0, "y": 0.0, "z": 0.0}
    return t


# ---------------------------------------------------------------------------
# Profile initialisation tests
# ---------------------------------------------------------------------------

class TestProfileDefaults:
    def test_profile_defaults_to_balanced(self):
        """No profile param → balanced profile values."""
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(target=target)
        ap = RendezvousAutopilot(ship, target_id="T001")

        assert ap.profile_name == "balanced"
        assert ap.max_thrust == pytest.approx(0.8)
        assert ap.brake_margin == pytest.approx(1.3)
        assert ap.flip_safety_factor == pytest.approx(1.5)

    def test_profile_aggressive(self):
        """Aggressive profile sets full thrust and minimal margin."""
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(target=target)
        ap = RendezvousAutopilot(ship, target_id="T001",
                                 params={"profile": "aggressive"})

        assert ap.profile_name == "aggressive"
        assert ap.max_thrust == pytest.approx(1.0)
        assert ap.brake_margin == pytest.approx(1.1)
        assert ap.flip_safety_factor == pytest.approx(1.0)

    def test_profile_conservative(self):
        """Conservative profile sets half thrust and generous margin."""
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(target=target)
        ap = RendezvousAutopilot(ship, target_id="T001",
                                 params={"profile": "conservative"})

        assert ap.profile_name == "conservative"
        assert ap.max_thrust == pytest.approx(0.5)
        assert ap.brake_margin == pytest.approx(1.6)
        assert ap.flip_safety_factor == pytest.approx(2.0)

    def test_explicit_param_overrides_profile(self):
        """Individual param beats the profile default."""
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(target=target)
        ap = RendezvousAutopilot(
            ship,
            target_id="T001",
            params={"profile": "aggressive", "max_thrust": 0.3},
        )

        assert ap.profile_name == "aggressive"
        # The explicit max_thrust=0.3 must win over profile's 1.0
        assert ap.max_thrust == pytest.approx(0.3)

    def test_unknown_profile_falls_back_to_balanced(self):
        """An unrecognised profile name silently uses balanced values."""
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(target=target)
        ap = RendezvousAutopilot(ship, target_id="T001",
                                 params={"profile": "ludicrous_speed"})

        # profile_name is stored as given, but values come from balanced
        assert ap.max_thrust == pytest.approx(NAV_PROFILES["balanced"]["max_thrust"])


# ---------------------------------------------------------------------------
# Braking distance / flip time accounting
# ---------------------------------------------------------------------------

class TestBrakingDistanceFlipTime:
    """The corrected braking trigger distance must exceed the naive v²/2a
    point so the ship starts flipping early enough to avoid overshoot."""

    def test_braking_trigger_larger_than_naive_kinematic(self):
        """d_trigger > v²/2a for any positive closing speed."""
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            target=target,
            mass=10000.0,
            max_thrust=50000.0,
            rcs_flip_time=10.0,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")

        # Max accel = 50000 / 10000 = 5 m/s²
        a_max = ap._get_max_accel()
        closing_speed = 500.0  # m/s

        naive_d = (closing_speed ** 2) / (2.0 * a_max)
        corrected_d = ap._corrected_braking_distance(closing_speed, a_max)

        assert corrected_d > naive_d, (
            f"Corrected distance {corrected_d:.1f} m must exceed "
            f"naive {naive_d:.1f} m at {closing_speed} m/s"
        )

    def test_braking_trigger_includes_flip_coast_distance(self):
        """The extra distance accounts for coasting during flip."""
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        flip_time = 15.0
        ship = _make_ship(
            target=target,
            mass=10000.0,
            max_thrust=50000.0,
            rcs_flip_time=flip_time,
        )
        ap = RendezvousAutopilot(ship, target_id="T001",
                                 params={"profile": "balanced"})

        closing_speed = 200.0
        a_max = ap._get_max_accel()

        d_brake = ap._braking_distance(closing_speed, a_max)
        flip_coast = closing_speed * flip_time * ap.flip_safety_factor
        expected = d_brake * ap.brake_margin + flip_coast

        actual = ap._corrected_braking_distance(closing_speed, a_max)

        assert actual == pytest.approx(expected, rel=1e-6)

    def test_higher_flip_time_gives_larger_trigger(self):
        """Slower RCS (longer flip) must produce a larger safety margin."""
        target = _make_target({"x": 500000.0, "y": 0.0, "z": 0.0})
        closing_speed = 300.0
        a_max_val = 5.0

        ship_fast_rcs = _make_ship(target=target, rcs_flip_time=5.0)
        ship_slow_rcs = _make_ship(target=target, rcs_flip_time=30.0)

        ap_fast = RendezvousAutopilot(ship_fast_rcs, target_id="T001")
        ap_slow = RendezvousAutopilot(ship_slow_rcs, target_id="T001")

        d_fast = ap_fast._corrected_braking_distance(closing_speed, a_max_val)
        d_slow = ap_slow._corrected_braking_distance(closing_speed, a_max_val)

        assert d_slow > d_fast, (
            "Slower RCS should require a larger braking trigger distance"
        )


# ---------------------------------------------------------------------------
# Phase transitions
# ---------------------------------------------------------------------------

class TestPhaseTransitions:
    def test_initial_phase_is_burn(self):
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(target=target)
        ap = RendezvousAutopilot(ship, target_id="T001")
        assert ap.phase == "burn"

    def test_burn_to_flip_when_inside_trigger(self):
        """Ship in burn phase transitions to flip when range <= d_trigger.

        Ship at origin, target at x=1000 m, ship velocity x=200 m/s
        (closing at 200 m/s). With a_max=5 m/s² and flip_time=10 s:
            naive d_brake = 200²/(2*5) = 4000 m
            flip_coast = 200 * 10 * 1.5 = 3000 m   (balanced flip_safety=1.5)
            corrected = 4000*1.3 + 3000 = 8200 m    (balanced brake_margin=1.3)
        range = 1000 m < 8200 m → trigger fires immediately.
        """
        target = _make_target({"x": 1000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 200.0, "y": 0.0, "z": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "burn"

        ap.compute(0.1, 0.0)

        assert ap.phase == "flip", (
            f"Expected flip phase, got {ap.phase!r}"
        )

    def test_flip_to_brake_when_retrograde_aligned(self):
        """Ship flips to brake when heading is within FLIP_TOLERANCE_DEG of retrograde.

        Ship approaching target along +X at 50 m/s. Target velocity = 0.
        rel_vel = target_vel - ship_vel = {-50, 0, 0}.
        Retrograde heading points along +rel_vel i.e. along {-50,0,0}.
        vector_to_heading({-50,0,0}) gives yaw ≈ 180°.
        We set ship orientation to yaw=178° (within 10° tolerance).
        """
        target = _make_target({"x": 5000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 50.0, "y": 0.0, "z": 0.0},
            orientation={"pitch": 0.0, "yaw": 178.0, "roll": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "flip"

        ap.compute(0.1, 0.0)

        assert ap.phase == "brake", (
            f"Expected brake phase after retrograde alignment, got {ap.phase!r}"
        )

    def test_brake_to_burn_when_closing_speed_lost(self):
        """Brake phase re-enters burn if closing speed drops to zero outside stationkeep range."""
        target = _make_target({"x": 50000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},  # no relative velocity
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "brake"

        # range=50 km, closing_speed=0 → overshoot recovery to burn
        ap.compute(0.1, 0.0)

        assert ap.phase == "burn", (
            f"Expected overshoot recovery to burn, got {ap.phase!r}"
        )

    def test_stationkeep_entered_within_range_and_speed(self):
        """Within stationkeep_range and below stationkeep_speed → stationkeep phase."""
        target = _make_target({"x": 50.0, "y": 0.0, "z": 0.0})  # 50 m away
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},  # relative speed ≈ 0
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")

        ap.compute(0.1, 0.0)

        assert ap.phase == "stationkeep"
        assert ap.status == "stationkeeping"


# ---------------------------------------------------------------------------
# get_state telemetry
# ---------------------------------------------------------------------------

class TestGetState:
    def test_get_state_includes_profile_and_phase(self):
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(target=target)
        ap = RendezvousAutopilot(ship, target_id="T001",
                                 params={"profile": "conservative"})

        state = ap.get_state()

        assert state["profile"] == "conservative"
        assert state["phase"] == "burn"

    def test_get_state_includes_flip_time_estimate(self):
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(target=target, rcs_flip_time=12.5)
        ap = RendezvousAutopilot(ship, target_id="T001")

        state = ap.get_state()

        assert "flip_time_estimate" in state
        assert state["flip_time_estimate"] == pytest.approx(12.5)

    def test_get_state_includes_braking_distance(self):
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 100.0, "y": 0.0, "z": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")

        state = ap.get_state()

        assert "braking_distance" in state
        assert state["braking_distance"] >= 0.0

    def test_get_state_without_target_has_status_text(self):
        """get_state gracefully handles missing target."""
        ship = _make_ship()  # sensors return None (no target)
        ap = RendezvousAutopilot(ship, target_id="MISSING")

        state = ap.get_state()

        assert "status_text" in state
        # Either the status_text mentions "lost" or the autopilot status is error
        assert ("lost" in state["status_text"].lower()
                or "error" in state.get("status", ""))


# ---------------------------------------------------------------------------
# Error state
# ---------------------------------------------------------------------------

class TestErrorState:
    def test_no_target_id_sets_error_status(self):
        ship = _make_ship()
        ap = RendezvousAutopilot(ship, target_id=None)
        assert ap.status == "error"
        assert ap.error_message is not None

    def test_compute_returns_none_on_error(self):
        ship = _make_ship()  # sensors return None for any contact
        ap = RendezvousAutopilot(ship, target_id="GHOST")
        result = ap.compute(0.1, 0.0)
        assert result is None
