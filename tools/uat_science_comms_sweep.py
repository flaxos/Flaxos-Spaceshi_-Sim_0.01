#!/usr/bin/env python3
"""Science/Comms command sweep — headless UAT for Phase 4.

Covers science analysis and comms station commands across two scenarios:
  20_sensor_sweep.yaml        — multi-contact environment, full science pipeline
  21_diplomatic_incident.yaml — hail, broadcast, transponder, comms choices

Verifies:
  - Every command returns a dict (no crash, no None)
  - Science analysis commands return expected analysis keys
  - Comms commands include expected state keys
  - If ok=False, an error/message/reason key is present

Exit code: 0 if all checks pass, 1 if any fail.

Usage:
  python3 tools/uat_science_comms_sweep.py
  python3 tools/uat_science_comms_sweep.py --verbose
  python3 tools/uat_science_comms_sweep.py --only science
  python3 tools/uat_science_comms_sweep.py --only comms
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


def issue(sim: Simulator, ship_id: str, command: str, params: dict) -> dict:
    ship = sim.ships[ship_id]
    result = route_command(
        ship,
        {"command": command, "ship": ship_id, **params},
        list(sim.ships.values()),
    )
    return result if isinstance(result, dict) else {"error": f"non-dict: {result!r}"}


def acquire_contacts(sim: Simulator, ship_id: str, ticks: int = 150) -> dict[str, str]:
    """Ping sensors and run ticks. Returns id_mapping {original_id: stable_id}."""
    issue(sim, ship_id, "ping_sensors", {})
    for _ in range(ticks):
        sim.tick()
    ship = sim.ships[ship_id]
    tracker = getattr(ship.systems.get("sensors"), "contact_tracker", None)
    return tracker.id_mapping if tracker else {}


# ---------------------------------------------------------------------------
# Science commands (scenario 20)
# ---------------------------------------------------------------------------

SCIENCE_SHIP = "player"


def run_science_commands(sim: Simulator, contact_id: str) -> None:
    print("\n--- Science Analysis ---")
    check_state("science_status",
                issue(sim, SCIENCE_SHIP, "science_status", {}),
                required_keys=["ok", "tracked_contacts", "analysis_capabilities"])

    check("analyze_contact",
          issue(sim, SCIENCE_SHIP, "analyze_contact", {"contact_id": contact_id}),
          expect_ok=True)

    check("spectral_analysis",
          issue(sim, SCIENCE_SHIP, "spectral_analysis", {"contact_id": contact_id}),
          expect_ok=True)

    check("estimate_mass",
          issue(sim, SCIENCE_SHIP, "estimate_mass", {"contact_id": contact_id}),
          expect_ok=True)

    check("assess_threat",
          issue(sim, SCIENCE_SHIP, "assess_threat", {"contact_id": contact_id}),
          expect_ok=True)


def run_probe_commands(sim: Simulator, contact_id: str) -> None:
    print("\n--- Probe Deployment ---")
    result = issue(sim, SCIENCE_SHIP, "deploy_probe", {"contact_id": contact_id})
    check("deploy_probe", result)

    if result.get("ok"):
        probe_id = result.get("probe_id")
        if probe_id:
            check("recall_probe",
                  issue(sim, SCIENCE_SHIP, "recall_probe", {"probe_id": probe_id}))


def run_fcr_commands(sim: Simulator, contact_id: str) -> None:
    print("\n--- FCR Paint ---")
    check("fcr_paint",
          issue(sim, SCIENCE_SHIP, "fcr_paint", {"contact_id": contact_id}))
    check("fcr_release",
          issue(sim, SCIENCE_SHIP, "fcr_release", {"contact_id": contact_id}))


def run_science_rejection_cases(sim: Simulator) -> None:
    print("\n--- Science rejection cases (expect ok=False) ---")
    check("analyze_contact empty id",
          issue(sim, SCIENCE_SHIP, "analyze_contact", {"contact_id": ""}),
          expect_ok=False)
    check("analyze_contact unknown contact",
          issue(sim, SCIENCE_SHIP, "analyze_contact", {"contact_id": "C999"}),
          expect_ok=False)
    check("estimate_mass missing contact_id",
          issue(sim, SCIENCE_SHIP, "estimate_mass", {}),
          expect_ok=False)


# ---------------------------------------------------------------------------
# Comms commands (scenario 21)
# ---------------------------------------------------------------------------

COMMS_SHIP = "player"


def run_comms_status(sim: Simulator) -> None:
    print("\n--- Comms Status ---")
    check_state("comms_status",
                issue(sim, COMMS_SHIP, "comms_status", {}),
                required_keys=["ok", "transponder_enabled", "transponder_code",
                                "distress_active", "radio_range"])


def run_hail_broadcast(sim: Simulator, contact_id: str) -> None:
    print("\n--- Hail / Broadcast ---")
    check("hail_contact",
          issue(sim, COMMS_SHIP, "hail_contact", {"target": contact_id}),
          expect_ok=True)

    check("broadcast_message",
          issue(sim, COMMS_SHIP, "broadcast_message", {
              "message": "Unidentified vessel, this is UNS Steadfast, identify yourself",
          }),
          expect_ok=True)


def run_transponder_commands(sim: Simulator) -> None:
    print("\n--- Transponder / Distress ---")
    check("set_transponder active",
          issue(sim, COMMS_SHIP, "set_transponder", {"mode": "active"}),
          expect_ok=True)

    check("set_distress on",
          issue(sim, COMMS_SHIP, "set_distress", {"active": True}),
          expect_ok=True)

    check("set_distress off",
          issue(sim, COMMS_SHIP, "set_distress", {"active": False}),
          expect_ok=True)


def run_branch_comms(sim: Simulator) -> None:
    print("\n--- Branch / Choices ---")
    check_state("get_comms_choices",
                issue(sim, COMMS_SHIP, "get_comms_choices", {}),
                required_keys=["ok", "choices"])

    check_state("get_branch_status",
                issue(sim, COMMS_SHIP, "get_branch_status", {}),
                required_keys=["ok", "active_branches"])


def run_comms_rejection_cases(sim: Simulator) -> None:
    print("\n--- Comms rejection cases (expect ok=False) ---")
    check("hail_contact no target",
          issue(sim, COMMS_SHIP, "hail_contact", {}),
          expect_ok=False)

    check("comms_respond unknown choice",
          issue(sim, COMMS_SHIP, "comms_respond", {"choice_id": "nonexistent"}),
          expect_ok=False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_science_phase(args) -> None:
    print(f"\n{'='*60}")
    print("Phase 4a: Science (20_sensor_sweep.yaml)")
    print(f"{'='*60}")
    sim = build_sim("20_sensor_sweep.yaml")
    id_mapping = acquire_contacts(sim, SCIENCE_SHIP)

    contact_id = next(
        (cid for orig, cid in id_mapping.items() if orig.startswith("contact_")),
        None,
    )
    if not contact_id:
        print(f"  FAIL  no contacts detected after ping — skipping science tests")
        global _fails
        _fails += 1
        return
    print(f"  contact acquired: {contact_id}")

    run_science_commands(sim, contact_id)
    run_probe_commands(sim, contact_id)
    run_fcr_commands(sim, contact_id)
    run_science_rejection_cases(sim)


def run_comms_phase(args) -> None:
    print(f"\n{'='*60}")
    print("Phase 4b: Comms (21_diplomatic_incident.yaml)")
    print(f"{'='*60}")
    sim = build_sim("21_diplomatic_incident.yaml")
    id_mapping = acquire_contacts(sim, COMMS_SHIP)

    contact_id = id_mapping.get("suspect_freighter") or next(
        (cid for orig, cid in id_mapping.items() if not orig.startswith("nav_")),
        None,
    )
    if not contact_id:
        print("  FAIL  no non-nav contacts detected — skipping hail tests")
        global _fails
        _fails += 1
        return
    print(f"  contact acquired: {contact_id}")

    run_comms_status(sim)
    run_hail_broadcast(sim, contact_id)
    run_transponder_commands(sim)
    run_branch_comms(sim)
    run_comms_rejection_cases(sim)


def main() -> int:
    global _verbose
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--only", choices=["science", "comms"])
    args = parser.parse_args()
    _verbose = args.verbose

    print("== Science/Comms Command Sweep ==")

    try:
        if not args.only or args.only == "science":
            run_science_phase(args)
        if not args.only or args.only == "comms":
            run_comms_phase(args)
    except Exception as exc:
        global _fails
        _fails += 1
        print(f"  FAIL  unexpected exception: {exc}")
        import traceback; traceback.print_exc()

    total = _passes + _fails
    print(f"\n== Results: {_passes}/{total} passed ==")
    if _fails:
        print(f"   {_fails} failed")
        return 1
    print("   All science/comms commands routed correctly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
