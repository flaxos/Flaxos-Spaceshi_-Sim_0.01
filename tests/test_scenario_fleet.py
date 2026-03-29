# tests/test_scenario_fleet.py
"""
Tests for Scenario 12: Fleet Engagement — Combined Arms.

Validates:
1. Scenario YAML loads cleanly and all 7 ships spawn.
2. Fleet definitions are parsed (2 fleets with correct membership).
3. Player ship is a destroyer with expected systems.
4. AI-controlled escorts have correct behavior profiles.
5. Enemy fleet ships have MCRN faction and combat/escort AI roles.
6. Mission objectives parse with correct types and targets.
7. Victory tier evaluation logic (total, tactical, partial).
8. Flagship survival failure condition triggers correctly.
9. Station has no propulsion (stationary target).
"""

import math
import os
import sys
import logging
import pytest

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

SCENARIO_PATH = os.path.join(ROOT, "scenarios", "12_fleet_battle.yaml")
DT = 0.1

PLAYER_ID = "player"
ESCORT_IDS = ["escort_wolf", "escort_dagger"]
ENEMY_IDS = ["mcrn_frigate_1", "mcrn_frigate_2", "mcrn_corvette_1"]
STATION_ID = "deimos_station"

ALL_SHIP_IDS = [PLAYER_ID] + ESCORT_IDS + ENEMY_IDS + [STATION_ID]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_scenario_data():
    """Load raw scenario data via ScenarioLoader (no simulator)."""
    from hybrid.scenarios.loader import ScenarioLoader
    return ScenarioLoader.load(SCENARIO_PATH)


def _build_sim():
    """Create a Simulator from the scenario, start it.

    Returns:
        (runner, sim) tuple.
    """
    from hybrid_runner import HybridRunner

    runner = HybridRunner(dt=DT)
    count = runner._load_scenario_file(SCENARIO_PATH)
    assert count >= len(ALL_SHIP_IDS), (
        f"Expected at least {len(ALL_SHIP_IDS)} ships, got {count}"
    )

    sim = runner.simulator
    sim.start()
    return runner, sim


def _distance(ship_a, ship_b) -> float:
    """Euclidean distance between two ships in metres."""
    dx = ship_a.position["x"] - ship_b.position["x"]
    dy = ship_a.position["y"] - ship_b.position["y"]
    dz = ship_a.position["z"] - ship_b.position["z"]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


# ---------------------------------------------------------------------------
# Test 1: Scenario loads and all ships spawn
# ---------------------------------------------------------------------------

def test_scenario_loads_all_ships():
    """All 7 ships (3 UNSA + 3 MCRN + 1 station) spawn from the YAML."""
    runner, sim = _build_sim()

    for ship_id in ALL_SHIP_IDS:
        assert ship_id in sim.ships, (
            f"Ship '{ship_id}' missing from simulator. "
            f"Present: {list(sim.ships.keys())}"
        )


# ---------------------------------------------------------------------------
# Test 2: Fleet definitions are parsed
# ---------------------------------------------------------------------------

def test_fleet_definitions_parsed():
    """Scenario data contains 2 fleet definitions with correct members."""
    data = _load_scenario_data()

    fleets = data.get("fleets", [])
    assert len(fleets) == 2, f"Expected 2 fleets, got {len(fleets)}"

    fleet_ids = {f["fleet_id"] for f in fleets}
    assert "task_force_hammer" in fleet_ids
    assert "deimos_defense" in fleet_ids

    # Check membership
    for fleet in fleets:
        if fleet["fleet_id"] == "task_force_hammer":
            assert PLAYER_ID in fleet["ships"]
            assert "escort_wolf" in fleet["ships"]
            assert "escort_dagger" in fleet["ships"]
            assert fleet["flagship"] == PLAYER_ID
        elif fleet["fleet_id"] == "deimos_defense":
            assert "mcrn_frigate_1" in fleet["ships"]
            assert "mcrn_frigate_2" in fleet["ships"]
            assert "mcrn_corvette_1" in fleet["ships"]
            assert fleet["flagship"] == "mcrn_frigate_1"


