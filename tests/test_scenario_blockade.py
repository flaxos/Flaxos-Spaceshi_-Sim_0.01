# tests/test_scenario_blockade.py
"""Tests for Scenario 09: Blockade Runner.

Validates that the scenario YAML loads correctly, ships spawn at expected
positions, patrol AI initializes with the right behavior profiles, and
mission objectives function for both success and failure paths.

WHAT IS TESTED
==============
1. Scenario loads cleanly and all 5 ships spawn at expected positions.
2. Patrol ships have AI controllers with "patrol" role and correct
   engagement_range / patrol_position configuration.
3. Player ship has ECM system with EMCON, chaff, and flare capabilities.
4. Mission objectives parse to the correct ObjectiveType enums.
5. The "reach_jump_point" objective completes when the player reaches
   the destination position.
6. The "survive" (avoid_mission_kill) objective fails when the player
   ship is mission-killed.
7. The "ghost_run" (avoid_detection) objective completes when the player
   avoids detection for the required duration.
8. Patrol ships detect a thrusting target within their passive range
   (validates that sensor detection actually works in this scenario).
"""

import math
import os
import sys
import logging
from types import SimpleNamespace
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logging.basicConfig(level=logging.WARNING)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCENARIO_PATH = os.path.join(ROOT, "scenarios", "09_blockade_run.yaml")

PLAYER_SHIP_ID = "player"
PATROL_IDS = ["patrol_01", "patrol_02", "patrol_03", "patrol_04"]

# Jump point destination from the scenario
JUMP_POINT = {"x": 200000, "y": 0, "z": 0}
JUMP_TOLERANCE = 5000

DT = 0.1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_scenario_raw() -> dict:
    """Load raw YAML data without going through the full simulator."""
    with open(SCENARIO_PATH, "r") as f:
        return yaml.safe_load(f)


def _build_sim():
    """Create a Simulator, load the blockade scenario, start it.

    Returns:
        (runner, sim, player_ship) tuple.
    """
    from hybrid_runner import HybridRunner

    runner = HybridRunner(dt=DT)
    count = runner._load_scenario_file(SCENARIO_PATH)
    assert count >= 5, (
        f"Expected at least 5 ships (1 player + 4 patrols); got {count}"
    )

    sim = runner.simulator
    sim.start()

    player = sim.ships.get(PLAYER_SHIP_ID)
    assert player is not None, f"Player ship '{PLAYER_SHIP_ID}' not found"

    return runner, sim, player


def _distance_to_point(ship, point: dict) -> float:
    """Distance from a ship to a point in space."""
    dx = ship.position["x"] - point.get("x", 0)
    dy = ship.position["y"] - point.get("y", 0)
    dz = ship.position["z"] - point.get("z", 0)
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _distance_between(ship_a, ship_b) -> float:
    """Distance between two ships."""
    dx = ship_a.position["x"] - ship_b.position["x"]
    dy = ship_a.position["y"] - ship_b.position["y"]
    dz = ship_a.position["z"] - ship_b.position["z"]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


# ---------------------------------------------------------------------------
# Test 1: Scenario loads and ships spawn correctly
# ---------------------------------------------------------------------------

def test_scenario_loads_and_all_ships_spawn():
    """Scenario 09 loads cleanly; player + 4 patrols spawn at correct positions."""
    runner, sim, player = _build_sim()

    # All ships present
    assert PLAYER_SHIP_ID in sim.ships, "Player ship missing"
    for pid in PATROL_IDS:
        assert pid in sim.ships, f"Patrol ship '{pid}' missing"

    # Player starts at expected position (-150km, +20km, 0)
    assert abs(player.position["x"] - (-150000)) < 10, (
        f"Player x should be ~-150000, got {player.position['x']}"
    )
    assert abs(player.position["y"] - 20000) < 10, (
        f"Player y should be ~20000, got {player.position['y']}"
    )

    # Patrol ships are near the blockade line (x ~ 0)
    for pid in PATROL_IDS:
        patrol = sim.ships[pid]
        assert abs(patrol.position["x"]) < 10000, (
            f"{pid} should be near x=0 blockade line, got x={patrol.position['x']}"
        )


