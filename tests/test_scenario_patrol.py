# tests/test_scenario_patrol.py
"""Tests for Scenario 11: Patrol & Ambush Encounter.

Validates:
  1. Scenario YAML loads without errors
  2. All ships spawn at expected positions with correct attributes
  3. Player starts mid-patrol: 60% fuel, cruising velocity, full weapons
  4. NPC ships have correct AI behavior profiles
  5. All mission objectives use valid ObjectiveType enum values
  6. Sensor detection works for the unknown contact
  7. Mission tracker initializes and updates without error
  8. Fuel constraint is meaningful (player starts at 60% capacity)
  9. Pirate ambusher has combat profile with high aggression
  10. Friendly vessel has freighter profile (non-combatant)
"""

from __future__ import annotations

import math
import os
import sys
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.WARNING)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCENARIO_PATH = ROOT / "scenarios" / "11_patrol_ambush.yaml"
PLAYER_ID = "player"
UNKNOWN_ID = "unknown_contact"
PIRATE_ID = "pirate_ambusher"
FRIENDLY_ID = "friendly_vessel"
DT = 0.1

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_raw_yaml() -> dict:
    """Load the raw YAML data without going through the full scenario loader."""
    return yaml.safe_load(SCENARIO_PATH.read_text())


def _build_sim():
    """Create a HybridRunner, load the patrol scenario, start it.

    Returns:
        (runner, sim, player_ship) tuple.
    """
    from hybrid_runner import HybridRunner

    runner = HybridRunner(dt=DT)
    count = runner._load_scenario_file(str(SCENARIO_PATH))
    assert count >= 2, (
        f"Expected at least 2 ships from scenario; got {count}."
    )

    sim = runner.simulator
    sim.start()

    player = sim.ships.get(PLAYER_ID)
    assert player is not None, f"Player ship '{PLAYER_ID}' not found"

    return runner, sim, player


def _distance_3d(pos_a: dict, pos_b: dict) -> float:
    """Euclidean distance between two {x,y,z} dicts."""
    dx = pos_a["x"] - pos_b["x"]
    dy = pos_a["y"] - pos_b["y"]
    dz = pos_a["z"] - pos_b["z"]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _speed(ship) -> float:
    """Magnitude of a ship's velocity vector."""
    v = ship.velocity
    return math.sqrt(v["x"] ** 2 + v["y"] ** 2 + v["z"] ** 2)


# ===========================================================================
# Test 1: Scenario YAML loads cleanly
# ===========================================================================

def test_scenario_yaml_loads():
    """11_patrol_ambush.yaml loads without YAML parse errors."""
    data = _load_raw_yaml()

    assert data is not None
    assert data.get("name") == "Patrol: Ambush Encounter"
    assert "ships" in data
    assert "mission" in data
    assert data.get("dt") == 0.1


# ===========================================================================
# Test 2: All ships defined with required fields
# ===========================================================================

def test_all_ships_have_required_fields():
    """Every ship in the YAML has id, position, velocity, and systems."""
    data = _load_raw_yaml()
    ships = data["ships"]

    assert len(ships) >= 4, f"Expected 4 ships, got {len(ships)}"

    ship_ids = {s["id"] for s in ships}
    assert PLAYER_ID in ship_ids
    assert UNKNOWN_ID in ship_ids
    assert PIRATE_ID in ship_ids
    assert FRIENDLY_ID in ship_ids

    for ship_def in ships:
        sid = ship_def["id"]
        assert "position" in ship_def, f"Ship {sid} missing position"
        assert "velocity" in ship_def, f"Ship {sid} missing velocity"
        assert "systems" in ship_def, f"Ship {sid} missing systems"
        assert "mass" in ship_def, f"Ship {sid} missing mass"


# ===========================================================================
# Test 3: Player starts mid-patrol with correct state
# ===========================================================================

def test_player_mid_patrol_state():
    """Player ship starts with 60% fuel, cruising velocity, and full weapons."""
    data = _load_raw_yaml()

    player_def = next(s for s in data["ships"] if s["id"] == PLAYER_ID)

    # Fuel: 6000 / 10000 = 60%
    prop = player_def["systems"]["propulsion"]
    assert prop["fuel_level"] == 6000
    assert prop["max_fuel"] == 10000

    # Cruising velocity: 200 m/s in +X
    assert player_def["velocity"]["x"] == 200
    assert player_def["velocity"]["y"] == 0

    # Weapons: 6 torpedoes, 2 railguns, 4 PDCs
    combat = player_def["systems"]["combat"]
    assert combat["railguns"] == 2
    assert combat["pdcs"] == 4

    weapons = player_def["systems"]["weapons"]["weapons"]
    torpedo = next(w for w in weapons if w["name"] == "torpedo")
    assert torpedo["ammo"] == 6


# ===========================================================================
# Test 4: NPC AI behavior profiles
# ===========================================================================

