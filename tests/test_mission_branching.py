# tests/test_mission_branching.py
"""Tests for the mission branching and consequence system.

Tests cover:
1. Condition evaluation (all ConditionTypes)
2. BranchPoint triggering and activation
3. BranchingMission lifecycle (branch activation, objective mutation)
4. CommsChoiceManager (present, resolve, timeout)
5. YAML loader integration (branching scenario parses correctly)
6. Command registration (all 3 places)
"""

import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from hybrid.missions.conditions import (
    BranchCondition,
    ConditionType,
    evaluate_condition,
)
from hybrid.missions.branching import (
    BranchPoint,
    BranchingMission,
    MissionBranch,
)
from hybrid.missions.comms_choices import (
    CommsChoice,
    CommsChoiceManager,
    CommsChoiceOption,
)
from hybrid.scenarios.objectives import Objective, ObjectiveType, ObjectiveStatus


# ------------------------------------------------------------------
# Fixtures: lightweight mock sim and ships
# ------------------------------------------------------------------

def make_ship(ship_id="player", position=None, systems=None, damage_model=None):
    """Create a minimal mock ship for testing."""
    ship = SimpleNamespace()
    ship.id = ship_id
    ship.position = position or {"x": 0, "y": 0, "z": 0}
    ship.systems = systems or {}
    ship.damage_model = damage_model
    ship.event_bus = MagicMock()
    ship._runner_ref = None
    return ship


def make_sim(ships=None, time=0.0):
    """Create a minimal mock simulator."""
    sim = SimpleNamespace()
    sim.ships = ships or {}
    sim.time = time
    return sim


def make_damage_model(factors=None):
    """Create a mock damage model with configurable degradation factors."""
    dm = MagicMock()
    _factors = factors or {}
    dm.get_degradation_factor = lambda subsys: _factors.get(subsys, 1.0)
    dm.is_mission_kill = lambda: any(f <= 0 for f in _factors.values())
    return dm


def make_propulsion(fuel_level=1000, max_fuel=1000):
    """Create a mock propulsion system."""
    prop = SimpleNamespace()
    prop.fuel_level = fuel_level
    prop.max_fuel = max_fuel
    return prop


# ------------------------------------------------------------------
# Condition evaluation tests
# ------------------------------------------------------------------

