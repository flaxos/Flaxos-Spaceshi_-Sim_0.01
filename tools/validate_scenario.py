#!/usr/bin/env python3
"""Validate scenario YAML files against the required schema.

Usage:
    python tools/validate_scenario.py                           # validate all
    python tools/validate_scenario.py scenarios/01_tutorial_intercept.yaml
"""

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml is required. Install with: pip install pyyaml")
    sys.exit(1)

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
RESET  = "\033[0m"

PASS_TAG = f"{GREEN}PASS{RESET}"
FAIL_TAG = f"{RED}FAIL{RESET}"

# ── Constants ─────────────────────────────────────────────────────────────────
# Derived from ObjectiveType enum in hybrid/scenarios/objectives.py
VALID_OBJECTIVE_TYPES = {
    "reach_range",
    "destroy_target",
    "mission_kill",
    "avoid_mission_kill",
    "survive_time",
    "protect_ship",
    "dock_with",
    "match_velocity",
    "reach_position",
    "scan_target",
    "avoid_detection",
    "collect_item",
    "escape_range",
    "ammo_depleted",
}

# Known factions observed in the codebase and all scenario files
KNOWN_FACTIONS = {
    "unsa", "mcrn", "civilian", "hostile", "neutral", "pirates",
    "pirate", "opa", "independent", "mars", "smuggler", "unknown",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def err(errors: list[str], msg: str) -> None:
    errors.append(msg)


def validate_scenario(data: dict, scenario_path: Path,
                      ship_classes_dir: Path, scenarios_dir: Path) -> list[str]:
    """Validate a parsed scenario dict.  Returns list of error strings."""
    errors: list[str] = []

    # ── 1. Required top-level fields ─────────────────────────────────────────
    if "name" not in data:
        err(errors, "Missing required top-level field: 'name'")
    elif not isinstance(data["name"], str):
        err(errors, f"'name' must be a string (got {type(data['name']).__name__})")

    if "ships" not in data:
        err(errors, "Missing required top-level field: 'ships'")
    elif not isinstance(data["ships"], list):
        err(errors, f"'ships' must be a list (got {type(data['ships']).__name__})")

    # Return early — the ships block is required for most other checks.
    if "ships" not in data or not isinstance(data["ships"], list):
        return errors

    # ── 2. Ship validation ────────────────────────────────────────────────────
    seen_ship_ids: set[str] = set()

    for i, ship in enumerate(data["ships"]):
        tag = f"ships[{i}]"

        if not isinstance(ship, dict):
            err(errors, f"{tag} must be an object")
            continue

        # id
        ship_id = ship.get("id")
        if ship_id is None:
            err(errors, f"{tag} missing required field 'id'")
        elif not isinstance(ship_id, str):
            err(errors, f"{tag}.id must be a string")
        elif ship_id in seen_ship_ids:
            err(errors, f"Duplicate ship id '{ship_id}'")
        else:
            seen_ship_ids.add(ship_id)

        # name
        if "name" not in ship:
            err(errors, f"{tag} (id={ship_id!r}) missing required field 'name'")

        # ship_class / class → verify file exists
        raw_class = ship.get("ship_class") or ship.get("class")
        if raw_class is not None:
            # Normalise: "frigate" -> "frigate.json"
            class_file = ship_classes_dir / f"{raw_class}.json"
            if not class_file.is_file():
                err(errors, (
                    f"{tag} (id={ship_id!r}) references ship_class '{raw_class}' "
                    f"but {class_file} does not exist"
                ))

        # faction
        faction = ship.get("faction")
        if faction is not None:
            if not isinstance(faction, str):
                err(errors, f"{tag} (id={ship_id!r}).faction must be a string")
            elif faction not in KNOWN_FACTIONS:
                err(errors, (
                    f"{tag} (id={ship_id!r}).faction '{faction}' is not a recognised faction; "
                    f"known factions: {sorted(KNOWN_FACTIONS)}"
                ))

    # ── 3. mission.objectives ─────────────────────────────────────────────────
    mission = data.get("mission")
    if mission is not None:
        if not isinstance(mission, dict):
            err(errors, "'mission' must be an object")
        else:
            objectives = mission.get("objectives")
            if objectives is not None:
                if not isinstance(objectives, list):
                    err(errors, "mission.objectives must be a list")
                else:
                    seen_obj_ids: set[str] = set()
                    for j, obj in enumerate(objectives):
                        otag = f"mission.objectives[{j}]"
                        if not isinstance(obj, dict):
                            err(errors, f"{otag} must be an object")
                            continue

                        obj_id = obj.get("id")
                        if obj_id is None:
                            err(errors, f"{otag} missing required field 'id'")
                        elif not isinstance(obj_id, str):
                            err(errors, f"{otag}.id must be a string")
                        elif obj_id in seen_obj_ids:
                            err(errors, f"Duplicate objective id '{obj_id}'")
                        else:
                            seen_obj_ids.add(obj_id)

                        if "type" not in obj:
                            err(errors, f"{otag} (id={obj_id!r}) missing required field 'type'")
                        else:
                            obj_type = obj["type"]
                            if obj_type not in VALID_OBJECTIVE_TYPES:
                                err(errors, (
                                    f"{otag} (id={obj_id!r}) has unknown type '{obj_type}'; "
                                    f"valid types: {sorted(VALID_OBJECTIVE_TYPES)}"
                                ))

                        if "description" not in obj:
                            err(errors, f"{otag} (id={obj_id!r}) missing required field 'description'")

            # ── 4. next_scenario → verify file exists ─────────────────────────
            next_scenario = mission.get("next_scenario")
            if next_scenario is not None:
                if not isinstance(next_scenario, str):
                    err(errors, "mission.next_scenario must be a string")
                else:
                    # Try .yaml first, then .yml
                    candidate_yaml = scenarios_dir / f"{next_scenario}.yaml"
                    candidate_yml  = scenarios_dir / f"{next_scenario}.yml"
                    if not candidate_yaml.is_file() and not candidate_yml.is_file():
                        err(errors, (
                            f"mission.next_scenario '{next_scenario}' refers to a scenario "
                            f"that does not exist (tried {candidate_yaml} and {candidate_yml})"
                        ))

    return errors


def validate_file(path: Path, ship_classes_dir: Path, scenarios_dir: Path) -> bool:
    """Parse and validate one scenario file.  Prints result.  Returns True if passed."""
    label = str(path)

    # ── YAML parse ────────────────────────────────────────────────────────────
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except FileNotFoundError:
        print(f"{FAIL_TAG}  {label}")
        print(f"       File not found: {path}")
        return False
    except yaml.YAMLError as exc:
        print(f"{FAIL_TAG}  {label}")
        print(f"       YAML parse error: {exc}")
        return False

    if not isinstance(data, dict):
        print(f"{FAIL_TAG}  {label}")
        print(f"       Expected a YAML mapping at top level, got {type(data).__name__}")
        return False

    errors = validate_scenario(data, path, ship_classes_dir, scenarios_dir)

    if errors:
        print(f"{FAIL_TAG}  {label}")
        for e in errors:
            print(f"       {YELLOW}•{RESET} {e}")
        return False
    else:
        print(f"{PASS_TAG}  {label}")
        return True


def main() -> int:
    project_root    = Path(__file__).resolve().parent.parent
    scenarios_dir   = project_root / "scenarios"
    ship_classes_dir = project_root / "ship_classes"

    parser = argparse.ArgumentParser(
        description="Validate scenario YAML files against the required schema."
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Specific YAML file(s) to validate. Omit to validate all in scenarios/.",
    )
    args = parser.parse_args()

    if args.files:
        paths = [Path(f) for f in args.files]
    else:
        if not scenarios_dir.is_dir():
            print(f"{RED}ERROR:{RESET} scenarios/ directory not found at {scenarios_dir}")
            return 1
        paths = sorted(scenarios_dir.glob("*.yaml")) + sorted(scenarios_dir.glob("*.yml"))
        if not paths:
            print(f"{YELLOW}WARNING:{RESET} No YAML files found in {scenarios_dir}")
            return 0

    if not ship_classes_dir.is_dir():
        print(f"{RED}ERROR:{RESET} ship_classes/ directory not found at {ship_classes_dir}")
        return 1

    passed = 0
    total  = len(paths)
    for path in paths:
        if validate_file(path, ship_classes_dir, scenarios_dir):
            passed += 1

    print()
    colour = GREEN if passed == total else RED
    print(f"{colour}{passed}/{total} files passed{RESET}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
