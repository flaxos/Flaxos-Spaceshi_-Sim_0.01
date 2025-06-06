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
