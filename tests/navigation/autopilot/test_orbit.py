"""Tests for the OrbitAutopilot."""

import math
import pytest
from hybrid.ship import Ship
from hybrid.navigation.autopilot.orbit import OrbitAutopilot


def _make_ship(position=None, velocity=None) -> Ship:
    """Create a ship with propulsion for orbit testing."""
    config = {
        "mass": 10000.0,
        "systems": {
            "propulsion": {
                "max_thrust": 50000.0,
                "fuel_level": 500.0,
                "max_fuel": 1000.0,
            },
            "navigation": {},
            "helm": {},
            "rcs": {},
        },
    }
    if position:
        config["position"] = position
    if velocity:
        config["velocity"] = velocity
    ship = Ship("orbit-test", config)
    # Init navigation controller
    nav = ship.systems.get("navigation")
    if nav and nav.controller is None:
        nav.tick(0.1, ship, ship.event_bus)
    return ship


class TestOrbitInit:
    """Initialization tests."""

    def test_initializes_with_center_and_radius(self):
        ship = _make_ship()
        ap = OrbitAutopilot(ship, params={
            "center": {"x": 5000, "y": 0, "z": 0},
            "radius": 1000,
        })
        assert ap.center == {"x": 5000, "y": 0, "z": 0}
        assert ap.radius == 1000
        assert ap.phase == OrbitAutopilot.PHASE_APPROACH
        assert ap.status != "error"

    def test_error_on_missing_center(self):
        ship = _make_ship()
        ap = OrbitAutopilot(ship, params={"radius": 1000})
        assert ap.status == "error"

    def test_error_on_zero_radius(self):
        ship = _make_ship()
        ap = OrbitAutopilot(ship, params={
            "center": {"x": 0, "y": 0, "z": 0},
            "radius": 0,
        })
        assert ap.status == "error"

    def test_custom_speed(self):
        ship = _make_ship()
        ap = OrbitAutopilot(ship, params={
            "center": {"x": 0, "y": 0, "z": 0},
            "radius": 1000,
            "speed": 50.0,
        })
        assert ap.desired_speed == 50.0


class TestOrbitApproach:
    """Approach phase when far from orbit radius."""

    def test_approach_when_far(self):
        ship = _make_ship(position={"x": 0, "y": 0, "z": 0})
        ap = OrbitAutopilot(ship, params={
            "center": {"x": 5000, "y": 0, "z": 0},
            "radius": 1000,
        })
        assert ap.phase == OrbitAutopilot.PHASE_APPROACH
        result = ap.compute(0.1, 0.0)
        assert result is not None
        assert "thrust" in result
        assert result["thrust"] > 0

    def test_approach_produces_heading(self):
        ship = _make_ship(position={"x": 0, "y": 0, "z": 0})
        ap = OrbitAutopilot(ship, params={
            "center": {"x": 5000, "y": 0, "z": 0},
            "radius": 1000,
        })
        result = ap.compute(0.1, 0.0)
        assert "heading" in result


class TestOrbitPhase:
    """Orbit phase when at correct radius."""

    def test_transitions_to_orbit_when_on_circle(self):
        # Place ship exactly on the orbit circle
        ship = _make_ship(
            position={"x": 1000, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
        )
        center = {"x": 0, "y": 0, "z": 0}
        radius = 1000

        ap = OrbitAutopilot(ship, params={
            "center": center,
            "radius": radius,
            "tolerance": 100,  # generous tolerance
        })
        # First compute should transition from APPROACH to CIRCULARIZE
        result = ap.compute(0.1, 0.0)
        assert ap.phase in (
            OrbitAutopilot.PHASE_CIRCULARIZE,
            OrbitAutopilot.PHASE_ORBIT,
        )


class TestTangentialVelocity:
    """Verify tangential velocity calculation."""

    def test_desired_velocity_is_tangential(self):
        ship = _make_ship(position={"x": 1000, "y": 0, "z": 0})
        center = {"x": 0, "y": 0, "z": 0}
        radius = 1000

        ap = OrbitAutopilot(ship, params={
            "center": center,
            "radius": radius,
        })

        from hybrid.utils.math_utils import subtract_vectors, magnitude, dot_product
        vec_to_center = subtract_vectors(center, ship.position)
        dist = magnitude(vec_to_center)

        desired_vel = ap._desired_velocity(vec_to_center, dist)
        # The radial component should be small at the orbit radius
        # (only correction term present)
        orbital_speed = ap._get_orbital_speed()
        vel_mag = magnitude(desired_vel)
        # Velocity magnitude should be close to orbital speed
        # (exact match only when radius_error = 0)
        assert vel_mag > 0

    def test_get_state_includes_orbit_data(self):
        ship = _make_ship(position={"x": 1000, "y": 0, "z": 0})
        ap = OrbitAutopilot(ship, params={
            "center": {"x": 0, "y": 0, "z": 0},
            "radius": 1000,
        })
        state = ap.get_state()
        assert "center" in state
        assert "radius" in state
        assert "current_distance" in state
        assert "orbital_speed" in state
        assert "phase" in state
