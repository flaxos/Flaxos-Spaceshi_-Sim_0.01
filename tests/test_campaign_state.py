"""Tests for the campaign state system (Phase 4A).

Covers: new_campaign, save/load roundtrip, apply_mission_result,
inject_into_scenario, and campaign command handlers.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from hybrid.campaign.campaign_state import CampaignState


# ---------- CampaignState.new_campaign ----------

class TestNewCampaign:
    """Verify that new_campaign produces a valid starter state."""

    def test_creates_valid_state(self):
        state = CampaignState.new_campaign()
        assert state.credits > 0
        assert state.current_chapter == 0
        assert len(state.crew_roster) >= 1
        assert state.ship_state["hull_percent"] == 100.0
        assert "propulsion" in state.ship_state["subsystems"]

    def test_starter_ship_class(self):
        state = CampaignState.new_campaign(ship_class="frigate")
        assert state.ship_state["class"] == "frigate"

    def test_starter_ammo(self):
        state = CampaignState.new_campaign()
        ammo = state.ship_state.get("ammo", {})
        assert "railgun" in ammo
        assert "pdc" in ammo
        assert ammo["railgun"] > 0

    def test_starter_reputation(self):
        state = CampaignState.new_campaign()
        assert "UNS" in state.reputation
        assert "OPA" in state.reputation
        # Neutral start
        assert state.reputation["UNS"] == 0

    def test_unlocked_scenarios(self):
        state = CampaignState.new_campaign()
        assert len(state.unlocked_scenarios) >= 1
        assert "01_tutorial_intercept" in state.unlocked_scenarios


# ---------- Save / Load roundtrip ----------

class TestSaveLoad:
    """Verify campaign serialisation round-trips cleanly."""

    def test_roundtrip(self, tmp_path):
        original = CampaignState.new_campaign()
        # Mutate to ensure non-default values survive
        original.credits = 9999
        original.reputation["UNS"] = 42
        original.current_chapter = 3
        original.mission_history.append({
            "scenario_id": "test", "outcome": "success", "score": 80,
        })

        filepath = str(tmp_path / "campaign.json")
        original.save(filepath)

        loaded = CampaignState.load(filepath)

        assert loaded.credits == 9999
        assert loaded.reputation["UNS"] == 42
        assert loaded.current_chapter == 3
        assert len(loaded.mission_history) == 1
        assert loaded.mission_history[0]["scenario_id"] == "test"

    def test_save_creates_parent_dirs(self, tmp_path):
        state = CampaignState.new_campaign()
        filepath = str(tmp_path / "nested" / "deep" / "save.json")
        state.save(filepath)
        assert os.path.exists(filepath)

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            CampaignState.load("/nonexistent/path/save.json")

    def test_load_invalid_json_raises(self, tmp_path):
        filepath = str(tmp_path / "bad.json")
        Path(filepath).write_text("not json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            CampaignState.load(filepath)

    def test_file_is_valid_json(self, tmp_path):
        state = CampaignState.new_campaign()
        filepath = str(tmp_path / "campaign.json")
        state.save(filepath)
        data = json.loads(Path(filepath).read_text(encoding="utf-8"))
        assert "version" in data
        assert data["version"] == 1

    def test_crew_roster_survives(self, tmp_path):
        state = CampaignState.new_campaign()
        original_names = [c["name"] for c in state.crew_roster]
        filepath = str(tmp_path / "campaign.json")
        state.save(filepath)
        loaded = CampaignState.load(filepath)
        loaded_names = [c["name"] for c in loaded.crew_roster]
        assert original_names == loaded_names


# ---------- apply_mission_result ----------

class TestApplyMissionResult:
    """Verify campaign state updates after a mission."""

    def _make_result(self, **overrides):
        base = {
            "outcome": "success",
            "scenario_id": "test_scenario",
            "score": 75,
            "ship_snapshot": {
                "hull_percent": 80.0,
                "subsystems": {"propulsion": 90.0, "sensors": 60.0},
                "ammo": {"railgun": 10, "pdc": 3000},
                "fuel": 5000,
            },
            "crew_snapshot": [],
            "choices": [],
            "next_scenarios": ["02_combat_destroy"],
            "reputation_changes": {"UNS": 10, "OPA": -5},
        }
        base.update(overrides)
        return base

    def test_credits_awarded_on_success(self):
        state = CampaignState.new_campaign()
        initial_credits = state.credits
        state.apply_mission_result(self._make_result())
        assert state.credits > initial_credits

    def test_credits_awarded_on_failure(self):
        state = CampaignState.new_campaign()
        initial_credits = state.credits
        state.apply_mission_result(self._make_result(outcome="failure", score=20))
        # Failure still awards some credits
        assert state.credits > initial_credits

    def test_ship_damage_carries_forward(self):
        state = CampaignState.new_campaign()
        state.apply_mission_result(self._make_result())
        assert state.ship_state["hull_percent"] == 80.0
        assert state.ship_state["subsystems"]["propulsion"] == 90.0

    def test_ammo_carries_forward(self):
        state = CampaignState.new_campaign()
        state.apply_mission_result(self._make_result())
        assert state.ship_state["ammo"]["railgun"] == 10

    def test_fuel_carries_forward(self):
        state = CampaignState.new_campaign()
        state.apply_mission_result(self._make_result())
        assert state.ship_state["fuel"] == 5000

    def test_reputation_updated(self):
        state = CampaignState.new_campaign()
        state.apply_mission_result(self._make_result(
            reputation_changes={"UNS": 30, "OPA": -20}
        ))
        assert state.reputation["UNS"] == 30
        assert state.reputation["OPA"] == -20

    def test_reputation_clamped(self):
        state = CampaignState.new_campaign()
        state.reputation["UNS"] = 95
        state.apply_mission_result(self._make_result(
            reputation_changes={"UNS": 50}
        ))
        assert state.reputation["UNS"] == 100  # clamped

    def test_next_scenarios_unlocked(self):
        state = CampaignState.new_campaign()
        state.apply_mission_result(self._make_result(
            next_scenarios=["03_escort_protect"]
        ))
        assert "03_escort_protect" in state.unlocked_scenarios

    def test_no_duplicate_unlock(self):
        state = CampaignState.new_campaign()
        state.unlocked_scenarios.append("02_combat_destroy")
        state.apply_mission_result(self._make_result(
            next_scenarios=["02_combat_destroy"]
        ))
        assert state.unlocked_scenarios.count("02_combat_destroy") == 1

    def test_mission_history_recorded(self):
        state = CampaignState.new_campaign()
        state.apply_mission_result(self._make_result())
        assert len(state.mission_history) == 1
        assert state.mission_history[0]["scenario_id"] == "test_scenario"
        assert state.mission_history[0]["outcome"] == "success"

    def test_chapter_advances_on_success(self):
        state = CampaignState.new_campaign()
        assert state.current_chapter == 0
        state.apply_mission_result(self._make_result(outcome="success"))
        assert state.current_chapter == 1

    def test_chapter_does_not_advance_on_failure(self):
        state = CampaignState.new_campaign()
        state.apply_mission_result(self._make_result(outcome="failure"))
        assert state.current_chapter == 0

    def test_crew_xp_on_success(self):
        state = CampaignState.new_campaign()
        # Find highest skill of first crew member
        crew = state.crew_roster[0]
        skills = crew["skills"]
        top_skill_name = max(skills, key=skills.get)
        top_skill_before = skills[top_skill_name]

        state.apply_mission_result(self._make_result(outcome="success"))
        top_skill_after = state.crew_roster[0]["skills"][top_skill_name]

        # Should increase by 1 (unless already at cap 6)
        if top_skill_before < 6:
            assert top_skill_after == top_skill_before + 1
        else:
            assert top_skill_after == 6


# ---------- inject_into_scenario ----------

class TestInjectIntoScenario:
    """Verify campaign state overlays onto scenario ship definitions."""

    def _make_scenario(self):
        return {
            "name": "Test Scenario",
            "ships": [
                {
                    "id": "player",
                    "player_controlled": True,
                    "mass": 5000,
                    "max_hull_integrity": 500,
                    "systems": {
                        "propulsion": {"max_thrust": 500000, "fuel_level": 10000},
                        "sensors": {"passive": {"range": 500000}},
                        "weapons": {"type": "railgun"},
                    },
                },
                {
                    "id": "enemy",
                    "mass": 8000,
                    "systems": {"propulsion": {"max_thrust": 300000}},
                },
            ],
        }

    def test_hull_damage_injected(self):
        state = CampaignState.new_campaign()
        state.ship_state["hull_percent"] = 60.0
        scenario = self._make_scenario()
        result = state.inject_into_scenario(scenario)
        player = result["ships"][0]
        # 60% of max_hull_integrity=500 -> 300
        assert player["hull_integrity"] == 300.0

    def test_fuel_injected(self):
        state = CampaignState.new_campaign()
        state.ship_state["fuel"] = 7500
        result = state.inject_into_scenario(self._make_scenario())
        player = result["ships"][0]
        assert player["systems"]["propulsion"]["fuel_level"] == 7500

    def test_ammo_injected(self):
        state = CampaignState.new_campaign()
        state.ship_state["ammo"] = {"railgun": 5, "pdc": 1000}
        result = state.inject_into_scenario(self._make_scenario())
        player = result["ships"][0]
        assert player["systems"]["weapons"]["ammo"] == {"railgun": 5, "pdc": 1000}

    def test_subsystem_health_injected(self):
        state = CampaignState.new_campaign()
        state.ship_state["subsystems"]["sensors"] = 50.0
        result = state.inject_into_scenario(self._make_scenario())
        player = result["ships"][0]
        assert player["systems"]["sensors"]["health"] == 0.5

    def test_enemy_ship_untouched(self):
        state = CampaignState.new_campaign()
        state.ship_state["hull_percent"] = 30.0
        scenario = self._make_scenario()
        result = state.inject_into_scenario(scenario)
        enemy = result["ships"][1]
        # Enemy should not have hull_integrity set by campaign
        assert "hull_integrity" not in enemy

    def test_original_not_mutated(self):
        state = CampaignState.new_campaign()
        state.ship_state["hull_percent"] = 50.0
        scenario = self._make_scenario()
        state.inject_into_scenario(scenario)
        # Original scenario unchanged
        assert "hull_integrity" not in scenario["ships"][0]

    def test_crew_roster_injected(self):
        state = CampaignState.new_campaign()
        result = state.inject_into_scenario(self._make_scenario())
        player = result["ships"][0]
        assert "crew_roster" in player
        assert len(player["crew_roster"]) == len(state.crew_roster)


# ---------- Campaign commands (handler functions) ----------

class TestCampaignCommands:
    """Test the campaign command handler functions directly."""

    class MockRunner:
        """Minimal runner mock for campaign command testing."""
        def __init__(self):
            self._campaign_state = None
            self.root_dir = tempfile.mkdtemp()

    def test_campaign_new(self):
        from hybrid.commands.campaign_commands import cmd_campaign_new
        runner = self.MockRunner()
        result = cmd_campaign_new(runner, {})
        assert result["ok"] is True
        assert runner._campaign_state is not None
        assert result["campaign"]["credits"] > 0

    def test_campaign_status_no_campaign(self):
        from hybrid.commands.campaign_commands import cmd_campaign_status
        runner = self.MockRunner()
        result = cmd_campaign_status(runner, {})
        assert result["ok"] is False
        assert result["error"] == "NO_CAMPAIGN"

    def test_campaign_status_with_campaign(self):
        from hybrid.commands.campaign_commands import cmd_campaign_status
        runner = self.MockRunner()
        runner._campaign_state = CampaignState.new_campaign()
        result = cmd_campaign_status(runner, {})
        assert result["ok"] is True
        assert "campaign" in result

    def test_campaign_save_load_roundtrip(self):
        from hybrid.commands.campaign_commands import (
            cmd_campaign_new, cmd_campaign_save, cmd_campaign_load,
        )
        runner = self.MockRunner()

        # Create
        cmd_campaign_new(runner, {})
        runner._campaign_state.credits = 12345

        # Save
        save_result = cmd_campaign_save(runner, {})
        assert save_result["ok"] is True
        filepath = save_result["filepath"]

        # Clear and reload
        runner._campaign_state = None
        load_result = cmd_campaign_load(runner, {"filepath": filepath})
        assert load_result["ok"] is True
        assert runner._campaign_state.credits == 12345

    def test_campaign_save_no_campaign(self):
        from hybrid.commands.campaign_commands import cmd_campaign_save
        runner = self.MockRunner()
        result = cmd_campaign_save(runner, {})
        assert result["ok"] is False

    def test_campaign_load_missing_file(self):
        from hybrid.commands.campaign_commands import cmd_campaign_load
        runner = self.MockRunner()
        result = cmd_campaign_load(runner, {"filepath": "/nonexistent.json"})
        assert result["ok"] is False
        assert result["error"] == "FILE_NOT_FOUND"


# ---------- get_summary ----------

class TestGetSummary:
    """Verify the summary dict has all expected fields."""

    def test_summary_fields(self):
        state = CampaignState.new_campaign()
        summary = state.get_summary()
        expected_keys = {
            "credits", "reputation", "current_chapter", "ship_class",
            "hull_percent", "subsystems", "ammo", "fuel", "max_fuel",
            "crew_count", "crew_roster", "missions_completed",
            "mission_history", "unlocked_scenarios",
        }
        assert expected_keys.issubset(set(summary.keys()))

    def test_summary_is_json_serialisable(self):
        state = CampaignState.new_campaign()
        summary = state.get_summary()
        # Should not raise
        json.dumps(summary)
