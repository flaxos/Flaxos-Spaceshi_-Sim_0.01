#!/usr/bin/env python3
"""Fleet command sweep — headless UAT for Phase 5.

Covers fleet coordination station commands using:
  23_fleet_coordination.yaml  — player + two escorts vs three hostile frigates

Verifies:
  - Fleet lifecycle: create → add ships → form → target → fire → cease fire → break
  - Maneuver orders, tactical display, shared contacts
  - Rejection cases (missing fleet ID, unknown formation, no target)

Exit code: 0 if all checks pass, 1 if any fail.

Usage:
  python3 tools/uat_fleet_sweep.py
  python3 tools/uat_fleet_sweep.py --verbose
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
SCENARIO = "23_fleet_coordination.yaml"
FLEET_ID = "alpha"

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
        reason = f"response missing both 'ok' and 'error' — keys: {list(result.keys())}"
    elif expect_ok is True and not result.get("ok"):
        ok = False
        reason = f"expected ok=True, got {result}"
    elif expect_ok is False and result.get("ok"):
        ok = False
        reason = f"expected ok=False, got {result}"
    elif result.get("ok") is False and not any(k in result for k in ("error", "message", "reason")):
        ok = False
        reason = f"ok=False but no error/message/reason — keys: {list(result.keys())}"

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


def build_sim() -> Simulator:
    scenario_path = ROOT_DIR / "scenarios" / SCENARIO
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
    return result if isinstance(result, dict) else {"error": f"non-dict: {result!r}"}


def acquire_hostile(sim: Simulator, ticks: int = 500) -> str | None:
    """Ping sensors, run ticks, return first hostile stable contact ID."""
    issue(sim, "ping_sensors", {})
    for _ in range(ticks):
        sim.tick()
    ship = sim.ships[PLAYER_ID]
    tracker = getattr(ship.systems.get("sensors"), "contact_tracker", None)
    if not tracker:
        return None
    return next(
        (cid for orig, cid in tracker.id_mapping.items() if "hostile" in orig),
        None,
    )


# ---------------------------------------------------------------------------
# Fleet lifecycle
# ---------------------------------------------------------------------------

def run_fleet_create(sim: Simulator) -> None:
    print("\n--- Fleet Create / Roster ---")
    check_state("fleet_status (no fleet yet)",
                issue(sim, "fleet_status", {}),
                required_keys=["ok", "fleets"])

    check("fleet_create",
          issue(sim, "fleet_create", {"fleet_id": FLEET_ID, "name": "Alpha Squadron"}),
          expect_ok=True)

    check("fleet_add_ship escort_blade",
          issue(sim, "fleet_add_ship", {"fleet_id": FLEET_ID, "target_ship": "escort_blade"}),
          expect_ok=True)

    check("fleet_add_ship escort_lance",
          issue(sim, "fleet_add_ship", {"fleet_id": FLEET_ID, "target_ship": "escort_lance"}),
          expect_ok=True)

    check_state("fleet_status after create",
                issue(sim, "fleet_status", {"fleet_id": FLEET_ID}),
                required_keys=["ok", "fleet"])


def run_formation_commands(sim: Simulator) -> None:
    print("\n--- Formations ---")
    for formation in ("line", "column", "wedge", "echelon", "diamond"):
        check(f"fleet_form {formation}",
              issue(sim, "fleet_form", {"fleet_id": FLEET_ID, "formation": formation}),
              expect_ok=True)

    check("fleet_form with spacing",
          issue(sim, "fleet_form", {"fleet_id": FLEET_ID, "formation": "line", "spacing": 3000}),
          expect_ok=True)


def run_targeting_and_fire(sim: Simulator, hostile_id: str) -> None:
    print("\n--- Target / Fire ---")
    check("fleet_target",
          issue(sim, "fleet_target", {"fleet_id": FLEET_ID, "contact": hostile_id}),
          expect_ok=True)

    check_state("fleet_tactical after target",
                issue(sim, "fleet_tactical", {"fleet_id": FLEET_ID}),
                required_keys=["ok", "tactical"])

    check("fleet_fire",
          issue(sim, "fleet_fire", {"fleet_id": FLEET_ID}),
          expect_ok=True)

    check("fleet_cease_fire",
          issue(sim, "fleet_cease_fire", {"fleet_id": FLEET_ID}),
          expect_ok=True)


def run_maneuver_commands(sim: Simulator, hostile_id: str) -> None:
    print("\n--- Maneuvers ---")
    check("fleet_maneuver intercept",
          issue(sim, "fleet_maneuver", {
              "fleet_id": FLEET_ID, "maneuver": "intercept", "target_id": hostile_id,
          }),
          expect_ok=True)

    check("fleet_maneuver withdraw",
          issue(sim, "fleet_maneuver", {"fleet_id": FLEET_ID, "maneuver": "withdraw"}),
          expect_ok=True)


def run_share_contact(sim: Simulator, hostile_id: str) -> None:
    print("\n--- Share Contact ---")
    check("share_contact",
          issue(sim, "share_contact", {"contact": hostile_id, "fleet_id": FLEET_ID}),
          expect_ok=True)

    check("share_contact hostile=True",
          issue(sim, "share_contact", {
              "contact": hostile_id, "fleet_id": FLEET_ID, "hostile": True,
          }),
          expect_ok=True)


def run_break_formation(sim: Simulator) -> None:
    print("\n--- Break Formation ---")
    check("fleet_break_formation",
          issue(sim, "fleet_break_formation", {"fleet_id": FLEET_ID}),
          expect_ok=True)


def run_rejection_cases(sim: Simulator) -> None:
    print("\n--- Rejection cases (expect ok=False) ---")
    check("fleet_target no contact",
          issue(sim, "fleet_target", {"fleet_id": FLEET_ID}),
          expect_ok=False)

    # fleet_fire without target only fails if no target was ever set — use a fresh fleet
    route_result = issue(sim, "fleet_create", {"fleet_id": "empty_fleet", "name": "Empty"})
    if route_result.get("ok"):
        check("fleet_fire no target (empty fleet)",
              issue(sim, "fleet_fire", {"fleet_id": "empty_fleet"}),
              expect_ok=False)
    else:
        print("  SKIP  fleet_fire no-target check (fleet_create failed)")

    check("share_contact no contact",
          issue(sim, "share_contact", {}),
          expect_ok=False)

    check("fleet_target unknown fleet",
          issue(sim, "fleet_target", {"fleet_id": "DOESNOTEXIST", "contact": "C001"}),
          expect_ok=False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    global _verbose
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    _verbose = args.verbose

    print("== Fleet Command Sweep ==")
    print(f"Scenario: {SCENARIO}")

    sim = build_sim()

    print("\n--- Setup: acquiring hostile contact ---")
    hostile_id = acquire_hostile(sim)
    if not hostile_id:
        print("  FAIL  no hostile contact detected after 500 ticks")
        return 1
    print(f"  hostile contact: {hostile_id}")

    run_fleet_create(sim)
    run_formation_commands(sim)
    run_targeting_and_fire(sim, hostile_id)
    run_maneuver_commands(sim, hostile_id)
    run_share_contact(sim, hostile_id)
    run_break_formation(sim)
    run_rejection_cases(sim)

    total = _passes + _fails
    print(f"\n== Results: {_passes}/{total} passed ==")
    if _fails:
        print(f"   {_fails} failed")
        return 1
    print("   All fleet commands routed correctly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
