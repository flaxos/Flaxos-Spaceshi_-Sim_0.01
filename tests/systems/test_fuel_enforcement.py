# tests/systems/test_fuel_enforcement.py
"""Tests for fuel consumption enforcement.

Verifies that:
1. Fuel is consumed each tick proportional to thrust and ISP
2. Ship mass decreases as fuel burns (dynamic mass model)
3. Thrust is killed when fuel hits zero
4. Throttle is zeroed when fuel is exhausted (no phantom throttle)
5. BINGO FUEL event fires once at 10% threshold
6. Refueling resets bingo warning
7. set_throttle rejects commands when fuel is empty
"""

import pytest
import math
from hybrid.systems.propulsion_system import PropulsionSystem, G_FORCE
from hybrid.utils.quaternion import Quaternion


class MockShip:
    """Mock ship for fuel enforcement tests."""

    def __init__(self, mass=10000.0):
        self.id = "test_ship"
        self.mass = mass
        self.thrust = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.orientation = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        self.quaternion = Quaternion.from_euler(0, 0, 0)
        self.systems = {}


class MockEventBus:
    """Mock event bus that records all published events."""

    def __init__(self):
        self.events = []

    def publish(self, event_type, data):
        self.events.append((event_type, data))

    def get_events(self, event_type):
        """Return all events of a given type."""
        return [(t, d) for t, d in self.events if t == event_type]


class TestFuelConsumptionPhysics:
    """Verify that fuel consumption follows Tsiolkovsky: mdot = F / Ve."""

    def test_isp_based_consumption_rate(self):
        """Mass flow rate should equal thrust / exhaust_velocity."""
        isp = 3000.0
        max_thrust = 1000.0
        exhaust_vel = isp * G_FORCE  # ~29430 m/s

        prop = PropulsionSystem({
            "max_thrust": max_thrust,
            "fuel_level": 1000.0,
            "max_fuel": 1000.0,
            "isp": isp,
        })
        ship = MockShip()
        bus = MockEventBus()

        initial_fuel = prop.fuel_level
        prop.set_throttle({"thrust": 1.0})
        dt = 1.0
        prop.tick(dt, ship, bus)

        expected_consumption = max_thrust / exhaust_vel * dt
        actual_consumption = initial_fuel - prop.fuel_level
        assert abs(actual_consumption - expected_consumption) < 1e-6, (
            f"Expected {expected_consumption:.6f} kg consumed, got {actual_consumption:.6f}"
        )

    def test_partial_throttle_proportional_consumption(self):
        """Half throttle should consume half as much fuel."""
        prop = PropulsionSystem({
            "max_thrust": 2000.0,
            "fuel_level": 500.0,
            "max_fuel": 500.0,
            "isp": 3000.0,
        })
        ship = MockShip()
        bus = MockEventBus()

        prop.set_throttle({"thrust": 0.5})
        initial = prop.fuel_level
        prop.tick(1.0, ship, bus)
        consumed_half = initial - prop.fuel_level

        # Reset
        prop.fuel_level = 500.0
        prop.set_throttle({"thrust": 1.0})
        initial2 = prop.fuel_level
        prop.tick(1.0, ship, bus)
        consumed_full = initial2 - prop.fuel_level

        ratio = consumed_half / consumed_full
        assert abs(ratio - 0.5) < 0.01, f"Half-throttle ratio should be 0.5, got {ratio:.4f}"

    def test_fuel_reaches_zero_kills_thrust(self):
        """When fuel runs out mid-tick, thrust and throttle must be zeroed."""
        # Tiny fuel supply that will exhaust in one tick
        prop = PropulsionSystem({
            "max_thrust": 10000.0,
            "fuel_level": 0.001,
            "max_fuel": 100.0,
            "isp": 3000.0,
        })
        ship = MockShip()
        bus = MockEventBus()

        prop.set_throttle({"thrust": 1.0})
        prop.tick(1.0, ship, bus)

        assert prop.fuel_level == 0.0
        assert prop.throttle == 0.0, "Throttle must be zeroed when fuel exhausted"
        assert prop.status == "no_fuel"
        assert ship.thrust == {"x": 0.0, "y": 0.0, "z": 0.0}
        assert ship.acceleration == {"x": 0.0, "y": 0.0, "z": 0.0}

    def test_subsequent_ticks_with_no_fuel(self):
        """After fuel runs out, subsequent ticks should short-circuit cleanly."""
        prop = PropulsionSystem({
            "max_thrust": 1000.0,
            "fuel_level": 0.0,
            "max_fuel": 100.0,
        })
        ship = MockShip()
        bus = MockEventBus()

        # Tick should not crash and should maintain no_fuel status
        for _ in range(10):
            prop.tick(0.1, ship, bus)

        assert prop.status == "no_fuel"
        assert prop.throttle == 0.0
        assert ship.thrust == {"x": 0.0, "y": 0.0, "z": 0.0}


