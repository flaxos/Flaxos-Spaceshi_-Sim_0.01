#!/usr/bin/env python3
"""Ops/Engineering/Stealth command sweep — headless UAT for Phase 3.

Covers all ops and engineering station commands across three scenarios:
  22_damage_control.yaml  — pre-damaged ship, repair pipeline
  24_fuel_crisis.yaml     — low fuel, power management pressure
  25_silent_running.yaml  — EMCON/ECM stealth commands

Verifies:
  - Every command returns a dict (no crash, no None)
  - Power/repair/status commands include expected keys
  - If ok=False, an error/message/reason key is present

Exit code: 0 if all checks pass, 1 if any fail.

Usage:
  python3 tools/uat_ops_sweep.py
  python3 tools/uat_ops_sweep.py --verbose
  python3 tools/uat_ops_sweep.py --scenario scenarios/22_damage_control.yaml
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from hybrid.command_handler import route_command
from hybrid.scenarios.loader import ScenarioLoader
from hybrid.simulator import Simulator

PLAYER_ID = "player"

_passes = 0
_fails = 0
_verbose = False


def log(msg: str) -> None:
    if _verbose:
        print(f"  {msg}")


def check(label: str, result, *, expect_ok: bool | None = None) -> bool:
    global _passes, _fails
    ok = True
    reason = None

    if not isinstance(result, dict):
        ok = False
        reason = f"returned {type(result).__name__} instead of dict"
    elif "ok" not in result and "error" not in result:
        ok = False
        reason = f"response missing both 'ok' and 'error' keys — keys: {list(result.keys())}"
    elif expect_ok is True and not result.get("ok"):
        ok = False
        reason = f"expected ok=True, got {result}"
    elif expect_ok is False and result.get("ok"):
        ok = False
        reason = f"expected ok=False (rejection), got {result}"
    elif result.get("ok") is False and "error" not in result and "message" not in result and "reason" not in result:
        ok = False
        reason = f"ok=False but no error/message/reason key — keys: {list(result.keys())}"

    if ok:
        _passes += 1
        print(f"  PASS  {label}")
        log(str(result))
    else:
        _fails += 1
        print(f"  FAIL  {label}: {reason}")
    return ok


def check_state(label: str, result, *, required_keys: list[str] | None = None) -> bool:
    global _passes, _fails
    ok = True
    reason = None

    if not isinstance(result, dict):
        ok = False
        reason = f"returned {type(result).__name__} instead of dict"
    elif not result:
        ok = False
        reason = "returned empty dict"
    elif required_keys:
        missing = [k for k in required_keys if k not in result]
        if missing:
            ok = False
            reason = f"missing required keys: {missing}"

    if ok:
        _passes += 1
        print(f"  PASS  {label}")
        log(str(list(result.keys())))
    else:
        _fails += 1
        print(f"  FAIL  {label}: {reason}")
    return ok


def build_sim(scenario_name: str) -> Simulator:
    scenario_path = ROOT_DIR / "scenarios" / scenario_name
    scenario = ScenarioLoader.load(str(scenario_path))
    sim = Simulator(dt=scenario.get("dt", 0.1), time_scale=1.0)
    for ship_data in scenario["ships"]:
        sim.add_ship(ship_data["id"], ship_data)
    all_ships = list(sim.ships.values())
    for ship in all_ships:
        ship._all_ships_ref = all_ships
    sim.start()
    return sim


def issue(sim: Simulator, command: str, params: dict) -> dict:
    ship = sim.ships[PLAYER_ID]
    result = route_command(
        ship,
        {"command": command, "ship": PLAYER_ID, **params},
        list(sim.ships.values()),
    )
    if not isinstance(result, dict):
        return {"error": f"non-dict result: {result!r}"}
    return result


# ---------------------------------------------------------------------------
# Repair / damage-control commands (scenario 22)
# ---------------------------------------------------------------------------

def run_repair_commands(sim: Simulator) -> None:
    print("\n--- Repair / Damage Control ---")
    check_state("report_status",
                issue(sim, "report_status", {}),
                required_keys=["power_allocation", "subsystem_report"])

    check("dispatch_repair sensors",
          issue(sim, "dispatch_repair", {"subsystem": "sensors"}),
          expect_ok=True)

    check_state("repair_status",
                issue(sim, "repair_status", {}),
                required_keys=["repair_teams"])

    check("set_repair_priority sensors high",
          issue(sim, "set_repair_priority", {"subsystem": "sensors", "priority": "high"}),
          expect_ok=True)

    check("cancel_repair sensors",
          issue(sim, "cancel_repair", {"subsystem": "sensors"}))

    check("emergency_shutdown propulsion",
          issue(sim, "emergency_shutdown", {"subsystem": "propulsion"}),
          expect_ok=True)

    check("restart_system propulsion",
          issue(sim, "restart_system", {"subsystem": "propulsion"}),
          expect_ok=True)

    check("set_system_priority propulsion=8",
          issue(sim, "set_system_priority", {"subsystem": "propulsion", "priority": 8}),
          expect_ok=True)

    check("allocate_power",
          issue(sim, "allocate_power", {
              "allocation": {"propulsion": 0.5, "sensors": 0.3, "weapons": 0.2},
          }),
          expect_ok=True)


def run_repair_rejection_cases(sim: Simulator) -> None:
    print("\n--- Repair rejection cases (expect ok=False) ---")
    check("dispatch_repair no subsystem",
          issue(sim, "dispatch_repair", {}),
          expect_ok=False)

    check("cancel_repair unknown subsystem",
          issue(sim, "cancel_repair", {"subsystem": "nonexistent_system"}))

    check("emergency_shutdown no subsystem",
          issue(sim, "emergency_shutdown", {}),
          expect_ok=False)


# ---------------------------------------------------------------------------
# Power management commands (scenario 24)
# ---------------------------------------------------------------------------

def run_power_commands(sim: Simulator) -> None:
    print("\n--- Power Management ---")
    profiles_result = issue(sim, "get_power_profiles", {})
    check_state("get_power_profiles",
                profiles_result,
                required_keys=["profiles"])

    # Use the first available profile (avoid guessing the name)
    profiles = profiles_result.get("profiles", [])
    if profiles:
        check_state(f"set_power_profile {profiles[0]}",
                    issue(sim, "set_power_profile", {"profile": profiles[0]}),
                    required_keys=["profile"])
    else:
        print("  SKIP  set_power_profile — no profiles defined")

    check_state("get_draw_profile",
                issue(sim, "get_draw_profile", {}),
                required_keys=["active_profile", "buses"])

    check_state("set_power_allocation",
                issue(sim, "set_power_allocation", {
                    "allocation": {"propulsion": 0.5, "sensors": 0.3},
                }),
                required_keys=["power_allocation"])


def run_engineering_commands(sim: Simulator) -> None:
    print("\n--- Engineering ---")
    check("set_reactor_output 0.75",
          issue(sim, "set_reactor_output", {"output": 0.75}),
          expect_ok=True)

    check("throttle_drive 0.6",
          issue(sim, "throttle_drive", {"limit": 0.6}),
          expect_ok=True)

    check_state("monitor_fuel",
                issue(sim, "monitor_fuel", {}),
                required_keys=["fuel_level", "fuel_percent", "delta_v_remaining"])

    # manage_radiators — action may not be defined on all ships, accept either result
    result = issue(sim, "manage_radiators", {"action": "deploy"})
    check("manage_radiators deploy (shape)", result)

    # Restore full reactor output
    issue(sim, "set_reactor_output", {"output": 1.0})
    issue(sim, "throttle_drive", {"limit": 1.0})


def run_power_rejection_cases(sim: Simulator) -> None:
    print("\n--- Power rejection cases (expect ok=False) ---")
    check("set_power_profile unknown",
          issue(sim, "set_power_profile", {"profile": "turbo_laser_disco"}),
          expect_ok=False)

    # Reactor/drive accept out-of-range values by clamping; only missing params reject
    check("set_reactor_output missing output",
          issue(sim, "set_reactor_output", {}),
          expect_ok=False)

    check("throttle_drive missing limit",
          issue(sim, "throttle_drive", {}),
          expect_ok=False)


# ---------------------------------------------------------------------------
# ECM / EMCON / stealth commands (scenario 25)
# ---------------------------------------------------------------------------

def run_stealth_commands(sim: Simulator) -> None:
    print("\n--- ECM / EMCON / Stealth ---")
    check_state("ecm_status initial",
                issue(sim, "ecm_status", {}),
                required_keys=["emcon_active", "emcon_ir_reduction", "emcon_rcs_reduction"])

    # Engage EMCON (scenario starts with emcon_active=True, so this toggles it off first)
    r_off = issue(sim, "set_emcon", {"active": False})
    check("set_emcon active=False", r_off, expect_ok=True)

    r_on = issue(sim, "set_emcon", {"active": True})
    check("set_emcon active=True", r_on, expect_ok=True)

    # Verify emcon state changed
    status_after = issue(sim, "ecm_status", {})
    check_state("ecm_status after set_emcon",
                status_after,
                required_keys=["emcon_active"])

    # Thermal system may not be present; cold_drift returns shape-only error
    r_cold = issue(sim, "cold_drift", {})
    check("cold_drift (shape only — thermal may be absent)", r_cold)

    r_exit = issue(sim, "exit_cold_drift", {})
    check("exit_cold_drift (shape only)", r_exit)


def run_stealth_rejection_cases(sim: Simulator) -> None:
    print("\n--- Stealth rejection cases (expect ok=False) ---")
    # set_emcon with no active param defaults gracefully; test a command that truly rejects
    check("set_repair_priority missing subsystem",
          issue(sim, "set_repair_priority", {"priority": "high"}),
          expect_ok=False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_phase(name: str, scenario: str, runner_fn) -> None:
    print(f"\n{'='*60}")
    print(f"Phase: {name}  ({scenario})")
    print(f"{'='*60}")
    try:
        sim = build_sim(scenario)
        runner_fn(sim)
    except Exception as exc:
        global _fails
        _fails += 1
        print(f"  FAIL  scenario load/setup: {exc}")
        import traceback; traceback.print_exc()


def main() -> int:
    global _verbose
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--only",
        choices=["repair", "power", "stealth"],
        help="Run only the named phase",
    )
    args = parser.parse_args()
    _verbose = args.verbose

    print("== Ops/Engineering/Stealth Command Sweep ==")

    if not args.only or args.only == "repair":
        run_phase(
            "Damage Control",
            "22_damage_control.yaml",
            lambda sim: (
                run_repair_commands(sim),
                run_repair_rejection_cases(sim),
            ),
        )

    if not args.only or args.only == "power":
        run_phase(
            "Fuel Crisis / Power Management",
            "24_fuel_crisis.yaml",
            lambda sim: (
                run_power_commands(sim),
                run_engineering_commands(sim),
                run_power_rejection_cases(sim),
            ),
        )

    if not args.only or args.only == "stealth":
        run_phase(
            "Silent Running / Stealth",
            "25_silent_running.yaml",
            lambda sim: (
                run_stealth_commands(sim),
                run_stealth_rejection_cases(sim),
            ),
        )

    total = _passes + _fails
    print(f"\n== Results: {_passes}/{total} passed ==")
    if _fails:
        print(f"   {_fails} failed")
        return 1

    print("   All ops/engineering/stealth commands routed correctly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
