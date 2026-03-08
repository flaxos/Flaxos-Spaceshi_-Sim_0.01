"""Tests for the flight computer system."""

import pytest
from hybrid.ship import Ship
from hybrid.systems.flight_computer.system import FlightComputer
from hybrid.systems.flight_computer.models import FlightComputerStatus


def _make_ship(ship_id: str = "test-ship", **overrides) -> Ship:
    """Create a minimal ship with navigation and propulsion for testing."""
    config = {
        "name": ship_id, "mass": 10000.0,
        "systems": {
            "propulsion": {"max_thrust": 50000.0, "fuel_level": 500.0,
                           "max_fuel": 1000.0, "fuel_consumption": 0.5},
            "navigation": {}, "helm": {}, "rcs": {}, "flight_computer": {},
        },
    }
    config.update(overrides)
    ship = Ship(ship_id, config)
    nav = ship.systems.get("navigation")
    if nav and nav.controller is None:
        nav.tick(0.1, ship, ship.event_bus)
    return ship


class TestFlightComputerInit:
    """Initialisation tests."""

    def test_creates_successfully(self):
        fc = FlightComputer()
        assert fc is not None
        assert fc.enabled is True

    def test_starts_idle(self):
        fc = FlightComputer()
        assert fc._mode == "idle"
        assert fc._command_name == ""
        assert fc._burn_plan is None

    def test_included_in_ship_systems(self):
        ship = _make_ship()
        assert "flight_computer" in ship.systems
        fc = ship.systems["flight_computer"]
        assert isinstance(fc, FlightComputer)

    def test_get_state_defaults(self):
        fc = FlightComputer()
        state = fc.get_state()
        assert state["mode"] == "idle"
        assert state["command"] == ""
        assert state["burn_plan"] is None
        assert state["enabled"] is True

    def test_state_in_ship_get_state(self):
        ship = _make_ship()
        state = ship.get_state()
        assert "flight_computer" in state["systems"]
        fc_state = state["systems"]["flight_computer"]
        assert fc_state["mode"] == "idle"


class TestNavigateTo:
    """Navigate-to command tests."""

    def test_navigate_to_sets_mode(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        result = fc.navigate_to(
            ship, {"x": 1000.0, "y": 0.0, "z": 0.0}
        )
        assert result.get("ok") is True
        assert fc._mode == "executing"
        assert fc._command_name == "navigate_to"

    def test_navigate_to_returns_burn_plan(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        result = fc.navigate_to(
            ship, {"x": 5000.0, "y": 0.0, "z": 0.0}
        )
        assert "burn_plan" in result
        plan = result["burn_plan"]
        assert plan["command"] == "navigate_to"
        assert plan["delta_v"] > 0
        assert plan["confidence"] > 0

    def test_navigate_via_command_dispatch(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        result = fc.command("navigate_to", {
            "ship": ship, "x": 2000, "y": 0, "z": 0,
        })
        assert result.get("ok") is True
        assert fc._mode == "executing"


class TestIntercept:
    """Intercept command tests."""

    def test_intercept_requires_target(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        result = fc.command("intercept", {"ship": ship})
        assert result.get("ok") is False

    def test_intercept_accepts_target_id(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        # Even without a real sensor contact, the autopilot should engage
        result = fc.command("intercept", {
            "ship": ship, "target": "bogey-1",
        })
        # The autopilot will engage even if the target isn't found in sensors
        assert result.get("ok") is True or "burn_plan" in result


class TestMatchVelocity:
    """Match-velocity command tests."""

    def test_match_requires_target(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        result = fc.command("match_velocity", {"ship": ship})
        assert result.get("ok") is False

    def test_match_accepts_target_id(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        result = fc.command("match_velocity", {
            "ship": ship, "target": "bogey-1",
        })
        assert result.get("ok") is True or "burn_plan" in result


class TestHoldPosition:
    """Hold-position command tests."""

    def test_hold_engages(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        result = fc.hold_position(ship)
        assert result.get("ok") is True
        assert fc._mode == "executing"
        assert fc._command_name == "hold_position"

    def test_hold_via_command(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        result = fc.command("hold_position", {"ship": ship})
        assert result.get("ok") is True


class TestOrbit:
    """Orbit command tests."""

    def test_orbit_computes_params(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        center = {"x": 5000.0, "y": 0.0, "z": 0.0}
        result = fc.orbit(ship, center, 1000.0)
        assert result.get("ok") is True
        assert fc._mode == "executing"
        assert "burn_plan" in result
        plan = result["burn_plan"]
        assert plan["command"] == "orbit"

    def test_orbit_via_command(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        result = fc.command("orbit", {
            "ship": ship,
            "center_x": 3000, "center_y": 0, "center_z": 0,
            "radius": 500,
        })
        assert result.get("ok") is True


class TestEvasive:
    """Evasive command tests."""

    def test_evasive_engages(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        result = fc.evasive(ship)
        assert result.get("ok") is True
        assert fc._mode == "executing"
        assert fc._command_name == "evasive"

    def test_evasive_with_duration(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        result = fc.evasive(ship, {"duration": 30})
        assert result.get("ok") is True
        plan = result.get("burn_plan", {})
        assert plan.get("estimated_time") == 30.0


class TestManualOverride:
    """Manual override tests."""

    def test_manual_disengages(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        # First engage something
        fc.hold_position(ship)
        assert fc._mode == "executing"
        # Then manual override
        result = fc.manual_override(ship)
        assert result.get("ok") is True
        assert fc._mode == "manual"
        assert fc._command_name == ""

    def test_manual_via_command(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        result = fc.command("manual", {"ship": ship})
        assert result.get("ok") is True
        assert fc._mode == "manual"


class TestAbort:
    """Abort command tests."""

    def test_abort_stops_program(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        fc.hold_position(ship)
        assert fc._mode == "executing"
        result = fc.abort(ship)
        assert result.get("ok") is True
        assert fc._mode == "idle"
        assert fc._command_name == ""
        assert fc._burn_plan is None

    def test_abort_via_command(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        fc.evasive(ship)
        result = fc.command("abort", {"ship": ship})
        assert result.get("ok") is True
        assert fc._mode == "idle"


class TestStatus:
    """Status reporting tests."""

    def test_status_idle(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        status = fc.get_flight_status(ship)
        assert isinstance(status, FlightComputerStatus)
        assert status.mode == "idle"
        assert "standing by" in status.status_text.lower()

    def test_status_dict_fields(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        result = fc.command("status", {"ship": ship})
        assert "mode" in result
        assert "command" in result
        assert "status_text" in result

    def test_status_executing(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        fc.hold_position(ship)
        status = fc.get_flight_status(ship)
        assert status.mode == "executing"
        assert status.command == "hold_position"

    def test_status_manual(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        fc.manual_override(ship)
        status = fc.get_flight_status(ship)
        assert status.mode == "manual"
        assert "manual" in status.status_text.lower()


class TestTickIntegration:
    """Verify tick integration with the ship loop."""

    def test_tick_called_in_ship_loop(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        # Should not raise
        ship.tick(0.1, [ship], sim_time=0.0)
        assert fc._mode == "idle"

    def test_tick_executing_monitors_autopilot(self):
        ship = _make_ship()
        fc = ship.systems["flight_computer"]
        fc.hold_position(ship)
        assert fc._mode == "executing"
        # Run a few ticks
        for i in range(5):
            ship.tick(0.1, [ship], sim_time=float(i) * 0.1)
        # Should still be executing (hold doesn't complete)
        assert fc._mode == "executing"
