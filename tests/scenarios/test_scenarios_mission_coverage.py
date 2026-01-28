from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

import yaml

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT_DIR))

from hybrid.scenarios.objectives import Objective, ObjectiveStatus, ObjectiveType


SCENARIO_DIR = ROOT_DIR / "scenarios"
EXPECTED_MISSION_SCENARIOS = {
    "01_tutorial_intercept.yaml",
    "02_combat_destroy.yaml",
    "03_escort_protect.yaml",
    "04_stealth_recon.yaml",
    "05_race_checkpoint.yaml",
}


def _load_yaml_scenarios():
    scenario_files = sorted(SCENARIO_DIR.glob("*.yaml"))
    assert scenario_files, f"No YAML scenarios found in {SCENARIO_DIR}"
    return scenario_files


def test_mission_scenarios_have_supported_objective_types():
    scenario_files = _load_yaml_scenarios()
    covered_names = {path.name for path in scenario_files}
    assert EXPECTED_MISSION_SCENARIOS.issubset(covered_names)

    for scenario_path in scenario_files:
        data = yaml.safe_load(scenario_path.read_text())
        assert data.get("mission"), f"Scenario {scenario_path.name} is missing a mission block"
        objectives = data["mission"].get("objectives", [])
        assert objectives, f"Scenario {scenario_path.name} has no mission objectives"

        for objective in objectives:
            obj_type = objective.get("type")
            assert obj_type, f"Scenario {scenario_path.name} has objective without type"
            assert ObjectiveType(obj_type)


def test_objective_checks_can_complete_with_minimal_state():
    class DummyContact:
        def __init__(self, detection_method: str = "active", confidence: float = 1.0):
            self.detection_method = detection_method
            self.confidence = confidence

    class DummySensors:
        def __init__(self, contacts=None):
            self._contacts = contacts or {}

        def get_contact(self, target_id):
            return self._contacts.get(target_id)

    class DummyShip:
        def __init__(self, ship_id, position):
            self.id = ship_id
            self.position = position
            self.systems = {}

    player_ship = DummyShip("player", {"x": 0, "y": 0, "z": 0})
    target_ship = DummyShip("target", {"x": 0, "y": 0, "z": 0})

    sim = SimpleNamespace(time=10, ships={"player": player_ship, "target": target_ship})

    reach_range = Objective(
        obj_id="reach_range",
        obj_type=ObjectiveType.REACH_RANGE,
        description="reach range",
        params={"target": "target", "range": 100},
    )
    assert reach_range.check(sim, player_ship)
    assert reach_range.status == ObjectiveStatus.COMPLETED

    destroy_target = Objective(
        obj_id="destroy_target",
        obj_type=ObjectiveType.DESTROY_TARGET,
        description="destroy target",
        params={"target": "missing_target"},
    )
    assert destroy_target.check(sim, player_ship)
    assert destroy_target.status == ObjectiveStatus.COMPLETED

    avoid_detection = Objective(
        obj_id="avoid_detection",
        obj_type=ObjectiveType.AVOID_DETECTION,
        description="avoid detection",
        params={"time": 5, "detection_range": 1000},
    )

    enemy_ship = DummyShip("enemy", {"x": 10000, "y": 0, "z": 0})
    enemy_ship.systems["sensors"] = DummySensors()
    sim.ships["enemy"] = enemy_ship

    assert avoid_detection.check(sim, player_ship)
    assert avoid_detection.status == ObjectiveStatus.COMPLETED

    scan_target = Objective(
        obj_id="scan_target",
        obj_type=ObjectiveType.SCAN_TARGET,
        description="scan target",
        params={"target": "target"},
    )
    player_ship.systems["sensors"] = DummySensors(
        contacts={"target": DummyContact(detection_method="active", confidence=0.95)}
    )
    assert scan_target.check(sim, player_ship)
    assert scan_target.status == ObjectiveStatus.COMPLETED