class TestConditionEvaluation:
    """Tests for individual condition types."""

    def test_subsystem_state_destroyed(self):
        dm = make_damage_model({"propulsion": 0.0})
        ship = make_ship(damage_model=dm)
        sim = make_sim({"player": ship})

        cond = BranchCondition(
            ConditionType.SUBSYSTEM_STATE,
            {"target": "player", "subsystem": "propulsion", "state": "destroyed"},
        )
        assert evaluate_condition(cond, sim, ship, {}) is True

    def test_subsystem_state_nominal(self):
        dm = make_damage_model({"propulsion": 0.8})
        ship = make_ship(damage_model=dm)
        sim = make_sim({"player": ship})

        cond = BranchCondition(
            ConditionType.SUBSYSTEM_STATE,
            {"target": "player", "subsystem": "propulsion", "state": "nominal"},
        )
        assert evaluate_condition(cond, sim, ship, {}) is True

    def test_subsystem_state_impaired(self):
        dm = make_damage_model({"sensors": 0.3})
        ship = make_ship(damage_model=dm)
        sim = make_sim({"player": ship})

        cond = BranchCondition(
            ConditionType.SUBSYSTEM_STATE,
            {"target": "player", "subsystem": "sensors", "state": "impaired"},
        )
        assert evaluate_condition(cond, sim, ship, {}) is True

    def test_subsystem_no_damage_model_is_nominal(self):
        ship = make_ship(damage_model=None)
        sim = make_sim({"player": ship})

        cond = BranchCondition(
            ConditionType.SUBSYSTEM_STATE,
            {"target": "player", "subsystem": "propulsion", "state": "nominal"},
        )
        assert evaluate_condition(cond, sim, ship, {}) is True

    def test_fuel_level_low(self):
        prop = make_propulsion(fuel_level=200, max_fuel=1000)
        ship = make_ship(systems={"propulsion": prop})
        sim = make_sim({"player": ship})

        cond = BranchCondition(
            ConditionType.FUEL_LEVEL,
            {"target": "player", "comparison": "lt", "threshold": 0.25},
        )
        assert evaluate_condition(cond, sim, ship, {}) is True

    def test_fuel_level_not_low(self):
        prop = make_propulsion(fuel_level=900, max_fuel=1000)
        ship = make_ship(systems={"propulsion": prop})
        sim = make_sim({"player": ship})

        cond = BranchCondition(
            ConditionType.FUEL_LEVEL,
            {"target": "player", "comparison": "lt", "threshold": 0.25},
        )
        assert evaluate_condition(cond, sim, ship, {}) is False

    def test_time_elapsed_gt(self):
        sim = make_sim(time=400.0)
        ship = make_ship()
        context = {"start_time": 0.0}

        cond = BranchCondition(
            ConditionType.TIME_ELAPSED,
            {"threshold": 300, "comparison": "gt"},
        )
        assert evaluate_condition(cond, sim, ship, context) is True

    def test_time_elapsed_lt(self):
        sim = make_sim(time=100.0)
        ship = make_ship()
        context = {"start_time": 0.0}

        cond = BranchCondition(
            ConditionType.TIME_ELAPSED,
            {"threshold": 300, "comparison": "lt"},
        )
        assert evaluate_condition(cond, sim, ship, context) is True

    def test_contact_range_lt(self):
        player = make_ship(position={"x": 0, "y": 0, "z": 0})
        target = make_ship("target", position={"x": 500, "y": 0, "z": 0})
        sim = make_sim({"player": player, "target": target})

        cond = BranchCondition(
            ConditionType.CONTACT_RANGE,
            {"target": "target", "comparison": "lt", "range": 1000},
        )
        assert evaluate_condition(cond, sim, player, {}) is True

    def test_contact_range_gt(self):
        player = make_ship(position={"x": 0, "y": 0, "z": 0})
        target = make_ship("target", position={"x": 50000, "y": 0, "z": 0})
        sim = make_sim({"player": player, "target": target})

        cond = BranchCondition(
            ConditionType.CONTACT_RANGE,
            {"target": "target", "comparison": "gt", "range": 40000},
        )
        assert evaluate_condition(cond, sim, player, {}) is True

    def test_contact_lost_no_sensors(self):
        ship = make_ship(systems={})
        sim = make_sim()

        cond = BranchCondition(
            ConditionType.CONTACT_LOST,
            {"target": "enemy"},
        )
        # No sensors = contact is lost
        assert evaluate_condition(cond, sim, ship, {}) is True

    def test_comms_choice_matched(self):
        cond = BranchCondition(
            ConditionType.COMMS_CHOICE,
            {"choice_id": "surrender", "expected_option": "accept"},
        )
        context = {"comms_choices": {"surrender": "accept"}}
        ship = make_ship()
        sim = make_sim()
        assert evaluate_condition(cond, sim, ship, context) is True

    def test_comms_choice_not_matched(self):
        cond = BranchCondition(
            ConditionType.COMMS_CHOICE,
            {"choice_id": "surrender", "expected_option": "accept"},
        )
        context = {"comms_choices": {"surrender": "refuse"}}
        ship = make_ship()
        sim = make_sim()
        assert evaluate_condition(cond, sim, ship, context) is False

    def test_comms_choice_not_yet_made(self):
        cond = BranchCondition(
            ConditionType.COMMS_CHOICE,
            {"choice_id": "surrender", "expected_option": "accept"},
        )
        context = {"comms_choices": {}}
        ship = make_ship()
        sim = make_sim()
        assert evaluate_condition(cond, sim, ship, context) is False

    def test_objective_status_completed(self):
        cond = BranchCondition(
            ConditionType.OBJECTIVE_STATUS,
            {"objective_id": "detect", "status": "completed"},
        )
        context = {"objective_statuses": {"detect": "completed"}}
        ship = make_ship()
        sim = make_sim()
        assert evaluate_condition(cond, sim, ship, context) is True

    def test_ship_destroyed(self):
        sim = make_sim(ships={})  # target not in ships
        ship = make_ship()

        cond = BranchCondition(
            ConditionType.SHIP_DESTROYED,
            {"target": "enemy"},
        )
        assert evaluate_condition(cond, sim, ship, {}) is True

    def test_ship_not_destroyed(self):
        enemy = make_ship("enemy")
        sim = make_sim(ships={"enemy": enemy})
        ship = make_ship()

        cond = BranchCondition(
            ConditionType.SHIP_DESTROYED,
            {"target": "enemy"},
        )
        assert evaluate_condition(cond, sim, ship, {}) is False


# ------------------------------------------------------------------
# BranchPoint tests
# ------------------------------------------------------------------

