# tests/systems/power/test_reactor.py

import pytest
from hybrid.systems.power.reactor import Reactor


def test_reactor_ramp_and_overheat():
    r = Reactor(name="test", capacity=50.0, output_rate=10.0, thermal_limit=30.0,
                cooling_rate=0.0)
    r.temperature = 35.0
    r.available = 0.0
    r.tick(1.0)
    # Overheating derates new generation.
    assert r.available == pytest.approx(5.0)
    assert r.status == "overheated"


@pytest.mark.parametrize("dt", [0.05, 0.1, 0.2, 1.0])
def test_continuous_load_conserves_energy_with_explicit_adequate_cooling(dt):
    # Isolate energy accounting from the unchanged production thermal policy.
    reactor = Reactor("rated", capacity=100.0, output_rate=50.0, cooling_rate=5.05)
    drawn = generated = 0.0
    for _ in range(round(60.0 / dt)):
        energy = 50.0 * dt
        assert reactor.draw_power(energy)
        drawn += energy
        reactor.tick(dt)
        generated += reactor.last_generated
        assert reactor.status == "nominal"
        assert reactor.temperature <= reactor.thermal_limit
    assert drawn == pytest.approx(3000.0)
    assert generated == pytest.approx(drawn)
    assert reactor.available == pytest.approx(100.0)


def test_hot_reactor_derates_generation_and_preserves_stored_energy():
    reactor = Reactor("hot", capacity=100.0, output_rate=10.0,
                      thermal_limit=100.0, cooling_rate=0.0, heat_rate=0.0)
    reactor.available = 50.0
    reactor.temperature = 120.0
    reactor.tick(1.0)
    assert reactor.last_generated == pytest.approx(5.0)
    assert reactor.available == pytest.approx(55.0)
    assert reactor.status == "overheated"

    reactor.temperature = 95.0
    reactor.tick(1.0)
    assert reactor.last_generated == pytest.approx(5.0)
    assert reactor.status == "overheated"
    reactor.temperature = 90.0
    reactor.tick(1.0)
    assert reactor.last_generated == pytest.approx(10.0)
    assert reactor.status == "nominal"


@pytest.mark.parametrize("cooling_rate", [0.0, 0.1])
def test_explicit_inadequate_cooling_still_overheats(cooling_rate):
    reactor = Reactor("weak", capacity=100.0, output_rate=10.0,
                      thermal_limit=30.0, cooling_rate=cooling_rate)
    for _ in range(12):
        assert reactor.draw_power(10.0)
        reactor.tick(1.0)
    assert reactor.temperature > reactor.thermal_limit
    assert reactor.status == "overheated"
    assert reactor.last_generated == pytest.approx(5.0)


def test_default_cooling_remains_original_fixed_value_when_output_changes():
    reactor = Reactor("rated", capacity=100.0, output_rate=10.0)
    assert reactor.cooling_rate == pytest.approx(1.5)
    reactor.output_rate = 20.0
    reactor.capacity = 200.0
    reactor.tick(1.0)
    assert reactor.cooling_rate == pytest.approx(1.5)
    reactor.output_rate = 2.0
    reactor.capacity = 20.0
    reactor.tick(1.0)
    assert reactor.cooling_rate == pytest.approx(1.5)


@pytest.mark.parametrize("cooling_rate,expected", [(None, 0.0), (0.0, 0.0), (7.0, 7.0)])
def test_explicit_cooling_keeps_original_conversion(cooling_rate, expected):
    reactor = Reactor("explicit", output_rate=50.0, cooling_rate=cooling_rate)
    assert reactor.cooling_rate == expected


def test_generation_only_consumes_fuel_for_storage_headroom():
    reactor = Reactor("finite", capacity=100.0, output_rate=50.0,
                      fuel_capacity=10.0, fuel_consumption_rate=0.1)
    reactor.available = 99.0
    reactor.tick(1.0)
    assert reactor.available == pytest.approx(100.0)
    assert reactor.last_generated == pytest.approx(1.0)
    assert reactor.fuel_level == pytest.approx(9.9)
    reactor.tick(1.0)
    assert reactor.last_generated == 0.0
    assert reactor.fuel_level == pytest.approx(9.9)


def test_actual_fuel_exhaustion_limits_generation_then_denies_draw():
    reactor = Reactor("finite", capacity=10.0, output_rate=10.0,
                      fuel_capacity=1.0, fuel_consumption_rate=0.2)
    reactor.available = 0.0
    reactor.tick(1.0)
    assert reactor.last_generated == pytest.approx(5.0)
    assert reactor.fuel_level == 0.0
    assert reactor.draw_power(5.0)
    reactor.tick(1.0)
    assert reactor.status == "depleted"
    assert reactor.last_generated == 0.0
    assert not reactor.draw_power(1.0)


def test_explicit_empty_fuel_level_is_not_refilled():
    reactor = Reactor("empty", fuel_capacity=10.0, fuel_level=0.0,
                      fuel_consumption_rate=0.1)
    assert reactor.fuel_level == 0.0
    reactor.tick(1.0)
    assert reactor.status == "depleted"
    assert not reactor.draw_power(1.0)


def test_impossible_and_negative_draws_cannot_change_reserve_or_heat():
    reactor = Reactor("finite", capacity=100.0, output_rate=10.0,
                      fuel_capacity=10.0, fuel_consumption_rate=0.1)
    reactor.available = 50.0
    for amount in (51.0, -10.0):
        assert not reactor.draw_power(amount)
        assert reactor.available == 50.0
        assert reactor.temperature == 25.0
        assert reactor.last_drawn == 0.0
        assert reactor.fuel_level == 10.0
