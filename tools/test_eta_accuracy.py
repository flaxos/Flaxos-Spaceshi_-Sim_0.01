#!/usr/bin/env python3
"""Headless ETA accuracy test harness.

Runs the rendezvous autopilot at several distances and compares the
autopilot's reported ETA (from get_state()["time_to_arrival"]) against
the actual remaining time at each phase transition and at regular
intervals.  Produces a comparison table with error percentages.

The goal is to validate that _estimate_eta() gives the pilot useful
information.  An ETA that jumps around wildly or is consistently 2x
off erodes trust in the flight computer.

Success criteria: ETA should be within 30% of actual remaining time
at all major phase transitions.

Usage:
    python3 tools/test_eta_accuracy.py
    python3 tools/test_eta_accuracy.py --distances-km 10 50 100
    python3 tools/test_eta_accuracy.py --profile aggressive --max-ticks 20000
"""

from __future__ import annotations

import argparse
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
from hybrid.utils.math_utils import magnitude, subtract_vectors

# ---------------------------------------------------------------------------
# Logging: keep autopilot phase changes visible, suppress noisy modules
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname).1s %(name)s: %(message)s",
)
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

logger = logging.getLogger("test_eta_accuracy")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ETASample:
    """A single ETA reading captured during the run."""
    sim_time: float
    phase: str
    reported_eta: float | None
    range_m: float
    closing_speed: float
    # Filled in post-run once we know when the sim actually finished
    actual_remaining: float | None = None
    error_pct: float | None = None
    trigger: str = ""  # "phase_change", "periodic", "initial"


@dataclass
class DistanceResult:
    """Results from one distance run."""
    distance_km: float
    distance_m: float
    profile: str
    success: bool
    failure_reason: str | None = None
    total_sim_time: float = 0.0
    total_ticks: int = 0
    initial_eta: float | None = None
    # All ETA samples collected during the run
    samples: list[ETASample] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scenario builder -- identical to test_burn_flip_brake pattern
# ---------------------------------------------------------------------------