# ---------------------------------------------------------------------------
# Test 3: Player ship is a destroyer with expected combat systems
# ---------------------------------------------------------------------------

def test_player_is_destroyer_with_combat_systems():
    """Player ship resolves as destroyer class with railguns and PDCs."""
    runner, sim = _build_sim()
    player = sim.ships[PLAYER_ID]

    # Ship class check
    class_type = getattr(player, "class_type", getattr(player, "ship_class", ""))
    assert "destroyer" in class_type.lower(), (
        f"Player should be a destroyer, got '{class_type}'"
    )

    # Player is NOT AI-controlled (player-controlled means ai_enabled=False)
    assert not getattr(player, "ai_enabled", True), (
        "Player ship should not be AI-enabled (it is player-controlled)"
    )

    # Has essential combat systems
    assert "combat" in player.systems, "Player missing combat system"
    assert "sensors" in player.systems, "Player missing sensors system"
    assert "targeting" in player.systems, "Player missing targeting system"
    assert "navigation" in player.systems, "Player missing navigation system"
    assert "propulsion" in player.systems, "Player missing propulsion system"


# ---------------------------------------------------------------------------
# Test 4: AI escorts have correct behavior profiles
# ---------------------------------------------------------------------------

def test_escort_ai_profiles():
    """Escort corvettes have escort role and protect the player."""
    runner, sim = _build_sim()

    for escort_id in ESCORT_IDS:
        ship = sim.ships[escort_id]

        # Must be AI-enabled
        ai = getattr(ship, "ai_controller", None)
        assert ai is not None, (
            f"Escort '{escort_id}' should have an AI controller"
        )

        # Must have escort profile
        assert ai.profile.role == "escort", (
            f"Escort '{escort_id}' should have role 'escort', "
            f"got '{ai.profile.role}'"
        )

        # Must protect the player ship
        assert ai.profile.protect_target == PLAYER_ID, (
            f"Escort '{escort_id}' should protect '{PLAYER_ID}', "
            f"got '{ai.profile.protect_target}'"
        )

        # Faction check
        assert getattr(ship, "faction", "") == "unsa", (
            f"Escort '{escort_id}' should be UNSA faction"
        )


# ---------------------------------------------------------------------------
# Test 5: Enemy fleet has MCRN faction and correct AI roles
# ---------------------------------------------------------------------------

def test_enemy_fleet_faction_and_roles():
    """MCRN ships have correct faction and AI behavior roles."""
    runner, sim = _build_sim()

    for enemy_id in ENEMY_IDS:
        ship = sim.ships[enemy_id]

        # Faction
        assert getattr(ship, "faction", "") == "mcrn", (
            f"Enemy '{enemy_id}' should be MCRN faction, "
            f"got '{getattr(ship, 'faction', '')}'"
        )

        # Must be AI-enabled
        ai = getattr(ship, "ai_controller", None)
        assert ai is not None, (
            f"Enemy '{enemy_id}' should have an AI controller"
        )

    # Frigates should be combat role
    for frig_id in ["mcrn_frigate_1", "mcrn_frigate_2"]:
        ai = sim.ships[frig_id].ai_controller
        assert ai.profile.role == "combat", (
            f"Frigate '{frig_id}' should have role 'combat', "
            f"got '{ai.profile.role}'"
        )

    # Corvette escort should protect the station
    corvette_ai = sim.ships["mcrn_corvette_1"].ai_controller
    assert corvette_ai.profile.role == "escort", (
        f"MCRN corvette should have role 'escort', "
        f"got '{corvette_ai.profile.role}'"
    )
    assert corvette_ai.profile.protect_target == STATION_ID, (
        f"MCRN corvette should protect station, "
        f"got '{corvette_ai.profile.protect_target}'"
    )


# ---------------------------------------------------------------------------
# Test 6: Faction hostility is correct (UNSA vs MCRN)
# ---------------------------------------------------------------------------