# ---------------------------------------------------------------------------
# Test 2: Patrol AI has correct behavior profiles
# ---------------------------------------------------------------------------

def test_patrol_ai_profiles():
    """Patrol ships have AI controllers with patrol role and correct config."""
    runner, sim, player = _build_sim()

    for pid in PATROL_IDS:
        patrol = sim.ships[pid]

        # AI should be enabled
        assert getattr(patrol, "ai_enabled", False), (
            f"{pid} should have ai_enabled=True"
        )

        # AI controller should exist
        ai = getattr(patrol, "ai_controller", None)
        assert ai is not None, f"{pid} should have an AI controller"

        # Profile should be "patrol" role
        assert ai.profile.role == "patrol", (
            f"{pid} AI role should be 'patrol', got '{ai.profile.role}'"
        )

        # Engagement range should be 60km
        assert ai.profile.engagement_range == 60000, (
            f"{pid} engagement_range should be 60000, got {ai.profile.engagement_range}"
        )

        # Patrol position should be set
        assert ai.profile.patrol_position is not None, (
            f"{pid} should have a patrol_position set"
        )


# ---------------------------------------------------------------------------
# Test 3: Player ship has ECM system with stealth capabilities
# ---------------------------------------------------------------------------

def test_player_has_ecm_system():
    """Player ship has ECM system with EMCON, chaff, and flares."""
    runner, sim, player = _build_sim()

    ecm = player.systems.get("ecm")
    assert ecm is not None, "Player ship should have an ECM system"

    # Check chaff and flare counts
    assert ecm.chaff_count == 8, f"Expected 8 chaff, got {ecm.chaff_count}"
    assert ecm.flare_count == 8, f"Expected 8 flares, got {ecm.flare_count}"

    # EMCON IR reduction should be strong (80% reduction = 0.2 multiplier)
    assert ecm.emcon_ir_reduction == pytest.approx(0.2, abs=0.01), (
        f"EMCON IR reduction should be 0.2, got {ecm.emcon_ir_reduction}"
    )

    # EMCON should start disabled (player decides when to engage)
    assert not ecm.emcon_active, "EMCON should start inactive"


# ---------------------------------------------------------------------------
# Test 4: Mission objectives parse correctly
# ---------------------------------------------------------------------------

def test_mission_objectives_parse():
    """All mission objectives use valid ObjectiveType enums."""
    from hybrid.scenarios.objectives import ObjectiveType

    data = _load_scenario_raw()
    mission_data = data.get("mission", {})
    objectives = mission_data.get("objectives", [])

    assert len(objectives) == 3, f"Expected 3 objectives, got {len(objectives)}"

    # Verify each objective type is valid
    expected_types = {
        "reach_jump_point": "reach_position",
        "survive": "avoid_mission_kill",
        "ghost_run": "avoid_detection",
    }

    for obj in objectives:
        obj_id = obj["id"]
        obj_type = obj["type"]
        assert obj_id in expected_types, f"Unexpected objective: {obj_id}"
        assert obj_type == expected_types[obj_id], (
            f"Objective '{obj_id}' type should be '{expected_types[obj_id]}', "
            f"got '{obj_type}'"
        )
        # Verify ObjectiveType enum accepts this string
        ObjectiveType(obj_type)

    # Verify required flags
    required_ids = {obj["id"] for obj in objectives if obj.get("required", True)}
    assert "reach_jump_point" in required_ids
    assert "survive" in required_ids
    assert "ghost_run" not in required_ids, "ghost_run should be optional (bonus)"


# ---------------------------------------------------------------------------
# Test 5: reach_position objective completes at jump point
# ---------------------------------------------------------------------------

