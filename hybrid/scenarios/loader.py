# hybrid/scenarios/loader.py
"""Scenario loader for mission definitions."""

import yaml
import json
import os
import logging
from typing import Dict, List, Optional
from hybrid.scenarios.objectives import Objective, ObjectiveType
from hybrid.scenarios.mission import Mission

logger = logging.getLogger(__name__)

class ScenarioLoader:
    """Loads scenarios from YAML or JSON files."""

    @staticmethod
    def load(filepath: str) -> Dict:
        """Load a scenario from file.

        Args:
            filepath: Path to scenario file (.yaml or .json)

        Returns:
            dict: Scenario data with mission, ships, and configuration
        """
        _, ext = os.path.splitext(filepath)

        with open(filepath, 'r') as f:
            if ext in ['.yaml', '.yml']:
                data = yaml.safe_load(f)
            elif ext == '.json':
                data = json.load(f)
            else:
                raise ValueError(f"Unsupported file format: {ext}")

        logger.info(f"Loaded scenario: {data.get('name', 'Unknown')}")

        # Parse scenario data
        scenario = {
            "name": data.get("name", "Untitled Scenario"),
            "description": data.get("description", ""),
            "dt": data.get("dt", 0.1),
            "ships": ScenarioLoader._parse_ships(data.get("ships", [])),
            "mission": ScenarioLoader._parse_mission(data.get("mission", {})),
            "config": data.get("config", {}),
            "fleets": data.get("fleets", []),
        }

        return scenario

    @staticmethod
    def _parse_ships(ships_data: List[Dict]) -> List[Dict]:
        """Parse ship definitions.

        If a ship definition contains a ``ship_class`` field, the class
        template is resolved from the ship class registry and merged with
        the instance-specific overrides.  Ships without ``ship_class``
        are passed through unchanged for backward compatibility.

        Args:
            ships_data: List of ship configuration dicts

        Returns:
            list: Parsed ship configs
        """
        from hybrid.ship_class_registry import resolve_ship_config

        ships = []

        for ship_def in ships_data:
            # Resolve ship class template (no-op if no ship_class field)
            resolved = resolve_ship_config(ship_def)

            # Ensure minimum required fields with defaults
            ship_config = {
                "id": resolved.get("id", "ship"),
                "name": resolved.get("name", resolved.get("id", "ship")),
                "class": resolved.get("class", "corvette"),
                "faction": resolved.get("faction", "neutral"),
                "mass": resolved.get("mass", 1000),
                "player_controlled": resolved.get("player_controlled", False),
                "position": resolved.get("position", {"x": 0, "y": 0, "z": 0}),
                "velocity": resolved.get("velocity", {"x": 0, "y": 0, "z": 0}),
                "orientation": resolved.get("orientation", {"pitch": 0, "yaw": 0, "roll": 0}),
                "systems": resolved.get("systems", {}),
            }

            # Carry through all other resolved fields (dry_mass, damage_model,
            # armor, dimensions, weapon_mounts, crew_complement, etc.)
            for key in resolved:
                if key not in ship_config:
                    ship_config[key] = resolved[key]

            # Add AI behavior if specified
            if "ai" in resolved:
                ship_config["ai"] = resolved["ai"]

            ships.append(ship_config)

        return ships

    @staticmethod
    def _parse_mission(mission_data: Dict) -> Optional[Mission]:
        """Parse mission definition.

        Args:
            mission_data: Mission configuration dict

        Returns:
            Mission: Parsed mission or None
        """
        if not mission_data:
            return None

        # Parse objectives
        objectives = []
        for obj_data in mission_data.get("objectives", []):
            obj_type_str = obj_data.get("type")

            # Convert string to ObjectiveType enum
            try:
                obj_type = ObjectiveType(obj_type_str)
            except ValueError:
                logger.warning(f"Unknown objective type: {obj_type_str}")
                continue

            objective = Objective(
                obj_id=obj_data.get("id", f"obj_{len(objectives)}"),
                obj_type=obj_type,
                description=obj_data.get("description", ""),
                params=obj_data.get("params", {}),
                required=obj_data.get("required", True)
            )

            objectives.append(objective)

        # Check for branching data -- if present, create a BranchingMission
        # instead of a plain Mission.  The branching loader handles the
        # extended YAML schema (branch_points, comms_choices).
        if mission_data.get("branch_points") or mission_data.get("comms_choices"):
            from hybrid.missions.loader_ext import parse_branching_mission
            branching = parse_branching_mission(mission_data, objectives)
            if branching:
                return branching

        # Create standard mission (no branching data)
        mission = Mission(
            name=mission_data.get("name", "Mission"),
            description=mission_data.get("description", ""),
            objectives=objectives,
            briefing=mission_data.get("briefing", ""),
            success_message=mission_data.get("success_message", ""),
            failure_message=mission_data.get("failure_message", ""),
            hints=mission_data.get("hints", []),
            time_limit=mission_data.get("time_limit"),
            next_scenario=mission_data.get("next_scenario")
        )

        return mission

    @staticmethod
    def list_scenarios(scenarios_dir: str = "scenarios") -> List[str]:
        """List available scenario files.

        Args:
            scenarios_dir: Directory containing scenarios

        Returns:
            list: List of scenario file paths
        """
        if not os.path.exists(scenarios_dir):
            return []

        scenarios = []
        for filename in os.listdir(scenarios_dir):
            if filename.endswith(('.yaml', '.yml', '.json')):
                scenarios.append(os.path.join(scenarios_dir, filename))

        return sorted(scenarios)
