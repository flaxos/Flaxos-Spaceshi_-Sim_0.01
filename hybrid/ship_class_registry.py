# hybrid/ship_class_registry.py
"""Ship class registry for loading and resolving modular ship definitions.

Ship classes are JSON files in the ``ship_classes/`` directory that define
the baseline specs for each hull type (corvette, destroyer, freighter, etc.).

Scenarios reference ship classes by name and can override any field to
create specific instances (different loadouts, damage states, fuel levels).

Resolution order (later wins):
    ship_class defaults -> scenario ship_config overrides
"""

import json
import os
import copy
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Singleton registry instance
_registry: Optional["ShipClassRegistry"] = None


class ShipClassRegistry:
    """Loads and caches ship class definitions from JSON files."""

    def __init__(self, classes_dir: str = None):
        """Initialize the registry.

        Args:
            classes_dir: Path to directory containing ship class JSON files.
                         Defaults to ``ship_classes/`` relative to project root.
        """
        if classes_dir is None:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            classes_dir = os.path.join(root, "ship_classes")

        self.classes_dir = classes_dir
        self._classes: Dict[str, dict] = {}
        self._load_all()

    def _load_all(self):
        """Load all ship class definitions from the classes directory."""
        if not os.path.isdir(self.classes_dir):
            logger.warning(f"Ship classes directory not found: {self.classes_dir}")
            return

        for filename in sorted(os.listdir(self.classes_dir)):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self.classes_dir, filename)
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                class_id = data.get("class_id", os.path.splitext(filename)[0])
                self._classes[class_id] = data
                logger.info(f"Loaded ship class: {class_id} from {filename}")
            except Exception as e:
                logger.error(f"Failed to load ship class from {filepath}: {e}")

        logger.info(f"Ship class registry: {len(self._classes)} classes loaded")

    def get_class(self, class_id: str) -> Optional[dict]:
        """Get a ship class definition by ID.

        Args:
            class_id: Ship class identifier (e.g. "corvette", "destroyer")

        Returns:
            Deep copy of class definition, or None if not found
        """
        if class_id in self._classes:
            return copy.deepcopy(self._classes[class_id])
        return None

    def list_classes(self) -> list:
        """List all available ship classes.

        Returns:
            List of class summary dicts with id, name, description
        """
        result = []
        for class_id, data in sorted(self._classes.items()):
            result.append({
                "class_id": class_id,
                "class_name": data.get("class_name", class_id),
                "description": data.get("description", ""),
                "dry_mass": data.get("mass", {}).get("dry_mass", 0),
                "dimensions": data.get("dimensions", {}),
            })
        return result

    def resolve_ship_config(self, ship_def: dict) -> dict:
        """Resolve a scenario ship definition against its ship class.

        If the ship definition contains a ``ship_class`` field, the class
        template is loaded and the ship definition is deep-merged on top.
        Instance-specific fields (id, name, position, velocity, orientation,
        ai_enabled, faction) always come from the ship definition.

        If no ``ship_class`` is specified, the ship definition is returned
        unchanged for backward compatibility.

        Args:
            ship_def: Ship definition from a scenario file

        Returns:
            Fully resolved ship config dict ready for Ship constructor
        """
        class_id = ship_def.get("ship_class")
        if not class_id:
            return ship_def

        class_data = self.get_class(class_id)
        if class_data is None:
            logger.warning(
                f"Ship class '{class_id}' not found for ship '{ship_def.get('id')}', "
                f"using raw config"
            )
            return ship_def

        # Start from class template
        resolved = self._build_from_class(class_data)

        # Deep-merge instance overrides on top
        resolved = _deep_merge(resolved, ship_def)

        # Remove the ship_class key (it was consumed)
        resolved.pop("ship_class", None)

        # Ensure 'class' field is set to the class_id
        resolved.setdefault("class", class_id)

        return resolved

    def _build_from_class(self, class_data: dict) -> dict:
        """Convert a ship class definition into a Ship-constructor-compatible config.

        Maps class-level fields (mass.dry_mass, etc.) into the flat config
        format that Ship.__init__ expects.

        Args:
            class_data: Raw ship class definition

        Returns:
            Config dict compatible with Ship constructor
        """
        config = {}

        # Mass properties
        mass_block = class_data.get("mass", {})
        if "dry_mass" in mass_block:
            config["dry_mass"] = mass_block["dry_mass"]
            # Calculate initial total mass: dry + fuel
            fuel = mass_block.get("max_fuel", 0)
            config["mass"] = mass_block["dry_mass"] + fuel
        if "max_hull_integrity" in mass_block:
            config["max_hull_integrity"] = mass_block["max_hull_integrity"]
            config["hull_integrity"] = mass_block["max_hull_integrity"]

        # Class metadata
        config["class"] = class_data.get("class_id", "unknown")
        if "class_name" in class_data:
            config["class_name"] = class_data["class_name"]
        if "description" in class_data:
            config["class_description"] = class_data["description"]

        # Ship geometry (informational, stored on ship state)
        for key in ("dimensions", "armor", "crew_complement", "weapon_mounts"):
            if key in class_data:
                config[key] = copy.deepcopy(class_data[key])

        # Systems (deep copy)
        if "systems" in class_data:
            config["systems"] = copy.deepcopy(class_data["systems"])

        # Damage model
        if "damage_model" in class_data:
            config["damage_model"] = copy.deepcopy(class_data["damage_model"])

        return config


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override dict into base dict.

    For nested dicts, recurse. For all other types, override wins.
    Keys present only in override are added. Keys only in base are kept.

    Args:
        base: Base dictionary (modified in place)
        override: Override dictionary

    Returns:
        Merged dictionary (same object as base)
    """
    for key, value in override.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, dict)
        ):
            _deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def get_registry(classes_dir: str = None) -> ShipClassRegistry:
    """Get or create the singleton ship class registry.

    Args:
        classes_dir: Optional path to ship classes directory

    Returns:
        ShipClassRegistry singleton instance
    """
    global _registry
    if _registry is None:
        _registry = ShipClassRegistry(classes_dir)
    return _registry


def resolve_ship_config(ship_def: dict) -> dict:
    """Convenience function to resolve a ship config via the global registry.

    Args:
        ship_def: Ship definition that may contain a ``ship_class`` field

    Returns:
        Fully resolved ship config
    """
    return get_registry().resolve_ship_config(ship_def)
