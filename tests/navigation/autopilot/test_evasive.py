"""Tests for the EvasiveAutopilot."""

import pytest
from hybrid.ship import Ship
from hybrid.navigation.autopilot.evasive import EvasiveAutopilot


def _make_ship() -> Ship:
    """Create a minimal ship for evasive testing."""
    config = {
        "mass": 10000.0,
        "systems": {
            "propulsion": {"max_thrust": 50000.0},
            "navigation": {},
            "helm": {},
            "rcs": {},
        },
    }
    ship = Ship("evasive-test", config)
    nav = ship.systems.get("navigation")
    if nav and nav.controller is None:
        nav.tick(0.1, ship, ship.event_bus)
    return ship


class TestEvasiveInit:
    """Initialization tests."""

    def test_initializes(self):
        ship = _make_ship()
        ap = EvasiveAutopilot(ship, params={})
        assert ap.status == "active"
        assert ap.completed is False
        assert ap._jink_count == 0

    def test_default_intervals(self):
        ship = _make_ship()
        ap = EvasiveAutopilot(ship, params={})
        assert ap.min_interval == 2.0
        assert ap.max_interval == 5.0

    def test_custom_intervals(self):
        ship = _make_ship()
        ap = EvasiveAutopilot(ship, params={
            "min_interval": 1.0,
            "max_interval": 3.0,
        })
        assert ap.min_interval == 1.0
        assert ap.max_interval == 3.0

    def test_duration_none_for_indefinite(self):
        ship = _make_ship()
        ap = EvasiveAutopilot(ship, params={})
        assert ap.duration is None

    def test_duration_zero_treated_as_indefinite(self):
        ship = _make_ship()
        ap = EvasiveAutopilot(ship, params={"duration": 0})
        assert ap.duration is None


class TestEvasiveDirectionChanges:
    """Test that direction changes within specified interval range."""

    def test_first_compute_picks_jink(self):
        ship = _make_ship()
        ap = EvasiveAutopilot(ship, params={"seed": 42})
        result = ap.compute(0.1, 0.0)
        assert result is not None
        assert ap._jink_count == 1

    def test_changes_direction_after_interval(self):
        ship = _make_ship()
        ap = EvasiveAutopilot(ship, params={
            "seed": 42,
            "min_interval": 1.0,
            "max_interval": 2.0,
        })
        # First compute at t=0
        ap.compute(0.1, 0.0)
        first_heading = dict(ap._current_heading)
        jinks_at_start = ap._jink_count

        # Advance past max_interval to guarantee a new jink
        ap.compute(0.1, 3.0)
        assert ap._jink_count > jinks_at_start
        # Heading should have changed (very unlikely to be identical with RNG)
        heading_changed = (
            ap._current_heading["yaw"] != first_heading["yaw"]
            or ap._current_heading["pitch"] != first_heading["pitch"]
        )
        assert heading_changed

    def test_no_change_within_interval(self):
        ship = _make_ship()
        ap = EvasiveAutopilot(ship, params={
            "seed": 42,
            "min_interval": 5.0,
            "max_interval": 10.0,
        })
        ap.compute(0.1, 0.0)
        count_after_first = ap._jink_count
        # Advance only 1 second -- well within min_interval
        ap.compute(0.1, 1.0)
        assert ap._jink_count == count_after_first


class TestEvasiveThrust:
    """Test that thrust varies between min and max bounds."""

    def test_thrust_within_bounds(self):
        ship = _make_ship()
        ap = EvasiveAutopilot(ship, params={
            "seed": 42,
            "min_thrust": 0.3,
            "max_thrust": 0.9,
        })
        result = ap.compute(0.1, 0.0)
        assert 0.0 <= result["thrust"] <= 1.0
        # The internal thrust should be within the configured range
        assert ap.min_thrust <= ap._current_thrust <= ap.max_thrust

    def test_thrust_varies_across_jinks(self):
        ship = _make_ship()
        ap = EvasiveAutopilot(ship, params={
            "seed": 42,
            "min_interval": 0.5,
            "max_interval": 1.0,
            "min_thrust": 0.2,
            "max_thrust": 1.0,
        })
        thrusts = []
        t = 0.0
        for _ in range(20):
            ap.compute(0.1, t)
            thrusts.append(ap._current_thrust)
            t += 1.5  # jump past max_interval to force new jink
        # With 20 jinks, we should see variation
        unique_thrusts = set(round(t, 4) for t in thrusts)
        assert len(unique_thrusts) > 1


class TestEvasiveDuration:
    """Test duration-based completion."""

    def test_completes_after_duration(self):
        ship = _make_ship()
        ap = EvasiveAutopilot(ship, params={
            "duration": 10.0,
            "seed": 42,
        })
        # Start
        ap.compute(0.1, 0.0)
        assert not ap.completed
        # After duration
        result = ap.compute(0.1, 11.0)
        assert ap.completed is True
        assert ap.status == "complete"
        assert result["thrust"] == 0.0

    def test_indefinite_does_not_complete(self):
        ship = _make_ship()
        ap = EvasiveAutopilot(ship, params={"seed": 42})
        ap.compute(0.1, 0.0)
        ap.compute(0.1, 1000.0)
        assert ap.completed is False


class TestEvasiveState:
    """Test get_state output."""

    def test_get_state_fields(self):
        ship = _make_ship()
        ap = EvasiveAutopilot(ship, params={"seed": 42})
        ap.compute(0.1, 0.0)
        state = ap.get_state()
        assert "phase" in state
        assert "jink_count" in state
        assert "duration" in state
        assert "complete" in state
        assert state["jink_count"] == 1