def test_faction_hostility():
    """UNSA and MCRN factions are hostile to each other."""
    from hybrid.fleet.faction_rules import are_hostile

    assert are_hostile("unsa", "mcrn"), "UNSA and MCRN should be hostile"
    assert are_hostile("mcrn", "unsa"), "Hostility should be symmetric"
    assert not are_hostile("unsa", "unsa"), "Same faction should not be hostile"
    assert not are_hostile("mcrn", "mcrn"), "Same faction should not be hostile"


# ---------------------------------------------------------------------------
# Test 7: Mission objectives parse with correct types
# ---------------------------------------------------------------------------

def test_mission_objectives_parse():
    """Mission has the expected objectives with correct types and targets."""
    data = _load_scenario_data()
    mission = data.get("mission")
    assert mission is not None, "Scenario should have a mission"

    # Get objectives from the tracker
    objectives = mission.tracker.objectives

    # Required objective: flagship survives
    assert "flagship_survives" in objectives
    flagship_obj = objectives["flagship_survives"]
    assert flagship_obj.required is True
    assert flagship_obj.params.get("target") == PLAYER_ID

    # Optional kill objectives
    kill_ids = ["kill_frigate_1", "kill_frigate_2", "kill_corvette"]
    for kid in kill_ids:
        assert kid in objectives, f"Missing objective '{kid}'"
        assert objectives[kid].required is False

    # Station destroy objective
    assert "destroy_station" in objectives
    assert objectives["destroy_station"].params.get("target") == STATION_ID
    assert objectives["destroy_station"].required is False


# ---------------------------------------------------------------------------
# Test 8: Victory tier evaluation
# ---------------------------------------------------------------------------

def test_victory_tier_evaluation():
    """Victory tiers are correctly determined from objective completion.

    This tests the tier logic that would run after the mission framework
    evaluates individual objectives.
    """
    from hybrid.scenarios.objectives import Objective, ObjectiveType, ObjectiveStatus

    # Build mock objectives matching the scenario
    objectives = {
        "destroy_station": Objective("destroy_station", ObjectiveType.DESTROY_TARGET,
                                     "Destroy station", {"target": STATION_ID}, required=False),
        "kill_frigate_1": Objective("kill_frigate_1", ObjectiveType.MISSION_KILL,
                                   "Kill frigate 1", {"target": "mcrn_frigate_1"}, required=False),
        "kill_frigate_2": Objective("kill_frigate_2", ObjectiveType.MISSION_KILL,
                                   "Kill frigate 2", {"target": "mcrn_frigate_2"}, required=False),
        "kill_corvette": Objective("kill_corvette", ObjectiveType.MISSION_KILL,
                                  "Kill corvette", {"target": "mcrn_corvette_1"}, required=False),
    }

    def _evaluate_tier(objs):
        """Determine victory tier from completed objectives."""
        completed = {oid for oid, obj in objs.items()
                     if obj.status == ObjectiveStatus.COMPLETED}

        if "destroy_station" in completed:
            return "total"
        kill_objs = {"kill_frigate_1", "kill_frigate_2", "kill_corvette"}
        if kill_objs.issubset(completed):
            return "tactical"
        kill_count = len(kill_objs & completed)
        if kill_count >= 2:
            return "partial"
        return "draw"

    # No completions -> draw
    assert _evaluate_tier(objectives) == "draw"

    # 1 kill -> still draw
    objectives["kill_frigate_1"].status = ObjectiveStatus.COMPLETED
    assert _evaluate_tier(objectives) == "draw"

    # 2 kills -> partial victory
    objectives["kill_corvette"].status = ObjectiveStatus.COMPLETED
    assert _evaluate_tier(objectives) == "partial"

    # All 3 kills -> tactical victory
    objectives["kill_frigate_2"].status = ObjectiveStatus.COMPLETED
    assert _evaluate_tier(objectives) == "tactical"

    # Station destroyed -> total victory (overrides tactical)
    objectives["destroy_station"].status = ObjectiveStatus.COMPLETED
    assert _evaluate_tier(objectives) == "total"


# ---------------------------------------------------------------------------
# Test 9: Station has no propulsion (stationary target)
# ---------------------------------------------------------------------------

