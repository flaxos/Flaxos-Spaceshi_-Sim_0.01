from hybrid_runner import HybridRunner
from server.run_server import dispatch


def test_get_events_returns_entries_after_tick():
    runner = HybridRunner(dt=0.1)
    runner.simulator.add_ship(
        "test_ship",
        {
            "id": "test_ship",
            "systems": {
                "navigation": {},
            },
        },
    )
    runner.simulator.start()
    runner.simulator.tick()

    response = dispatch(runner, {"cmd": "get_events", "limit": 10})

    assert response["ok"] is True
    assert response["events"]
