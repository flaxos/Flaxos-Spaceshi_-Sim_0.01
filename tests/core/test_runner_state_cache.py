from types import SimpleNamespace

from hybrid_runner import HybridRunner


class DummyShip:
    def __init__(self, sensors):
        self.systems = {"sensors": sensors}

    def get_state(self):
        return {"systems": {}}


def test_update_state_cache_handles_active_sensor_object():
    sensors = SimpleNamespace(
        active=SimpleNamespace(last_ping_time=None),
        passive=SimpleNamespace(),
        config={},
    )
    ship = DummyShip(sensors)
    runner = HybridRunner(dt=0.1)
    runner.simulator = SimpleNamespace(ships={"ship": ship})

    runner._update_state_cache()

    assert sensors.active.last_ping_time == 0
    assert "ship" in runner.state_cache
