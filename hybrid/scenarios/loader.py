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
            "config": data.get("config", {})
        }

        return scenario

    @staticmethod
    def _parse_ships(ships_data: List[Dict]) -> List[Dict]:
        """Parse ship definitions.

        Args:
            ships_data: List of ship configuration dicts

        Returns:
            list: Parsed ship configs
        """
        ships = []

        for ship_def in ships_data:
            # Ensure position/velocity/orientation are in correct format
            ship_config = {
                "id": ship_def.get("id", "ship"),
                "name": ship_def.get("name", ship_def.get("id", "ship")),
                "class": ship_def.get("class", "corvette"),
                "faction": ship_def.get("faction", "neutral"),
                "mass": ship_def.get("mass", 1000),
                "player_controlled": ship_def.get("player_controlled", False),
                "position": ship_def.get("position", {"x": 0, "y": 0, "z": 0}),
                "velocity": ship_def.get("velocity", {"x": 0, "y": 0, "z": 0}),
                "orientation": ship_def.get("orientation", {"pitch": 0, "yaw": 0, "roll": 0}),
                "systems": ship_def.get("systems", {})
            }

            # Add AI behavior if specified
            if "ai" in ship_def:
                ship_config["ai"] = ship_def["ai"]

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

        # Create mission
        mission = Mission(
            name=mission_data.get("name", "Mission"),
            description=mission_data.get("description", ""),
            objectives=objectives,
            briefing=mission_data.get("briefing", ""),
            success_message=mission_data.get("success_message", ""),
            failure_message=mission_data.get("failure_message", ""),
            hints=mission_data.get("hints", []),
            time_limit=mission_data.get("time_limit")
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
