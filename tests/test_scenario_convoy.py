"""Tests for Scenario 10: Convoy Defense.

Validates:
  1. YAML loads without errors and has the expected structure
  2. All objective types are recognized by the ObjectiveType enum
  3. Ship configuration: player, 3 freighters, 2 enemies
  4. Freighter AI behavior: role=freighter, flee-on-threat, never fire
  5. Enemy AI behavior: role=combat, aggression thresholds
  6. Fleet definitions: convoy and raider fleets
  7. Armor configuration: freighters have light armor, corvettes heavy
  8. Mission branch points are documented
  9. Objective evaluation with mock sim state
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Dict

import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
SCENARIO_PATH = ROOT_DIR / "scenarios" / "10_convoy_defense.yaml"


# ── Fixture: load scenario once ────────────────────────────────────

@pytest.fixture(scope="module")
def scenario_data() -> Dict:
    """Load the convoy defense scenario YAML."""
    assert SCENARIO_PATH.exists(), f"Scenario file missing: {SCENARIO_PATH}"
    return yaml.safe_load(SCENARIO_PATH.read_text())


# ── Structure tests ────────────────────────────────────────────────

def test_scenario_loads(scenario_data):
    """Scenario YAML parses without error."""
    assert scenario_data is not None
    assert "name" in scenario_data
    assert "ships" in scenario_data
    assert "mission" in scenario_data


def test_scenario_has_required_top_level_fields(scenario_data):
    """Top-level keys include name, description, dt, ships, mission, fleets."""
    for key in ("name", "description", "dt", "ships", "mission", "fleets"):
        assert key in scenario_data, f"Missing top-level key: {key}"


def test_dt_is_positive(scenario_data):
    """Simulation timestep must be positive."""
    assert scenario_data["dt"] > 0


# ── Ship configuration ─────────────────────────────────────────────

def test_ship_count(scenario_data):
    """Scenario has at least 6 ships: 1 player + 3 freighters + 2 enemies + nav buoys."""
    assert len(scenario_data["ships"]) >= 6


def test_player_ship_exists(scenario_data):
    """Player ship is present and marked player_controlled."""
    ships = {s["id"]: s for s in scenario_data["ships"]}
    assert "player_ship" in ships
    assert ships["player_ship"]["player_controlled"] is True
    assert ships["player_ship"]["faction"] == "unsa"


def test_freighter_ships_exist(scenario_data):
    """Three convoy freighters are present with correct faction."""
    ships = {s["id"]: s for s in scenario_data["ships"]}
    freighter_ids = ["freighter_alpha", "freighter_beta", "freighter_gamma"]
    for fid in freighter_ids:
        assert fid in ships, f"Missing freighter: {fid}"
        assert ships[fid]["faction"] == "civilian"
        assert ships[fid]["ai_enabled"] is True
        assert ships[fid]["class"] == "freighter"


def test_enemy_ships_exist(scenario_data):
    """Two enemy corvettes are present with pirate faction."""
    ships = {s["id"]: s for s in scenario_data["ships"]}
    enemy_ids = ["enemy_alpha", "enemy_beta"]
    for eid in enemy_ids:
        assert eid in ships, f"Missing enemy: {eid}"
        assert ships[eid]["faction"] == "pirates"
        assert ships[eid]["ai_enabled"] is True
        assert ships[eid]["class"] == "corvette"


def test_ships_have_positions_and_velocities(scenario_data):
    """Every ship has position and velocity dicts with x, y, z."""
    for ship in scenario_data["ships"]:
        for field in ("position", "velocity"):
            assert field in ship, f"Ship {ship['id']} missing {field}"
            for axis in ("x", "y", "z"):
                assert axis in ship[field], (
                    f"Ship {ship['id']}.{field} missing axis {axis}"
                )


def test_enemies_approach_from_different_vectors(scenario_data):
    """Enemy corvettes approach from distinct vectors (not same bearing)."""
    ships = {s["id"]: s for s in scenario_data["ships"]}
    alpha_pos = ships["enemy_alpha"]["position"]
    beta_pos = ships["enemy_beta"]["position"]

    # Y-coordinates have opposite signs -- different approach bearings
    assert alpha_pos["y"] * beta_pos["y"] < 0, (
        "Enemies should approach from different Y-axis sides"
    )


# ── AI behavior ────────────────────────────────────────────────────

def test_freighter_ai_behavior(scenario_data):
    """Freighter AI behavior is role=freighter with high flee threshold."""
    ships = {s["id"]: s for s in scenario_data["ships"]}
    for fid in ["freighter_alpha", "freighter_beta", "freighter_gamma"]:
        behavior = ships[fid].get("ai_behavior", {})
        assert behavior.get("role") == "freighter"
        assert behavior.get("flee_threshold", 0) >= 0.8, (
            f"Freighter {fid} should flee easily (threshold >= 0.8)"
        )


def test_enemy_ai_behavior(scenario_data):
    """Enemy AI behavior is role=combat with high aggression."""
    ships = {s["id"]: s for s in scenario_data["ships"]}
    for eid in ["enemy_alpha", "enemy_beta"]:
        behavior = ships[eid].get("ai_behavior", {})
        assert behavior.get("role") == "combat"
        assert behavior.get("aggression", 0) >= 0.5, (
            f"Enemy {eid} should be aggressive"
        )
        assert behavior.get("engagement_range", 0) > 0


def test_enemy_alpha_more_aggressive_than_beta(scenario_data):
    """Razorback (alpha) is more aggressive than Nightfang (beta)."""
    ships = {s["id"]: s for s in scenario_data["ships"]}
    alpha_aggr = ships["enemy_alpha"]["ai_behavior"]["aggression"]
    beta_aggr = ships["enemy_beta"]["ai_behavior"]["aggression"]
    assert alpha_aggr > beta_aggr


# ── Armor configuration ───────────────────────────────────────────

def test_freighter_armor_is_steel_composite(scenario_data):
    """Freighters use lighter steel_composite armor."""
    ships = {s["id"]: s for s in scenario_data["ships"]}
    for fid in ["freighter_alpha", "freighter_beta", "freighter_gamma"]:
        armor = ships[fid].get("armor", {})
        assert armor, f"Freighter {fid} missing armor config"
        for face, spec in armor.items():
            assert spec["material"] == "steel_composite"


def test_enemy_armor_is_cermet(scenario_data):
    """Enemy corvettes use heavier composite_cermet armor."""
    ships = {s["id"]: s for s in scenario_data["ships"]}
    for eid in ["enemy_alpha", "enemy_beta"]:
        armor = ships[eid].get("armor", {})
        assert armor, f"Enemy {eid} missing armor config"
        for face, spec in armor.items():
            assert spec["material"] == "composite_cermet"


# ── Fleet definitions ──────────────────────────────────────────────

def test_fleet_definitions(scenario_data):
    """Fleets are defined for convoy and raiders."""
    fleets = {f["id"]: f for f in scenario_data["fleets"]}
    assert "convoy" in fleets
    assert "raider_force" in fleets


def test_convoy_fleet_contains_all_freighters(scenario_data):
    """Convoy fleet includes all 3 freighter ship IDs."""
    fleets = {f["id"]: f for f in scenario_data["fleets"]}
    convoy = fleets["convoy"]
    assert set(convoy["ships"]) == {
        "freighter_alpha", "freighter_beta", "freighter_gamma"
    }


def test_raider_fleet_contains_both_enemies(scenario_data):
    """Raider fleet includes both enemy corvette IDs."""
    fleets = {f["id"]: f for f in scenario_data["fleets"]}
    raiders = fleets["raider_force"]
    assert set(raiders["ships"]) == {"enemy_alpha", "enemy_beta"}


def test_convoy_has_destination(scenario_data):
    """Convoy fleet has a destination position."""
    fleets = {f["id"]: f for f in scenario_data["fleets"]}
    convoy = fleets["convoy"]
    dest = convoy.get("destination")
    assert dest is not None
    assert "x" in dest


# ── Mission objectives ─────────────────────────────────────────────

def test_mission_has_objectives(scenario_data):
    """Mission has at least 3 objectives."""
    objectives = scenario_data["mission"]["objectives"]
    assert len(objectives) >= 3


def test_all_objective_types_valid(scenario_data):
    """Every objective type is recognized by ObjectiveType enum."""
    from hybrid.scenarios.objectives import ObjectiveType

    for obj in scenario_data["mission"]["objectives"]:
        obj_type = obj.get("type")
        assert obj_type, f"Objective {obj.get('id')} missing type"
        # This will raise ValueError if the type is not recognized
        ObjectiveType(obj_type)


def test_player_survive_objective_is_required(scenario_data):
    """Player survival objective is present and required."""
    objectives = {o["id"]: o for o in scenario_data["mission"]["objectives"]}
    assert "player_survives" in objectives
    assert objectives["player_survives"]["required"] is True
    assert objectives["player_survives"]["type"] == "avoid_mission_kill"


def test_at_least_one_protect_objective_required(scenario_data):
    """At least one freighter protection objective is required."""
    protect_objectives = [
        o for o in scenario_data["mission"]["objectives"]
        if o["type"] == "protect_ship" and o.get("required", False)
    ]
    assert len(protect_objectives) >= 1


def test_enemy_kill_objectives_are_bonus(scenario_data):
    """Enemy mission-kill objectives are optional (bonus)."""
    kill_objectives = [
        o for o in scenario_data["mission"]["objectives"]
        if o["type"] == "mission_kill"
    ]
    assert len(kill_objectives) == 2
    for obj in kill_objectives:
        assert obj.get("required") is False, (
            f"Kill objective {obj['id']} should be optional"
        )


# ── Mission metadata ──────────────────────────────────────────────

def test_mission_has_briefing(scenario_data):
    """Mission includes a briefing string."""
    assert scenario_data["mission"].get("briefing")
    assert len(scenario_data["mission"]["briefing"]) > 100


def test_mission_has_time_limit(scenario_data):
    """Mission has a time limit of 600 seconds (10 minutes)."""
    assert scenario_data["mission"]["time_limit"] == 600


def test_mission_has_success_and_failure_messages(scenario_data):
    """Mission has both success and failure messages."""
    assert scenario_data["mission"].get("success_message")
    assert scenario_data["mission"].get("failure_message")


def test_mission_has_hints(scenario_data):
    """Mission has at least 3 hints."""
    hints = scenario_data["mission"].get("hints", [])
    assert len(hints) >= 3


def test_mission_has_branch_points(scenario_data):
    """Mission documents branch points for enemy tactics."""
    branches = scenario_data["mission"].get("branches", [])
    assert len(branches) == 3

    branch_ids = {b["id"] for b in branches}
    assert "focus_fire" in branch_ids
    assert "isolation" in branch_ids
    assert "boarding" in branch_ids


# ── Scenario loader integration ───────────────────────────────────

def test_scenario_loader_can_parse():
    """ScenarioLoader.load() can parse the convoy defense scenario."""
    from hybrid.scenarios.loader import ScenarioLoader

    result = ScenarioLoader.load(str(SCENARIO_PATH))
    assert result["name"] == "Convoy Defense: Gauntlet Run"
    assert len(result["ships"]) >= 6  # 6 combat ships + nav buoys
    assert result["mission"] is not None
    assert len(result["fleets"]) == 2


def test_scenario_loader_parses_objectives():
    """ScenarioLoader resolves objective types from the scenario."""
    from hybrid.scenarios.loader import ScenarioLoader
    from hybrid.scenarios.objectives import ObjectiveType

    result = ScenarioLoader.load(str(SCENARIO_PATH))
    mission = result["mission"]

    # Mission should have parsed objectives
    assert hasattr(mission, "tracker")
    objectives = mission.tracker.objectives
    assert len(objectives) >= 3

    # Check specific objective types
    obj_types = {obj.type for obj in objectives.values()}
    assert ObjectiveType.AVOID_MISSION_KILL in obj_types
    assert ObjectiveType.PROTECT_SHIP in obj_types


# ── Objective evaluation with mock state ──────────────────────────

def test_protect_ship_objective_fails_when_ship_destroyed():
    """protect_ship objective fails when the target ship is removed."""
    from hybrid.scenarios.objectives import (
        Objective, ObjectiveType, ObjectiveStatus,
    )

    obj = Objective(
        obj_id="protect_alpha",
        obj_type=ObjectiveType.PROTECT_SHIP,
        description="Protect MV Stellarwind",
        params={"target": "freighter_alpha", "time": 600, "start_time": 0},
    )

    # Sim without the freighter -- it was destroyed
    player = SimpleNamespace(id="player_ship", position={"x": 0, "y": 0, "z": 0})
    sim = SimpleNamespace(time=100.0, ships={"player_ship": player})

    obj.check(sim, player)
    assert obj.status == ObjectiveStatus.FAILED
    assert "destroyed" in obj.failure_reason.lower()


def test_protect_ship_objective_succeeds_after_time():
    """protect_ship objective completes when time elapses with ship alive."""
    from hybrid.scenarios.objectives import (
        Objective, ObjectiveType, ObjectiveStatus,
    )

    obj = Objective(
        obj_id="protect_alpha",
        obj_type=ObjectiveType.PROTECT_SHIP,
        description="Protect MV Stellarwind",
        params={"target": "freighter_alpha", "time": 600, "start_time": 0},
    )

    player = SimpleNamespace(id="player_ship", position={"x": 0, "y": 0, "z": 0})
    freighter = SimpleNamespace(
        id="freighter_alpha",
        position={"x": 2000, "y": 500, "z": 0},
    )
    sim = SimpleNamespace(
        time=601.0,
        ships={"player_ship": player, "freighter_alpha": freighter},
    )

    obj.check(sim, player)
    assert obj.status == ObjectiveStatus.COMPLETED


def test_avoid_mission_kill_fails_when_player_destroyed():
    """avoid_mission_kill objective fails when player hull reaches 0."""
    from hybrid.scenarios.objectives import (
        Objective, ObjectiveType, ObjectiveStatus,
    )

    obj = Objective(
        obj_id="player_survives",
        obj_type=ObjectiveType.AVOID_MISSION_KILL,
        description="Keep your ship operational",
        params={"target": "player_ship"},
    )

    player = SimpleNamespace(
        id="player_ship",
        position={"x": 0, "y": 0, "z": 0},
        hull_integrity=0,
        is_destroyed=lambda: True,
    )
    sim = SimpleNamespace(time=100.0, ships={"player_ship": player})

    obj.check(sim, player)
    assert obj.status == ObjectiveStatus.FAILED


# ── AI integration smoke tests ────────────────────────────────────

def test_freighter_ai_creates_correct_profile():
    """Ship created with freighter ai_behavior gets freighter profile."""
    from hybrid.ship import Ship

    ship = Ship("freighter_alpha", {
        "mass": 8000,
        "class": "freighter",
        "faction": "civilian",
        "ai_enabled": True,
        "ai_behavior": {
            "role": "freighter",
            "flee_threshold": 0.9,
            "max_thrust_profile": 0.3,
        },
        "systems": {
            "sensors": {"passive": {"range": 20000}},
            "navigation": {},
            "propulsion": {"max_thrust": 600, "fuel_level": 3000},
        },
    })

    assert ship.ai_controller is not None
    assert ship.ai_controller.profile.role == "freighter"
    assert ship.ai_controller.profile.flee_threshold == 0.9
    # Freighters should never fire
    assert ship.ai_controller.profile.weapon_confidence_threshold >= 1.0


def test_enemy_ai_creates_correct_profile():
    """Ship created with combat ai_behavior gets combat profile."""
    from hybrid.ship import Ship

    ship = Ship("enemy_alpha", {
        "mass": 1200,
        "class": "corvette",
        "faction": "pirates",
        "ai_enabled": True,
        "ai_behavior": {
            "role": "combat",
            "aggression": 0.9,
            "engagement_range": 80000,
            "flee_threshold": 0.15,
            "evade_threshold": 0.3,
        },
        "systems": {
            "sensors": {"passive": {"range": 35000}},
            "targeting": {},
            "combat": {"railguns": 1, "pdcs": 2},
            "navigation": {},
            "propulsion": {"max_thrust": 280, "fuel_level": 400},
        },
    })

    assert ship.ai_controller is not None
    assert ship.ai_controller.profile.role == "combat"
    assert ship.ai_controller.profile.aggression == 0.9
    assert ship.ai_controller.engagement_range == 80000
    assert ship.ai_controller.profile.flee_threshold == 0.15


def test_faction_hostility_for_scenario():
    """Pirates are hostile to both UNSA and civilians (scenario factions)."""
    from hybrid.fleet.faction_rules import are_hostile

    assert are_hostile("pirates", "unsa")
    assert are_hostile("pirates", "civilian")
    assert not are_hostile("unsa", "civilian")
    assert not are_hostile("civilian", "civilian")
