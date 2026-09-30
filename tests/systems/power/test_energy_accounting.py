"""Finite power budgets, thermal reporting, and real tutorial power regression."""

import random
from types import SimpleNamespace

import numpy as np
import pytest

from hybrid.core.event_bus import EventBus
from hybrid.systems.power.management import PowerManagementSystem
from hybrid.systems.power_system import PowerSystem


class HeatLedger:
    """Capture energy-derived heat without simulating unrelated damage effects."""

    def __init__(self, factor=1.0, coefficient=0.3):
        self.factor = factor
        self.subsystems = {"power": SimpleNamespace(heat_generation=coefficient)}
        self.heat = []

    def get_combined_factor(self, subsystem):
        assert subsystem == "power"
        return self.factor

    def add_heat(self, subsystem, amount, event_bus, ship_id):
        self.heat.append(amount)


def ship_with_power(power, damage_factor=1.0):
    return SimpleNamespace(id="test", systems={"power_management": power},
                           damage_model=HeatLedger(damage_factor))


@pytest.mark.parametrize("dt", [0.05, 0.1, 0.2, 1.0])
def test_management_reports_generated_energy_once_at_every_timestep(dt):
    # Adequate explicit cooling isolates this conservation test from derating.
    power = PowerManagementSystem({"primary": {
        "capacity": 100.0, "output_rate": 50.0, "cooling_rate": 5.05,
    }})
    ship = ship_with_power(power)
    generated = 0.0
    for _ in range(round(60.0 / dt)):
        assert power.request_power(50.0 * dt, "propulsion")
        power.tick(dt, ship)
        generated += power.reactors["primary"].last_generated
        power.report_heat(ship, None)
        assert power.reactors["primary"].last_drawn == 0.0
    assert generated == pytest.approx(3000.0)
    assert sum(ship.damage_model.heat) == pytest.approx(0.3 * generated)


@pytest.mark.parametrize("hot,damage_factor", [(True, 1.0), (False, 0.5)])
def test_management_hot_or_damaged_reactor_reduces_supply(hot, damage_factor):
    power = PowerManagementSystem({"primary": {
        "capacity": 100.0, "output_rate": 10.0,
        "thermal_limit": 100.0, "cooling_rate": 0.0, "heat_rate": 0.0,
    }})
    reactor = power.reactors["primary"]
    reactor.available = 0.0
    if hot:
        reactor.temperature = 120.0
    power.tick(1.0, ship_with_power(power, damage_factor))
    assert reactor.last_generated == pytest.approx(5.0)
    assert not power.request_power(6.0, "propulsion")
    assert reactor.available == pytest.approx(5.0)
    assert power.request_power(5.0, "propulsion")


def test_overdrive_exceeds_fixed_cooling_and_retains_thermal_derating():
    power = PowerManagementSystem({"primary": {
        "capacity": 100.0, "output_rate": 10.0, "thermal_limit": 30.0,
    }})
    reactor = power.reactors["primary"]
    power.set_overdrive_limits({"primary": 2.0})
    for _ in range(12):
        assert power.request_power(20.0, "propulsion")
        power.tick(1.0)
    assert reactor.cooling_rate == pytest.approx(1.5)
    assert reactor.status == "overheated"
    assert reactor.last_generated == pytest.approx(10.0)


@pytest.mark.parametrize("params,expected", [({}, 1.5), ({"cooling_rate": None}, 0.0),
                                           ({"cooling_rate": 0.0}, 0.0),
                                           ({"cooling_rate": 7.0}, 7.0)])
def test_management_keeps_original_cooling_policy_across_output_changes(params, expected):
    power = PowerManagementSystem({"primary": {"capacity": 100.0, "output_rate": 50.0, **params}})
    reactor = power.reactors["primary"]
    assert reactor.cooling_rate == expected
    power.set_overdrive_limits({"primary": 2.0})
    power.tick(1.0)
    assert reactor.output_rate == pytest.approx(100.0)
    assert reactor.cooling_rate == expected
    power.tick(1.0, ship_with_power(power, damage_factor=0.25))
    assert reactor.output_rate == pytest.approx(25.0)
    assert reactor.cooling_rate == expected


def test_management_impossible_load_does_not_destroy_or_create_energy():
    power = PowerManagementSystem({
        "primary": {"capacity": 20.0}, "secondary": {"capacity": 10.0},
    })
    assert not power.request_power(30.0, "impossible")
    assert [r.available for r in power.reactors.values()] == [20.0, 10.0]
    assert all(r.last_drawn == 0.0 for r in power.reactors.values())


