"""Tests for fuel consumption enforcement and depletion.

Validates:
  1. Propulsion fuel consumption follows Tsiolkovsky (mass flow = F/Ve)
  2. Drive locks out when fuel hits zero -- no thrust, ship drifts
  3. RCS remains functional when main drive is fuel-depleted
  4. Autopilot fuel budget checks refuse burns when insufficient delta-v
  5. AI ships switch to conservative behavior when fuel is low
  6. Telemetry includes real-time burn rate and time remaining
  7. Dynamic mass decreases as fuel is consumed
  8. Bingo fuel warning fires at 10%
"""

import math
import pytest
import logging

logger = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────

def _make_ship(fuel_level: float = 1000.0, max_fuel: float = 1000.0,
               max_thrust: float = 50000.0, isp: float = 3000.0,
               mass: float = 5000.0, ai_enabled: bool = False,
               faction: str = "unsa") -> "Ship":
    """Create a ship with configurable fuel parameters.

    Args:
        fuel_level: Initial fuel in kg
        max_fuel: Tank capacity in kg
        max_thrust: Max drive thrust in Newtons
        isp: Specific impulse in seconds
        mass: Dry mass in kg
        ai_enabled: Whether to enable AI controller
        faction: Ship faction

    Returns:
        Configured Ship instance
    """
    from hybrid.ship import Ship

    config = {
        "name": "test_ship",
        "mass": mass,
        "faction": faction,
        "systems": {
            "propulsion": {
                "max_thrust": max_thrust,
                "fuel_level": fuel_level,
                "max_fuel": max_fuel,
                "isp": isp,
            },
            "navigation": {},
        },
        "ai_enabled": ai_enabled,
    }
    ship = Ship("test_ship", config)
    return ship


def _tick_ship(ship, dt: float = 0.1, n: int = 1, sim_time: float = 0.0):
    """Tick a ship n times.

    Args:
        ship: Ship to tick
        dt: Time step per tick
        n: Number of ticks
        sim_time: Starting simulation time
    """
    for i in range(n):
        ship.tick(dt, all_ships=[ship], sim_time=sim_time + i * dt)


# ── 1. Fuel consumption follows Tsiolkovsky ──────────────────────

def test_fuel_consumed_proportional_to_thrust():
    """Higher thrust consumes more fuel per tick (mass flow = F/Ve)."""
    ship_lo = _make_ship(fuel_level=1000.0)
    ship_hi = _make_ship(fuel_level=1000.0)

    # Set different throttle levels
    ship_lo.systems["propulsion"].set_throttle({"thrust": 0.3})
    ship_hi.systems["propulsion"].set_throttle({"thrust": 1.0})

    _tick_ship(ship_lo, dt=1.0, n=1)
    _tick_ship(ship_hi, dt=1.0, n=1)

    fuel_used_lo = 1000.0 - ship_lo.systems["propulsion"].fuel_level
    fuel_used_hi = 1000.0 - ship_hi.systems["propulsion"].fuel_level

    # Higher throttle should use more fuel
    assert fuel_used_hi > fuel_used_lo
    # Ratio should be approximately 1.0/0.3 = 3.33x
    ratio = fuel_used_hi / fuel_used_lo if fuel_used_lo > 0 else float("inf")
    assert abs(ratio - (1.0 / 0.3)) < 0.5, f"Fuel ratio {ratio} not near 3.33"


def test_fuel_consumption_uses_exhaust_velocity():
    """Fuel consumption rate = thrust / exhaust_velocity."""
    ship = _make_ship(fuel_level=1000.0, max_thrust=50000.0, isp=3000.0)
    propulsion = ship.systems["propulsion"]

    exhaust_velocity = 3000.0 * 9.81  # Ve = Isp * g0

    propulsion.set_throttle({"thrust": 1.0})
    _tick_ship(ship, dt=1.0, n=1)

    expected_consumption = 50000.0 / exhaust_velocity * 1.0  # F/Ve * dt
    actual_consumption = 1000.0 - propulsion.fuel_level

    assert abs(actual_consumption - expected_consumption) < 0.01, (
        f"Expected {expected_consumption:.4f} kg, got {actual_consumption:.4f} kg"
    )


# ── 2. Drive locks out at zero fuel ─────────────────────────────

