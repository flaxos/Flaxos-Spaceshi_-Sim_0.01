"""Tests for GoToPositionAutopilot nav solution profiles."""

import pytest
from unittest.mock import MagicMock
from hybrid.navigation.autopilot.goto_position import GoToPositionAutopilot, GOTO_PROFILES


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class MockPropulsion:
    def __init__(self, max_thrust=50000.0):
        self.max_thrust = max_thrust


class SystemsDict:
    """dict-like container with proper .get() for system objects."""

    def __init__(self, mapping):
        self._d = mapping

    def get(self, key, default=None):
        return self._d.get(key, default)

    def __getitem__(self, key):
        return self._d[key]

    def __setitem__(self, key, value):
        self._d[key] = value


class MockShip:
    def __init__(self, position=None, velocity=None, orientation=None,
                 mass=10000.0, max_thrust=50000.0):
        self.id = "goto_test_ship"
        self.mass = mass
        self.moment_of_inertia = mass * 10.0
        self.position = position or {"x": 0.0, "y": 0.0, "z": 0.0}
        self.velocity = velocity or {"x": 0.0, "y": 0.0, "z": 0.0}
        self.orientation = orientation or {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}

        propulsion = MockPropulsion(max_thrust)
        self.systems = SystemsDict({"propulsion": propulsion})
        self._all_ships_ref = []


def _ap_with_destination(profile=None, extra_params=None, **ship_kwargs):
    """Return a GoToPositionAutopilot heading to x=1_000_000 m."""
    ship = MockShip(**ship_kwargs)
    params = {"destination": {"x": 1_000_000.0, "y": 0.0, "z": 0.0}}
    if profile:
        params["profile"] = profile
    if extra_params:
        params.update(extra_params)
    return GoToPositionAutopilot(ship, params=params)


# ---------------------------------------------------------------------------
# Profile defaults
# ---------------------------------------------------------------------------

class TestGotoProfileDefaults:
    def test_defaults_to_balanced(self):
        """No profile arg → balanced values."""
        ap = _ap_with_destination()
        assert ap.profile_name == "balanced"
        assert ap.max_thrust == pytest.approx(GOTO_PROFILES["balanced"]["max_thrust"])

    def test_balanced_brake_buffer_derived_from_profile(self):
        """brake_buffer = tolerance * brake_buffer_factor when not explicit."""
        ap = _ap_with_destination(profile="balanced")
        tolerance = ap.tolerance
        expected = tolerance * GOTO_PROFILES["balanced"]["brake_buffer_factor"]
        assert ap.brake_buffer == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Aggressive profile
# ---------------------------------------------------------------------------

class TestGotoAggressiveProfile:
    def test_aggressive_max_thrust_is_full(self):
        ap = _ap_with_destination(profile="aggressive")
        assert ap.profile_name == "aggressive"
        assert ap.max_thrust == pytest.approx(1.0)

    def test_aggressive_smallest_brake_buffer(self):
        """Aggressive has the smallest brake_buffer_factor among all profiles."""
        aggressive_factor = GOTO_PROFILES["aggressive"]["brake_buffer_factor"]
        for other_name, other_profile in GOTO_PROFILES.items():
            if other_name != "aggressive":
                assert aggressive_factor < other_profile["brake_buffer_factor"], (
                    f"Aggressive brake_buffer_factor should be < {other_name}'s"
                )

    def test_aggressive_compute_returns_full_thrust_while_accelerating(self):
        """Aggressive profile burns at full thrust when far from destination."""
        ap = _ap_with_destination(profile="aggressive")
        result = ap.compute(0.1, 0.0)
        assert result is not None
        assert result["thrust"] == pytest.approx(1.0)

    def test_explicit_max_thrust_overrides_aggressive(self):
        """Explicit max_thrust param beats the aggressive profile default."""
        ap = _ap_with_destination(profile="aggressive",
                                  extra_params={"max_thrust": 0.4})
        assert ap.max_thrust == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# Conservative profile
# ---------------------------------------------------------------------------