def test_smuggler_freighter_ai_profile():
    """Smuggler freighter has freighter role and high flee threshold."""
    data = _load_raw_yaml()

    unknown = next(s for s in data["ships"] if s["id"] == UNKNOWN_ID)
    ai = unknown["ai_behavior"]

    assert ai["role"] == "freighter"
    assert ai["flee_threshold"] >= 0.9, "Smuggler should flee at first sign of trouble"
    assert unknown["ai_enabled"] is True


def test_pirate_ambusher_ai_profile():
    """Pirate ambusher has combat role with high aggression."""
    data = _load_raw_yaml()

    pirate = next(s for s in data["ships"] if s["id"] == PIRATE_ID)
    ai = pirate["ai_behavior"]

    assert ai["role"] == "combat"
    assert ai["aggression"] >= 0.8, "Ambush predator should be highly aggressive"
    assert ai["flee_threshold"] <= 0.2, "Pirate should fight to near-death"
    assert pirate["faction"] == "pirates"
    assert pirate["ai_enabled"] is True


def test_friendly_vessel_ai_profile():
    """Friendly vessel has freighter role and UNSA faction."""
    data = _load_raw_yaml()

    friendly = next(s for s in data["ships"] if s["id"] == FRIENDLY_ID)

    assert friendly["faction"] == "unsa"
    assert friendly["ai_enabled"] is True
    ai = friendly["ai_behavior"]
    assert ai["role"] == "freighter"


# ===========================================================================
# Test 5: All mission objectives use valid ObjectiveType values
# ===========================================================================

def test_mission_objectives_valid_types():
    """Every objective type in the mission block is a valid ObjectiveType."""
    from hybrid.scenarios.objectives import ObjectiveType

    data = _load_raw_yaml()
    objectives = data["mission"]["objectives"]
    assert len(objectives) >= 3, "Expected at least 3 objectives"

    for obj in objectives:
        obj_type = obj.get("type")
        assert obj_type is not None, f"Objective {obj.get('id')} has no type"
        # This will raise ValueError if the type string is invalid
        ObjectiveType(obj_type)


# ===========================================================================
# Test 6: Scenario loads through HybridRunner
# ===========================================================================

def test_scenario_loads_through_runner():
    """Scenario loads through HybridRunner and ships spawn correctly."""
    runner, sim, player = _build_sim()

    # Player ship present and at origin
    assert abs(player.position["x"]) < 1.0
    assert abs(player.position["y"]) < 1.0

    # Unknown contact present and ~113km away
    unknown = sim.ships.get(UNKNOWN_ID)
    assert unknown is not None, f"Ship '{UNKNOWN_ID}' not found in sim"

    distance = _distance_3d(player.position, unknown.position)
    assert 100_000 < distance < 130_000, (
        f"Unknown contact should be ~113km away, got {distance / 1000:.1f}km"
    )

    # Player has cruising velocity
    assert abs(_speed(player) - 200.0) < 5.0, (
        f"Player should start at ~200 m/s, got {_speed(player):.1f} m/s"
    )


# ===========================================================================
# Test 7: Sensor detection of unknown contact
# ===========================================================================

def test_sensor_detects_unknown_contact():
    """Player passive sensors detect the unknown contact within 60 sim-seconds.

    The unknown contact is at ~113km and the player has 200km passive range,
    so detection should happen quickly.
    """
    runner, sim, player = _build_sim()

    detected = False
    detection_ticks = int(60.0 / DT)

    for tick in range(detection_ticks):
        sim.tick()
        sensors = player.systems.get("sensors")
        if sensors is None:
            continue
        if hasattr(sensors, "contact_tracker"):
            mapping = sensors.contact_tracker.id_mapping
            if UNKNOWN_ID in mapping:
                detected = True
                break

    assert detected, (
        f"Player sensors failed to detect '{UNKNOWN_ID}' within 60 sim-seconds. "
        f"Contact is at ~113km, player passive range is 200km."
    )


# ===========================================================================
# Test 8: Mission tracker initializes and updates
# ===========================================================================

def test_mission_tracker_initializes():
    """Mission loads with correct name and objectives."""
    runner, sim, player = _build_sim()

    assert runner.mission is not None, "Mission should be loaded from scenario"
    assert runner.mission.name == "Patrol Sector 7-G"

    # Check objectives exist
    status = runner.mission.get_status(sim_time=sim.time)
    objectives = status.get("objectives", {})
    assert "detect_contact" in objectives
    assert "close_to_id_range" in objectives
    assert "mission_kill_smuggler" in objectives
    assert "player_survives" in objectives


def test_mission_updates_without_error():
    """Mission update loop runs for 100 ticks without raising."""
    runner, sim, player = _build_sim()

    if runner.mission and runner.mission.start_time is None:
        runner.mission.start(sim.time)

    # Run 100 ticks -- should not raise
    for _ in range(100):
        sim.tick()
        runner._update_mission()

    # Mission should still be in progress (not enough time for completion)
    status = runner.mission.get_status(sim_time=sim.time)
    assert status["mission_status"] == "in_progress"


