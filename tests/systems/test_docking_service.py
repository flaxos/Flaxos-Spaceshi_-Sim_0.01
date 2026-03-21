# tests/systems/test_docking_service.py
"""Tests for station dock repair, refuel, and resupply.

When a ship docks with a station (class_type == "station"), the docking
system should fully service the ship: repair hull and subsystems, refuel,
resupply ammo, and reset heat.  These tests verify each of those
behaviours independently and together.
"""

import pytest
from unittest.mock import MagicMock


def _make_ship(ship_id="test_ship", overrides=None):
    """Create a Ship with propulsion and weapons for docking tests."""
    from hybrid.ship import Ship

    config = {
        "mass": 5000.0,
        "systems": {
            "propulsion": {"max_thrust": 100.0, "max_fuel": 1000.0, "fuel_level": 1000.0},
        },
    }
    if overrides:
        config.update(overrides)
    return Ship(ship_id, config)


def _make_station(station_id="station_alpha"):
    """Create a minimal station object for docking target."""
    station = MagicMock()
    station.id = station_id
    station.class_type = "station"
    station.position = {"x": 0.0, "y": 0.0, "z": 0.0}
    station.velocity = {"x": 0.0, "y": 0.0, "z": 0.0}
    return station


def _make_docking_system():
    from hybrid.systems.docking_system import DockingSystem
    return DockingSystem({"docking_range": 50.0, "max_relative_velocity": 1.0})


class TestStationDockRepair:
    """Verify hull and subsystem repair on station docking."""

    def test_hull_restored_to_max(self):
        """Docking at a station should restore hull to max_hull_integrity."""
        ship = _make_ship()
        station = _make_station()
        ds = _make_docking_system()
        event_bus = MagicMock()

        ship.hull_integrity = ship.max_hull_integrity * 0.5

        ds._handle_station_dock(ship, event_bus, station)

        assert ship.hull_integrity == ship.max_hull_integrity

    def test_subsystems_repaired_to_full(self):
        """All damage model subsystems should be at max health after docking."""
        ship = _make_ship()
        station = _make_station()
        ds = _make_docking_system()
        event_bus = MagicMock()

        # Damage some subsystems
        for name, data in ship.damage_model.subsystems.items():
            data.health = data.max_health * 0.3

        ds._handle_station_dock(ship, event_bus, station)

        for name, data in ship.damage_model.subsystems.items():
            assert data.health == data.max_health, f"{name} not fully repaired"

    def test_subsystem_heat_reset(self):
        """Subsystem heat should be zeroed after station dock."""
        ship = _make_ship()
        station = _make_station()
        ds = _make_docking_system()
        event_bus = MagicMock()

        # Overheat some subsystems
        for name, data in ship.damage_model.subsystems.items():
            data.heat = data.max_heat * 0.9

        ds._handle_station_dock(ship, event_bus, station)

        for name, data in ship.damage_model.subsystems.items():
            assert data.heat == 0.0, f"{name} heat not reset"


class TestStationDockRefuel:
    """Verify fuel resupply on station docking."""

    def test_fuel_topped_off(self):
        """Propulsion fuel_level should equal max_fuel after docking."""
        ship = _make_ship()
        station = _make_station()
        ds = _make_docking_system()
        event_bus = MagicMock()

        propulsion = ship.systems["propulsion"]
        propulsion.fuel_level = 200.0  # partially depleted

        ds._handle_station_dock(ship, event_bus, station)

        assert propulsion.fuel_level == propulsion.max_fuel

    def test_fuel_already_full_no_op(self):
        """If fuel is already full, no harm done -- fuel stays at max."""
        ship = _make_ship()
        station = _make_station()
        ds = _make_docking_system()
        event_bus = MagicMock()

        propulsion = ship.systems["propulsion"]
        propulsion.fuel_level = propulsion.max_fuel

        ds._handle_station_dock(ship, event_bus, station)

        assert propulsion.fuel_level == propulsion.max_fuel


class TestStationDockResupply:
    """Verify weapon ammo resupply on station docking."""

    def test_legacy_weapons_resupplied(self):
        """Legacy weapon system ammo should be restored."""
        ship = _make_ship(overrides={
            "systems": {
                "propulsion": {"max_thrust": 100.0, "max_fuel": 1000.0},
                "weapons": {
                    "weapons": [
                        {"name": "laser", "power_cost": 5.0, "max_heat": 50.0,
                         "damage": 10.0, "ammo_capacity": 50},
                    ],
                },
            },
        })
        station = _make_station()
        ds = _make_docking_system()
        event_bus = MagicMock()

        weapon_system = ship.systems.get("weapons")
        assert hasattr(weapon_system, "weapons"), "WeaponSystem should have weapons dict"
        for w in weapon_system.weapons.values():
            if hasattr(w, "ammo"):
                w.ammo = 5  # nearly empty

        ds._handle_station_dock(ship, event_bus, station)

        for w in weapon_system.weapons.values():
            if w.ammo_capacity is not None:
                assert w.ammo == w.ammo_capacity, f"{w.name} not resupplied"

    def test_combat_system_resupplied(self):
        """Combat system truth weapons should be resupplied if present."""
        ship = _make_ship()
        station = _make_station()
        ds = _make_docking_system()
        event_bus = MagicMock()

        # Mock a combat system with resupply
        mock_combat = MagicMock()
        mock_combat.resupply.return_value = {"weapons": [{"weapon_id": "railgun_1"}]}
        ship.systems["combat"] = mock_combat

        ds._handle_station_dock(ship, event_bus, station)

        mock_combat.resupply.assert_called_once()