def test_legacy_delegation_has_one_generation_draw_and_heat_owner():
    power = PowerManagementSystem({"primary": {"capacity": 100.0, "output_rate": 10.0}})
    ship = ship_with_power(power)
    legacy = PowerSystem({"generation": 1000.0, "initial": 50.0})
    ship.systems["power"] = legacy
    events = EventBus.get_instance()
    legacy.tick(1.0, ship, events)
    assert legacy.request_power(10.0, "propulsion")
    power.tick(1.0, ship, events)
    legacy.report_heat(ship, events)
    power.report_heat(ship, events)
    assert power.reactors["primary"].available == pytest.approx(100.0)
    assert power.reactors["primary"].last_generated == pytest.approx(10.0)
    assert legacy.stored_power == pytest.approx(50.0)
    assert legacy._last_generated == 0.0
    assert sum(ship.damage_model.heat) == pytest.approx(3.0)


@pytest.mark.parametrize("initial,expected_generation", [(98.0, 2.0), (100.0, 0.0)])
def test_legacy_standalone_heat_counts_only_generation_that_fits(initial, expected_generation):
    legacy = PowerSystem({"generation": 10.0, "capacity": 100.0,
                          "initial": initial, "efficiency": 0.5})
    ship = SimpleNamespace(id="standalone", systems={"power": legacy}, damage_model=HeatLedger())
    events = EventBus.get_instance()
    legacy.tick(1.0, ship, events)
    assert legacy._last_generated == pytest.approx(expected_generation)
    assert legacy.current == pytest.approx(legacy.stored_power)
    assert legacy.request_power(10.0, "propulsion")
    legacy.report_heat(ship, events)
    assert sum(ship.damage_model.heat) == pytest.approx(0.3 * expected_generation)


def test_legacy_standalone_draw_cannot_exceed_actual_reserve():
    legacy = PowerSystem({"capacity": 100.0, "initial": 80.0})
    assert legacy.current == legacy.stored_power == 80.0
    assert not legacy.request_power(-10.0, "invalid")
    assert legacy.request_power(0.0, "idle")
    assert not legacy.request_power(90.0, "impossible")
    assert legacy.stored_power == 80.0
    assert legacy.request_power(80.0, "propulsion")
    assert legacy.stored_power == legacy.current == 0.0
    legacy.command("add_power", {"amount": 25.0})
    assert legacy.stored_power == legacy.current == 25.0


@pytest.fixture
def seeded_tutorial():
    """Reproduce sensor noise while preserving other tests' random state."""
    random_state = random.getstate()
    numpy_state = np.random.get_state()
    random.seed(20261001)
    np.random.seed(20261001)
    try:
        yield
    finally:
        random.setstate(random_state)
        np.random.set_state(numpy_state)


@pytest.mark.parametrize("max_thrust", [0.3, 0.5])
def test_tutorial_contact_rendezvous_docks_with_original_cooling(seeded_tutorial, max_thrust,
                                                               record_property):
    """Exercise actual sensor IDs and command routing, without mission objectives."""
    from tools.check_station_wiring import build_simulator, distance, issue, wait_for_contact

    sim = build_simulator()
    player = sim.ships["player"]
    station = sim.ships["target_station"]
    issue(sim, "player", "ping_sensors", {})
    contact_id = wait_for_contact(sim, "player", "target_station")
    assert contact_id != "target_station"
    issue(sim, "player", "lock_target", {"contact_id": contact_id})
    issue(sim, "player", "autopilot", {
        "enable": True, "program": "rendezvous", "target": contact_id,
        "profile": "balanced", "max_thrust": max_thrust,
    })
    assert all(reactor.cooling_rate == 1.5
               for reactor in player.systems["power_management"].reactors.values())
    requested_docking = False
    power_shortage_ticks = 0
    for _ in range(15000):
        sim.tick()
        if not player.systems["propulsion"].power_status:
            power_shortage_ticks += 1
        if distance(player, station) < 5000.0 and not requested_docking:
            issue(sim, "player", "request_docking", {"target": contact_id})
            requested_docking = True
        if getattr(player, "docked_to", None) == "target_station":
            break
    assert requested_docking
    assert player.docked_to == "target_station"
    assert distance(player, station) < 50.0
    docking_check = player.systems["docking"].last_check
    assert docking_check["range"] < 50.0
    assert docking_check["relative_velocity"] < 1.0
    if max_thrust == 0.3:
        assert power_shortage_ticks == 0
    # Record overload evidence at 50% thrust without imposing fragile exact counts.
    for name, value in {
        "max_thrust": max_thrust, "power_shortage_ticks": power_shortage_ticks,
        "sim_time": sim.time, "docking_range": docking_check["range"],
        "docking_relative_speed": docking_check["relative_velocity"],
    }.items():
        record_property(name, value)