def test_drive_lockout_at_zero_fuel():
    """When fuel hits zero, throttle commands are rejected."""
    ship = _make_ship(fuel_level=0.0)
    propulsion = ship.systems["propulsion"]

    result = propulsion.set_throttle({"thrust": 1.0})
    assert "error" in result
    assert "No fuel" in result["error"]


def test_drive_lockout_mid_burn():
    """Ship transitions to no_fuel status when fuel runs out mid-burn."""
    # Give just enough fuel for ~1 tick at full thrust
    isp = 3000.0
    max_thrust = 50000.0
    ve = isp * 9.81
    # mass_flow = F/Ve, so fuel for 0.5s = F/Ve * 0.5
    tiny_fuel = (max_thrust / ve) * 0.5

    ship = _make_ship(fuel_level=tiny_fuel, max_thrust=max_thrust, isp=isp)
    propulsion = ship.systems["propulsion"]
    propulsion.set_throttle({"thrust": 1.0})

    # Tick for 1 second -- should exhaust fuel mid-tick
    _tick_ship(ship, dt=1.0, n=1)

    assert propulsion.fuel_level == 0.0
    assert propulsion.status == "no_fuel"
    assert propulsion.throttle == 0.0


def test_ship_drifts_after_fuel_depletion():
    """After fuel is depleted, ship maintains velocity but has zero acceleration."""
    # Use low ISP so fuel burns faster in the test
    ship = _make_ship(fuel_level=50.0, isp=300.0)
    propulsion = ship.systems["propulsion"]

    # Build up some velocity
    propulsion.set_throttle({"thrust": 1.0})
    _tick_ship(ship, dt=0.1, n=10, sim_time=0.0)

    # Keep ticking until fuel is gone
    for i in range(500):
        ship.tick(0.1, all_ships=[ship], sim_time=1.0 + i * 0.1)
        if propulsion.fuel_level <= 0:
            break

    assert propulsion.fuel_level == 0.0, (
        f"Fuel should be depleted, got {propulsion.fuel_level:.2f} kg"
    )

    # Ship should still be moving (drifting)
    speed_after = math.sqrt(sum(v**2 for v in ship.velocity.values()))
    assert speed_after > 0.1, "Ship should drift after fuel depletion"

    # One more tick to confirm zero acceleration
    ship.tick(0.1, all_ships=[ship], sim_time=100.0)
    accel = math.sqrt(sum(a**2 for a in ship.acceleration.values()))
    assert accel < 0.001, "Acceleration should be zero with no fuel"


# ── 3. RCS remains functional without main drive fuel ────────────

def test_rcs_works_without_main_fuel():
    """RCS attitude control works even when main drive fuel is zero."""
    ship = _make_ship(fuel_level=0.0)
    rcs = ship.systems.get("rcs")

    if rcs is None:
        pytest.skip("No RCS system in test ship config")

    # RCS should still accept commands
    result = rcs.set_attitude_target({"pitch": 0.0, "yaw": 90.0, "roll": 0.0})
    assert "error" not in result

    # Tick should not crash
    _tick_ship(ship, dt=0.1, n=5)

    # RCS should be active (providing torque for rotation)
    assert rcs.status in ("active", "standby")


# ── 4. Autopilot fuel budget checks ─────────────────────────────

def test_autopilot_base_remaining_delta_v():
    """BaseAutopilot correctly calculates remaining delta-v."""
    from hybrid.utils.units import calculate_delta_v

    ship = _make_ship(fuel_level=500.0, mass=5000.0, isp=3000.0)
    propulsion = ship.systems["propulsion"]

    # Create a concrete autopilot for testing
    from hybrid.navigation.autopilot.goto_position import GoToPositionAutopilot
    ap = GoToPositionAutopilot(ship, params={
        "x": 100000, "y": 0, "z": 0,
    })

    expected_dv = calculate_delta_v(ship.dry_mass, 500.0, 3000.0)
    actual_dv = ap._get_remaining_delta_v()

    assert abs(actual_dv - expected_dv) < 1.0, (
        f"Expected {expected_dv:.1f} m/s, got {actual_dv:.1f} m/s"
    )


