#!/usr/bin/env python3
"""Headless rendezvous autopilot test harness.

Loads the Tutorial: Intercept and Dock scenario, engages the rendezvous
autopilot targeting the station, and runs the simulation tick loop without
the GUI/WebSocket stack.  Prints status lines and detects success/failure.

Success: range < 50m AND rel_speed < 1 m/s (docking criteria).
Failure: stuck in same phase for >1000 ticks without range progress,
         or oscillating between phases.

Usage:
    python3 tools/test_rendezvous.py [--profile balanced] [--max-ticks 3000]
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import time

# Ensure project root is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from hybrid.simulator import Simulator
from hybrid.scenarios.loader import ScenarioLoader
from hybrid.utils.math_utils import magnitude, subtract_vectors

# ---------------------------------------------------------------------------
# Logging: keep autopilot phase changes visible, suppress noisy modules
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname).1s %(name)s: %(message)s",
)
# Mute chatty subsystems so our status lines are readable
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

logger = logging.getLogger("test_rendezvous")


def build_simulator(scenario_path: str) -> Simulator:
    """Load the scenario and return a ready-to-tick Simulator."""
    scenario = ScenarioLoader.load(scenario_path)
    ships_data = scenario["ships"]
    dt = scenario.get("dt", 0.1)

    sim = Simulator(dt=dt, time_scale=1.0)
    for ship_data in ships_data:
        ship_id = ship_data["id"]
        sim.add_ship(ship_id, ship_data)

    # Wire up cross-ship references (sensors need this)
    all_ships = list(sim.ships.values())
    for ship in all_ships:
        ship._all_ships_ref = all_ships

    sim.start()
    return sim


def engage_rendezvous(sim: Simulator, player_id: str, target_id: str,
                      profile: str) -> None:
    """Engage the rendezvous autopilot on the player ship.

    We must run a few sensor ticks first so the contact tracker picks up
    the target, then issue the autopilot command through the navigation
    system -- exactly as the server would.
    """
    player = sim.ships[player_id]

    # Run 20 ticks to let passive sensors detect the station
    for _ in range(20):
        sim.tick()

    # Check sensor contacts
    sensors = player.systems.get("sensors")
    if sensors and hasattr(sensors, "get_contact"):
        contact = sensors.get_contact(target_id)
        if contact:
            logger.info("Sensor contact found for '%s' (pos=%s)",
                        target_id, getattr(contact, "position", "?"))
        else:
            logger.warning("No sensor contact for '%s' -- autopilot will "
                           "use direct ship lookup fallback", target_id)

    # Engage autopilot via the navigation system command interface
    nav = player.systems.get("navigation")
    if nav is None:
        raise RuntimeError("Player ship has no navigation system")

    # The navigation system initialises its controller on first tick,
    # which already happened in the warm-up ticks above.
    result = nav.command("set_autopilot", {
        "program": "rendezvous",
        "target": target_id,
        "profile": profile,
        "ship": player,
        "_ship": player,
        "event_bus": player.event_bus,
    })
    logger.info("set_autopilot result: %s", result)
    if isinstance(result, dict) and result.get("error"):
        raise RuntimeError(f"Autopilot engage failed: {result}")


def run_sim(sim: Simulator, player_id: str, target_id: str,
            max_ticks: int) -> dict:
    """Run the tick loop and monitor progress.

    Returns a summary dict with success/failure info.
    """
    player = sim.ships[player_id]
    target = sim.ships[target_id]

    phase_history: list[str] = []
    phase_tick_counter: dict[str, int] = {}
    phase_range_at_entry: dict[str, float] = {}
    last_phase = None
    success = False
    failure_reason = None

    # Track oscillation: count phase transitions
    transition_count = 0
    transition_log: list[tuple[int, str, str]] = []

    for tick in range(max_ticks):
        sim.tick()

        # -- Gather telemetry --
        rel_pos = subtract_vectors(target.position, player.position)
        current_range = magnitude(rel_pos)
        rel_vel = subtract_vectors(target.velocity, player.velocity)
        rel_speed = magnitude(rel_vel)
        # Closing speed: positive = closing
        if current_range > 0.01:
            from hybrid.utils.math_utils import dot_product, normalize_vector
            rng_dir = normalize_vector(rel_pos)
            range_rate = dot_product(rel_vel, rng_dir)
            closing_speed = -range_rate
        else:
            closing_speed = 0.0

        # Get autopilot phase
        nav = player.systems.get("navigation")
        phase = "unknown"
        if nav and nav.controller and nav.controller.autopilot:
            ap = nav.controller.autopilot
            phase = getattr(ap, "phase", "unknown")

        # Track phase transitions
        if phase != last_phase:
            if last_phase is not None:
                transition_count += 1
                transition_log.append((tick, last_phase, phase))
            phase_history.append(phase)
            phase_tick_counter[phase] = 0
            phase_range_at_entry[phase] = current_range
            last_phase = phase

        phase_tick_counter[phase] = phase_tick_counter.get(phase, 0) + 1

        # -- Print status every 100 ticks --
        if tick % 100 == 0:
            print(f"[tick {tick:5d}] phase={phase:<20s} "
                  f"range={current_range:12.1f}m "
                  f"speed={rel_speed:8.1f}m/s "
                  f"closing={closing_speed:8.1f}m/s")

        # -- Success check --
        if current_range < 50.0 and rel_speed < 1.0:
            print(f"\n*** SUCCESS at tick {tick} ***")
            print(f"    range={current_range:.1f}m  rel_speed={rel_speed:.2f}m/s")
            success = True
            break

        # -- Failure: stuck in same phase >1000 ticks without progress --
        if phase_tick_counter.get(phase, 0) > 1000:
            entry_range = phase_range_at_entry.get(phase, current_range)
            range_progress = entry_range - current_range
            if abs(range_progress) < 100.0 and phase not in ("stationkeep",):
                failure_reason = (
                    f"Stuck in phase '{phase}' for >1000 ticks with "
                    f"<100m range progress (entry={entry_range:.0f}, "
                    f"now={current_range:.0f})")
                print(f"\n*** FAILURE: {failure_reason} ***")
                break

        # -- Failure: excessive oscillation --
        if transition_count > 20:
            # Check if recent transitions oscillate between 2 phases
            recent = transition_log[-10:]
            phases_seen = set(t[2] for t in recent)
            if len(phases_seen) <= 2:
                failure_reason = (
                    f"Phase oscillation: {transition_count} transitions, "
                    f"cycling between {phases_seen}")
                print(f"\n*** FAILURE: {failure_reason} ***")
                break

    else:
        if not success:
            failure_reason = f"Timed out after {max_ticks} ticks"
            print(f"\n*** FAILURE: {failure_reason} ***")

    # Print phase timeline
    print("\n--- Phase Timeline ---")
    for i, (t, from_p, to_p) in enumerate(transition_log):
        print(f"  tick {t:5d}: {from_p} -> {to_p}")
    print(f"  Final phase: {last_phase}")
    print(f"  Total transitions: {transition_count}")

    return {
        "success": success,
        "failure_reason": failure_reason,
        "final_range": current_range,
        "final_rel_speed": rel_speed,
        "ticks": tick + 1,
        "sim_time": sim.time,
        "phase_history": phase_history,
        "transition_log": transition_log,
        "transition_count": transition_count,
    }


def main():
    parser = argparse.ArgumentParser(description="Headless rendezvous test")
    parser.add_argument("--profile", default="balanced",
                        choices=["aggressive", "balanced", "conservative"],
                        help="Nav profile (default: balanced)")
    parser.add_argument("--max-ticks", type=int, default=3000,
                        help="Max simulation ticks (default: 3000)")
    parser.add_argument("--target", default="target_station",
                        help="Target ship ID (default: target_station)")
    args = parser.parse_args()

    scenario_path = os.path.join(ROOT_DIR, "scenarios",
                                 "01_tutorial_intercept.yaml")
    if not os.path.exists(scenario_path):
        print(f"ERROR: scenario not found: {scenario_path}")
        sys.exit(1)

    print(f"=== Rendezvous Test Harness ===")
    print(f"Scenario: {scenario_path}")
    print(f"Profile:  {args.profile}")
    print(f"Max ticks: {args.max_ticks}")
    print()

    sim = build_simulator(scenario_path)

    # Identify player and target
    player_id = "player"
    target_id = args.target

    if player_id not in sim.ships:
        print(f"ERROR: player ship '{player_id}' not found")
        sys.exit(1)
    if target_id not in sim.ships:
        print(f"ERROR: target ship '{target_id}' not found")
        sys.exit(1)

    # Print initial state
    player = sim.ships[player_id]
    target = sim.ships[target_id]
    initial_range = magnitude(subtract_vectors(target.position, player.position))
    print(f"Player position: {player.position}")
    print(f"Target position: {target.position}")
    print(f"Initial range:   {initial_range:.0f}m ({initial_range/1000:.1f}km)")
    print()

    # Engage autopilot
    engage_rendezvous(sim, player_id, target_id, args.profile)
    print()

    # Run simulation
    t0 = time.monotonic()
    result = run_sim(sim, player_id, target_id, args.max_ticks)
    wall_time = time.monotonic() - t0

    # Summary
    print(f"\n--- Summary ---")
    print(f"Result:     {'SUCCESS' if result['success'] else 'FAILURE'}")
    if result["failure_reason"]:
        print(f"Reason:     {result['failure_reason']}")
    print(f"Ticks:      {result['ticks']}")
    print(f"Sim time:   {result['sim_time']:.1f}s ({result['sim_time']/60:.1f}min)")
    print(f"Wall time:  {wall_time:.1f}s")
    print(f"Final range: {result['final_range']:.1f}m")
    print(f"Final speed: {result['final_rel_speed']:.1f}m/s")
    print(f"Phases:     {' -> '.join(result['phase_history'])}")

    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