class TestGotoConservativeProfile:
    def test_conservative_half_thrust(self):
        ap = _ap_with_destination(profile="conservative")
        assert ap.profile_name == "conservative"
        assert ap.max_thrust == pytest.approx(0.5)

    def test_conservative_largest_brake_buffer(self):
        """Conservative has the largest brake_buffer_factor."""
        conservative_factor = GOTO_PROFILES["conservative"]["brake_buffer_factor"]
        for other_name, other_profile in GOTO_PROFILES.items():
            if other_name != "conservative":
                assert conservative_factor > other_profile["brake_buffer_factor"], (
                    f"Conservative brake_buffer_factor should be > {other_name}'s"
                )

    def test_conservative_brake_buffer_exceeds_balanced(self):
        """Conservative brake buffer is strictly larger than balanced."""
        cons = _ap_with_destination(profile="conservative")
        bal = _ap_with_destination(profile="balanced")
        assert cons.brake_buffer > bal.brake_buffer

    def test_conservative_compute_uses_half_thrust(self):
        """Conservative profile accelerates at half thrust."""
        ap = _ap_with_destination(profile="conservative")
        result = ap.compute(0.1, 0.0)
        assert result is not None
        assert result["thrust"] == pytest.approx(0.5)

    def test_explicit_brake_buffer_overrides_profile(self):
        """An explicit brake_buffer param overrides profile-derived value."""
        explicit_buffer = 999.0
        ap = _ap_with_destination(profile="conservative",
                                  extra_params={"brake_buffer": explicit_buffer})
        assert ap.brake_buffer == pytest.approx(explicit_buffer)


# ---------------------------------------------------------------------------
# Profile ordering sanity checks
# ---------------------------------------------------------------------------

class TestGotoProfileOrdering:
    """Verify the profiles have a consistent risk/speed/precision hierarchy."""

    def test_thrust_ordering_aggressive_gt_balanced_gt_conservative(self):
        agg = GOTO_PROFILES["aggressive"]["max_thrust"]
        bal = GOTO_PROFILES["balanced"]["max_thrust"]
        con = GOTO_PROFILES["conservative"]["max_thrust"]
        assert agg > bal > con

    def test_brake_buffer_factor_ordering_conservative_gt_balanced_gt_aggressive(self):
        agg = GOTO_PROFILES["aggressive"]["brake_buffer_factor"]
        bal = GOTO_PROFILES["balanced"]["brake_buffer_factor"]
        con = GOTO_PROFILES["conservative"]["brake_buffer_factor"]
        assert con > bal > agg


# ---------------------------------------------------------------------------
# get_state includes profile
# ---------------------------------------------------------------------------

class TestGotoGetState:
    def test_get_state_includes_profile(self):
        ap = _ap_with_destination(profile="conservative")
        state = ap.get_state()
        assert "profile" in state
        assert state["profile"] == "conservative"

    def test_get_state_includes_phase(self):
        ap = _ap_with_destination()
        state = ap.get_state()
        assert "phase" in state

    def test_get_state_includes_braking_distance(self):
        ap = _ap_with_destination()
        state = ap.get_state()
        assert "braking_distance" in state


# ---------------------------------------------------------------------------
# Error / edge cases
# ---------------------------------------------------------------------------

class TestGotoEdgeCases:
    def test_no_destination_sets_error(self):
        ship = MockShip()
        ap = GoToPositionAutopilot(ship, params={})  # no destination
        assert ap.status == "error"

    def test_compute_returns_none_on_error(self):
        ship = MockShip()
        ap = GoToPositionAutopilot(ship, params={})
        result = ap.compute(0.1, 0.0)
        assert result is None

    def test_ship_within_tolerance_and_stopped_holds(self):
        """Ship already at destination and stopped → HOLD phase."""
        ship = MockShip(
            position={"x": 999990.0, "y": 0.0, "z": 0.0},  # within 50 m tolerance
            velocity={"x": 0.1, "y": 0.0, "z": 0.0},  # near-zero speed
        )
        ap = GoToPositionAutopilot(ship, params={
            "destination": {"x": 1_000_000.0, "y": 0.0, "z": 0.0},
            "tolerance": 50.0,
            "arrival_speed_tolerance": 0.5,
        })
        result = ap.compute(0.1, 0.0)
        assert ap.phase == GoToPositionAutopilot.PHASE_HOLD
        assert result["thrust"] == pytest.approx(0.0)
