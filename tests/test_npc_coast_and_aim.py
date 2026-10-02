"""Bounded NPC aiming, operator ownership, and real enemy fire regressions."""

import math
import random
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from hybrid.core.event_bus import EventBus
from hybrid.fleet.ai_controller import AIBehavior, AIController
from hybrid.navigation.autopilot.factory import AutopilotFactory
from hybrid.navigation.autopilot.npc_coast_and_aim import NPCCoastAndAimAutopilot
from hybrid.navigation.navigation_controller import NavigationController
from hybrid.systems.helm_system import HelmSystem
from hybrid.systems.sensors.contact import ContactData, ContactTracker
from hybrid.utils.quaternion import Quaternion


@pytest.fixture(autouse=True)
def preserve_rng_state():
    """These seeded regressions must not change other tests' process RNGs."""
    python_state, numpy_state = random.getstate(), np.random.get_state()
    yield
    random.setstate(python_state)
    np.random.set_state(numpy_state)


def _aim_ship(position=(5000.0, 0.0, 0.0)):
    contact = ContactData(
        "C001", dict(zip(("x", "y", "z"), position)),
        {"x": 0.0, "y": 0.0, "z": 0.0}, 0.9, 10.0, "passive",
        faction="unsa",
    )
    tracker = ContactTracker(stale_threshold=5.0)
    tracker.contacts[contact.id] = contact
    ship = SimpleNamespace(
        id="npc", class_type="corvette", faction="pirates", ai_enabled=True,
        position={"x": 0.0, "y": 0.0, "z": 0.0},
        velocity={"x": 50.0, "y": 10.0, "z": -2.0},
        orientation={"pitch": 75.0, "yaw": -140.0, "roll": 37.0},
        mass=5000.0, event_bus=EventBus(), systems={},
    )
    ship.systems["sensors"] = SimpleNamespace(
        enabled=True, contact_tracker=tracker, get_contact=tracker.get_contact,
    )
    ship.systems["helm"] = HelmSystem({})
    controller = NavigationController(ship)
    from hybrid.systems.navigation.navigation import NavigationSystem
    nav = NavigationSystem({})
    nav.controller = controller
    ship.systems["navigation"] = nav
    ship.ai_controller = AIController(ship)
    ai = ship.ai_controller
    ai.set_behavior(AIBehavior.ATTACK)
    ai.current_target = (contact.id, contact)
    ai._last_sim_time = 10.0
    return ship, contact, controller


def _engage(ship, controller):
    ship.ai_controller._behavior_attack()
    assert controller.autopilot_program_name == "npc_coast_and_aim"
    assert isinstance(controller.autopilot, NPCCoastAndAimAutopilot)
    return controller.autopilot


@pytest.mark.parametrize("position", [
    (5000, 0, 0), (0, 5000, 0), (-5000, 0, 0),
    (5000, -2500, 1000), (0, 0, 5000), (0, 0, -5000),
])
def test_coast_command_physically_faces_contact_without_moving_ship(position):
    ship, _, controller = _aim_ship(position)
    before_position, before_velocity = dict(ship.position), dict(ship.velocity)
    before_heading = dict(ship.orientation)
    command = _engage(ship, controller).compute(0.1, 10.0)
    heading = command["heading"]
    forward = Quaternion.from_euler(
        heading["pitch"], heading["yaw"], heading["roll"],
    ).rotate_vector(np.array([1.0, 0.0, 0.0]))
    assert np.dot(forward, np.array(position) / math.hypot(*position)) == pytest.approx(1.0)
    assert heading["roll"] == before_heading["roll"]
    assert command["thrust"] == 0.0
    assert ship.position == before_position
    assert ship.velocity == before_velocity
    assert ship.orientation == before_heading


def test_non_npc_cannot_select_combat_aim_program():
    ship, _, _ = _aim_ship()
    ship.ai_enabled = False
    with pytest.raises(ValueError, match="AI-enabled"):
        AutopilotFactory.create("npc_coast_and_aim", ship, "C001", {})