class TestStationDockEvents:
    """Verify event publishing on station dock."""

    def test_repair_complete_event_published(self):
        """A repair_complete event should be published with hull data."""
        ship = _make_ship()
        station = _make_station()
        ds = _make_docking_system()
        event_bus = MagicMock()

        ship.hull_integrity = ship.max_hull_integrity * 0.5
        hull_before = ship.hull_integrity

        ds._handle_station_dock(ship, event_bus, station)

        calls = [c for c in event_bus.publish.call_args_list
                 if c[0][0] == "repair_complete"]
        assert len(calls) == 1
        payload = calls[0][0][1]
        assert payload["ship"] == ship.id
        assert payload["hull_before"] == hull_before
        assert payload["hull_after"] == ship.max_hull_integrity

    def test_resupply_complete_event_published(self):
        """A resupply_complete event should be published with fuel data."""
        ship = _make_ship()
        station = _make_station()
        ds = _make_docking_system()
        event_bus = MagicMock()

        propulsion = ship.systems["propulsion"]
        propulsion.fuel_level = 300.0

        ds._handle_station_dock(ship, event_bus, station)

        calls = [c for c in event_bus.publish.call_args_list
                 if c[0][0] == "resupply_complete"]
        assert len(calls) == 1
        payload = calls[0][0][1]
        assert payload["fuel_before"] == 300.0
        assert payload["fuel_after"] == propulsion.max_fuel

    def test_no_events_without_event_bus(self):
        """Servicing should still work even when event_bus is None."""
        ship = _make_ship()
        station = _make_station()
        ds = _make_docking_system()

        ship.hull_integrity = ship.max_hull_integrity * 0.3
        propulsion = ship.systems["propulsion"]
        propulsion.fuel_level = 100.0

        # Should not raise
        ds._handle_station_dock(ship, None, station)

        assert ship.hull_integrity == ship.max_hull_integrity
        assert propulsion.fuel_level == propulsion.max_fuel


class TestStationDockTelemetry:
    """Verify get_state includes service report when docked."""

    def test_service_report_in_state_when_docked(self):
        """get_state should include service_report when status is docked."""
        ship = _make_ship()
        station = _make_station()
        ds = _make_docking_system()
        event_bus = MagicMock()

        ship.hull_integrity = ship.max_hull_integrity * 0.5
        ship.systems["propulsion"].fuel_level = 200.0

        ds._handle_station_dock(ship, event_bus, station)
        ds.status = "docked"

        state = ds.get_state()
        assert "service_report" in state
        report = state["service_report"]
        assert report["hull_repaired"] > 0
        assert report["fuel_added"] > 0

    def test_no_service_report_when_idle(self):
        """get_state should not include service_report when undocked."""
        ds = _make_docking_system()
        ds.status = "idle"
        state = ds.get_state()
        assert "service_report" not in state

    def test_service_report_cleared_on_undock(self):
        """Undocking should clear the service report."""
        ship = _make_ship()
        station = _make_station()
        ds = _make_docking_system()
        event_bus = MagicMock()

        ds._handle_station_dock(ship, event_bus, station)
        ds.status = "docked"
        assert ds._last_service_report is not None

        ds._cmd_undock({"_ship": ship, "event_bus": event_bus})
        assert ds._last_service_report is None

    def test_undocked_ship_state_has_no_report(self):
        """After undock, get_state should not contain service_report."""
        ship = _make_ship()
        station = _make_station()
        ds = _make_docking_system()
        event_bus = MagicMock()

        ds._handle_station_dock(ship, event_bus, station)
        ds.status = "docked"
        ds._cmd_undock({"_ship": ship, "event_bus": event_bus})

        state = ds.get_state()
        assert "service_report" not in state


class TestNonStationDock:
    """Docking with a non-station ship should NOT trigger servicing."""

    def test_no_servicing_for_ship_to_ship_dock(self):
        """Docking with another ship (non-station) should not repair."""
        from hybrid.systems.docking_system import DockingSystem

        ds = DockingSystem({"docking_range": 100.0})
        ship = _make_ship()
        other_ship = _make_ship("other_ship")
        other_ship.class_type = "corvette"
        other_ship.position = {"x": 0.0, "y": 0.0, "z": 0.0}
        other_ship.velocity = {"x": 0.0, "y": 0.0, "z": 0.0}

        ship.hull_integrity = ship.max_hull_integrity * 0.5
        original_hull = ship.hull_integrity
        ship.position = {"x": 0.0, "y": 0.0, "z": 0.0}
        ship.velocity = {"x": 0.0, "y": 0.0, "z": 0.0}

        ds.target_id = "other_ship"
        ds.target_ship = other_ship
        ds.tick(0.1, ship=ship, event_bus=MagicMock())

        # Hull should NOT be repaired since target is not a station
        assert ship.hull_integrity == original_hull