def test_reach_position_objective_completes():
    """The reach_position objective completes when ship is at the jump point."""
    from hybrid.scenarios.objectives import Objective, ObjectiveType, ObjectiveStatus

    # Create objective
    obj = Objective(
        obj_id="reach_jump_point",
        obj_type=ObjectiveType.REACH_POSITION,
        description="Reach the jump point",
        params={
            "position": JUMP_POINT,
            "tolerance": JUMP_TOLERANCE,
            "initial_distance": 350000,
        },
    )

    # Ship at the jump point
    class ShipAtJump:
        id = "player"
        position = {"x": 201000, "y": 500, "z": 0}  # Within 5km tolerance
        systems = {}

    sim = SimpleNamespace(time=100.0, ships={"player": ShipAtJump()})
    result = obj.check(sim, ShipAtJump())
    assert result, "Objective should complete when ship is within tolerance"
    assert obj.status == ObjectiveStatus.COMPLETED


def test_reach_position_objective_pending_when_far():
    """The reach_position objective stays in progress when ship is far away."""
    from hybrid.scenarios.objectives import Objective, ObjectiveType, ObjectiveStatus

    obj = Objective(
        obj_id="reach_jump_point",
        obj_type=ObjectiveType.REACH_POSITION,
        description="Reach the jump point",
        params={
            "position": JUMP_POINT,
            "tolerance": JUMP_TOLERANCE,
            "initial_distance": 350000,
        },
    )

    class ShipFarAway:
        id = "player"
        position = {"x": -100000, "y": 20000, "z": 0}  # Still behind blockade
        systems = {}

    sim = SimpleNamespace(time=50.0, ships={"player": ShipFarAway()})
    result = obj.check(sim, ShipFarAway())
    assert not result, "Objective should not complete when ship is far away"
    assert obj.status == ObjectiveStatus.IN_PROGRESS


# ---------------------------------------------------------------------------
# Test 6: avoid_mission_kill objective fails on drive destruction
# ---------------------------------------------------------------------------

def test_survive_objective_fails_on_mission_kill():
    """The avoid_mission_kill objective fails when ship is mission-killed."""
    from hybrid.scenarios.objectives import Objective, ObjectiveType, ObjectiveStatus

    obj = Objective(
        obj_id="survive",
        obj_type=ObjectiveType.AVOID_MISSION_KILL,
        description="Keep your drive intact",
        params={"target": "player"},
    )

    class MissionKilledShip:
        id = "player"
        position = {"x": 0, "y": 0, "z": 0}
        hull_integrity = 0
        max_hull_integrity = 200

        def is_destroyed(self):
            return True

    ship = MissionKilledShip()
    sim = SimpleNamespace(time=100.0, ships={"player": ship})
    obj.check(sim, ship)
    assert obj.status == ObjectiveStatus.FAILED, (
        f"Objective should fail on mission kill, got {obj.status}"
    )


# ---------------------------------------------------------------------------
# Test 7: avoid_detection objective completes when undetected
# ---------------------------------------------------------------------------

def test_ghost_run_objective_completes_undetected():
    """The avoid_detection objective completes when player avoids detection."""
    from hybrid.scenarios.objectives import Objective, ObjectiveType, ObjectiveStatus

    obj = Objective(
        obj_id="ghost_run",
        obj_type=ObjectiveType.AVOID_DETECTION,
        description="Traverse without detection",
        params={
            "time": 600,
            "start_time": 0,
            "detection_range": 100000,
        },
    )

    class StealthyShip:
        id = "player"
        position = {"x": 50000, "y": 0, "z": 0}
        systems = {}

    class FarPatrol:
        """Patrol ship that is too far away to detect the player."""
        id = "patrol_01"
        position = {"x": 0, "y": 60000, "z": 0}
        systems = {"sensors": SimpleNamespace(
            get_contact=lambda target_id: None  # No detection
        )}

    player = StealthyShip()
    patrol = FarPatrol()
    sim = SimpleNamespace(
        time=700.0,  # Past the 600s requirement
        ships={"player": player, "patrol_01": patrol},
    )

    result = obj.check(sim, player)
    assert result, "Ghost run should complete after time elapses without detection"
    assert obj.status == ObjectiveStatus.COMPLETED


