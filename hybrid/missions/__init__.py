# hybrid/missions/__init__.py
"""Mission branching and consequence system.

Extends the base mission framework with conditional branch points,
comms-based player choices, and dynamic objective modification.
"""

from .conditions import BranchCondition, ConditionType, evaluate_condition
from .branching import BranchPoint, MissionBranch, BranchingMission
from .comms_choices import CommsChoice, CommsChoiceManager

__all__ = [
    "BranchCondition",
    "ConditionType",
    "evaluate_condition",
    "BranchPoint",
    "MissionBranch",
    "BranchingMission",
    "CommsChoice",
    "CommsChoiceManager",
]
