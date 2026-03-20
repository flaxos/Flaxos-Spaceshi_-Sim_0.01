#!/usr/bin/env python3
"""Headless burn-flip-brake precision test harness.

Tests the autopilot's ability to accelerate toward a stationary target,
flip, brake, and stop precisely at various distances.  Measures overshoot,
stop accuracy, phase timing, and acceleration profiles.

Usage:
    python3 tools/test_burn_flip_brake.py
    python3 tools/test_burn_flip_brake.py --distances 10000 50000
    python3 tools/test_burn_flip_brake.py --max-ticks 20000 --profile aggressive
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from dataclasses import dataclass, field

# Ensure project root is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from hybrid.simulator import Simulator
from hybrid.scenarios.loader import ScenarioLoader
from hybrid.utils.math_utils import magnitude, subtract_vectors, dot_product, normalize_vector

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(levelname).1s %(name)s: %(message)s")
for noisy in (
    "hybrid.core.event_bus", "hybrid.systems", "hybrid.ship", "hybrid.fleet",
    "hybrid.systems.combat", "hybrid.systems.sensors", "hybrid.systems.propulsion",
    "hybrid.systems.helm", "hybrid.navigation.navigation_controller",
    "hybrid.systems.navigation.navigation", "hybrid.navigation.autopilot.match_velocity",
):
    logging.getLogger(noisy).setLevel(logging.WARNING)

logger = logging.getLogger("test_burn_flip_brake")


# ---------------------------------------------------------------------------
# Data classes for results
# ---------------------------------------------------------------------------
@dataclass
class PhaseRecord:
    name: str
    start_tick: int
    end_tick: int = 0
    start_range: float = 0.0
    end_range: float = 0.0
    start_speed: float = 0.0
    end_speed: float = 0.0
    peak_speed: float = 0.0
    peak_accel: float = 0.0
    duration_s: float = 0.0


@dataclass
class RunResult:
    distance_km: float
    distance_m: float
    success: bool
    failure_reason: str | None = None
    total_ticks: int = 0
    total_time_s: float = 0.0
    final_range_m: float = 0.0
    final_speed_ms: float = 0.0
    overshoot_m: float = 0.0
    min_range_m: float = float("inf")
    peak_speed_ms: float = 0.0
    theoretical_time_s: float = 0.0
    time_ratio: float = 0.0  # actual / theoretical
    phases: list[PhaseRecord] = field(default_factory=list)
    accel_samples: list[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scenario builder
# ---------------------------------------------------------------------------
def build_scenario_at_distance(distance_m: float, dt: float = 0.1) -> dict:
    """Build a minimal scenario with player and stationary target at given distance."""
    return {
        "name": f"Burn-Flip-Brake Test ({distance_m/1000:.0f}km)",
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
                        "max_thrust": 500000,  # 500kN = 10.2G for 5t
                        "fuel_level": 10000,
                        "max_fuel": 10000,
                    },
                    "sensors": {
                        "passive": {"range": max(distance_m * 2, 500000)},
                        "active": {"scan_range": max(distance_m * 2, 500000)},
                    },
                    "navigation": {},
                    "targeting": {},
                    "docking": {
                        "docking_range": 50,
                        "max_relative_velocity": 1.0,
                    },
                },
            },
            {
                "id": "target",
                "name": "Target Waypoint",
                "class": "station",
                "position": {"x": distance_m, "y": 0, "z": 0},
                "velocity": {"x": 0, "y": 0, "z": 0},
                "mass": 100000,
                "systems": {
                    "sensors": {"passive": {"range": 100000}},
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

    all_ships = list(sim.ships.values())
    for ship in all_ships:
        ship._all_ships_ref = all_ships

    sim.start()
    return sim


# ---------------------------------------------------------------------------
# Run a single distance test
# ---------------------------------------------------------------------------
def run_distance_test(distance_m: float, profile: str, max_ticks: int,
                      dt: float = 0.1) -> RunResult:
    """Run burn-flip-brake at a specific distance and collect detailed metrics."""

    distance_km = distance_m / 1000.0
    result = RunResult(distance_km=distance_km, distance_m=distance_m, success=False)

    # Theoretical optimal time (brachistochrone): accelerate halfway, brake halfway
    # Ship: 5000 kg, 500 kN => a = 100 m/s²
    a_max = 500000 / 5000  # 100 m/s²
    # But alignment guard delivers ~35% of theoretical
    a_effective = a_max * 0.35  # 35 m/s²
    # t = 2 * sqrt(d / a)  for brachistochrone
    result.theoretical_time_s = 2.0 * math.sqrt(distance_m / a_effective)

    print(f"\n{'='*70}")
    print(f"  DISTANCE TEST: {distance_km:.0f} km ({distance_m:.0f} m)")
    print(f"  Theoretical time (35% eff): {result.theoretical_time_s:.1f}s")
    print(f"  Profile: {profile}")
    print(f"{'='*70}")

    # Build and run
    scenario = build_scenario_at_distance(distance_m, dt)
    sim = build_simulator_from_dict(scenario)

    player = sim.ships["player"]
    target = sim.ships["target"]

    # Warm up sensors
    for _ in range(20):
        sim.tick()

    # Engage rendezvous autopilot
    nav = player.systems.get("navigation")
    if nav is None:
        result.failure_reason = "No navigation system"
        return result

    engage_result = nav.command("set_autopilot", {
        "program": "rendezvous",
        "target": "target",
        "profile": profile,
        "ship": player,
        "_ship": player,
        "event_bus": player.event_bus,
    })
    if isinstance(engage_result, dict) and engage_result.get("error"):
        result.failure_reason = f"Autopilot engage failed: {engage_result}"
        return result

    # Tracking state
    last_phase = None
    current_phase_record: PhaseRecord | None = None
    prev_speed = 0.0

    for tick in range(max_ticks):
        sim.tick()

        # Telemetry
        rel_pos = subtract_vectors(target.position, player.position)
        current_range = magnitude(rel_pos)
        rel_vel = subtract_vectors(target.velocity, player.velocity)
        rel_speed = magnitude(rel_vel)
        player_speed = magnitude(player.velocity)

        # Closing speed
        closing_speed = 0.0
        if current_range > 0.01:
            rng_dir = normalize_vector(rel_pos)
            closing_speed = -dot_product(rel_vel, rng_dir)

        # Instantaneous accel
        accel = magnitude(player.acceleration) if hasattr(player, "acceleration") else 0.0

        # Track min range (for overshoot detection)
        if current_range < result.min_range_m:
            result.min_range_m = current_range

        # Track peak speed
        if rel_speed > result.peak_speed_ms:
            result.peak_speed_ms = rel_speed

        # Get autopilot phase
        phase = "unknown"
        if nav and nav.controller and nav.controller.autopilot:
            ap = nav.controller.autopilot
            phase = getattr(ap, "phase", "unknown")

        # Phase tracking
        if phase != last_phase:
            # Close previous phase record
            if current_phase_record:
                current_phase_record.end_tick = tick
                current_phase_record.end_range = current_range
                current_phase_record.end_speed = rel_speed
                current_phase_record.duration_s = (tick - current_phase_record.start_tick) * dt

            # Start new phase record
            current_phase_record = PhaseRecord(
                name=phase,
                start_tick=tick,
                start_range=current_range,
                start_speed=rel_speed,
            )
            result.phases.append(current_phase_record)
            last_phase = phase

        # Update current phase stats
        if current_phase_record:
            if rel_speed > current_phase_record.peak_speed:
                current_phase_record.peak_speed = rel_speed
            if accel > current_phase_record.peak_accel:
                current_phase_record.peak_accel = accel

        # Sample acceleration every 10 ticks
        if tick % 10 == 0:
            result.accel_samples.append(accel)

        # Status output every 200 ticks
        if tick % 200 == 0:
            print(f"  [t={tick:5d}] phase={phase:<18s} "
                  f"range={current_range:12.1f}m  "
                  f"speed={rel_speed:8.1f}m/s  "
                  f"accel={accel:6.1f}m/s²  "
                  f"closing={closing_speed:8.1f}m/s")

        # Success: docking criteria
        if current_range < 50.0 and rel_speed < 1.0:
            # Close final phase
            if current_phase_record:
                current_phase_record.end_tick = tick
                current_phase_record.end_range = current_range
                current_phase_record.end_speed = rel_speed
                current_phase_record.duration_s = (tick - current_phase_record.start_tick) * dt

            result.success = True
            result.total_ticks = tick + 1
            result.total_time_s = sim.time
            result.final_range_m = current_range
            result.final_speed_ms = rel_speed
            result.time_ratio = result.total_time_s / result.theoretical_time_s if result.theoretical_time_s > 0 else 0
            print(f"\n  *** SUCCESS at tick {tick} ({sim.time:.1f}s) ***")
            print(f"      range={current_range:.1f}m  speed={rel_speed:.2f}m/s")
            return result

        # Failure: stuck
        if tick > 1000 and phase == last_phase:
            # Check for no progress
            pass  # Let max_ticks handle timeout

    # Close final phase
    if current_phase_record:
        current_phase_record.end_tick = max_ticks
        current_phase_record.end_range = current_range
        current_phase_record.end_speed = rel_speed
        current_phase_record.duration_s = (max_ticks - current_phase_record.start_tick) * dt

    result.failure_reason = f"Timed out after {max_ticks} ticks"
    result.total_ticks = max_ticks
    result.total_time_s = sim.time
    result.final_range_m = current_range
    result.final_speed_ms = rel_speed
    result.time_ratio = result.total_time_s / result.theoretical_time_s if result.theoretical_time_s > 0 else 0
    print(f"\n  *** TIMEOUT at tick {max_ticks} ({sim.time:.1f}s) ***")
    print(f"      range={current_range:.1f}m  speed={rel_speed:.2f}m/s")
    return result


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------
def print_summary_table(results: list[RunResult]) -> None:
    """Print a comparison table across all distances."""

    print(f"\n{'='*100}")
    print(f"  BURN-FLIP-BRAKE PERFORMANCE SUMMARY")
    print(f"{'='*100}")

    # Header
    print(f"\n{'Distance':>10s} | {'Result':>7s} | {'Time':>8s} | {'Theor.':>8s} | "
          f"{'Ratio':>6s} | {'Peak v':>10s} | {'Final r':>9s} | {'Final v':>9s} | "
          f"{'Phases':>6s}")
    print(f"{'-'*10}-+-{'-'*7}-+-{'-'*8}-+-{'-'*8}-+-"
          f"{'-'*6}-+-{'-'*10}-+-{'-'*9}-+-{'-'*9}-+-{'-'*6}")

    for r in results:
        status = "OK" if r.success else "FAIL"
        time_str = f"{r.total_time_s:.1f}s" if r.total_time_s > 0 else "---"
        theor_str = f"{r.theoretical_time_s:.1f}s"
        ratio_str = f"{r.time_ratio:.2f}x" if r.time_ratio > 0 else "---"
        peak_str = f"{r.peak_speed_ms:.0f}m/s"
        final_r_str = f"{r.final_range_m:.1f}m"
        final_v_str = f"{r.final_speed_ms:.2f}m/s"
        n_phases = len(r.phases)

        print(f"{r.distance_km:8.0f}km | {status:>7s} | {time_str:>8s} | {theor_str:>8s} | "
              f"{ratio_str:>6s} | {peak_str:>10s} | {final_r_str:>9s} | {final_v_str:>9s} | "
              f"{n_phases:>6d}")

    # Phase breakdown per distance
    print(f"\n{'='*100}")
    print(f"  PHASE BREAKDOWN")
    print(f"{'='*100}")

    for r in results:
        print(f"\n  --- {r.distance_km:.0f} km ---")
        for p in r.phases:
            dur = p.duration_s
            rng_delta = p.start_range - p.end_range
            print(f"    {p.name:<20s}  {dur:7.1f}s  "
                  f"range: {p.start_range/1000:8.1f}km -> {p.end_range/1000:8.1f}km  "
                  f"speed: {p.start_speed:8.1f} -> {p.end_speed:8.1f}m/s  "
                  f"peak_accel: {p.peak_accel:6.1f}m/s²")

    # Acceleration analysis
    print(f"\n{'='*100}")
    print(f"  ACCELERATION ANALYSIS")
    print(f"{'='*100}")

    theoretical_accel = 500000 / 5000  # 100 m/s²

    for r in results:
        if not r.accel_samples:
            continue
        nonzero = [a for a in r.accel_samples if a > 0.1]
        if nonzero:
            avg_accel = sum(nonzero) / len(nonzero)
            max_accel = max(nonzero)
            min_accel = min(nonzero)
            eff_pct = (avg_accel / theoretical_accel) * 100
            print(f"  {r.distance_km:6.0f}km: avg={avg_accel:6.1f} m/s²  "
                  f"min={min_accel:5.1f}  max={max_accel:5.1f}  "
                  f"efficiency={eff_pct:5.1f}%  "
                  f"(theoretical={theoretical_accel:.0f} m/s²)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Burn-flip-brake distance tests")
    parser.add_argument("--distances", nargs="+", type=float, default=None,
                        help="Distances in meters (default: 10k,50k,100k,200k)")
    parser.add_argument("--distances-km", nargs="+", type=float, default=None,
                        help="Distances in kilometers")
    parser.add_argument("--profile", default="balanced",
                        choices=["aggressive", "balanced", "conservative"])
    parser.add_argument("--max-ticks", type=int, default=15000)
    args = parser.parse_args()

    # Parse distances
    if args.distances_km:
        distances = [d * 1000 for d in args.distances_km]
    elif args.distances:
        distances = args.distances
    else:
        distances = [10_000, 50_000, 100_000, 200_000]  # 10, 50, 100, 200 km

    print(f"=== Burn-Flip-Brake Precision Test ===")
    print(f"Ship: 5000 kg, 500 kN (theoretical 100 m/s², ~35 m/s² effective)")
    print(f"Profile: {args.profile}")
    print(f"Max ticks per test: {args.max_ticks}")
    print(f"Distances: {', '.join(f'{d/1000:.0f}km' for d in distances)}")
    print(f"Target: stationary, on X-axis")
    print(f"Success: range < 50m AND speed < 1 m/s")

    results: list[RunResult] = []
    wall_start = time.monotonic()

    for distance_m in distances:
        t0 = time.monotonic()
        result = run_distance_test(distance_m, args.profile, args.max_ticks)
        wall = time.monotonic() - t0
        print(f"  Wall time: {wall:.1f}s")
        results.append(result)

    total_wall = time.monotonic() - wall_start
    print_summary_table(results)

    print(f"\nTotal wall time: {total_wall:.1f}s")

    # Exit code: 0 if all passed, 1 if any failed
    all_passed = all(r.success for r in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