class TestBranchPoint:
    """Tests for branch point evaluation."""

    def _make_branch_point(self, conditions, logic="and"):
        branch = MissionBranch(
            branch_id="test_branch",
            description="Test branch",
        )
        return BranchPoint(
            point_id="bp1",
            conditions=conditions,
            branch=branch,
            logic=logic,
        )

    def test_and_logic_all_true(self):
        conds = [
            BranchCondition(ConditionType.TIME_ELAPSED, {"threshold": 10, "comparison": "gt"}),
            BranchCondition(ConditionType.TIME_ELAPSED, {"threshold": 100, "comparison": "lt"}),
        ]
        bp = self._make_branch_point(conds, "and")
        sim = make_sim(time=50.0)
        ship = make_ship()
        assert bp.evaluate(sim, ship, {"start_time": 0}) is True

    def test_and_logic_one_false(self):
        conds = [
            BranchCondition(ConditionType.TIME_ELAPSED, {"threshold": 10, "comparison": "gt"}),
            BranchCondition(ConditionType.TIME_ELAPSED, {"threshold": 20, "comparison": "lt"}),
        ]
        bp = self._make_branch_point(conds, "and")
        sim = make_sim(time=50.0)
        ship = make_ship()
        # 50 > 10 is true, 50 < 20 is false
        assert bp.evaluate(sim, ship, {"start_time": 0}) is False

    def test_or_logic_one_true(self):
        conds = [
            BranchCondition(ConditionType.TIME_ELAPSED, {"threshold": 100, "comparison": "gt"}),
            BranchCondition(ConditionType.TIME_ELAPSED, {"threshold": 100, "comparison": "lt"}),
        ]
        bp = self._make_branch_point(conds, "or")
        sim = make_sim(time=50.0)
        ship = make_ship()
        # 50 > 100 is false, 50 < 100 is true -> OR = true
        assert bp.evaluate(sim, ship, {"start_time": 0}) is True

    def test_activated_branch_not_reevaluated(self):
        conds = [
            BranchCondition(ConditionType.TIME_ELAPSED, {"threshold": 10, "comparison": "gt"}),
        ]
        bp = self._make_branch_point(conds)
        bp.activated = True
        sim = make_sim(time=50.0)
        ship = make_ship()
        assert bp.evaluate(sim, ship, {"start_time": 0}) is False


# ------------------------------------------------------------------
# BranchingMission tests
# ------------------------------------------------------------------

