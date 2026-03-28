# hybrid/missions/branching.py
"""Mission branching state machine.

A BranchingMission wraps the base Mission and adds conditional branch
points.  Each branch point defines conditions that, when satisfied,
activate a MissionBranch -- injecting new objectives, modifying
win/lose conditions, and optionally triggering comms choices.

The branching system is evaluated every tick AFTER the base mission
objectives update, so branch conditions can react to objective
completions within the same frame.

Key design choice: branches are one-way.  Once a branch activates,
the mission cannot un-branch.  This prevents combinatorial explosion
and makes mission state easy to reason about.  Sequential branches
(branch A leads to branch B) are supported naturally because later
branch points are evaluated against the already-branched state.
"""

import logging
from typing import Any, Dict, List, Optional

from hybrid.scenarios.mission import Mission
from hybrid.scenarios.objectives import Objective, ObjectiveType, ObjectiveStatus
from hybrid.missions.conditions import (
    BranchCondition,
    ConditionType,
    evaluate_condition,
)

logger = logging.getLogger(__name__)


class MissionBranch:
    """A branch outcome: new objectives and/or modified conditions.

    When activated, a branch can:
    - Add new objectives to the tracker
    - Remove (cancel) existing objectives
    - Override the mission success/failure messages
    - Queue a comms choice for the player
    """

    def __init__(
        self,
        branch_id: str,
        description: str,
        add_objectives: Optional[List[Objective]] = None,
        remove_objective_ids: Optional[List[str]] = None,
        success_message: Optional[str] = None,
        failure_message: Optional[str] = None,
        comms_choice_id: Optional[str] = None,
    ):
        """Initialize a mission branch.

        Args:
            branch_id: Unique identifier for this branch.
            description: Human-readable description of what changed.
            add_objectives: New objectives to inject into the tracker.
            remove_objective_ids: IDs of objectives to cancel/remove.
            success_message: Override for mission success message.
            failure_message: Override for mission failure message.
            comms_choice_id: If set, present this comms choice to the player.
        """
        self.branch_id = branch_id
        self.description = description
        self.add_objectives = add_objectives or []
        self.remove_objective_ids = remove_objective_ids or []
        self.success_message = success_message
        self.failure_message = failure_message
        self.comms_choice_id = comms_choice_id

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for telemetry."""
        return {
            "branch_id": self.branch_id,
            "description": self.description,
            "added_objectives": [o.id for o in self.add_objectives],
            "removed_objectives": self.remove_objective_ids,
            "comms_choice_id": self.comms_choice_id,
        }


class BranchPoint:
    """A conditional fork in the mission timeline.

    A branch point has one or more conditions (AND-ed together by default)
    and a branch that activates when all conditions are true.  For OR logic,
    use multiple BranchPoints with the same branch outcome.

    Once evaluated to True and activated, the branch point is retired
    and never re-checked.
    """

    def __init__(
        self,
        point_id: str,
        conditions: List[BranchCondition],
        branch: MissionBranch,
        logic: str = "and",
        priority: int = 0,
    ):
        """Initialize a branch point.

        Args:
            point_id: Unique ID for this branch point.
            conditions: List of conditions that must be satisfied.
            branch: The branch to activate when conditions are met.
            logic: 'and' (all conditions) or 'or' (any condition).
            priority: Higher priority branch points are evaluated first.
                When two branch points fire on the same tick, only the
                highest-priority one activates.
        """
        self.point_id = point_id
        self.conditions = conditions
        self.branch = branch
        self.logic = logic
        self.priority = priority
        self.activated = False

    def evaluate(
        self,
        sim: Any,
        player_ship: Any,
        context: Dict[str, Any],
    ) -> bool:
        """Test whether this branch point's conditions are met.

        Args:
            sim: Simulator object.
            player_ship: Player's ship.
            context: Mission context dict (start_time, comms_choices, etc.).

        Returns:
            True if the branch should activate.
        """
        if self.activated:
            return False

        results = [
            evaluate_condition(c, sim, player_ship, context)
            for c in self.conditions
        ]

        if self.logic == "or":
            return any(results)
        return all(results)  # default AND


class BranchingMission(Mission):
    """Mission with conditional branching support.

    Extends the base Mission with branch points that are evaluated
    each tick.  Active branch history is tracked for telemetry.
    """

    def __init__(
        self,
        name: str,
        description: str,
        objectives: List[Objective],
        branch_points: Optional[List[BranchPoint]] = None,
        briefing: str = "",
        success_message: str = "",
        failure_message: str = "",
        hints: Optional[List[Dict]] = None,
        time_limit: Optional[float] = None,
    ):
        """Initialize branching mission.

        Args:
            name: Mission name.
            description: Short description.
            objectives: Initial objectives (pre-branch).
            branch_points: Conditional branch points.
            briefing: Pre-mission briefing text.
            success_message: Default success message (branches can override).
            failure_message: Default failure message (branches can override).
            hints: Hint triggers.
            time_limit: Optional time limit in seconds.
        """
        super().__init__(
            name=name,
            description=description,
            objectives=objectives,
            briefing=briefing,
            success_message=success_message,
            failure_message=failure_message,
            hints=hints,
            time_limit=time_limit,
        )
        self.branch_points = branch_points or []
        self.active_branches: List[str] = []
        self.branch_history: List[Dict[str, Any]] = []
        # Player comms choices: choice_id -> selected option_id
        self.comms_choices: Dict[str, str] = {}
        # Pending comms choice IDs (waiting for player response)
        self.pending_comms_choices: List[str] = []

    def record_comms_choice(self, choice_id: str, option_id: str) -> None:
        """Record a player's comms choice.

        Called by the comms command handler when the player selects
        a response option.

        Args:
            choice_id: The choice prompt identifier.
            option_id: The selected option identifier.
        """
        self.comms_choices[choice_id] = option_id
        if choice_id in self.pending_comms_choices:
            self.pending_comms_choices.remove(choice_id)
        logger.info(f"Comms choice recorded: {choice_id} -> {option_id}")

    def update(self, sim: Any, player_ship: Any) -> None:
        """Update mission: base objectives then branch evaluation.

        Args:
            sim: Simulator object.
            player_ship: Player's ship.
        """
        # Run base mission update (objectives, time limit, hints)
        super().update(sim, player_ship)

        # Don't evaluate branches if mission already concluded
        if self.is_complete():
            return

        # Build context for condition evaluation
        context = self._build_context()

        # Evaluate branch points (sorted by priority, highest first)
        sorted_points = sorted(
            self.branch_points, key=lambda bp: bp.priority, reverse=True
        )

        for bp in sorted_points:
            if bp.activated:
                continue
            if bp.evaluate(sim, player_ship, context):
                self._activate_branch(bp, sim)
                # Only one branch per tick to avoid race conditions
                break

        # Handle comms choice timeouts -- auto-resolve expired choices
        # and feed results back into the choice dict for next tick.
        manager = getattr(self, "comms_choice_manager", None)
        if manager:
            auto_resolved = manager.check_timeouts(sim.time)
            for ar in auto_resolved:
                self.record_comms_choice(ar["choice_id"], ar["option_id"])

    def _build_context(self) -> Dict[str, Any]:
        """Build the context dict passed to condition evaluators."""
        # Collect objective statuses for cross-referencing
        obj_statuses = {}
        for obj_id, obj in self.tracker.objectives.items():
            obj_statuses[obj_id] = obj.status.value

        return {
            "start_time": self.start_time or 0,
            "comms_choices": self.comms_choices,
            "objective_statuses": obj_statuses,
        }

    def _activate_branch(self, bp: BranchPoint, sim: Any) -> None:
        """Activate a branch point and apply its branch effects.

        Args:
            bp: The branch point that triggered.
            sim: Simulator for timestamp.
        """
        bp.activated = True
        branch = bp.branch

        logger.info(
            f"Branch activated: {bp.point_id} -> {branch.branch_id}: "
            f"{branch.description}"
        )

        # Remove cancelled objectives
        for obj_id in branch.remove_objective_ids:
            if obj_id in self.tracker.objectives:
                removed = self.tracker.objectives.pop(obj_id)
                logger.info(f"  Removed objective: {obj_id} ({removed.description})")

        # Add new objectives
        for obj in branch.add_objectives:
            self.tracker.objectives[obj.id] = obj
            logger.info(f"  Added objective: {obj.id} ({obj.description})")

        # Override messages if specified
        if branch.success_message:
            self.success_message = branch.success_message
        if branch.failure_message:
            self.failure_message = branch.failure_message

        # Queue comms choice if specified -- auto-present via the manager
        if branch.comms_choice_id:
            self.pending_comms_choices.append(branch.comms_choice_id)
            manager = getattr(self, "comms_choice_manager", None)
            if manager:
                manager.present_choice(branch.comms_choice_id, sim.time)

        # Record history
        self.active_branches.append(branch.branch_id)
        self.branch_history.append({
            "branch_point": bp.point_id,
            "branch": branch.branch_id,
            "time": sim.time,
            "description": branch.description,
        })

    def get_status(self, sim_time: Optional[float] = None) -> Dict:
        """Get mission status including branch information.

        Args:
            sim_time: Current simulation time.

        Returns:
            dict: Full mission status with branching data.
        """
        status = super().get_status(sim_time)
        status["active_branches"] = self.active_branches.copy()
        status["branch_history"] = self.branch_history.copy()
        status["pending_comms_choices"] = self.pending_comms_choices.copy()
        return status
