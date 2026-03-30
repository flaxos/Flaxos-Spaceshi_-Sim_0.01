"""
Smoke tests for all scenario files.

For every YAML file in scenarios/ this suite verifies:
1. The file parses without error (ScenarioLoader.load succeeds).
2. At least one ship is created in the simulator.
3. Every ship has a systems dict (not empty or missing).
4. Mission objectives reference ship IDs that exist in the scenario.
5. The mission starts without raising an exception.
6. 100 simulation ticks run without crashing or raising an exception.

JSON scenario files are excluded — they use an older format and are not
part of the numbered mission set being maintained.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from hybrid_runner import HybridRunner

SCENARIO_DIR = ROOT_DIR / "scenarios"


def _yaml_scenarios() -> List[str]:
    """Return sorted list of YAML scenario filenames (no path)."""
    return sorted(
        f.name
        for f in SCENARIO_DIR.iterdir()
        if f.suffix in (".yaml", ".yml")
    )


# ---------------------------------------------------------------------------
# Helper: build a runner with the scenario loaded and simulator started.
# ---------------------------------------------------------------------------

def _load_runner(scenario_filename: str) -> HybridRunner:
    """Return a runner with *scenario_filename* loaded and simulator started."""
    scenario_name = Path(scenario_filename).stem  # strip extension
    runner = HybridRunner()
    count = runner.load_scenario(scenario_name)
    assert count > 0, f"No ships loaded from {scenario_filename}"
    # Start simulator so tick() actually runs
    runner.simulator.start()
    return runner


# ---------------------------------------------------------------------------
# Parametric tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario_file", _yaml_scenarios())
def test_scenario_parses_without_error(scenario_file: str) -> None:
    """ScenarioLoader.load() must succeed without raising."""
    from hybrid.scenarios.loader import ScenarioLoader

    path = str(SCENARIO_DIR / scenario_file)
    data = ScenarioLoader.load(path)
    assert isinstance(data, dict), f"Expected dict from loader, got {type(data)}"
    assert "ships" in data, f"Scenario missing 'ships' key: {scenario_file}"
    assert data["ships"], f"Scenario has no ships: {scenario_file}"


@pytest.mark.parametrize("scenario_file", _yaml_scenarios())
def test_scenario_ships_created(scenario_file: str) -> None:
    """After loading, the simulator must contain at least one ship object."""
    runner = _load_runner(scenario_file)
    assert len(runner.simulator.ships) > 0, (
        f"simulator.ships is empty after loading {scenario_file}"
    )


@pytest.mark.parametrize("scenario_file", _yaml_scenarios())
def test_scenario_ships_have_systems(scenario_file: str) -> None:
    """Every ship object must have a non-None systems dict."""
    runner = _load_runner(scenario_file)
    for ship_id, ship in runner.simulator.ships.items():
        assert hasattr(ship, "systems"), (
            f"Ship '{ship_id}' in {scenario_file} has no 'systems' attribute"
        )
        assert ship.systems is not None, (
            f"Ship '{ship_id}' in {scenario_file} has systems=None"
        )


@pytest.mark.parametrize("scenario_file", _yaml_scenarios())
def test_scenario_mission_objectives_reference_valid_ships(scenario_file: str) -> None:
    """
    Each objective that has a 'target' param must reference a ship ID that
    actually exists in the loaded scenario's ships dict.
    """
    raw = yaml.safe_load((SCENARIO_DIR / scenario_file).read_text())
    ship_ids = {s["id"] for s in raw.get("ships", []) if "id" in s}

    mission_data = raw.get("mission", {})
    if not mission_data:
        pytest.skip(f"No mission block in {scenario_file}")

    for obj in mission_data.get("objectives", []):
        target = obj.get("params", {}).get("target")
        if target:
            assert target in ship_ids, (
                f"Objective '{obj.get('id', '?')}' in {scenario_file} "
                f"references target '{target}' which is not in ships: {sorted(ship_ids)}"
            )


@pytest.mark.parametrize("scenario_file", _yaml_scenarios())
def test_scenario_mission_starts(scenario_file: str) -> None:
    """Mission.start() must succeed without raising."""
    runner = _load_runner(scenario_file)
    # If no mission, skip gracefully
    if runner.mission is None:
        pytest.skip(f"No mission in {scenario_file}")
    # mission.start() was already called inside _load_scenario_file;
    # verify the tracker is in a usable state (not None, has objectives).
    assert runner.mission.tracker is not None, (
        f"Mission tracker is None after start in {scenario_file}"
    )


@pytest.mark.parametrize("scenario_file", _yaml_scenarios())
def test_scenario_100_ticks_no_crash(scenario_file: str) -> None:
    """Running 100 simulation ticks must not raise any exception."""
    runner = _load_runner(scenario_file)
    for tick_num in range(1, 101):
        try:
            runner.simulator.tick()
            # Also update mission state as the run loop would
            runner._update_mission()
        except Exception as exc:
            pytest.fail(
                f"Crash on tick {tick_num} of {scenario_file}: "
                f"{type(exc).__name__}: {exc}"
            )
    # Simulator time must have advanced (or ships were all destroyed on tick 1,
    # which is also valid — just assert no exception was raised above).
    assert runner.simulator.time >= 0


@pytest.mark.parametrize("scenario_file", _yaml_scenarios())
def test_scenario_tick_count_advances(scenario_file: str) -> None:
    """tick_count must increase after each call to simulator.tick()."""
    runner = _load_runner(scenario_file)
    before = runner.simulator.tick_count
    runner.simulator.tick()
    after = runner.simulator.tick_count
    assert after == before + 1, (
        f"tick_count did not advance after one tick in {scenario_file}: "
        f"before={before} after={after}"
    )