class TestThrottleRejectionOnEmptyFuel:
    """set_throttle must refuse commands when fuel is empty."""

    def test_set_throttle_rejected_when_no_fuel(self):
        """Player cannot set throttle when fuel is zero."""
        prop = PropulsionSystem({
            "max_thrust": 1000.0,
            "fuel_level": 0.0,
            "max_fuel": 100.0,
        })
        result = prop.set_throttle({"thrust": 1.0})

        assert "error" in result
        assert "fuel" in result["error"].lower()
        assert prop.throttle == 0.0

    def test_set_throttle_works_after_refuel(self):
        """After refueling from empty, throttle commands work again."""
        prop = PropulsionSystem({
            "max_thrust": 1000.0,
            "fuel_level": 0.0,
            "max_fuel": 100.0,
        })
        # Rejected
        result = prop.set_throttle({"thrust": 1.0})
        assert "error" in result

        # Refuel
        prop.refuel({"amount": 50.0})
        assert prop.fuel_level == 50.0

        # Now should work
        result = prop.set_throttle({"thrust": 0.5})
        assert "error" not in result
        assert prop.throttle == 0.5


class TestBingoFuelEvent:
    """BINGO FUEL event should fire once when fuel drops below 10%."""

    def test_bingo_fires_at_10_percent(self):
        """Bingo event fires when fuel crosses below 10% threshold."""
        prop = PropulsionSystem({
            "max_thrust": 1000.0,
            "fuel_level": 100.0,
            "max_fuel": 1000.0,  # 10% threshold = 100 kg
            "isp": 3000.0,
        })
        ship = MockShip()
        bus = MockEventBus()

        prop.set_throttle({"thrust": 1.0})

        # Burn a small amount to push below 10%
        prop.tick(1.0, ship, bus)
        assert prop.fuel_level < 100.0  # Should have consumed some fuel

        bingo_events = bus.get_events("bingo_fuel")
        assert len(bingo_events) == 1, f"Expected 1 bingo event, got {len(bingo_events)}"
        assert bingo_events[0][1]["ship_id"] == "test_ship"
        # fuel_pct is rounded to 1 decimal, so at the boundary it may report 10.0
        assert bingo_events[0][1]["fuel_pct"] <= 10.0

    def test_bingo_fires_only_once(self):
        """Bingo event must not repeat on subsequent ticks."""
        prop = PropulsionSystem({
            "max_thrust": 1000.0,
            "fuel_level": 50.0,
            "max_fuel": 1000.0,  # Already below 10%
            "isp": 3000.0,
        })
        ship = MockShip()
        bus = MockEventBus()

        prop.set_throttle({"thrust": 1.0})
        for _ in range(10):
            prop.tick(0.1, ship, bus)

        bingo_events = bus.get_events("bingo_fuel")
        assert len(bingo_events) == 1, f"Bingo must fire only once, got {len(bingo_events)}"

    def test_bingo_does_not_fire_above_threshold(self):
        """No bingo event when fuel is above 10%."""
        prop = PropulsionSystem({
            "max_thrust": 1000.0,
            "fuel_level": 500.0,
            "max_fuel": 1000.0,
            "isp": 3000.0,
        })
        ship = MockShip()
        bus = MockEventBus()

        prop.set_throttle({"thrust": 1.0})
        prop.tick(1.0, ship, bus)

        bingo_events = bus.get_events("bingo_fuel")
        assert len(bingo_events) == 0

    def test_bingo_resets_after_refuel(self):
        """Refueling above 10% resets the bingo warning so it can fire again."""
        prop = PropulsionSystem({
            "max_thrust": 1000.0,
            "fuel_level": 50.0,
            "max_fuel": 1000.0,
            "isp": 3000.0,
        })
        ship = MockShip()
        bus = MockEventBus()

        prop.set_throttle({"thrust": 1.0})
        prop.tick(0.1, ship, bus)
        assert len(bus.get_events("bingo_fuel")) == 1

        # Refuel above 10%
        prop.refuel({"amount": 500.0})
        assert not prop._bingo_warned

        # Drain back below 10%
        prop.fuel_level = 50.0
        bus.events.clear()
        prop.set_throttle({"thrust": 1.0})
        prop.tick(0.1, ship, bus)

        bingo_events = bus.get_events("bingo_fuel")
        assert len(bingo_events) == 1, "Bingo should fire again after refuel reset"