def test_autopilot_refuses_burn_when_budget_insufficient():
    """GoToPositionAutopilot refuses acceleration when fuel budget would
    leave insufficient braking delta-v."""
    # Create ship with very little fuel, already moving fast
    ship = _make_ship(fuel_level=10.0, mass=5000.0, isp=3000.0)
    ship.velocity = {"x": 500.0, "y": 0.0, "z": 0.0}

    from hybrid.navigation.autopilot.goto_position import GoToPositionAutopilot
    ap = GoToPositionAutopilot(ship, params={
        "x": 1000000, "y": 0, "z": 0,
        "stop": True,
    })

    # The ship is moving at 500 m/s but has very little fuel.
    # The autopilot should detect insufficient budget and enter braking.
    cmd = ap.compute(0.1, 0.0)

    # Should not be accelerating
    assert ap.phase != "ACCELERATE", (
        f"Autopilot should not accelerate with insufficient fuel, "
        f"phase={ap.phase}, status={ap.status}"
    )


def test_autopilot_fuel_depleted_sets_drift_status():
    """GoToPositionAutopilot reports drift status when fuel is depleted."""
    ship = _make_ship(fuel_level=0.0, mass=5000.0)
    ship.velocity = {"x": 100.0, "y": 0.0, "z": 0.0}

    from hybrid.navigation.autopilot.goto_position import GoToPositionAutopilot
    ap = GoToPositionAutopilot(ship, params={
        "x": 1000000, "y": 0, "z": 0,
    })

    cmd = ap.compute(0.1, 0.0)
    assert cmd["thrust"] == 0.0
    assert "no_fuel" in ap.status


def test_autopilot_allows_burn_with_sufficient_fuel():
    """GoToPositionAutopilot allows acceleration when fuel budget is healthy."""
    ship = _make_ship(fuel_level=1000.0, mass=5000.0, isp=3000.0)
    ship.velocity = {"x": 0.0, "y": 0.0, "z": 0.0}

    from hybrid.navigation.autopilot.goto_position import GoToPositionAutopilot
    ap = GoToPositionAutopilot(ship, params={
        "x": 100000, "y": 0, "z": 0,
        "stop": True,
    })

    cmd = ap.compute(0.1, 0.0)
    assert ap.phase == "ACCELERATE"


# ── 5. AI fuel-aware behavior ───────────────────────────────────

def test_ai_low_fuel_switches_to_conservative():
    """AI controller switches from ATTACK to conservative when fuel is low."""
    ship = _make_ship(fuel_level=50.0, max_fuel=1000.0,
                      ai_enabled=True, faction="pirates")
    ai = ship.ai_controller

    if ai is None:
        pytest.skip("AI controller not initialized")

    # Force into attack mode
    from hybrid.fleet.ai_controller import AIBehavior
    ai.set_behavior(AIBehavior.ATTACK)

    # Run a decision cycle -- fuel is at 5%, should trigger fuel reaction
    ai.last_decision_time = 0.0
    ai.update(0.1, 10.0)

    # Should no longer be in ATTACK -- fuel reaction should override
    assert ai.behavior != AIBehavior.ATTACK, (
        f"AI should not be in ATTACK with 5% fuel, got {ai.behavior.value}"
    )


def test_ai_emergency_dv_margin_switches_to_hold():
    """AI controller switches to HOLD when delta-v margin is critically low."""
    # Ship moving fast with almost no fuel -- can barely stop
    ship = _make_ship(fuel_level=5.0, max_fuel=1000.0,
                      ai_enabled=True, faction="pirates")
    ship.velocity = {"x": 200.0, "y": 0.0, "z": 0.0}
    ai = ship.ai_controller

    if ai is None:
        pytest.skip("AI controller not initialized")

    from hybrid.fleet.ai_controller import AIBehavior
    ai.set_behavior(AIBehavior.ATTACK)

    ai.last_decision_time = 0.0
    ai.update(0.1, 10.0)

    # Delta-v margin should be < 1.2 -> HOLD_POSITION
    assert ai.behavior == AIBehavior.HOLD_POSITION, (
        f"AI should switch to HOLD with critical dv margin, "
        f"got {ai.behavior.value}"
    )


def test_ai_full_fuel_no_fuel_reaction():
    """AI controller does not trigger fuel reaction with full tanks."""
    ship = _make_ship(fuel_level=1000.0, max_fuel=1000.0,
                      ai_enabled=True, faction="pirates")
    ai = ship.ai_controller

    if ai is None:
        pytest.skip("AI controller not initialized")

    # Fuel check should not override behavior
    assert not ai._check_fuel_reaction()