def test_station_is_stationary():
    """Deimos station has no propulsion and starts at origin."""
    runner, sim = _build_sim()
    station = sim.ships[STATION_ID]

    # Station at origin
    assert abs(station.position["x"]) < 1.0
    assert abs(station.position["y"]) < 1.0
    assert abs(station.position["z"]) < 1.0

    # Station is stationary
    vx = station.velocity.get("x", 0)
    vy = station.velocity.get("y", 0)
    vz = station.velocity.get("z", 0)
    speed = math.sqrt(vx**2 + vy**2 + vz**2)
    assert speed < 0.1, f"Station should be stationary, speed={speed:.3f}"


# ---------------------------------------------------------------------------
# Test 10: Initial fleet geometry is reasonable
# ---------------------------------------------------------------------------

def test_initial_fleet_geometry():
    """Player task force starts ~200km from station; enemy near station."""
    runner, sim = _build_sim()

    player = sim.ships[PLAYER_ID]
    station = sim.ships[STATION_ID]

    # Player starts ~200km from station
    player_range = _distance(player, station)
    assert 195_000 < player_range < 210_000, (
        f"Player should start ~200km from station, got {player_range/1000:.1f}km"
    )

    # Escorts are near the player (within 10km)
    for eid in ESCORT_IDS:
        escort = sim.ships[eid]
        escort_range = _distance(player, escort)
        assert escort_range < 10_000, (
            f"Escort '{eid}' should be within 10km of player, "
            f"got {escort_range/1000:.1f}km"
        )

    # Enemy ships are near the station (within 20km)
    for enemy_id in ENEMY_IDS:
        enemy = sim.ships[enemy_id]
        enemy_range = _distance(enemy, station)
        assert enemy_range < 20_000, (
            f"Enemy '{enemy_id}' should be within 20km of station, "
            f"got {enemy_range/1000:.1f}km"
        )


# ---------------------------------------------------------------------------
# Test 11: AI controllers initialize after a few ticks
# ---------------------------------------------------------------------------

def test_ai_controllers_active():
    """AI controllers are present and have initial state after warm-up ticks."""
    runner, sim = _build_sim()

    # Tick a few times to let AI initialize
    for _ in range(50):
        sim.tick()

    ai_ships = ESCORT_IDS + ENEMY_IDS
    for ship_id in ai_ships:
        ship = sim.ships[ship_id]
        ai = getattr(ship, "ai_controller", None)
        assert ai is not None, f"Ship '{ship_id}' should have AI controller"

        state = ai.get_state()
        assert "behavior" in state, (
            f"AI state for '{ship_id}' should have 'behavior' key"
        )
        assert "role" in state, (
            f"AI state for '{ship_id}' should have 'role' key"
        )


# ---------------------------------------------------------------------------
# Test 12: Mission time limit is set
# ---------------------------------------------------------------------------

def test_mission_has_time_limit():
    """Mission has a 10-minute (600s) time limit."""
    data = _load_scenario_data()
    mission = data.get("mission")
    assert mission is not None
    assert mission.time_limit == 600, (
        f"Expected 600s time limit, got {mission.time_limit}"
    )


# ---------------------------------------------------------------------------
# Test 13: Surviving until time limit = mission success, not failure
# ---------------------------------------------------------------------------