# ===========================================================================
# Test 9: Fuel constraint is meaningful
# ===========================================================================

def test_player_fuel_is_limited():
    """Player starts at 60% fuel, which constrains total delta-V budget.

    Verifies the fuel level is correctly set at 60% of max capacity
    after scenario load.
    """
    runner, sim, player = _build_sim()

    propulsion = player.systems.get("propulsion")
    assert propulsion is not None, "Player missing propulsion system"

    fuel_level = getattr(propulsion, "fuel_level", None)
    max_fuel = getattr(propulsion, "max_fuel", None)

    # The scenario sets fuel_level=6000, max_fuel=10000
    # The exact values after loading depend on the propulsion system impl,
    # but the ratio should be approximately 0.6
    if fuel_level is not None and max_fuel is not None and max_fuel > 0:
        ratio = fuel_level / max_fuel
        assert 0.5 <= ratio <= 0.7, (
            f"Fuel ratio should be ~0.6, got {ratio:.2f} "
            f"(fuel={fuel_level}, max={max_fuel})"
        )


# ===========================================================================
# Test 10: Pirate has low sensor signature (ambush capability)
# ===========================================================================

def test_pirate_low_sensor_signature():
    """Pirate ambusher has a low signature_base for ambush stealth."""
    data = _load_raw_yaml()

    pirate = next(s for s in data["ships"] if s["id"] == PIRATE_ID)
    sig = pirate["systems"]["sensors"]["signature_base"]

    assert sig < 1.0, (
        f"Pirate signature should be < 1.0 for stealth, got {sig}"
    )


# ===========================================================================
# Test 11: Contact positions form realistic spatial layout
# ===========================================================================

def test_contact_positions_realistic():
    """All three contacts are ~110-120km from player, clustered together.

    This simulates a single sensor return that could be any of the three
    contact types -- they occupy roughly the same region of space.
    """
    data = _load_raw_yaml()

    player_pos = next(s for s in data["ships"] if s["id"] == PLAYER_ID)["position"]

    for contact_id in [UNKNOWN_ID, PIRATE_ID, FRIENDLY_ID]:
        contact = next(s for s in data["ships"] if s["id"] == contact_id)
        dist = _distance_3d(player_pos, contact["position"])
        assert 100_000 < dist < 130_000, (
            f"Contact {contact_id} should be 100-130km away, got {dist / 1000:.1f}km"
        )


# ===========================================================================
# Test 12: Mission has time limit and briefing
# ===========================================================================

def test_mission_metadata():
    """Mission has time_limit, briefing, success/failure messages, and hints."""
    data = _load_raw_yaml()
    mission = data["mission"]

    assert mission.get("time_limit") == 600, "Time limit should be 600s (10 min)"
    assert len(mission.get("briefing", "")) > 100, "Briefing should be substantial"
    assert len(mission.get("success_message", "")) > 50
    assert len(mission.get("failure_message", "")) > 50
    assert len(mission.get("hints", [])) >= 5, "Should have at least 5 hints"


# ===========================================================================
# Test 13: Config block specifies default branch
# ===========================================================================

def test_config_default_branch():
    """Config block sets default contact_type to 'smuggler'."""
    data = _load_raw_yaml()
    config = data.get("config", {})

    assert config.get("contact_type") == "smuggler"


# ===========================================================================
# Test 14: AI controller initializes for NPC ships
# ===========================================================================

def test_npc_ai_controllers_initialize():
    """NPC ships with ai_enabled=True get AI controllers after loading."""
    runner, sim, player = _build_sim()

    for npc_id in [UNKNOWN_ID, PIRATE_ID, FRIENDLY_ID]:
        ship = sim.ships.get(npc_id)
        if ship is None:
            continue  # Ship may not exist if branch filtering is active
        assert ship.ai_enabled, f"Ship {npc_id} should have ai_enabled=True"
        assert ship.ai_controller is not None, (
            f"Ship {npc_id} should have an AI controller"
        )


def test_pirate_ai_is_combat_role():
    """Pirate ambusher's AI controller has combat role profile."""
    runner, sim, player = _build_sim()

    pirate = sim.ships.get(PIRATE_ID)
    if pirate is None:
        pytest.skip("Pirate ship not spawned (branch filtering may be active)")

    assert pirate.ai_controller.profile.role == "combat"
    assert pirate.ai_controller.profile.aggression >= 0.8


def test_smuggler_ai_is_freighter_role():
    """Smuggler's AI controller has freighter role profile."""
    runner, sim, player = _build_sim()

    unknown = sim.ships.get(UNKNOWN_ID)
    if unknown is None:
        pytest.skip("Unknown contact not spawned")

    assert unknown.ai_controller.profile.role == "freighter"
