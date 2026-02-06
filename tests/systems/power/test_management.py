# tests/systems/power/test_management.py

import pytest
from hybrid.systems.power.management import PowerManagementSystem


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


class _DummySystem:
    def __init__(self, power_draw, enabled=True):
        self.power_draw = power_draw
        self.enabled = enabled


class _DummyShip:
    def __init__(self, systems):
        self.systems = systems


def test_get_draw_profile_nominal_case():
    config = {
        "primary": {"capacity": 120.0, "output_rate": 10.0, "thermal_limit": 100.0},
        "secondary": {"capacity": 50.0, "output_rate": 5.0, "thermal_limit": 100.0},
        "tertiary": {"capacity": 20.0, "output_rate": 2.0, "thermal_limit": 100.0},
        "system_map": {
            "propulsion": "primary",
            "sensors": "primary",
            "rcs": "secondary",
            "nav": "tertiary",
        },
    }
    pm = PowerManagementSystem(config)
    pm.reactors["primary"].available = 100.0
    pm.reactors["secondary"].available = 40.0
    pm.reactors["tertiary"].available = 10.0

    ship = _DummyShip(
        {
            "power_management": pm,
            "propulsion": _DummySystem(60.0, enabled=True),
            "sensors": _DummySystem(20.0, enabled=True),
            "rcs": _DummySystem(12.0, enabled=True),
            "nav": _DummySystem(6.0, enabled=True),
        }
    )

    result = pm.get_draw_profile(ship=ship)
    assert set(result.keys()) == {"active_profile", "buses", "totals"}
    assert set(result["totals"].keys()) == {"available_kw", "requested_kw", "delta_kw"}

    primary = result["buses"]["primary"]
    assert primary["available_kw"] == pytest.approx(100.0)
    assert primary["requested_kw"] == pytest.approx(80.0)
    assert primary["delta_kw"] == pytest.approx(20.0)
    assert primary["status"] == "surplus"
    assert [s["name"] for s in primary["top_consumers"]] == ["propulsion", "sensors"]

    assert result["totals"]["available_kw"] == pytest.approx(150.0)
    assert result["totals"]["requested_kw"] == pytest.approx(98.0)
    assert result["totals"]["delta_kw"] == pytest.approx(52.0)


def test_get_draw_profile_deficit_and_command_path():
    config = {
        "primary": {"capacity": 120.0, "output_rate": 10.0, "thermal_limit": 100.0},
        "secondary": {"capacity": 20.0, "output_rate": 5.0, "thermal_limit": 100.0},
        "system_map": {
            "propulsion": "primary",
            "rcs": "secondary",
            "comms": "secondary",
        },
    }
    pm = PowerManagementSystem(config)
    pm.reactors["primary"].available = 30.0
    pm.reactors["secondary"].available = 8.0

    ship = _DummyShip(
        {
            "power_management": pm,
            "propulsion": _DummySystem(42.0, enabled=True),
            "rcs": _DummySystem(5.0, enabled=True),
            "comms": _DummySystem(6.0, enabled=True),
            "spare": _DummySystem(100.0, enabled=False),
        }
    )

    result = pm.command("get_draw_profile", {"ship": ship})

    assert result["buses"]["primary"]["status"] == "deficit"
    assert result["buses"]["primary"]["delta_kw"] == pytest.approx(-12.0)
    assert result["buses"]["secondary"]["status"] == "deficit"
    assert result["buses"]["secondary"]["requested_kw"] == pytest.approx(11.0)
    assert all(s["name"] != "spare" for s in result["buses"]["unassigned"]["systems"])