class TestBranchingMission:
    """Tests for the BranchingMission lifecycle."""

    def _make_mission(self, objectives=None, branch_points=None):
        objs = objectives or [
            Objective("obj1", ObjectiveType.SURVIVE_TIME, "Survive",
                      {"time": 60, "start_time": 0}, required=True),
        ]
        return BranchingMission(
            name="Test Mission",
            description="Test",
            objectives=objs,
            branch_points=branch_points or [],
        )

    def test_branch_activates_and_adds_objectives(self):
        new_obj = Objective(
            "bonus", ObjectiveType.REACH_RANGE, "Bonus objective",
            {"target": "enemy", "range": 100}, required=False,
        )
        branch = MissionBranch(
            branch_id="bonus_branch",
            description="Bonus!",
            add_objectives=[new_obj],
        )
        bp = BranchPoint(
            point_id="bp_time",
            conditions=[
                BranchCondition(ConditionType.TIME_ELAPSED,
                                {"threshold": 5, "comparison": "gt"}),
            ],
            branch=branch,
        )

        mission = self._make_mission(branch_points=[bp])
        mission.start(0.0)

        # Before threshold
        sim = make_sim(time=3.0)
        ship = make_ship()
        mission.update(sim, ship)
        assert "bonus" not in mission.tracker.objectives
        assert len(mission.active_branches) == 0

        # After threshold
        sim.time = 10.0
        mission.update(sim, ship)
        assert "bonus" in mission.tracker.objectives
        assert mission.active_branches == ["bonus_branch"]
        assert len(mission.branch_history) == 1

    def test_branch_removes_objectives(self):
        obj1 = Objective("obj1", ObjectiveType.SURVIVE_TIME, "Survive",
                         {"time": 60, "start_time": 0}, required=True)
        obj2 = Objective("obj2", ObjectiveType.SURVIVE_TIME, "Extra",
                         {"time": 120, "start_time": 0}, required=True)

        branch = MissionBranch(
            branch_id="remove_branch",
            description="Remove extra",
            remove_objective_ids=["obj2"],
        )
        bp = BranchPoint(
            point_id="bp1",
            conditions=[
                BranchCondition(ConditionType.TIME_ELAPSED,
                                {"threshold": 5, "comparison": "gt"}),
            ],
            branch=branch,
        )

        mission = self._make_mission(
            objectives=[obj1, obj2], branch_points=[bp]
        )
        mission.start(0.0)

        sim = make_sim(time=10.0)
        ship = make_ship()
        mission.update(sim, ship)

        assert "obj1" in mission.tracker.objectives
        assert "obj2" not in mission.tracker.objectives

    def test_branch_overrides_success_message(self):
        branch = MissionBranch(
            branch_id="override",
            description="Override messages",
            success_message="Custom victory!",
        )
        bp = BranchPoint(
            point_id="bp1",
            conditions=[
                BranchCondition(ConditionType.TIME_ELAPSED,
                                {"threshold": 1, "comparison": "gt"}),
            ],
            branch=branch,
        )

        mission = self._make_mission(branch_points=[bp])
        mission.start(0.0)

        sim = make_sim(time=5.0)
        ship = make_ship()
        mission.update(sim, ship)

        assert mission.success_message == "Custom victory!"

    def test_comms_choice_recording(self):
        mission = self._make_mission()
        mission.start(0.0)

        mission.record_comms_choice("choice1", "option_a")
        assert mission.comms_choices == {"choice1": "option_a"}

    def test_comms_choice_triggers_branch(self):
        """Comms choice made -> branch condition satisfied on next update."""
        new_obj = Objective(
            "escort", ObjectiveType.REACH_POSITION, "Escort",
            {"position": {"x": 100, "y": 0, "z": 0}, "tolerance": 50},
            required=True,
        )
        branch = MissionBranch(
            branch_id="escort_branch",
            description="Escort phase",
            add_objectives=[new_obj],
        )
        bp = BranchPoint(
            point_id="bp_choice",
            conditions=[
                BranchCondition(ConditionType.COMMS_CHOICE,
                                {"choice_id": "surrender", "expected_option": "escort"}),
            ],
            branch=branch,
        )

        mission = self._make_mission(branch_points=[bp])
        mission.start(0.0)

        sim = make_sim(time=10.0)
        ship = make_ship()

        # Before choice
        mission.update(sim, ship)
        assert "escort" not in mission.tracker.objectives

        # Make choice
        mission.record_comms_choice("surrender", "escort")

        # Next tick picks it up
        sim.time = 11.0
        mission.update(sim, ship)
        assert "escort" in mission.tracker.objectives

    def test_only_one_branch_per_tick(self):
        """Verify that only the highest-priority branch fires per tick."""
        branch_a = MissionBranch("a", "Branch A")
        branch_b = MissionBranch("b", "Branch B")

        bp_a = BranchPoint(
            "bp_a",
            [BranchCondition(ConditionType.TIME_ELAPSED,
                             {"threshold": 1, "comparison": "gt"})],
            branch_a,
            priority=10,
        )
        bp_b = BranchPoint(
            "bp_b",
            [BranchCondition(ConditionType.TIME_ELAPSED,
                             {"threshold": 1, "comparison": "gt"})],
            branch_b,
            priority=5,
        )

        mission = self._make_mission(branch_points=[bp_a, bp_b])
        mission.start(0.0)

        sim = make_sim(time=5.0)
        ship = make_ship()
        mission.update(sim, ship)

        # Only highest priority should fire
        assert mission.active_branches == ["a"]
        assert bp_a.activated is True
        assert bp_b.activated is False

        # Next tick, the other fires
        sim.time = 6.0
        mission.update(sim, ship)
        assert "b" in mission.active_branches

    def test_get_status_includes_branches(self):
        mission = self._make_mission()
        mission.start(0.0)
        mission.active_branches = ["test_branch"]
        mission.branch_history = [{"branch": "test_branch", "time": 5.0}]

        status = mission.get_status(sim_time=10.0)
        assert "active_branches" in status
        assert "branch_history" in status
        assert status["active_branches"] == ["test_branch"]


# ------------------------------------------------------------------
# CommsChoiceManager tests
# ------------------------------------------------------------------

