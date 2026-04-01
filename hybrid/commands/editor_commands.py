# hybrid/commands/editor_commands.py
"""Editor commands for ship class creation and management.

These are meta commands (not ship-scoped) handled directly by the server,
so they don't route through the hybrid command pipeline. This module
provides the handler logic that the server calls.
"""

import json
import os
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Required top-level fields for a valid ship class config
REQUIRED_FIELDS = {"class_id", "class_name", "mass"}


def validate_ship_class_config(config: dict) -> Optional[str]:
    """Validate a ship class config dict.

    Args:
        config: Ship class configuration dictionary

    Returns:
        Error string if invalid, None if valid
    """
    if not isinstance(config, dict):
        return "Config must be a dictionary"

    for field in REQUIRED_FIELDS:
        if field not in config:
            return f"Missing required field: {field}"

    class_id = config.get("class_id", "")
    if not class_id or not re.match(r"^[a-z][a-z0-9_]*$", class_id):
        return "class_id must be lowercase alphanumeric with underscores, starting with a letter"

    mass = config.get("mass", {})
    if not isinstance(mass, dict):
        return "mass must be a dictionary"
    if (mass.get("dry_mass") or 0) <= 0:
        return "mass.dry_mass must be positive"

    return None


def save_ship_class(config: dict, classes_dir: str = None) -> dict:
    """Save a ship class config to the ship_classes directory.

    Args:
        config: Ship class configuration dictionary
        classes_dir: Path to ship_classes directory (auto-detected if None)

    Returns:
        Response dict with ok/error
    """
    # Validate
    error = validate_ship_class_config(config)
    if error:
        return {"ok": False, "error": f"Validation failed: {error}"}

    # Resolve directory
    if classes_dir is None:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        classes_dir = os.path.join(root, "ship_classes")

    if not os.path.isdir(classes_dir):
        return {"ok": False, "error": f"Ship classes directory not found: {classes_dir}"}

    class_id = config["class_id"]
    filepath = os.path.join(classes_dir, f"{class_id}.json")

    try:
        with open(filepath, "w") as f:
            json.dump(config, f, indent=2)
        logger.info(f"Saved ship class '{class_id}' to {filepath}")
        return {"ok": True, "class_id": class_id, "path": filepath}
    except Exception as e:
        logger.error(f"Failed to save ship class '{class_id}': {e}")
        return {"ok": False, "error": f"Write failed: {str(e)}"}


def get_ship_classes_full(classes_dir: str = None) -> dict:
    """Return all ship class configs with full detail (not just summaries).

    Args:
        classes_dir: Path to ship_classes directory (auto-detected if None)

    Returns:
        Response dict with ok and ship_classes list
    """
    from hybrid.ship_class_registry import get_registry

    registry = get_registry(classes_dir)
    full_classes = []
    for class_id in sorted(registry._classes.keys()):
        cfg = registry.get_class(class_id)  # deep copy
        if cfg:
            full_classes.append(cfg)

    return {"ok": True, "ship_classes": full_classes}