def build_scenario_at_distance(distance_m: float, dt: float = 0.1) -> dict:
    """Build a minimal scenario with player and stationary target."""
    return {
        "name": f"ETA Accuracy Test ({distance_m / 1000:.0f}km)",
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
                        "max_thrust": 500000,  # 500kN => 100 m/s^2 theoretical
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

    # Wire up cross-ship references (sensors need this)
    all_ships = list(sim.ships.values())
    for ship in all_ships:
        ship._all_ships_ref = all_ships

    sim.start()
    return sim


# ---------------------------------------------------------------------------
# Core test runner for a single distance
# ---------------------------------------------------------------------------

# How often (in ticks) to sample ETA during each phase.
# More frequent during fast-changing phases, less during coast.
_SAMPLE_INTERVAL_TICKS = 50  # every 5 seconds at dt=0.1


def run_eta_test(distance_m: float, profile: str, max_ticks: int,
                 dt: float = 0.1) -> DistanceResult:
    """Run rendezvous at a given distance and collect ETA samples.

    Samples ETA at:
      - The first tick of BURN (the "initial" estimate)
      - Every phase transition
      - Every _SAMPLE_INTERVAL_TICKS ticks within a phase
    """
    distance_km = distance_m / 1000.0
    result = DistanceResult(
        distance_km=distance_km,
        distance_m=distance_m,
        profile=profile,
        success=False,
    )

    print(f"\n{'=' * 70}")
    print(f"  ETA ACCURACY TEST: {distance_km:.0f} km")
    print(f"  Profile: {profile}")
    print(f"{'=' * 70}")

    # Build sim
    scenario = build_scenario_at_distance(distance_m, dt)
    sim = build_simulator_from_dict(scenario)
    player = sim.ships["player"]
    target = sim.ships["target"]

    # Warm up sensors (20 ticks, same as other harnesses)
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

    # --- Tick loop: collect ETA samples ---
    last_phase: str | None = None
    initial_captured = False
    ticks_in_phase = 0

    for tick in range(max_ticks):
        sim.tick()

        # --- Gather telemetry ---
        rel_pos = subtract_vectors(target.position, player.position)
        current_range = magnitude(rel_pos)
        rel_vel = subtract_vectors(target.velocity, player.velocity)
        rel_speed = magnitude(rel_vel)

        # Closing speed (positive = closing)
        closing_speed = 0.0
        if current_range > 0.01:
            from hybrid.utils.math_utils import dot_product, normalize_vector
            rng_dir = normalize_vector(rel_pos)
            closing_speed = -dot_product(rel_vel, rng_dir)

        # --- Read autopilot state ---
        phase = "unknown"
        reported_eta: float | None = None

        if nav and nav.controller and nav.controller.autopilot:
            ap = nav.controller.autopilot
            phase = getattr(ap, "phase", "unknown")
            ap_state = ap.get_state()
            reported_eta = ap_state.get("time_to_arrival")

        # --- Decide whether to record a sample this tick ---
        should_sample = False
        trigger = ""

        # Capture initial ETA on the very first tick of BURN
        if not initial_captured and phase == "burn":
            should_sample = True
            trigger = "initial"
            initial_captured = True

        # Capture at every phase transition
        if phase != last_phase and last_phase is not None:
            should_sample = True
            trigger = f"phase:{last_phase}->{phase}"
            ticks_in_phase = 0

        # Capture at regular intervals within each phase
        if ticks_in_phase > 0 and ticks_in_phase % _SAMPLE_INTERVAL_TICKS == 0:
            should_sample = True
            trigger = "periodic"

        if should_sample:
            sample = ETASample(
                sim_time=sim.time,
                phase=phase,
                reported_eta=reported_eta,
                range_m=current_range,
                closing_speed=closing_speed,
                trigger=trigger,
            )
            result.samples.append(sample)

            if trigger == "initial":
                result.initial_eta = reported_eta

        # Track phase
        last_phase = phase
        ticks_in_phase += 1

        # --- Status printout every 200 ticks ---
        if tick % 200 == 0:
            eta_str = f"{reported_eta:8.1f}s" if reported_eta is not None else "     N/A"
            print(f"  [t={tick:5d} sim={sim.time:7.1f}s] "
                  f"phase={phase:<20s} "
                  f"range={current_range:12.1f}m  "
                  f"closing={closing_speed:8.1f}m/s  "
                  f"ETA={eta_str}")

        # --- Success: docking criteria ---
        if current_range < 50.0 and rel_speed < 1.0:
            result.success = True
            result.total_sim_time = sim.time
            result.total_ticks = tick + 1
            print(f"\n  *** SUCCESS at tick {tick} "
                  f"(sim_time={sim.time:.1f}s) ***")
            print(f"      range={current_range:.1f}m  "
                  f"speed={rel_speed:.2f}m/s")
            break
    else:
        # Timeout
        result.failure_reason = f"Timed out after {max_ticks} ticks"
        result.total_sim_time = sim.time
        result.total_ticks = max_ticks
        print(f"\n  *** TIMEOUT at tick {max_ticks} "
              f"(sim_time={sim.time:.1f}s) ***")
        print(f"      range={current_range:.1f}m  "
              f"speed={rel_speed:.2f}m/s")

    # --- Post-run: compute actual_remaining and error_pct ---
    finish_time = result.total_sim_time
    for sample in result.samples:
        sample.actual_remaining = finish_time - sample.sim_time
        if (sample.reported_eta is not None
                and sample.actual_remaining is not None
                and sample.actual_remaining > 0):
            sample.error_pct = (
                (sample.reported_eta - sample.actual_remaining)
                / sample.actual_remaining
            ) * 100.0

    return result


# ---------------------------------------------------------------------------
# Table printing
# ---------------------------------------------------------------------------

def print_eta_table(result: DistanceResult) -> None:
    """Print the per-sample ETA comparison table for one distance run."""

    print(f"\n  --- ETA Samples for {result.distance_km:.0f} km "
          f"({'OK' if result.success else 'FAIL'}) ---")

    if not result.samples:
        print("    (no samples collected)")
        return

    # Header
    print(f"  {'Trigger':<30s} {'Phase':<20s} {'SimTime':>8s} "
          f"{'ETA':>8s} {'Actual':>8s} {'Err%':>8s} "
          f"{'Range':>12s} {'Closing':>10s}")
    print(f"  {'-' * 30} {'-' * 20} {'-' * 8} "
          f"{'-' * 8} {'-' * 8} {'-' * 8} "
          f"{'-' * 12} {'-' * 10}")

    for s in result.samples:
        eta_str = f"{s.reported_eta:8.1f}" if s.reported_eta is not None else "     N/A"
        actual_str = (f"{s.actual_remaining:8.1f}"
                      if s.actual_remaining is not None else "     N/A")
        err_str = (f"{s.error_pct:+7.1f}%"
                   if s.error_pct is not None else "     N/A")
        range_str = _format_distance(s.range_m)
        closing_str = f"{s.closing_speed:8.1f}m/s"

        print(f"  {s.trigger:<30s} {s.phase:<20s} {s.sim_time:8.1f} "
              f"{eta_str} {actual_str} {err_str} "
              f"{range_str:>12s} {closing_str:>10s}")


def print_summary_table(results: list[DistanceResult]) -> None:
    """Print a cross-distance summary comparing initial ETA to actual."""

    print(f"\n{'=' * 90}")
    print(f"  ETA ACCURACY SUMMARY")
    print(f"{'=' * 90}")

    # Initial ETA vs actual total time
    print(f"\n  Initial ETA (first BURN tick) vs Actual Total Time:")
    print(f"  {'Distance':>10s} | {'Result':>7s} | {'Init ETA':>10s} | "
          f"{'Actual':>10s} | {'Error':>8s} | {'Abs Err':>10s}")
    print(f"  {'-' * 10}-+-{'-' * 7}-+-{'-' * 10}-+-"
          f"{'-' * 10}-+-{'-' * 8}-+-{'-' * 10}")

    for r in results:
        status = "OK" if r.success else "FAIL"
        init_str = (f"{r.initial_eta:8.1f}s"
                    if r.initial_eta is not None else "      N/A")
        actual_str = f"{r.total_sim_time:8.1f}s"

        if r.initial_eta is not None and r.total_sim_time > 0:
            err_pct = ((r.initial_eta - r.total_sim_time)
                       / r.total_sim_time * 100.0)
            err_str = f"{err_pct:+6.1f}%"
            abs_err_s = abs(r.initial_eta - r.total_sim_time)
            abs_str = f"{abs_err_s:8.1f}s"
        else:
            err_str = "    N/A"
            abs_str = "      N/A"

        print(f"  {r.distance_km:8.0f}km | {status:>7s} | {init_str:>10s} | "
              f"{actual_str:>10s} | {err_str:>8s} | {abs_str:>10s}")

    # Phase-transition ETA accuracy
    print(f"\n  ETA at Phase Transitions:")
    print(f"  {'Distance':>10s} | {'Transition':<30s} | {'ETA':>8s} | "
          f"{'Actual':>8s} | {'Error':>8s}")
    print(f"  {'-' * 10}-+-{'-' * 30}-+-{'-' * 8}-+-"
          f"{'-' * 8}-+-{'-' * 8}")

    for r in results:
        phase_samples = [s for s in r.samples
                         if s.trigger.startswith("phase:")]
        for s in phase_samples:
            eta_str = (f"{s.reported_eta:8.1f}"
                       if s.reported_eta is not None else "     N/A")
            actual_str = (f"{s.actual_remaining:8.1f}"
                          if s.actual_remaining is not None else "     N/A")
            err_str = (f"{s.error_pct:+7.1f}%"
                       if s.error_pct is not None else "     N/A")
            print(f"  {r.distance_km:8.0f}km | {s.trigger:<30s} | "
                  f"{eta_str} | {actual_str} | {err_str}")

    # Worst-case errors
    print(f"\n  Worst-Case ETA Error Per Distance:")
    print(f"  {'Distance':>10s} | {'Worst Err':>10s} | "
          f"{'At Phase':<20s} | {'At Trigger':<30s}")
    print(f"  {'-' * 10}-+-{'-' * 10}-+-{'-' * 20}-+-{'-' * 30}")

    for r in results:
        # Find the sample with largest absolute error_pct (excluding
        # samples where actual_remaining < 10s, since tiny denominators
        # produce misleading percentages)
        valid = [s for s in r.samples
                 if (s.error_pct is not None
                     and s.actual_remaining is not None
                     and s.actual_remaining > 10.0)]
        if valid:
            worst = max(valid, key=lambda s: abs(s.error_pct))
            print(f"  {r.distance_km:8.0f}km | "
                  f"{worst.error_pct:+8.1f}% | "
                  f"{worst.phase:<20s} | {worst.trigger:<30s}")
        else:
            print(f"  {r.distance_km:8.0f}km | {'N/A':>10s} | "
                  f"{'---':<20s} | {'---':<30s}")


def print_pass_fail(results: list[DistanceResult]) -> bool:
    """Print final PASS/FAIL verdict.  Returns True if all pass."""

    threshold_pct = 30.0
    all_pass = True

    print(f"\n{'=' * 90}")
    print(f"  PASS/FAIL VERDICT  (threshold: +/-{threshold_pct:.0f}%)")
    print(f"{'=' * 90}\n")

    for r in results:
        if not r.success:
            print(f"  {r.distance_km:6.0f}km: FAIL -- "
                  f"rendezvous did not converge ({r.failure_reason})")
            all_pass = False
            continue

        # Check all samples with meaningful actual_remaining (>10s).
        # Samples near the end have tiny denominators and aren't useful
        # for validating the ETA model.
        violations: list[ETASample] = []
        for s in r.samples:
            if (s.error_pct is not None
                    and s.actual_remaining is not None
                    and s.actual_remaining > 10.0
                    and abs(s.error_pct) > threshold_pct):
                violations.append(s)

        if violations:
            worst = max(violations, key=lambda s: abs(s.error_pct))
            print(f"  {r.distance_km:6.0f}km: FAIL -- "
                  f"{len(violations)} sample(s) exceed "
                  f"{threshold_pct:.0f}% error  "
                  f"(worst: {worst.error_pct:+.1f}% "
                  f"at phase={worst.phase}, "
                  f"trigger={worst.trigger})")
            all_pass = False
        else:
            n_valid = sum(1 for s in r.samples
                          if s.error_pct is not None
                          and s.actual_remaining is not None
                          and s.actual_remaining > 10.0)
            print(f"  {r.distance_km:6.0f}km: PASS -- "
                  f"{n_valid} samples all within "
                  f"+/-{threshold_pct:.0f}%")

    print()
    if all_pass:
        print("  OVERALL: PASS")
    else:
        print("  OVERALL: FAIL")
    print()
    return all_pass


def _format_distance(metres: float) -> str:
    """Format a distance for display."""
    if metres >= 1_000_000:
        return f"{metres / 1000:.0f}km"
    if metres >= 1_000:
        return f"{metres / 1000:.1f}km"
    return f"{metres:.0f}m"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ETA accuracy test: compare autopilot ETA to actual time")
    parser.add_argument(
        "--distances", nargs="+", type=float, default=None,
        help="Distances in metres (default: 10k, 50k, 100k, 200k, 427k)")
    parser.add_argument(
        "--distances-km", nargs="+", type=float, default=None,
        help="Distances in kilometres")
    parser.add_argument(
        "--profile", default="balanced",
        choices=["aggressive", "balanced", "conservative"],
        help="Nav profile (default: balanced)")
    parser.add_argument(
        "--max-ticks", type=int, default=20000,
        help="Max simulation ticks per distance (default: 20000)")
    args = parser.parse_args()

    # Parse distances
    if args.distances_km:
        distances = [d * 1000 for d in args.distances_km]
    elif args.distances:
        distances = args.distances
    else:
        distances = [10_000, 50_000, 100_000, 200_000, 427_000]

    print(f"=== ETA Accuracy Test Harness ===")
    print(f"Ship: 5000 kg, 500 kN (100 m/s^2 theoretical)")
    print(f"Profile: {args.profile}")
    print(f"Max ticks per test: {args.max_ticks}")
    print(f"Distances: {', '.join(f'{d / 1000:.0f}km' for d in distances)}")
    print(f"Success criteria: ETA within 30% of actual at all phases")
    print(f"Sample interval: every {_SAMPLE_INTERVAL_TICKS} ticks "
          f"({_SAMPLE_INTERVAL_TICKS * 0.1:.0f}s) + phase transitions")

    results: list[DistanceResult] = []
    wall_start = time.monotonic()

    for distance_m in distances:
        t0 = time.monotonic()
        result = run_eta_test(distance_m, args.profile, args.max_ticks)
        wall = time.monotonic() - t0
        print(f"  Wall time: {wall:.1f}s")
        results.append(result)

    total_wall = time.monotonic() - wall_start

    # Print detailed per-distance tables
    for r in results:
        print_eta_table(r)

    # Print cross-distance summary
    print_summary_table(results)

    # Print pass/fail verdict
    all_pass = print_pass_fail(results)

    print(f"Total wall time: {total_wall:.1f}s")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