class TestDynamicMassModel:
    """Ship mass must decrease as fuel is consumed."""

    def test_ship_infers_dry_mass(self):
        """Ship without explicit dry_mass should treat config mass as dry mass.

        Scenario convention: ``mass`` is the structural hull mass, fuel is
        configured separately.  So dry_mass == config mass, and total mass
        == dry_mass + fuel_level.
        """
        from hybrid.ship import Ship

        config = {
            "mass": 5000.0,
            "systems": {
                "propulsion": {
                    "max_thrust": 1000.0,
                    "fuel_level": 2000.0,
                    "max_fuel": 2000.0,
                    "isp": 3000.0,
                },
            },
        }
        ship = Ship("test_infer", config)

        assert ship._dynamic_mass is True
        assert ship.dry_mass == 5000.0, f"Expected dry_mass=5000 (config mass), got {ship.dry_mass}"
        # Total mass should be dry_mass + fuel
        assert ship.mass == 7000.0, f"Expected mass=7000 (5000+2000), got {ship.mass}"

    def test_mass_decreases_as_fuel_burns(self):
        """Ship total mass should decrease when fuel is consumed by thrust."""
        from hybrid.ship import Ship

        config = {
            "mass": 5000.0,
            "systems": {
                "propulsion": {
                    "max_thrust": 1000.0,
                    "fuel_level": 2000.0,
                    "max_fuel": 2000.0,
                    "isp": 3000.0,
                },
            },
        }
        ship = Ship("test_mass", config)
        prop = ship.systems["propulsion"]

        # With inferred dry_mass, total mass = 5000 + 2000 = 7000
        initial_mass = ship.mass
        assert initial_mass == 7000.0
        initial_fuel = prop.fuel_level

        prop.set_throttle({"thrust": 1.0})
        # Run a tick -- this calls propulsion.tick then _update_mass
        ship.tick(1.0)

        assert prop.fuel_level < initial_fuel, "Fuel should have been consumed"
        assert ship.mass < initial_mass, (
            f"Ship mass should decrease: was {initial_mass}, now {ship.mass}"
        )
        # Mass should equal dry_mass + remaining fuel (approximately, ignoring ammo)
        expected_mass = ship.dry_mass + prop.fuel_level
        assert abs(ship.mass - expected_mass) < 1.0, (
            f"Mass mismatch: ship.mass={ship.mass}, expected={expected_mass}"
        )

    def test_explicit_dry_mass_still_works(self):
        """Ships with explicit dry_mass in config should behave the same."""
        from hybrid.ship import Ship

        config = {
            "mass": 7000.0,
            "dry_mass": 5000.0,
            "systems": {
                "propulsion": {
                    "max_thrust": 1000.0,
                    "fuel_level": 2000.0,
                    "max_fuel": 2000.0,
                    "isp": 3000.0,
                },
            },
        }
        ship = Ship("test_explicit", config)

        assert ship._dynamic_mass is True
        assert ship.dry_mass == 5000.0
        assert ship.mass == 7000.0


class TestTelemetryFuelState:
    """Verify telemetry reports fuel state correctly."""

    def test_telemetry_includes_fuel(self):
        """Telemetry must include fuel level, max, and percent."""
        from hybrid.ship import Ship
        from hybrid.telemetry import get_ship_telemetry

        config = {
            "mass": 5000.0,
            "systems": {
                "propulsion": {
                    "max_thrust": 1000.0,
                    "fuel_level": 800.0,
                    "max_fuel": 1000.0,
                    "isp": 3000.0,
                },
            },
        }
        ship = Ship("test_telemetry", config)
        telem = get_ship_telemetry(ship, sim_time=0.0)

        assert "fuel" in telem
        assert telem["fuel"]["level"] == 800.0
        assert telem["fuel"]["max"] == 1000.0
        assert abs(telem["fuel"]["percent"] - 80.0) < 0.1
        assert telem["delta_v_remaining"] > 0
