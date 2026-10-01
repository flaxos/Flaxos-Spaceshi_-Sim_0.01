"""Real thermal telemetry reaches proposals without changing execution gates."""

import json
from pathlib import Path
import random

import numpy as np
import pytest

from hybrid.core.event_bus import EventBus
from hybrid.simulator import Simulator
from hybrid.systems.combat import combat_log
from hybrid.systems.crew_binding_system import CrewBindingSystem
from hybrid.systems.thermal_system import SPACE_BACKGROUND_TEMP


@pytest.fixture
def plant(monkeypatch):
    old_shared = (EventBus._instance, CrewBindingSystem._shared_crew_manager,
                  CrewBindingSystem._shared_binder)
    old_random, old_numpy = random.getstate(), np.random.get_state()
    old_combat_log = combat_log._combat_log_instance
    EventBus._instance = None
    CrewBindingSystem._shared_crew_manager = None
    CrewBindingSystem._shared_binder = None
    combat_log._combat_log_instance = None
    random.seed(20261001)
    np.random.seed(20261001)
    clock = {"now": 1000.0}
    monkeypatch.setattr("time.time", lambda: clock["now"])
    simulator = None
    try:
        config = json.loads((Path(__file__).resolve().parents[1] /
                             "scenarios/intercept_scenario.json").read_text())["ships"][0]
        simulator = Simulator(dt=0.1)
        ship = simulator.add_ship("thermal-test", config)
        simulator.start()
        yield simulator, ship, clock
    finally:
        if simulator is not None:
            simulator.stop()
        EventBus._instance, CrewBindingSystem._shared_crew_manager, \
            CrewBindingSystem._shared_binder = old_shared
        combat_log._combat_log_instance = old_combat_log
        random.setstate(old_random)
        np.random.set_state(old_numpy)


def prepare(ship, mode="manual"):
    auto = ship.systems["auto_engineering"]
    assert auto.command("set_mode", {"mode": mode})["ok"]
    assert auto.command("enable")["ok"]
    engineering = ship.systems["engineering"]
    assert engineering.command("manage_radiators", {"deployed": False})["ok"]
    return auto, engineering, ship.systems["thermal"]


def scan(auto, ship):
    auto.tick(0.1, ship, ship.event_bus)
    return {p["action"]: p for p in auto.get_state()["proposals"]}


@pytest.mark.parametrize("percent", [59.9, 60.0, 60.1, 84.0, 100.0])
def test_actual_percentage_units_and_strict_threshold(plant, percent):
    _, ship, _ = plant
    auto, engineering, thermal = prepare(ship)
    thermal.hull_temperature = (SPACE_BACKGROUND_TEMP + percent / 100.0 *
                                (thermal.max_temperature - SPACE_BACKGROUND_TEMP))
    assert thermal.get_state()["temperature_percent"] == percent
    assert "hull_temp_pct" not in thermal.get_state()
    before_thermal = thermal.get_state()
    before_engineering = engineering.get_state()

    proposals = scan(auto, ship)

    assert set(proposals) == ({"reduce_reactor", "deploy_radiators"}
                              if percent > 60.0 else set())
    for proposal in proposals.values():
        assert proposal["confidence"] == pytest.approx(percent / 100.0)
        assert proposal["reason"] == f"Hull temp at {percent / 100.0:.0%}"
        assert not proposal["auto_execute"]
    assert engineering.get_state() == before_engineering
    assert thermal.get_state() == before_thermal
    assert all(r.cooling_rate == 1.5
               for r in ship.systems["power_management"].reactors.values())


def test_disabled_by_default_and_disable_clears_hot_proposals(plant):
    _, ship, _ = plant
    auto = ship.systems["auto_engineering"]
    engineering = ship.systems["engineering"]
    ship.systems["thermal"].hull_temperature = 420.0
    assert engineering.command("manage_radiators", {"deployed": False})["ok"]
    assert not auto.enabled
    assert scan(auto, ship) == {}
    prepare(ship)
    assert len(scan(auto, ship)) == 2
    assert auto.command("disable")["ok"]
    assert scan(auto, ship) == {}
    assert engineering.reactor_output == 1.0
    assert not engineering.radiators_deployed


def test_unfitted_thermal_does_not_gain_capability(plant):
    _, ship, _ = plant
    auto, engineering, _ = prepare(ship)
    del ship.systems["thermal"]
    assert scan(auto, ship) == {}
    assert "thermal" not in ship.systems
    assert engineering.reactor_output == 1.0
    assert not engineering.radiators_deployed