class TestCommsChoiceManager:
    """Tests for the comms choice lifecycle."""

    def _make_choice(self, choice_id="ch1", timeout=None, default=None):
        return CommsChoice(
            choice_id=choice_id,
            contact_id="enemy",
            prompt="What do you want?",
            options=[
                CommsChoiceOption("opt_a", "Option A", "Do thing A"),
                CommsChoiceOption("opt_b", "Option B", "Do thing B"),
            ],
            timeout=timeout,
            default_option=default,
        )

    def test_register_and_present(self):
        mgr = CommsChoiceManager()
        choice = self._make_choice()
        mgr.register_choice(choice)

        result = mgr.present_choice("ch1", sim_time=10.0)
        assert result is not None
        assert result["choice_id"] == "ch1"
        assert len(result["options"]) == 2
        assert len(mgr.active_choices) == 1

    def test_present_unknown_returns_none(self):
        mgr = CommsChoiceManager()
        assert mgr.present_choice("nonexistent", 0.0) is None

    def test_resolve_valid(self):
        mgr = CommsChoiceManager()
        choice = self._make_choice()
        mgr.register_choice(choice)
        mgr.present_choice("ch1", 10.0)

        result = mgr.resolve_choice("ch1", "opt_a")
        assert result == "opt_a"
        assert mgr.resolved["ch1"] == "opt_a"
        assert "ch1" not in mgr.active_choices

    def test_resolve_invalid_option(self):
        mgr = CommsChoiceManager()
        choice = self._make_choice()
        mgr.register_choice(choice)
        mgr.present_choice("ch1", 10.0)

        result = mgr.resolve_choice("ch1", "bad_option")
        assert result is None
        assert "ch1" in mgr.active_choices  # still active

    def test_resolve_inactive_choice(self):
        mgr = CommsChoiceManager()
        result = mgr.resolve_choice("nonexistent", "opt_a")
        assert result is None

    def test_timeout_auto_resolves(self):
        mgr = CommsChoiceManager()
        choice = self._make_choice(timeout=60.0, default="opt_b")
        mgr.register_choice(choice)
        mgr.present_choice("ch1", sim_time=100.0)

        # Before timeout
        auto = mgr.check_timeouts(sim_time=150.0)
        assert len(auto) == 0

        # After timeout
        auto = mgr.check_timeouts(sim_time=161.0)
        assert len(auto) == 1
        assert auto[0]["option_id"] == "opt_b"
        assert auto[0]["reason"] == "timeout"
        assert mgr.resolved["ch1"] == "opt_b"

    def test_no_timeout_without_default(self):
        mgr = CommsChoiceManager()
        choice = self._make_choice(timeout=60.0, default=None)
        mgr.register_choice(choice)
        mgr.present_choice("ch1", sim_time=100.0)

        auto = mgr.check_timeouts(sim_time=200.0)
        assert len(auto) == 0  # No default = no auto-resolve

    def test_get_state(self):
        mgr = CommsChoiceManager()
        choice = self._make_choice()
        mgr.register_choice(choice)
        mgr.present_choice("ch1", 0.0)

        state = mgr.get_state()
        assert state["total_choices"] == 1
        assert len(state["active_choices"]) == 1
        assert state["resolved_choices"] == {}


# ------------------------------------------------------------------
# YAML loader integration tests
# ------------------------------------------------------------------

class TestBranchingLoader:
    """Tests for YAML scenario loading with branching."""

    def test_branching_scenario_loads(self):
        """The sample branching scenario YAML parses without error."""
        import os
        from hybrid.scenarios.loader import ScenarioLoader

        scenario_path = os.path.join(
            os.path.dirname(__file__), "..", "scenarios", "08_branching_intercept.yaml"
        )
        if not os.path.exists(scenario_path):
            pytest.skip("Sample scenario not found")

        data = ScenarioLoader.load(scenario_path)
        mission = data["mission"]

        # Should be a BranchingMission, not a plain Mission
        assert isinstance(mission, BranchingMission)
        assert len(mission.branch_points) >= 4
        assert hasattr(mission, "comms_choice_manager")

    def test_branching_mission_has_comms_choices(self):
        """Comms choices from YAML are registered in the manager."""
        import os
        from hybrid.scenarios.loader import ScenarioLoader

        scenario_path = os.path.join(
            os.path.dirname(__file__), "..", "scenarios", "08_branching_intercept.yaml"
        )
        if not os.path.exists(scenario_path):
            pytest.skip("Sample scenario not found")

        data = ScenarioLoader.load(scenario_path)
        mission = data["mission"]
        mgr = mission.comms_choice_manager

        assert "surrender_response" in mgr.choices
        choice = mgr.choices["surrender_response"]
        assert len(choice.options) == 3
        assert choice.timeout == 120
        assert choice.default_option == "escort"

    def test_plain_scenario_still_loads(self):
        """Existing scenarios without branching still load as plain Mission."""
        import os
        from hybrid.scenarios.loader import ScenarioLoader
        from hybrid.scenarios.mission import Mission

        scenario_path = os.path.join(
            os.path.dirname(__file__), "..", "scenarios", "01_tutorial_intercept.yaml"
        )
        if not os.path.exists(scenario_path):
            pytest.skip("Tutorial scenario not found")

        data = ScenarioLoader.load(scenario_path)
        mission = data["mission"]

        # Should be a plain Mission, not BranchingMission
        assert type(mission) is Mission
        assert not isinstance(mission, BranchingMission)