def test_survive_until_time_limit_succeeds():
    """When avoid_mission_kill is the only required objective and the timer
    expires with the player alive, the mission should be SUCCESS.

    Regression test for the fleet_battle win condition bug where
    avoid_mission_kill stayed IN_PROGRESS forever (no other required
    objectives to gate on), so time expiry always meant FAILURE.
    """
    from hybrid.scenarios.objectives import (
        Objective, ObjectiveType, ObjectiveStatus, ObjectiveTracker,
    )
    from hybrid.scenarios.mission import Mission

    # Build a minimal mission that mirrors fleet_battle's structure:
    # one required avoid_mission_kill, several optional kill objectives.
    objectives = [
        Objective("flagship_survives", ObjectiveType.AVOID_MISSION_KILL,
                  "Keep the flagship operational",
                  {"target": "player"}, required=True),
        Objective("kill_enemy", ObjectiveType.MISSION_KILL,
                  "Neutralize enemy", {"target": "enemy_1"}, required=False),
    ]

    mission = Mission(
        name="Test Fleet Battle",
        description="Survive the engagement",
        objectives=objectives,
        time_limit=600,
    )
    mission.start(sim_time=0.0)

    # Simulate a mock sim where the player is alive and time exceeds limit
    class MockDamageModel:
        def is_mission_kill(self):
            return False
        def get_degradation_factor(self, sys):
            return 1.0

    class MockShip:
        def __init__(self, ship_id):
            self.id = ship_id
            self.position = {"x": 0, "y": 0, "z": 0}
            self.velocity = {"x": 0, "y": 0, "z": 0}
            self.hull_integrity = 100
            self.damage_model = MockDamageModel()
        def is_destroyed(self):
            return False

    class MockSim:
        def __init__(self, t):
            self.time = t
            self.ships = {
                "player": MockShip("player"),
                "enemy_1": MockShip("enemy_1"),
            }

    # Time just before limit -- mission should still be in progress
    sim_before = MockSim(599.0)
    mission.update(sim_before, sim_before.ships["player"])
    assert mission.tracker.mission_status == "in_progress", (
        "Mission should be in_progress before time limit"
    )

    # Time past limit -- player survived, mission should succeed
    sim_after = MockSim(601.0)
    mission.update(sim_after, sim_after.ships["player"])

    flagship_obj = mission.tracker.objectives["flagship_survives"]
    assert flagship_obj.status == ObjectiveStatus.COMPLETED, (
        f"flagship_survives should be COMPLETED after surviving the time limit, "
        f"got {flagship_obj.status}"
    )
    assert mission.tracker.mission_status == "success", (
        f"Mission should be SUCCESS when player survives the time limit, "
        f"got '{mission.tracker.mission_status}'"
    )


# ---------------------------------------------------------------------------
# Test 14: Player killed before time limit = mission failure (unchanged)
# ---------------------------------------------------------------------------

def test_player_killed_before_time_limit_fails():
    """If the player is mission-killed before time expires, the mission
    should still fail -- the fix must not break this path.
    """
    from hybrid.scenarios.objectives import (
        Objective, ObjectiveType, ObjectiveStatus,
    )
    from hybrid.scenarios.mission import Mission

    objectives = [
        Objective("flagship_survives", ObjectiveType.AVOID_MISSION_KILL,
                  "Keep the flagship operational",
                  {"target": "player"}, required=True),
    ]

    mission = Mission(
        name="Test Fleet Battle Fail",
        description="Survive the engagement",
        objectives=objectives,
        time_limit=600,
    )
    mission.start(sim_time=0.0)

    class MockDamageModel:
        def __init__(self, killed=False):
            self._killed = killed
        def is_mission_kill(self):
            return self._killed
        def get_degradation_factor(self, sys):
            return 0.0 if self._killed else 1.0

    class MockShip:
        def __init__(self, ship_id, killed=False):
            self.id = ship_id
            self.position = {"x": 0, "y": 0, "z": 0}
            self.velocity = {"x": 0, "y": 0, "z": 0}
            self.hull_integrity = 0 if killed else 100
            self.damage_model = MockDamageModel(killed)
        def is_destroyed(self):
            return self.hull_integrity <= 0

    class MockSim:
        def __init__(self, t, player_killed=False):
            self.time = t
            self.ships = {
                "player": MockShip("player", killed=player_killed),
            }

    # Player gets mission-killed at t=300
    sim = MockSim(300.0, player_killed=True)
    mission.update(sim, sim.ships["player"])

    flagship_obj = mission.tracker.objectives["flagship_survives"]
    assert flagship_obj.status == ObjectiveStatus.FAILED, (
        f"flagship_survives should be FAILED when player is killed, "
        f"got {flagship_obj.status}"
    )
    assert mission.tracker.mission_status == "failure", (
        f"Mission should be FAILURE when player is killed, "
        f"got '{mission.tracker.mission_status}'"
    )