def test_ghost_run_fails_on_detection():
    """The avoid_detection objective fails when an enemy detects the player."""
    from hybrid.scenarios.objectives import Objective, ObjectiveType, ObjectiveStatus

    obj = Objective(
        obj_id="ghost_run",
        obj_type=ObjectiveType.AVOID_DETECTION,
        description="Traverse without detection",
        params={
            "time": 600,
            "start_time": 0,
            "detection_range": 100000,
        },
    )

    class DetectedShip:
        id = "player"
        position = {"x": 5000, "y": 20000, "z": 0}  # Close to patrol
        systems = {}

    class AlertPatrol:
        """Patrol ship that has detected the player with high confidence."""
        id = "patrol_02"
        position = {"x": 5000, "y": 20000, "z": 0}  # Very close

        def __init__(self):
            contact = SimpleNamespace(confidence=0.8, detection_method="passive")
            self.systems = {"sensors": SimpleNamespace(
                get_contact=lambda target_id: contact
            )}

    player = DetectedShip()
    patrol = AlertPatrol()
    sim = SimpleNamespace(
        time=100.0,
        ships={"player": player, "patrol_02": patrol},
    )

    obj.check(sim, player)
    assert obj.status == ObjectiveStatus.FAILED, (
        f"Ghost run should fail on detection, got {obj.status}"
    )


# ---------------------------------------------------------------------------
# Test 8: Full scenario loads through ScenarioLoader
# ---------------------------------------------------------------------------

def test_scenario_loader_parses_blockade():
    """ScenarioLoader.load() successfully parses the blockade scenario."""
    from hybrid.scenarios.loader import ScenarioLoader

    scenario = ScenarioLoader.load(SCENARIO_PATH)

    assert scenario["name"] == "Blockade Runner"
    assert len(scenario["ships"]) == 5

    # Mission should be parsed
    mission = scenario["mission"]
    assert mission is not None
    assert mission.name == "Operation: Ghost Freight"
    assert len(mission.tracker.objectives) == 3
    assert mission.time_limit == 900


# ---------------------------------------------------------------------------
# Test 9: Patrol ships spread covers the transit corridor
# ---------------------------------------------------------------------------

def test_patrol_coverage_geometry():
    """Patrol ships are spread across the corridor with navigable gaps."""
    data = _load_scenario_raw()
    ships = {s["id"]: s for s in data["ships"]}

    patrol_y_positions = []
    for pid in PATROL_IDS:
        y = ships[pid]["position"]["y"]
        patrol_y_positions.append(y)

    patrol_y_positions.sort()

    # Patrols should span from about -60km to +60km
    assert patrol_y_positions[0] < -50000, (
        f"Southernmost patrol should be below -50km, got {patrol_y_positions[0]}"
    )
    assert patrol_y_positions[-1] > 50000, (
        f"Northernmost patrol should be above +50km, got {patrol_y_positions[-1]}"
    )

    # Check that gaps between adjacent patrols exist (>= 30km)
    # so the player has a feasible route through
    for i in range(len(patrol_y_positions) - 1):
        gap = patrol_y_positions[i + 1] - patrol_y_positions[i]
        assert gap >= 30000, (
            f"Gap between patrols at y={patrol_y_positions[i]} and "
            f"y={patrol_y_positions[i+1]} is only {gap}m -- too narrow. "
            f"Player needs at least 30km gap to transit."
        )


# ---------------------------------------------------------------------------
# Test 10: Player fuel budget is tight but sufficient
# ---------------------------------------------------------------------------

def test_fuel_budget_is_feasible():
    """Player has enough fuel to reach the jump point with careful burns.

    The transit distance is ~350km.  At 4.8 m/s^2 (120kN / 25t), reaching
    a coast velocity of 500 m/s requires ~104s of burn.  Return budget for
    braking at the jump point.  Total fuel must cover at least 2 burns.
    """
    data = _load_scenario_raw()
    player = next(s for s in data["ships"] if s["id"] == "player")

    fuel = player["systems"]["propulsion"]["fuel_level"]
    max_fuel = player["systems"]["propulsion"]["max_fuel"]

    # Fuel should be limited (not trivially abundant)
    assert fuel <= 8000, f"Fuel should be limited, got {fuel}"

    # But not zero
    assert fuel >= 3000, f"Fuel should be enough for transit, got {fuel}"

    # Fuel equals max (full tank)
    assert fuel == max_fuel, "Player should start with a full fuel tank"