@pytest.mark.parametrize("deployed,recent_hit,actions", [
    (True, False, {"reduce_reactor"}),
    (False, True, {"reduce_reactor"}),
    (True, True, {"reduce_reactor", "retract_radiators"}),
])
def test_existing_radiator_and_recent_damage_guards(plant, deployed, recent_hit, actions):
    _, ship, clock = plant
    auto, engineering, thermal = prepare(ship)
    thermal.hull_temperature = 420.0
    assert engineering.command("manage_radiators", {"deployed": deployed})["ok"]
    if recent_hit:
        ship.damage_model.last_hit_time = clock["now"] - 1.0
    assert set(scan(auto, ship)) == actions
    assert engineering.radiators_deployed is deployed
    assert engineering.reactor_output == 1.0


@pytest.mark.parametrize("approved,denied", [
    ("deploy_radiators", "reduce_reactor"),
    ("reduce_reactor", "deploy_radiators"),
])
def test_manual_execution_requires_selected_approval(plant, approved, denied):
    _, ship, clock = plant
    auto, engineering, thermal = prepare(ship)
    thermal.hull_temperature = 420.0
    proposals = scan(auto, ship)
    clock["now"] += 1.0
    assert auto.command("deny", {"proposal_id": proposals[denied]["proposal_id"]})["ok"]
    assert engineering.reactor_output == 1.0
    assert not engineering.radiators_deployed
    assert auto.command("approve", {"proposal_id": proposals[approved]["proposal_id"],
                                    "_ship": ship, "event_bus": ship.event_bus})["ok"]
    assert engineering.reactor_output == (0.5 if approved == "reduce_reactor" else 1.0)
    assert engineering.radiators_deployed is (approved == "deploy_radiators")
    assert auto.get_state()["proposal_count"] == 0


@pytest.mark.parametrize("mode", ["manual", "auto"])
def test_existing_eight_second_expiry_or_execution_and_cooldown(plant, mode):
    _, ship, clock = plant
    auto, engineering, thermal = prepare(ship, mode)
    thermal.hull_temperature = 420.0
    proposals = scan(auto, ship)
    assert len(proposals) == 2
    assert all(p["auto_execute"] is (mode == "auto") for p in proposals.values())
    clock["now"] = 1007.9
    assert len(scan(auto, ship)) == 2
    assert engineering.reactor_output == 1.0
    assert not engineering.radiators_deployed
    clock["now"] = 1008.1
    assert scan(auto, ship) == {}
    assert engineering.reactor_output == (0.5 if mode == "auto" else 1.0)
    assert engineering.radiators_deployed is (mode == "auto")
    clock["now"] = 1011.0
    assert scan(auto, ship) == {}, "Existing cooldown prevents immediate replacement"
    assert all(r.cooling_rate == 1.5
               for r in ship.systems["power_management"].reactors.values())


def test_switching_to_manual_prevents_pending_auto_execution(plant):
    _, ship, clock = plant
    auto, engineering, thermal = prepare(ship, "auto")
    thermal.hull_temperature = 420.0
    assert len(scan(auto, ship)) == 2
    assert auto.command("set_mode", {"mode": "manual"})["ok"]
    assert all(not p["auto_execute"] for p in auto.get_state()["proposals"])
    clock["now"] = 1008.1
    assert scan(auto, ship) == {}
    assert engineering.reactor_output == 1.0
    assert not engineering.radiators_deployed


def test_simulator_heating_reaches_manual_proposals_without_policy_changes(plant):
    simulator, ship, clock = plant
    auto, engineering, thermal = prepare(ship)
    assert thermal.get_state()["temperature_percent"] < 60.0
    initial_temperature = thermal.hull_temperature
    initial_sinks = thermal.heat_sink_remaining
    proposals = {}
    for _ in range(100):
        clock["now"] += simulator.dt
        simulator.tick()
        proposals = {p["action"]: p for p in auto.get_state()["proposals"]}
        if proposals:
            break
    assert thermal.hull_temperature > initial_temperature
    assert thermal.get_state()["temperature_percent"] > 60.0
    assert set(proposals) == {"reduce_reactor", "deploy_radiators"}
    assert engineering.reactor_output == 1.0
    assert not engineering.radiators_deployed
    assert engineering.drive_limit == 1.0
    assert thermal.heat_sink_remaining == initial_sinks
    assert not thermal.heat_sink_active
    assert all(r.cooling_rate == 1.5
               for r in ship.systems["power_management"].reactors.values())
