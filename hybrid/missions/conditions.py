# hybrid/missions/conditions.py
"""Branch condition evaluation for mission branching.

Conditions are the atomic predicates that drive branch decisions.
Each condition tests one aspect of the simulation state: subsystem
health, fuel level, elapsed time, contact range, or a player choice
made through comms.  Conditions are pure functions of game state --
no side effects, no persistence.

Design rationale: conditions are intentionally simple and composable.
Complex branching emerges from combining multiple conditions with
AND/OR logic at the BranchPoint level, not from building god-objects.
"""

import logging
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ConditionType(Enum):
    """Types of branch conditions the mission system can evaluate."""
    SUBSYSTEM_STATE = "subsystem_state"
    FUEL_LEVEL = "fuel_level"
    TIME_ELAPSED = "time_elapsed"
    CONTACT_RANGE = "contact_range"
    CONTACT_LOST = "contact_lost"
    COMMS_CHOICE = "comms_choice"
    OBJECTIVE_STATUS = "objective_status"
    SHIP_DESTROYED = "ship_destroyed"


class BranchCondition:
    """A single testable condition for mission branching.

    Attributes:
        condition_type: What kind of game state to test.
        params: Type-specific parameters (target, threshold, etc.).
    """

    def __init__(self, condition_type: ConditionType, params: Dict[str, Any]):
        """Initialize a branch condition.

        Args:
            condition_type: The category of condition to evaluate.
            params: Parameters specific to the condition type.
                subsystem_state: target, subsystem, state (nominal/impaired/destroyed)
                fuel_level: target, comparison (lt/gt/eq), threshold (0.0-1.0)
                time_elapsed: threshold (seconds), comparison (lt/gt)
                contact_range: target, comparison (lt/gt), range (metres)
                contact_lost: target (ship ID no longer in sensor contacts)
                comms_choice: choice_id, expected_option
                objective_status: objective_id, status (completed/failed/in_progress)
                ship_destroyed: target
        """
        self.condition_type = condition_type
        self.params = params

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for telemetry/debugging."""
        return {
            "type": self.condition_type.value,
            "params": self.params,
        }


def evaluate_condition(
    condition: BranchCondition,
    sim: Any,
    player_ship: Any,
    mission_context: Dict[str, Any],
) -> bool:
    """Evaluate a single branch condition against current game state.

    Pure function: reads sim state, returns bool, no side effects.

    Args:
        condition: The condition to test.
        sim: Simulator object (has .ships, .time).
        player_ship: The player's ship object.
        mission_context: Dict with keys like 'start_time', 'comms_choices',
            'objective_statuses' populated by the mission runner.

    Returns:
        True if the condition is satisfied.
    """
    ct = condition.condition_type
    p = condition.params

    if ct == ConditionType.SUBSYSTEM_STATE:
        return _eval_subsystem_state(p, sim, player_ship)
    elif ct == ConditionType.FUEL_LEVEL:
        return _eval_fuel_level(p, sim, player_ship)
    elif ct == ConditionType.TIME_ELAPSED:
        return _eval_time_elapsed(p, sim, mission_context)
    elif ct == ConditionType.CONTACT_RANGE:
        return _eval_contact_range(p, sim, player_ship)
    elif ct == ConditionType.CONTACT_LOST:
        return _eval_contact_lost(p, sim, player_ship)
    elif ct == ConditionType.COMMS_CHOICE:
        return _eval_comms_choice(p, mission_context)
    elif ct == ConditionType.OBJECTIVE_STATUS:
        return _eval_objective_status(p, mission_context)
    elif ct == ConditionType.SHIP_DESTROYED:
        return _eval_ship_destroyed(p, sim)

    logger.warning(f"Unknown condition type: {ct}")
    return False


# ------------------------------------------------------------------
# Private evaluators -- one per ConditionType
# ------------------------------------------------------------------

def _eval_subsystem_state(
    params: Dict[str, Any], sim: Any, player_ship: Any
) -> bool:
    """Check if a ship's subsystem is in a specific damage state.

    Uses the damage_model degradation factor:
      nominal  = factor >= 0.5
      impaired = 0.0 < factor < 0.5
      destroyed = factor <= 0.0
    """
    target_id = params.get("target", "player")
    subsystem = params.get("subsystem")
    expected_state = params.get("state", "destroyed")

    ship = _resolve_ship(target_id, sim, player_ship)
    if not ship:
        return False

    damage_model = getattr(ship, "damage_model", None)
    if not damage_model:
        # No damage model means everything is nominal
        return expected_state == "nominal"

    factor = damage_model.get_degradation_factor(subsystem)

    if expected_state == "destroyed":
        return factor <= 0.0
    elif expected_state == "impaired":
        return 0.0 < factor < 0.5
    elif expected_state == "nominal":
        return factor >= 0.5
    return False


def _eval_fuel_level(
    params: Dict[str, Any], sim: Any, player_ship: Any
) -> bool:
    """Check fuel level as fraction of max capacity."""
    target_id = params.get("target", "player")
    comparison = params.get("comparison", "lt")
    threshold = float(params.get("threshold", 0.25))

    ship = _resolve_ship(target_id, sim, player_ship)
    if not ship:
        return False

    propulsion = ship.systems.get("propulsion") if hasattr(ship, "systems") else None
    if not propulsion:
        return False

    fuel = getattr(propulsion, "fuel_level", 0)
    max_fuel = getattr(propulsion, "max_fuel", 1)
    if max_fuel <= 0:
        return False

    fraction = fuel / max_fuel
    return _compare(fraction, comparison, threshold)


def _eval_time_elapsed(
    params: Dict[str, Any], sim: Any, context: Dict[str, Any]
) -> bool:
    """Check elapsed mission time against a threshold."""
    threshold = float(params.get("threshold", 300))
    comparison = params.get("comparison", "gt")

    start_time = context.get("start_time", 0)
    elapsed = sim.time - start_time
    return _compare(elapsed, comparison, threshold)


def _eval_contact_range(
    params: Dict[str, Any], sim: Any, player_ship: Any
) -> bool:
    """Check range between player and a target ship."""
    target_id = params.get("target")
    comparison = params.get("comparison", "lt")
    threshold = float(params.get("range", 1000))

    target_ship = sim.ships.get(target_id)
    if not target_ship:
        return False

    from hybrid.utils.math_utils import calculate_distance
    distance = calculate_distance(player_ship.position, target_ship.position)
    return _compare(distance, comparison, threshold)


def _eval_contact_lost(
    params: Dict[str, Any], sim: Any, player_ship: Any
) -> bool:
    """Check if a target has left sensor range (no longer tracked)."""
    target_id = params.get("target")

    sensors = player_ship.systems.get("sensors") if hasattr(player_ship, "systems") else None
    if not sensors or not hasattr(sensors, "get_contact"):
        # No sensors = effectively lost contact
        return True

    contact = sensors.get_contact(target_id)
    # Lost if no contact or confidence has dropped below useful threshold
    return contact is None or getattr(contact, "confidence", 0) < 0.1


def _eval_comms_choice(
    params: Dict[str, Any], context: Dict[str, Any]
) -> bool:
    """Check if a specific comms choice was made by the player."""
    choice_id = params.get("choice_id")
    expected_option = params.get("expected_option")

    choices_made = context.get("comms_choices", {})
    actual = choices_made.get(choice_id)
    return actual == expected_option


def _eval_objective_status(
    params: Dict[str, Any], context: Dict[str, Any]
) -> bool:
    """Check the status of another objective."""
    objective_id = params.get("objective_id")
    expected_status = params.get("status", "completed")

    statuses = context.get("objective_statuses", {})
    actual = statuses.get(objective_id)
    return actual == expected_status


def _eval_ship_destroyed(params: Dict[str, Any], sim: Any) -> bool:
    """Check if a ship has been removed from the simulation."""
    target_id = params.get("target")
    return target_id not in sim.ships


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _resolve_ship(target_id: str, sim: Any, player_ship: Any) -> Optional[Any]:
    """Resolve a target ID to a ship object.

    'player' resolves to the player ship; anything else looks up sim.ships.
    """
    if target_id == "player":
        return player_ship
    return sim.ships.get(target_id)


def _compare(value: float, comparison: str, threshold: float) -> bool:
    """Apply a comparison operator."""
    if comparison == "lt":
        return value < threshold
    elif comparison == "gt":
        return value > threshold
    elif comparison == "lte":
        return value <= threshold
    elif comparison == "gte":
        return value >= threshold
    elif comparison == "eq":
        return abs(value - threshold) < 1e-6
    return False
