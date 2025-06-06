# tests/systems/power/test_reactor.py

import pytest
from hybrid.systems.power.reactor import Reactor


def test_reactor_ramp_and_overheat():
    r = Reactor(name="test", capacity=50.0, output_rate=10.0, thermal_limit=30.0)
    r.temperature = 35.0
    r.available = 0.0
    r.tick(1.0)
    # Since temp > limit, available should be half of (0 + 10)
    assert r.available == pytest.approx(5.0)
    assert r.status == "overheated"