@pytest.mark.parametrize("owner", ["navigation", "manual", "override", "active_queue", "pending_queue"])
def test_operator_ownership_blocks_entry_and_running_aim(owner):
    ship, _, controller = _aim_ship()
    ap = _engage(ship, controller)
    helm = ship.systems["helm"]
    if owner == "navigation":
        controller.mode = "manual_override"
    elif owner == "manual":
        helm.mode = "manual"
    elif owner == "override":
        helm.manual_override = True
    elif owner == "active_queue":
        helm.active_command = {"cmd": "set_thrust", "thrust": 0.7}
    else:
        helm.command_queue = [{"cmd": "set_thrust", "thrust": 0.7}]
    assert ap.compute(0.1, 10.0) is None
    controller.autopilot = object()
    controller.autopilot_program_name = "match"
    original = controller.autopilot
    ship.ai_controller._autopilot_set_for_target = "match:C001"
    ship.ai_controller._behavior_attack()
    assert controller.autopilot is original
    assert controller.autopilot_program_name == "match"


@pytest.mark.parametrize("invalid", ["missing", "lost", "stale", "disabled", "nan", "coincident"])
def test_unusable_contact_coasts_and_holds_without_ship_truth(invalid):
    ship, contact, controller = _aim_ship()
    ap = _engage(ship, controller)
    ship._all_ships_ref = [SimpleNamespace(id="C001", position={"x": 0, "y": 5000, "z": 0})]
    if invalid == "missing":
        ship.systems["sensors"].contact_tracker.contacts.clear()
    elif invalid == "lost":
        contact.contact_state = "lost"
    elif invalid == "stale":
        contact.last_update = 0.0
    elif invalid == "disabled":
        ship.systems["sensors"].enabled = False
    elif invalid == "nan":
        contact.position["x"] = float("nan")
    else:
        contact.position = dict(ship.position)
    command = ap.compute(0.1, 10.0)
    assert command == {"thrust": 0.0, "heading": ship.orientation}
    assert command["heading"] is not ship.orientation


def test_reacquired_contact_and_cached_weapon_lead_cannot_supply_truth_aim():
    ship, contact, controller = _aim_ship()
    ap = _engage(ship, controller)
    ship.systems["combat"] = SimpleNamespace(truth_weapons={
        "railgun": SimpleNamespace(current_solution=SimpleNamespace(
            valid=True, target_id="OTHER", lead_angle={"yaw": 180, "pitch": 45},
        )),
    })
    tracker = ship.systems["sensors"].contact_tracker
    tracker.contacts.clear()
    assert ap.compute(0.1, 10.0)["heading"] == ship.orientation
    contact.position = {"x": 0.0, "y": 5000.0, "z": 0.0}
    contact.last_update = 11.0
    tracker.contacts[contact.id] = contact
    assert ap.compute(0.1, 11.0)["heading"]["yaw"] == pytest.approx(90.0)


@pytest.mark.parametrize("exit_reason", ["disabled", "behavior", "target"])
def test_phase_exit_releases_only_its_owned_slot(exit_reason):
    ship, _, controller = _aim_ship()
    ap = _engage(ship, controller)
    if exit_reason == "disabled":
        ship.ai_enabled = False
    elif exit_reason == "behavior":
        ship.ai_controller.set_behavior(AIBehavior.EVADE)
    else:
        ship.ai_controller.current_target = None
    assert ap.compute(0.1, 10.0) == {"thrust": 0.0, "heading": ship.orientation}
    assert controller.autopilot is None
    assert controller.mode == "manual"
    replacement = object()
    controller.autopilot = replacement
    controller.mode = "autopilot"
    assert ap.compute(0.1, 10.0) is None
    assert controller.autopilot is replacement