# ------------------------------------------------------------------
# Command registration tests
# ------------------------------------------------------------------

class TestCommandRegistration:
    """Verify mission commands are registered in all 3 places."""

    def test_commands_in_system_commands_dict(self):
        """Commands registered in hybrid/command_handler.py system_commands."""
        from hybrid.command_handler import system_commands

        for cmd in ["comms_respond", "get_comms_choices", "get_branch_status"]:
            assert cmd in system_commands, f"{cmd} missing from system_commands"
            assert system_commands[cmd][0] == "comms"

    def test_commands_in_dispatcher(self):
        """Commands registered with the command dispatcher."""
        from hybrid.commands.dispatch import create_default_dispatcher

        dispatcher = create_default_dispatcher()
        for cmd in ["comms_respond", "get_comms_choices", "get_branch_status"]:
            assert cmd in dispatcher.commands, f"{cmd} missing from dispatcher"

    def test_commands_in_station_types(self):
        """Commands in COMMS station definition."""
        from server.stations.station_types import (
            STATION_DEFINITIONS,
            StationType,
        )

        comms_cmds = STATION_DEFINITIONS[StationType.COMMS].commands
        for cmd in ["comms_respond", "get_comms_choices", "get_branch_status"]:
            assert cmd in comms_cmds, f"{cmd} missing from COMMS station commands"


# ------------------------------------------------------------------
# Integration: mission command handlers
# ------------------------------------------------------------------

class TestMissionCommandHandlers:
    """Test the comms_respond and get_comms_choices command handlers."""

    def _setup_mission_with_choice(self):
        """Create a BranchingMission with a pending comms choice."""
        obj = Objective("obj1", ObjectiveType.SURVIVE_TIME, "Survive",
                        {"time": 60, "start_time": 0}, required=True)
        mission = BranchingMission(
            name="Test", description="Test",
            objectives=[obj], branch_points=[],
        )
        mission.start(0.0)

        mgr = CommsChoiceManager()
        choice = CommsChoice(
            choice_id="test_choice",
            contact_id="enemy",
            prompt="Surrender?",
            options=[
                CommsChoiceOption("yes", "Yes"),
                CommsChoiceOption("no", "No"),
            ],
        )
        mgr.register_choice(choice)
        mgr.present_choice("test_choice", sim_time=0.0)
        mission.comms_choice_manager = mgr

        # Wire up ship -> runner -> mission
        runner = SimpleNamespace()
        runner.mission = mission
        ship = make_ship()
        ship._runner_ref = runner

        return ship, mission

    def test_comms_respond_success(self):
        from hybrid.commands.mission_commands import cmd_comms_respond

        ship, mission = self._setup_mission_with_choice()
        comms = MagicMock()

        result = cmd_comms_respond(comms, ship, {
            "choice_id": "test_choice",
            "option_id": "yes",
        })
        assert result.get("ok") is True
        assert mission.comms_choices["test_choice"] == "yes"

    def test_comms_respond_invalid_option(self):
        from hybrid.commands.mission_commands import cmd_comms_respond

        ship, mission = self._setup_mission_with_choice()
        comms = MagicMock()

        result = cmd_comms_respond(comms, ship, {
            "choice_id": "test_choice",
            "option_id": "maybe",
        })
        assert "error" in result

    def test_get_comms_choices(self):
        from hybrid.commands.mission_commands import cmd_get_comms_choices

        ship, mission = self._setup_mission_with_choice()
        comms = MagicMock()

        result = cmd_get_comms_choices(comms, ship, {})
        assert result.get("ok") is True
        assert len(result["choices"]) == 1

    def test_get_branch_status(self):
        from hybrid.commands.mission_commands import cmd_get_branch_status

        ship, mission = self._setup_mission_with_choice()
        comms = MagicMock()

        result = cmd_get_branch_status(comms, ship, {})
        assert result.get("ok") is True
        assert "active_branches" in result
