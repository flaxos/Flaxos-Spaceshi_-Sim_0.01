# tests/systems/power/test_management.py

import types

import pytest

from hybrid.core.event_bus import EventBus
from hybrid.systems.power.management import PowerManagementSystem


class DummySystem:
    def __init__(self, enabled=True):
        self.enabled = enabled


def _collect_events(bus):
    events = []

    def _listener(event_name, payload):
        events.append((event_name, payload))

    bus.subscribe_all(_listener)
    return events


def _make_ship():
    return types.SimpleNamespace(id="ship-test", systems={})


def test_request_power_priority():
    config = {
        "primary": {"capacity": 20.0, "output_rate": 10.0, "thermal_limit": 100.0},
        "secondary": {"capacity": 10.0, "output_rate": 5.0, "thermal_limit": 100.0}
    }
    pm = PowerManagementSystem(config)
    pm.reactors["primary"].available = 5.0
    pm.reactors["secondary"].available = 10.0

    # Request 6 units → primary can’t fulfill (only 5), so secondary should supply
    result = pm.request_power(6.0, "test_unit")
    assert result
    assert pm.reactors["secondary"].available == pytest.approx(4.0)


def test_secondary_threshold_crossing_and_shedding_order():
    EventBus._instance = EventBus()
    bus = EventBus.get_instance()
    events = _collect_events(bus)

    config = {
        "secondary": {"capacity": 100.0, "output_rate": 0.0, "thermal_limit": 100.0},
        "system_map": {
            "comms": {"bus": "secondary", "criticality": 10},
            "drones": {"bus": "secondary", "criticality": 20},
            "pdc": {"bus": "secondary", "criticality": 60},
        },
        "secondary_shedding": {
            "warning_threshold": 0.35,
            "critical_threshold": 0.2,
            "warning_recovery_threshold": 0.45,
            "critical_recovery_threshold": 0.3,
        },
    }
    pm = PowerManagementSystem(config)
    ship = _make_ship()
    ship.systems = {
        "comms": DummySystem(),
        "drones": DummySystem(),
        "pdc": DummySystem(),
    }

    pm.reactors["secondary"].available = 30.0  # warning band
    pm.tick(0.0, ship=ship)

    assert ship.systems["comms"].enabled is False
    assert ship.systems["drones"].enabled is False
    assert ship.systems["pdc"].enabled is True

    shed_events = [event for event in events if event[0] == "secondary_load_shed"]
    assert [payload["system"] for _, payload in shed_events] == ["comms", "drones"]
    assert any(event_name == "secondary_battery_band" and payload["band"] == "warning" for event_name, payload in events)


def test_secondary_recovery_uses_hysteresis_and_restores_high_criticality_first():
    EventBus._instance = EventBus()
    bus = EventBus.get_instance()
    events = _collect_events(bus)

    config = {
        "secondary": {"capacity": 100.0, "output_rate": 0.0, "thermal_limit": 100.0},
        "system_map": {
            "comms": {"bus": "secondary", "criticality": 10},
            "drones": {"bus": "secondary", "criticality": 20},
            "pdc": {"bus": "secondary", "criticality": 60},
        },
    }
    pm = PowerManagementSystem(config)
    ship = _make_ship()
    ship.systems = {
        "comms": DummySystem(),
        "drones": DummySystem(),
        "pdc": DummySystem(),
    }

    pm.reactors["secondary"].available = 20.0  # critical -> shed all three
    pm.tick(0.0, ship=ship)
    assert all(system.enabled is False for system in ship.systems.values())

    pm.reactors["secondary"].available = 25.0  # below critical recovery (0.3), no restore
    pm.tick(0.0, ship=ship)
    assert all(system.enabled is False for system in ship.systems.values())

    pm.reactors["secondary"].available = 35.0  # above critical recovery, restore
    pm.tick(0.0, ship=ship)
    assert all(system.enabled is True for system in ship.systems.values())

    restore_events = [event for event in events if event[0] == "secondary_load_restored"]
    assert [payload["system"] for _, payload in restore_events] == ["pdc", "drones", "comms"]
