#!/usr/bin/env python3
"""Headless station wiring smoke checks for GUI UAT.

This script exercises the tutorial intercept scenario through the same command
names the GUI sends so bridge/UAT issues can be separated into:

1. scenario / ship wiring,
2. command dispatch,
3. telemetry progression.

Checks:
  - the tutorial player ship inherits its class-defined systems
  - manual thrust increases speed
  - lock_target + rendezvous autopilot reduce target range

Usage:
  python3 tools/check_station_wiring.py
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from hybrid.command_handler import route_command
from hybrid.scenarios.loader import ScenarioLoader
from hybrid.simulator import Simulator


SCENARIO_PATH = ROOT_DIR / "scenarios" / "01_tutorial_intercept.yaml"


def build_simulator() -> Simulator:
    scenario = ScenarioLoader.load(str(SCENARIO_PATH))
    sim = Simulator(dt=scenario.get("dt", 0.1), time_scale=1.0)
    for ship_data in scenario["ships"]:
        sim.add_ship(ship_data["id"], ship_data)

    all_ships = list(sim.ships.values())
    for ship in all_ships:
        ship._all_ships_ref = all_ships

    sim.start()
    return sim


def issue(sim: Simulator, ship_id: str, command: str, params: dict) -> dict:
    ship = sim.ships[ship_id]
    result = route_command(ship, {"command": command, "ship": ship_id, **params}, list(sim.ships.values()))
    if isinstance(result, dict) and result.get("error"):
        raise RuntimeError(f"{command} failed: {result}")
    return result


def speed(ship) -> float:
    vel = ship.velocity
    return math.sqrt(vel["x"] ** 2 + vel["y"] ** 2 + vel["z"] ** 2)


def distance(a, b) -> float:
    dx = a.position["x"] - b.position["x"]
    dy = a.position["y"] - b.position["y"]
    dz = a.position["z"] - b.position["z"]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def wait_for_contact(sim: Simulator, player_id: str, target_ship_id: str, max_ticks: int = 120) -> str:
    player = sim.ships[player_id]
    sensors = player.systems.get("sensors")

    for _ in range(max_ticks):
        sim.tick()
        sensors = player.systems.get("sensors")
        tracker = getattr(sensors, "contact_tracker", None)
        if tracker and target_ship_id in tracker.id_mapping:
            return tracker.id_mapping[target_ship_id]

    raise RuntimeError(f"Target {target_ship_id} was not detected within {max_ticks} ticks")


def check_system_loadout(sim: Simulator) -> None:
    player = sim.ships["player"]
    required = {"propulsion", "navigation", "helm", "targeting", "combat", "power_management"}
    missing = sorted(required - set(player.systems.keys()))
    if missing:
        raise RuntimeError(f"Player ship missing required systems: {missing}")

    print("PASS loadout  player ship has full class-defined systems")


def check_manual_thrust(sim: Simulator) -> None:
    player = sim.ships["player"]
    start_speed = speed(player)
    issue(sim, "player", "set_thrust", {"thrust": 0.25})
    for _ in range(50):
        sim.tick()
    end_speed = speed(player)

    if end_speed <= start_speed + 10.0:
        raise RuntimeError(
            f"Manual thrust did not accelerate the ship enough: start={start_speed:.2f} m/s end={end_speed:.2f} m/s"
        )

    print(f"PASS manual   speed increased from {start_speed:.1f} to {end_speed:.1f} m/s")


def check_rendezvous(sim: Simulator) -> None:
    player = sim.ships["player"]
    target = sim.ships["target_station"]

    issue(sim, "player", "ping_sensors", {})
    contact_id = wait_for_contact(sim, "player", "target_station")
    issue(sim, "player", "lock_target", {"contact_id": contact_id})

    start_range = distance(player, target)
    issue(sim, "player", "autopilot", {
        "enable": True,
        "program": "rendezvous",
        "target": contact_id,
        "profile": "balanced",
    })

    for _ in range(200):
        sim.tick()

    end_range = distance(player, target)
    if end_range >= start_range - 1000.0:
        raise RuntimeError(
            f"Rendezvous did not close range enough: start={start_range:.1f}m end={end_range:.1f}m"
        )

    print(f"PASS auto     range decreased from {start_range:.0f}m to {end_range:.0f}m using contact {contact_id}")


def main() -> int:
    print("== Station Wiring Smoke Check ==")
    print(f"Scenario: {os.path.relpath(SCENARIO_PATH, ROOT_DIR)}")

    try:
        check_system_loadout(build_simulator())
        check_manual_thrust(build_simulator())
        check_rendezvous(build_simulator())
    except Exception as exc:
        print(f"FAIL         {exc}")
        return 1

    print("PASS overall tutorial manual + rendezvous wiring is functioning headlessly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

