# hybrid/missions/loader_ext.py
"""Loader extension for branching mission YAML.

Parses the 'branches', 'branch_points', and 'comms_choices' sections
of a mission YAML and produces a BranchingMission instead of a plain
Mission when branching data is present.

YAML schema extension (inside mission: block):

    comms_choices:
      - choice_id: "surrender_choice"
        contact_id: "enemy_freighter"
        prompt: "This is the freighter captain. We surrender. What are your orders?"
        timeout: 60
        default_option: "escort"
        options:
          - option_id: "accept"
            label: "Accept surrender"
            description: "Stand down and prepare for boarding."
          - option_id: "escort"
            label: "Escort to station"
            description: "Follow us to Tycho Station for inspection."

    branch_points:
      - id: "drive_destroyed_fast"
        priority: 10
        conditions:
          - type: "subsystem_state"
            params: {target: "enemy_freighter", subsystem: "propulsion", state: "destroyed"}
          - type: "time_elapsed"
            params: {threshold: 300, comparison: "lt"}
        logic: "and"
        branch:
          id: "bonus_capture"
          description: "Target disabled quickly -- boarding opportunity."
          add_objectives:
            - id: "board_target"
              type: "reach_range"
              description: "Close to boarding range"
              required: true
              params: {target: "enemy_freighter", range: 100}
          remove_objectives: []
          success_message: "Target boarded. Outstanding work."
          comms_choice_id: "surrender_choice"
"""

import logging
from typing import Any, Dict, List, Optional

from hybrid.scenarios.objectives import Objective, ObjectiveType
from hybrid.scenarios.mission import Mission
from hybrid.missions.branching import BranchPoint, BranchingMission, MissionBranch
from hybrid.missions.conditions import BranchCondition, ConditionType
from hybrid.missions.comms_choices import (
    CommsChoice,
    CommsChoiceManager,
    CommsChoiceOption,
)

logger = logging.getLogger(__name__)


def parse_branching_mission(
    mission_data: Dict[str, Any],
    base_objectives: List[Objective],
) -> Optional[BranchingMission]:
    """Parse a branching mission from YAML data.

    Falls back to None if no branching data is present (caller should
    use the standard Mission in that case).

    Args:
        mission_data: The 'mission' dict from the scenario YAML.
        base_objectives: Already-parsed base objectives.

    Returns:
        BranchingMission if branching data found, else None.
    """
    branch_points_data = mission_data.get("branch_points", [])
    comms_choices_data = mission_data.get("comms_choices", [])

    if not branch_points_data and not comms_choices_data:
        return None

    # Parse comms choices first (branch points may reference them)
    choice_manager = CommsChoiceManager()
    for cc_data in comms_choices_data:
        choice = _parse_comms_choice(cc_data)
        if choice:
            choice_manager.register_choice(choice)

    # Parse branch points
    branch_points = []
    for bp_data in branch_points_data:
        bp = _parse_branch_point(bp_data)
        if bp:
            branch_points.append(bp)

    mission = BranchingMission(
        name=mission_data.get("name", "Mission"),
        description=mission_data.get("description", ""),
        objectives=base_objectives,
        branch_points=branch_points,
        briefing=mission_data.get("briefing", ""),
        success_message=mission_data.get("success_message", ""),
        failure_message=mission_data.get("failure_message", ""),
        hints=mission_data.get("hints", []),
        time_limit=mission_data.get("time_limit"),
    )

    # Attach the choice manager so the comms command handler can find it
    mission.comms_choice_manager = choice_manager

    return mission


def _parse_comms_choice(data: Dict[str, Any]) -> Optional[CommsChoice]:
    """Parse a single comms choice definition."""
    choice_id = data.get("choice_id")
    if not choice_id:
        logger.warning("Comms choice missing choice_id, skipping")
        return None

    options = []
    for opt_data in data.get("options", []):
        options.append(CommsChoiceOption(
            option_id=opt_data.get("option_id", ""),
            label=opt_data.get("label", ""),
            description=opt_data.get("description", ""),
        ))

    if not options:
        logger.warning(f"Comms choice {choice_id} has no options, skipping")
        return None

    return CommsChoice(
        choice_id=choice_id,
        contact_id=data.get("contact_id", ""),
        prompt=data.get("prompt", ""),
        options=options,
        timeout=data.get("timeout"),
        default_option=data.get("default_option"),
    )


def _parse_branch_point(data: Dict[str, Any]) -> Optional[BranchPoint]:
    """Parse a single branch point definition."""
    point_id = data.get("id")
    if not point_id:
        logger.warning("Branch point missing id, skipping")
        return None

    # Parse conditions
    conditions = []
    for cond_data in data.get("conditions", []):
        condition = _parse_condition(cond_data)
        if condition:
            conditions.append(condition)

    if not conditions:
        logger.warning(f"Branch point {point_id} has no valid conditions, skipping")
        return None

    # Parse branch outcome
    branch_data = data.get("branch", {})
    branch = _parse_branch(branch_data)
    if not branch:
        logger.warning(f"Branch point {point_id} has no valid branch, skipping")
        return None

    return BranchPoint(
        point_id=point_id,
        conditions=conditions,
        branch=branch,
        logic=data.get("logic", "and"),
        priority=data.get("priority", 0),
    )


def _parse_condition(data: Dict[str, Any]) -> Optional[BranchCondition]:
    """Parse a single branch condition."""
    type_str = data.get("type")
    if not type_str:
        return None

    try:
        cond_type = ConditionType(type_str)
    except ValueError:
        logger.warning(f"Unknown condition type: {type_str}")
        return None

    return BranchCondition(
        condition_type=cond_type,
        params=data.get("params", {}),
    )


def _parse_branch(data: Dict[str, Any]) -> Optional[MissionBranch]:
    """Parse a branch outcome definition."""
    branch_id = data.get("id")
    if not branch_id:
        return None

    # Parse objectives to add
    add_objectives = []
    for obj_data in data.get("add_objectives", []):
        obj = _parse_objective(obj_data)
        if obj:
            add_objectives.append(obj)

    return MissionBranch(
        branch_id=branch_id,
        description=data.get("description", ""),
        add_objectives=add_objectives,
        remove_objective_ids=data.get("remove_objectives", []),
        success_message=data.get("success_message"),
        failure_message=data.get("failure_message"),
        comms_choice_id=data.get("comms_choice_id"),
    )


def _parse_objective(data: Dict[str, Any]) -> Optional[Objective]:
    """Parse an objective from branch data (same schema as base objectives)."""
    type_str = data.get("type")
    if not type_str:
        return None

    try:
        obj_type = ObjectiveType(type_str)
    except ValueError:
        logger.warning(f"Unknown objective type in branch: {type_str}")
        return None

    return Objective(
        obj_id=data.get("id", "branch_obj"),
        obj_type=obj_type,
        description=data.get("description", ""),
        params=data.get("params", {}),
        required=data.get("required", True),
    )
