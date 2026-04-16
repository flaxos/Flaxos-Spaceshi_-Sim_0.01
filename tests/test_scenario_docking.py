from __future__ import annotations

import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


SCENARIO_PATH = os.path.join(ROOT, "scenarios", "07_docking_test.yaml")
PLAYER_SHIP_ID = "player"
TARGET_SHIP_ID = "target_station"
DT = 0.1
MAX_SIM_SECONDS = 20 * 60
MAX_TICKS = int(MAX_SIM_SECONDS / DT)


def _build_sim():
    from hybrid_runner import HybridRunner

    runner = HybridRunner(dt=DT)
    count = runner._load_scenario_file(SCENARIO_PATH)
    assert count >= 2, f"Expected at least 2 ships from scenario; got {count}"

    sim = runner.simulator
    sim.start()

    if runner.mission and runner.mission.start_time is None:
        runner.mission.start(sim.time)

    player = sim.ships.get(PLAYER_SHIP_ID)
    target = sim.ships.get(TARGET_SHIP_ID)
    assert player is not None
    assert target is not None
    return runner, sim, player, target


def _issue_command(sim, ship, command: str, params: dict) -> dict:
    from hybrid.command_handler import route_command

    return route_command(
        ship,
        {"command": command, "ship": ship.id, **params},
        list(sim.ships.values()),
    )


def test_short_range_docking_scenario_reaches_mission_success():
    runner, sim, player, _target = _build_sim()

    contact_id = TARGET_SHIP_ID
    for _ in range(200):
        sim.tick()
        runner._update_mission()
        sensors = player.systems.get("sensors")
        if sensors and TARGET_SHIP_ID in sensors.contact_tracker.id_mapping:
            contact_id = sensors.contact_tracker.id_mapping[TARGET_SHIP_ID]
            break

    response = _issue_command(
        sim,
        player,
        "autopilot",
        {"program": "rendezvous", "target": contact_id},
    )
    assert "error" not in response, response

    dock_response = _issue_command(
        sim,
        player,
        "request_docking",
        {"target_id": TARGET_SHIP_ID},
    )
    assert "error" not in dock_response, dock_response

    for _ in range(MAX_TICKS):
        sim.tick()
        runner._update_mission()
        if player.docked_to == TARGET_SHIP_ID:
            break

    assert player.docked_to == TARGET_SHIP_ID, (
        "Short-range docking scenario never reached a docked state"
    )

    status = runner.mission.get_status(sim_time=sim.time)
    assert status["mission_status"] == "success", status