# ── 6. Telemetry includes burn rate ─────────────────────────────

def test_telemetry_burn_rate_during_thrust():
    """Telemetry reports non-zero burn rate during active thrust."""
    ship = _make_ship(fuel_level=1000.0)
    propulsion = ship.systems["propulsion"]
    propulsion.set_throttle({"thrust": 0.5})

    _tick_ship(ship, dt=0.1, n=1)

    state = propulsion.get_state()
    assert state["fuel_burn_rate"] > 0.0
    assert state["fuel_time_remaining"] is not None
    assert state["fuel_time_remaining"] > 0.0


def test_telemetry_burn_rate_zero_when_idle():
    """Telemetry reports zero burn rate when not thrusting."""
    ship = _make_ship(fuel_level=1000.0)
    _tick_ship(ship, dt=0.1, n=1)

    state = ship.systems["propulsion"].get_state()
    assert state["fuel_burn_rate"] == 0.0
    assert state["fuel_time_remaining"] is None


def test_telemetry_includes_fuel_budget():
    """Ship telemetry includes fuel burn rate and time remaining."""
    from hybrid.telemetry import get_ship_telemetry

    ship = _make_ship(fuel_level=500.0)
    propulsion = ship.systems["propulsion"]
    propulsion.set_throttle({"thrust": 1.0})
    _tick_ship(ship, dt=0.1, n=1)

    telemetry = get_ship_telemetry(ship, sim_time=1.0)
    fuel = telemetry["fuel"]

    assert "burn_rate" in fuel
    assert fuel["burn_rate"] > 0.0
    assert "time_remaining" in fuel
    assert fuel["time_remaining"] is not None


# ── 7. Dynamic mass decreases ───────────────────────────────────

def test_mass_decreases_as_fuel_burns():
    """Ship total mass decreases as propulsion fuel is consumed."""
    ship = _make_ship(fuel_level=500.0, mass=5000.0)
    initial_mass = ship.mass

    propulsion = ship.systems["propulsion"]
    propulsion.set_throttle({"thrust": 1.0})

    _tick_ship(ship, dt=1.0, n=10, sim_time=0.0)

    assert ship.mass < initial_mass, (
        f"Mass should decrease: initial={initial_mass}, current={ship.mass}"
    )
    # Mass decrease should equal fuel consumed
    fuel_consumed = 500.0 - propulsion.fuel_level
    expected_mass = initial_mass - fuel_consumed
    assert abs(ship.mass - expected_mass) < 1.0, (
        f"Mass mismatch: expected ~{expected_mass:.1f}, got {ship.mass:.1f}"
    )


# ── 8. Bingo fuel warning ───────────────────────────────────────

def test_bingo_fuel_fires_at_ten_percent():
    """Propulsion system fires bingo_fuel event when fuel drops below 10%."""
    ship = _make_ship(fuel_level=150.0, max_fuel=1000.0)
    propulsion = ship.systems["propulsion"]

    # Track events
    bingo_events = []
    ship.event_bus.subscribe("bingo_fuel", lambda data: bingo_events.append(data))

    propulsion.set_throttle({"thrust": 1.0})

    # Tick until fuel should be below 10% (100 kg)
    for i in range(500):
        ship.tick(0.1, all_ships=[ship], sim_time=i * 0.1)
        if propulsion.fuel_level <= 0:
            break

    assert len(bingo_events) >= 1, "Bingo fuel event should fire"
    assert bingo_events[0]["fuel_pct"] <= 10.0


# ── 9. Autopilot get_state includes fuel budget ─────────────────

def test_autopilot_state_includes_fuel_budget():
    """Autopilot state dict includes fuel_budget sub-dict."""
    ship = _make_ship(fuel_level=500.0, mass=5000.0, isp=3000.0)

    from hybrid.navigation.autopilot.goto_position import GoToPositionAutopilot
    ap = GoToPositionAutopilot(ship, params={
        "x": 100000, "y": 0, "z": 0,
    })

    state = ap.get_state()
    assert "fuel_budget" in state
    budget = state["fuel_budget"]
    assert "remaining_dv" in budget
    assert "dv_to_stop" in budget
    assert "margin" in budget
    assert "fuel_critical" in budget
    assert "fuel_depleted" in budget
    assert budget["remaining_dv"] > 0
    assert not budget["fuel_depleted"]
