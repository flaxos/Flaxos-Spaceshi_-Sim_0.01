#!/usr/bin/env python3
"""Headless all-stop autopilot test harness.

Tests the AllStopAutopilot's ability to decelerate a ship from various
initial velocities to a complete stop.  Measures stop time, phase
progression, and compares actual performance to theoretical predictions.

The ship starts at the origin with a given velocity, engages the all_stop
autopilot, and must reach magnitude(velocity) < 0.1 m/s within the time
budget.

Test matrix covers:
  - Single-axis and multi-axis velocities
  - G-levels from 0.3 to 3.4
  - Edge cases (already slow, reverse direction)

Usage:
    python3 tools/test_all_stop.py
    python3 tools/test_all_stop.py --g-level 2.0
    python3 tools/test_all_stop.py --max-ticks 8000
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

# Ensure project root is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from hybrid.simulator import Simulator
from hybrid.utils.math_utils import magnitude

# ---------------------------------------------------------------------------
# Logging -- keep autopilot phase changes visible, suppress noisy subsystems
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(levelname).1s %(name)s: %(message)s")
for noisy in (
    "hybrid.core.event_bus",
    "hybrid.systems",
    "hybrid.ship",
    "hybrid.fleet",
    "hybrid.systems.combat",
    "hybrid.systems.sensors",
    "hybrid.systems.propulsion",
    "hybrid.systems.helm",
    "hybrid.navigation.navigation_controller",
    "hybrid.systems.navigation.navigation",
    "hybrid.navigation.autopilot.match_velocity",
):
    logging.getLogger(noisy).setLevel(logging.WARNING)

logger = logging.getLogger("test_all_stop")


# ---------------------------------------------------------------------------
# Data classes for results
# ---------------------------------------------------------------------------
@dataclass
class PhaseRecord:
    """Tracks telemetry for a single autopilot phase."""
    name: str
    start_tick: int
    end_tick: int = 0
    start_speed: float = 0.0
    end_speed: float = 0.0
    peak_speed: float = 0.0
    peak_accel: float = 0.0
    duration_s: float = 0.0


@dataclass
class RunResult:
    """Complete result of a single all-stop test run."""
    test_name: str
    initial_velocity: tuple[float, float, float]
    initial_speed: float
    g_level: float
    success: bool
    failure_reason: Optional[str] = None
    total_ticks: int = 0
    total_time_s: float = 0.0
    final_speed_ms: float = 0.0
    theoretical_time_s: float = 0.0
    time_ratio: float = 0.0          # actual / theoretical
    time_budget_s: float = 0.0       # max allowed time (150% of theoretical + 20s)
    phases: list[PhaseRecord] = field(default_factory=list)
    phase_names: list[str] = field(default_factory=list)
    accel_samples: list[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Test case definition
# ---------------------------------------------------------------------------
@dataclass
class TestCase:
    """Definition of a single all-stop test scenario."""
    name: str
    velocity: tuple[float, float, float]
    g_level: float
    expected_time_approx: float       # Rough expected stop time (seconds)


# Default test matrix
DEFAULT_TESTS: list[TestCase] = [
    TestCase("slow_x",        (100, 0, 0),       1.0,   10),
    TestCase("fast_x",        (2000, 0, 0),      1.0,  204),
    TestCase("multi_axis",    (500, 300, -200),   1.0,   65),
    TestCase("combat_brake",  (1000, 0, 0),       3.0,   34),
    TestCase("belter_gentle", (500, 0, 0),        0.3,  170),
    TestCase("max_emergency", (3000, 0, 0),       3.4,   90),
    TestCase("already_slow",  (2, 1, -1),         1.0,   10),
    TestCase("reverse",       (-800, 0, 0),       1.0,   82),
]


# ---------------------------------------------------------------------------
# Scenario builder -- no target needed for all-stop
# ---------------------------------------------------------------------------
def build_all_stop_scenario(dt: float = 0.1) -> dict:
    """Build a minimal scenario with a single player ship at the origin.

    The ship has no target -- all_stop only cares about its own velocity.
    Ship specs: 5000 kg, 500 kN max thrust (same as tutorial corvette).
    """
    return {
        "name": "All-Stop Test",
        "dt": dt,
        "ships": [
            {
                "id": "player",
                "name": "Test Corvette",
                "class": "corvette",
                "player_controlled": True,
                "position": {"x": 0, "y": 0, "z": 0},
                "velocity": {"x": 0, "y": 0, "z": 0},
                "mass": 5000,
                "systems": {
                    "propulsion": {
                        "max_thrust": 500000,   # 500 kN = 10.2G for 5t
                        "fuel_level": 10000,
                        "max_fuel": 10000,
                    },
                    "sensors": {
                        "passive": {"range": 100000},
                    },
                    "navigation": {},
                },
            },
        ],
    }


def build_simulator_from_dict(scenario: dict) -> Simulator:
    """Build a simulator from a scenario dict (not a file)."""
    dt = scenario.get("dt", 0.1)
    sim = Simulator(dt=dt, time_scale=1.0)

    for ship_data in scenario["ships"]:
        sim.add_ship(ship_data["id"], ship_data)

    # Wire up cross-ship references (sensors need this)
    all_ships = list(sim.ships.values())
    for ship in all_ships:
        ship._all_ships_ref = all_ships

    sim.start()
    return sim


# ---------------------------------------------------------------------------
# Run a single test case
# ---------------------------------------------------------------------------
def run_test(test: TestCase, g_override: Optional[float],
             max_ticks: int, dt: float = 0.1) -> RunResult:
    """Run the all-stop autopilot for a single test case.

    Args:
        test: Test case definition.
        g_override: If set, overrides the test's g_level.
        max_ticks: Maximum simulation ticks before timeout.
        dt: Simulation time step.

    Returns:
        RunResult with success/failure and detailed metrics.
    """
    g_level = g_override if g_override is not None else test.g_level
    vx, vy, vz = test.velocity
    initial_speed = math.sqrt(vx**2 + vy**2 + vz**2)

    # Theoretical stop time: |v| / (g * 9.81), plus 20s flip allowance
    accel = g_level * 9.81
    theoretical = initial_speed / accel if accel > 0 else 0.0
    time_budget = theoretical * 1.5 + 20.0

    result = RunResult(
        test_name=test.name,
        initial_velocity=test.velocity,
        initial_speed=initial_speed,
        g_level=g_level,
        success=False,
        theoretical_time_s=theoretical,
        time_budget_s=time_budget,
    )

    print(f"\n{'='*70}")
    print(f"  TEST: {test.name}")
    print(f"  Velocity: ({vx}, {vy}, {vz}) m/s  |v|={initial_speed:.1f} m/s")
    print(f"  G-level: {g_level:.1f}  ({accel:.1f} m/s^2)")
    print(f"  Theoretical stop: {theoretical:.1f}s  Budget: {time_budget:.1f}s")
    print(f"{'='*70}")

    # Build scenario and simulator
    scenario = build_all_stop_scenario(dt)
    sim = build_simulator_from_dict(scenario)
    player = sim.ships["player"]

    # Set initial velocity directly on the ship
    player.velocity = {"x": vx, "y": vy, "z": vz}

    # Warm up -- let systems initialise (sensors, nav controller, etc.)
    for _ in range(10):
        sim.tick()

    # Engage all-stop autopilot via the navigation system command interface
    nav = player.systems.get("navigation")
    if nav is None:
        result.failure_reason = "No navigation system on player ship"
        return result

    engage_result = nav.command("set_autopilot", {
        "program": "all_stop",
        "g_level": g_level,
        "ship": player,
        "_ship": player,
        "event_bus": player.event_bus,
    })

    if isinstance(engage_result, dict) and engage_result.get("error"):
        result.failure_reason = f"Autopilot engage failed: {engage_result}"
        return result

    # ----- Tick loop -----
    last_phase: Optional[str] = None
    current_phase_record: Optional[PhaseRecord] = None
    stopped = False

    for tick in range(max_ticks):
        sim.tick()

        speed = magnitude(player.velocity)

        # Instantaneous acceleration (if available)
        accel_val = 0.0
        if hasattr(player, "acceleration"):
            accel_val = magnitude(player.acceleration)

        # Get autopilot phase
        phase = "unknown"
        if nav and nav.controller and nav.controller.autopilot:
            ap = nav.controller.autopilot
            phase = getattr(ap, "phase", "unknown")

        # Phase tracking
        if phase != last_phase:
            if current_phase_record:
                current_phase_record.end_tick = tick
                current_phase_record.end_speed = speed
                current_phase_record.duration_s = (tick - current_phase_record.start_tick) * dt

            current_phase_record = PhaseRecord(
                name=phase,
                start_tick=tick,
                start_speed=speed,
            )
            result.phases.append(current_phase_record)
            result.phase_names.append(phase)
            last_phase = phase

        # Update current phase stats
        if current_phase_record:
            if speed > current_phase_record.peak_speed:
                current_phase_record.peak_speed = speed
            if accel_val > current_phase_record.peak_accel:
                current_phase_record.peak_accel = accel_val

        # Sample acceleration every 10 ticks
        if tick % 10 == 0:
            result.accel_samples.append(accel_val)

        # Status output every 200 ticks
        if tick % 200 == 0:
            print(f"  [t={tick:5d}] phase={phase:<10s} "
                  f"speed={speed:10.3f} m/s  "
                  f"accel={accel_val:6.1f} m/s^2")

        # ----- Success check: speed < 0.1 m/s -----
        if speed < 0.1:
            # Close final phase record
            if current_phase_record:
                current_phase_record.end_tick = tick
                current_phase_record.end_speed = speed
                current_phase_record.duration_s = (tick - current_phase_record.start_tick) * dt

            result.success = True
            result.total_ticks = tick + 1
            result.total_time_s = sim.time
            result.final_speed_ms = speed
            result.time_ratio = (result.total_time_s / result.theoretical_time_s
                                 if result.theoretical_time_s > 0 else 0.0)

            # Check time budget
            if result.total_time_s > time_budget:
                result.success = False
                result.failure_reason = (
                    f"Stopped but too slow: {result.total_time_s:.1f}s "
                    f"> budget {time_budget:.1f}s "
                    f"(150% of theoretical {theoretical:.1f}s + 20s flip)")

            stopped = True
            print(f"\n  *** STOPPED at tick {tick} ({sim.time:.1f}s) ***")
            print(f"      speed={speed:.4f} m/s  "
                  f"time_ratio={result.time_ratio:.2f}x")
            break

    # Timeout
    if not stopped:
        if current_phase_record:
            current_phase_record.end_tick = max_ticks
            current_phase_record.end_speed = magnitude(player.velocity)
            current_phase_record.duration_s = (max_ticks - current_phase_record.start_tick) * dt

        result.failure_reason = f"Timed out after {max_ticks} ticks ({max_ticks * dt:.0f}s)"
        result.total_ticks = max_ticks
        result.total_time_s = sim.time
        result.final_speed_ms = magnitude(player.velocity)
        result.time_ratio = (result.total_time_s / result.theoretical_time_s
                             if result.theoretical_time_s > 0 else 0.0)

        print(f"\n  *** TIMEOUT at tick {max_ticks} ({sim.time:.1f}s) ***")
        print(f"      speed={result.final_speed_ms:.3f} m/s")

    return result


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------
def print_summary(results: list[RunResult]) -> None:
    """Print a comparison table across all tests."""

    print(f"\n{'='*110}")
    print(f"  ALL-STOP AUTOPILOT TEST SUMMARY")
    print(f"{'='*110}")

    # Header
    print(f"\n{'Test':<18s} | {'|v|':>7s} | {'G':>4s} | {'Result':>6s} | "
          f"{'Time':>8s} | {'Theor.':>8s} | {'Ratio':>6s} | "
          f"{'Budget':>8s} | {'Final v':>9s} | {'Phases'}")
    print(f"{'-'*18}-+-{'-'*7}-+-{'-'*4}-+-{'-'*6}-+-"
          f"{'-'*8}-+-{'-'*8}-+-{'-'*6}-+-"
          f"{'-'*8}-+-{'-'*9}-+-{'-'*20}")

    for r in results:
        status = "PASS" if r.success else "FAIL"
        time_str = f"{r.total_time_s:.1f}s" if r.total_time_s > 0 else "---"
        theor_str = f"{r.theoretical_time_s:.1f}s"
        ratio_str = f"{r.time_ratio:.2f}x" if r.time_ratio > 0 else "---"
        budget_str = f"{r.time_budget_s:.1f}s"
        final_v_str = f"{r.final_speed_ms:.3f}"
        phases_str = " -> ".join(r.phase_names) if r.phase_names else "---"

        print(f"{r.test_name:<18s} | {r.initial_speed:7.1f} | {r.g_level:4.1f} | "
              f"{status:>6s} | {time_str:>8s} | {theor_str:>8s} | "
              f"{ratio_str:>6s} | {budget_str:>8s} | {final_v_str:>9s} | "
              f"{phases_str}")

    # Phase breakdown per test
    print(f"\n{'='*110}")
    print(f"  PHASE BREAKDOWN")
    print(f"{'='*110}")

    for r in results:
        print(f"\n  --- {r.test_name} (|v|={r.initial_speed:.1f} m/s, {r.g_level:.1f}G) ---")
        for p in r.phases:
            print(f"    {p.name:<10s}  {p.duration_s:7.1f}s  "
                  f"speed: {p.start_speed:8.1f} -> {p.end_speed:8.1f} m/s  "
                  f"peak_accel: {p.peak_accel:6.1f} m/s^2")

    # Acceleration analysis
    print(f"\n{'='*110}")
    print(f"  ACCELERATION ANALYSIS")
    print(f"{'='*110}")

    ship_max_accel = 500000 / 5000  # 100 m/s^2 theoretical

    for r in results:
        if not r.accel_samples:
            continue
        nonzero = [a for a in r.accel_samples if a > 0.1]
        if nonzero:
            avg_accel = sum(nonzero) / len(nonzero)
            max_accel = max(nonzero)
            # Requested accel for this g_level
            requested = r.g_level * 9.81
            eff_pct = (avg_accel / requested) * 100 if requested > 0 else 0
            print(f"  {r.test_name:<18s}: avg={avg_accel:6.1f} m/s^2  "
                  f"max={max_accel:5.1f}  "
                  f"requested={requested:5.1f}  "
                  f"delivery={eff_pct:5.1f}%")

    # Failure details
    failures = [r for r in results if not r.success]
    if failures:
        print(f"\n{'='*110}")
        print(f"  FAILURES ({len(failures)})")
        print(f"{'='*110}")
        for r in failures:
            print(f"\n  {r.test_name}: {r.failure_reason}")
            print(f"    velocity=({r.initial_velocity[0]}, {r.initial_velocity[1]}, "
                  f"{r.initial_velocity[2]}) m/s  g={r.g_level}")
            print(f"    final_speed={r.final_speed_ms:.3f} m/s  "
                  f"time={r.total_time_s:.1f}s  "
                  f"phases={' -> '.join(r.phase_names)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Headless all-stop autopilot test harness")
    parser.add_argument(
        "--g-level", type=float, default=None,
        help="Override G-level for all tests (default: per-test)")
    parser.add_argument(
        "--max-ticks", type=int, default=5000,
        help="Maximum simulation ticks per test (default: 5000)")
    args = parser.parse_args()

    tests = DEFAULT_TESTS

    print(f"=== All-Stop Autopilot Test Harness ===")
    print(f"Ship: 5000 kg, 500 kN (theoretical max 10.2G)")
    g_desc = f"{args.g_level:.1f}G (override)" if args.g_level else "per-test"
    print(f"G-level: {g_desc}")
    print(f"Max ticks per test: {args.max_ticks}")
    print(f"Success: magnitude(velocity) < 0.1 m/s")
    print(f"Time budget: 150% of theoretical + 20s flip allowance")
    print(f"Tests: {len(tests)}")

    results: list[RunResult] = []
    wall_start = time.monotonic()

    for test in tests:
        t0 = time.monotonic()
        result = run_test(test, args.g_level, args.max_ticks)
        wall = time.monotonic() - t0
        print(f"  Wall time: {wall:.1f}s")
        results.append(result)

    total_wall = time.monotonic() - wall_start
    print_summary(results)

    passed = sum(1 for r in results if r.success)
    failed = len(results) - passed
    print(f"\nTotal wall time: {total_wall:.1f}s")
    print(f"Results: {passed}/{len(results)} passed, {failed} failed")

    overall = "PASS" if failed == 0 else "FAIL"
    print(f"Overall: {overall}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
