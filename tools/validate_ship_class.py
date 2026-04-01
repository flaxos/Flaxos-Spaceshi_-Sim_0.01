#!/usr/bin/env python3
"""Validate ship class JSON files against the required schema.

Usage:
    python tools/validate_ship_class.py               # validate all
    python tools/validate_ship_class.py ship_classes/corvette.json
"""

import argparse
import json
import sys
from pathlib import Path

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN = "\033[32m"
RED   = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"

PASS_TAG = f"{GREEN}PASS{RESET}"
FAIL_TAG = f"{RED}FAIL{RESET}"

# ── Constants ─────────────────────────────────────────────────────────────────
REQUIRED_TOP_LEVEL = {"class_id", "class_name", "mass", "armor", "systems",
                      "weapon_mounts", "damage_model"}

ARMOR_SECTIONS = {"fore", "aft", "port", "starboard", "dorsal", "ventral"}

REQUIRED_SYSTEMS = {"sensors", "navigation"}

VALID_WEAPON_TYPES = {"railgun", "pdc", "torpedo", "missile"}

VALID_SUBSYSTEMS = {
    "propulsion", "rcs", "weapons", "sensors", "reactor",
    "life_support", "navigation", "targeting", "combat", "ecm",
    "power_management", "fleet_coord", "comms", "docking",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def err(errors: list[str], msg: str) -> None:
    errors.append(msg)


def validate_ship_class(data: dict) -> list[str]:
    """Validate a parsed ship class dict.  Returns list of error strings."""
    errors: list[str] = []

    # ── 1. Required top-level fields ─────────────────────────────────────────
    missing = REQUIRED_TOP_LEVEL - set(data.keys())
    for field in sorted(missing):
        err(errors, f"Missing required top-level field: '{field}'")

    if missing:
        # Many further checks depend on these fields being present; skip them.
        return errors

    # ── 2. mass block ─────────────────────────────────────────────────────────
    mass = data.get("mass", {})
    if not isinstance(mass, dict):
        err(errors, "'mass' must be an object")
    else:
        dry_mass = mass.get("dry_mass")
        max_fuel = mass.get("max_fuel")
        max_hull = mass.get("max_hull_integrity")

        if dry_mass is None:
            err(errors, "mass.dry_mass is required")
        elif not isinstance(dry_mass, (int, float)) or dry_mass <= 0:
            err(errors, f"mass.dry_mass must be > 0 (got {dry_mass!r})")

        if max_fuel is None:
            err(errors, "mass.max_fuel is required")
        elif not isinstance(max_fuel, (int, float)) or max_fuel < 0:
            err(errors, f"mass.max_fuel must be >= 0 (got {max_fuel!r})")

        if max_hull is None:
            err(errors, "mass.max_hull_integrity is required")
        elif not isinstance(max_hull, (int, float)) or max_hull <= 0:
            err(errors, f"mass.max_hull_integrity must be > 0 (got {max_hull!r})")

        # ── 8a. Mass plausibility ─────────────────────────────────────────────
        if isinstance(dry_mass, (int, float)) and dry_mass > 0:
            if dry_mass < 10:
                err(errors, f"mass.dry_mass={dry_mass} is implausibly small (expected >= 10 kg)")
            if isinstance(max_fuel, (int, float)) and max_fuel > dry_mass * 2:
                err(errors, (
                    f"mass.max_fuel={max_fuel} > dry_mass*2 ({dry_mass * 2:.1f}); "
                    "fuel load implausibly large"
                ))

    # ── 3. armor block ────────────────────────────────────────────────────────
    armor = data.get("armor", {})
    if not isinstance(armor, dict):
        err(errors, "'armor' must be an object")
    else:
        missing_sections = ARMOR_SECTIONS - set(armor.keys())
        for section in sorted(missing_sections):
            err(errors, f"armor section '{section}' is missing")

        for section in ARMOR_SECTIONS:
            s = armor.get(section)
            if s is None:
                continue  # already reported as missing above
            if not isinstance(s, dict):
                err(errors, f"armor.{section} must be an object")
                continue
            thickness = s.get("thickness_cm")
            material = s.get("material")
            if thickness is None:
                err(errors, f"armor.{section}.thickness_cm is required")
            elif not isinstance(thickness, (int, float)) or thickness < 0:
                err(errors, f"armor.{section}.thickness_cm must be >= 0 (got {thickness!r})")
            if material is None:
                err(errors, f"armor.{section}.material is required")
            elif not isinstance(material, str):
                err(errors, f"armor.{section}.material must be a string (got {type(material).__name__})")

    # ── 4. systems block ──────────────────────────────────────────────────────
    systems = data.get("systems", {})
    if not isinstance(systems, dict):
        err(errors, "'systems' must be an object")
    else:
        missing_sys = REQUIRED_SYSTEMS - set(systems.keys())
        for sys_name in sorted(missing_sys):
            err(errors, f"systems.{sys_name} is required but missing")

    # ── 5. weapon_mounts ──────────────────────────────────────────────────────
    mounts = data.get("weapon_mounts", [])
    if not isinstance(mounts, list):
        err(errors, "'weapon_mounts' must be a list")
    else:
        seen_ids: set[str] = set()
        for i, mount in enumerate(mounts):
            tag = f"weapon_mounts[{i}]"
            if not isinstance(mount, dict):
                err(errors, f"{tag} must be an object")
                continue

            mount_id = mount.get("mount_id")
            if mount_id is None:
                err(errors, f"{tag} missing required field 'mount_id'")
            elif not isinstance(mount_id, str):
                err(errors, f"{tag}.mount_id must be a string")
            elif mount_id in seen_ids:
                err(errors, f"Duplicate mount_id '{mount_id}' in weapon_mounts")
            else:
                seen_ids.add(mount_id)

            weapon_type = mount.get("weapon_type")
            if weapon_type is None:
                err(errors, f"{tag} missing required field 'weapon_type'")
            elif weapon_type not in VALID_WEAPON_TYPES:
                err(errors, (
                    f"{tag}.weapon_type '{weapon_type}' is not valid; "
                    f"must be one of {sorted(VALID_WEAPON_TYPES)}"
                ))

            placement = mount.get("placement")
            if placement is None:
                err(errors, f"{tag} missing required field 'placement'")
            elif not isinstance(placement, dict):
                err(errors, f"{tag}.placement must be an object")
            else:
                if "section" not in placement:
                    err(errors, f"{tag}.placement missing required field 'section'")

    # ── 6. damage_model ───────────────────────────────────────────────────────
    damage_model = data.get("damage_model", {})
    if not isinstance(damage_model, dict):
        err(errors, "'damage_model' must be an object")
    else:
        for subsystem_key in damage_model.keys():
            if subsystem_key not in VALID_SUBSYSTEMS:
                err(errors, (
                    f"damage_model key '{subsystem_key}' is not a recognised subsystem; "
                    f"known subsystems: {sorted(VALID_SUBSYSTEMS)}"
                ))

    return errors


def validate_file(path: Path) -> bool:
    """Parse and validate one file.  Prints result.  Returns True if passed."""
    label = str(path)

    # ── JSON parse ────────────────────────────────────────────────────────────
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        print(f"{FAIL_TAG}  {label}")
        print(f"       File not found: {path}")
        return False
    except json.JSONDecodeError as exc:
        print(f"{FAIL_TAG}  {label}")
        print(f"       JSON parse error: {exc}")
        return False

    errors = validate_ship_class(data)

    if errors:
        print(f"{FAIL_TAG}  {label}")
        for e in errors:
            print(f"       {YELLOW}•{RESET} {e}")
        return False
    else:
        print(f"{PASS_TAG}  {label}")
        return True


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    ship_classes_dir = project_root / "ship_classes"

    parser = argparse.ArgumentParser(
        description="Validate ship class JSON files against the required schema."
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Specific JSON file(s) to validate. Omit to validate all in ship_classes/.",
    )
    args = parser.parse_args()

    if args.files:
        paths = [Path(f) for f in args.files]
    else:
        if not ship_classes_dir.is_dir():
            print(f"{RED}ERROR:{RESET} ship_classes/ directory not found at {ship_classes_dir}")
            return 1
        paths = sorted(ship_classes_dir.glob("*.json"))
        if not paths:
            print(f"{YELLOW}WARNING:{RESET} No JSON files found in {ship_classes_dir}")
            return 0

    passed = 0
    total = len(paths)
    for path in paths:
        if validate_file(path):
            passed += 1

    print()
    colour = GREEN if passed == total else RED
    print(f"{colour}{passed}/{total} files passed{RESET}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