@pytest.mark.parametrize("preemption", ["range", "standoff", "disengage"])
def test_existing_reposition_priorities_take_over_from_coast(preemption):
    ship, contact, controller = _aim_ship()
    ap = _engage(ship, controller)
    expected_program = "evasive"
    if preemption == "range":
        contact.position["x"] = ship.ai_controller.weapon_range + 1.0
        expected_program = "intercept"
    elif preemption == "standoff":
        ship.ai_controller.profile = replace(ship.ai_controller.profile, min_engagement_range=6000.0)
    else:
        ship.ai_controller._disengage_until = 12.0
    assert ap.compute(0.1, 10.0) == {"thrust": 0.0, "heading": ship.orientation}
    ship.ai_controller._behavior_attack()
    assert controller.autopilot_program_name == expected_program


@pytest.mark.parametrize("seed", [0, 1, 42])
def test_native_enemy_fire_preserves_gates_and_accounts_for_impacts(seed, monkeypatch):
    from tests.test_gameplay_loop import _build_runner, SCENARIO_02, DT

    random.seed(seed)
    np.random.seed(seed)
    _, sim = _build_runner(SCENARIO_02)
    player, pirate = sim.ships["player"], sim.ships["pirate01"]
    combat = pirate.systems["combat"]
    projectiles, impacts, shots, power_draws = [], [], [], []
    power = pirate.systems.get("power_management") or pirate.systems["power"]
    original_power_request = power.request_power

    def observe_power(amount, system_name):
        result = original_power_request(amount, system_name)
        power_draws.append((amount, system_name, result))
        return result

    monkeypatch.setattr(power, "request_power", observe_power)
    for weapon in combat.truth_weapons.values():
        original_fire = weapon.fire

        def observe_fire(*args, _weapon=weapon, _fire=original_fire, **kwargs):
            solution = _weapon.current_solution
            before = (_weapon.ammo, _weapon.heat, _weapon._charge_state.value,
                      pirate.systems["targeting"].lock_state.value)
            first_draw = len(power_draws)
            result = _fire(*args, **kwargs)
            if result.get("ok"):
                shots.append((solution, before, _weapon.ammo, _weapon.heat,
                              power_draws[first_draw:], result))
            return result

        monkeypatch.setattr(weapon, "fire", observe_fire)
    for _ in range(20):
        sim.tick()
    bus = combat._projectile_manager._event_bus
    for name, callback in [("projectile_spawned", projectiles.append), ("projectile_impact", impacts.append)]:
        monkeypatch.setitem(bus.listeners, name, [*bus.listeners.get(name, []), callback])
    # Preserve the existing enemy-fire test's setup and 60-second window.
    player.position = {"x": pirate.position["x"] + 5000.0,
                       "y": pirate.position["y"], "z": pirate.position["z"]}
    player.velocity = dict(pirate.velocity)
    initial_hull = player.hull_integrity
    for _ in range(int(60 / DT)):
        sim.tick()

    assert combat.shots_fired > 0
    assert shots
    for solution, before, ammo, heat, draws, result in shots:
        assert solution.valid and solution.in_range and solution.in_arc
        assert solution.tracking and solution.ready_to_fire
        assert before[2:] == ("ready", "locked")
        assert ammo == before[0] - 1
        assert heat > before[1]
        assert any(amount == 15.0 and granted for amount, _, granted in draws)
        assert result["ballistic"] and result["projectile_id"]
    enemy_projectiles = [event for event in projectiles if event["shooter"] == pirate.id]
    assert {event["projectile_id"] for event in enemy_projectiles} == {
        result["projectile_id"] for *_, result in shots
    }
    assert all(event["target"] == player.id for event in enemy_projectiles)
    damage = sum(event["damage"] for event in impacts
                 if event["shooter"] == pirate.id and event["target"] == player.id
                 and event["hit"])
    # Noisy native contacts can produce physical misses. Account for the
    # actual impact damage in every seed while retaining a positive-hit case.
    assert player.hull_integrity == pytest.approx(max(0.0, initial_hull - damage))
    if seed == 0:
        assert damage > 0
