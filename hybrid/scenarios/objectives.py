# hybrid/scenarios/objectives.py
"""Objective tracking for missions."""

from enum import Enum
from typing import Dict, List, Optional, Callable
import logging
from hybrid.navigation.relative_motion import calculate_relative_motion
from hybrid.utils.math_utils import magnitude

logger = logging.getLogger(__name__)

class ObjectiveType(Enum):
    """Types of mission objectives."""
    REACH_RANGE = "reach_range"
    DESTROY_TARGET = "destroy_target"
    SURVIVE_TIME = "survive_time"
    PROTECT_SHIP = "protect_ship"
    DOCK_WITH = "dock_with"
    MATCH_VELOCITY = "match_velocity"
    REACH_POSITION = "reach_position"
    SCAN_TARGET = "scan_target"
    AVOID_DETECTION = "avoid_detection"
    COLLECT_ITEM = "collect_item"

class ObjectiveStatus(Enum):
    """Status of an objective."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class Objective:
    """Represents a single mission objective."""

    def __init__(self, obj_id: str, obj_type: ObjectiveType, description: str,
                 params: Dict, required: bool = True):
        """Initialize objective.

        Args:
            obj_id: Unique objective ID
            obj_type: Type of objective
            description: Human-readable description
            params: Parameters for objective (target, range, time, etc.)
            required: Whether objective is required for mission success
        """
        self.id = obj_id
        self.type = obj_type
        self.description = description
        self.params = params
        self.required = required
        self.status = ObjectiveStatus.PENDING
        self.progress = 0.0  # 0.0 to 1.0
        self.completion_time = None
        self.failure_reason = None

    def check(self, sim, player_ship) -> bool:
        """Check if objective is completed.

        Args:
            sim: Simulator object
            player_ship: Player's ship

        Returns:
            bool: True if objective completed this check
        """
        if self.status in [ObjectiveStatus.COMPLETED, ObjectiveStatus.FAILED]:
            return False

        self.status = ObjectiveStatus.IN_PROGRESS

        # Check based on objective type
        if self.type == ObjectiveType.REACH_RANGE:
            return self._check_reach_range(sim, player_ship)
        elif self.type == ObjectiveType.DESTROY_TARGET:
            return self._check_destroy_target(sim, player_ship)
        elif self.type == ObjectiveType.SURVIVE_TIME:
            return self._check_survive_time(sim, player_ship)
        elif self.type == ObjectiveType.PROTECT_SHIP:
            return self._check_protect_ship(sim, player_ship)
        elif self.type == ObjectiveType.DOCK_WITH:
            return self._check_dock_with(sim, player_ship)
        elif self.type == ObjectiveType.MATCH_VELOCITY:
            return self._check_match_velocity(sim, player_ship)
        elif self.type == ObjectiveType.REACH_POSITION:
            return self._check_reach_position(sim, player_ship)
        elif self.type == ObjectiveType.SCAN_TARGET:
            return self._check_scan_target(sim, player_ship)
        elif self.type == ObjectiveType.AVOID_DETECTION:
            return self._check_avoid_detection(sim, player_ship)

        return False

    def _check_reach_range(self, sim, player_ship) -> bool:
        """Check if within range of target."""
        target_id = self.params.get("target")
        required_range = self.params.get("range", 1000)

        # Find target ship
        target_ship = sim.ships.get(target_id)
        if not target_ship:
            self.status = ObjectiveStatus.FAILED
            self.failure_reason = f"Target {target_id} not found"
            return False

        # Calculate range
        from hybrid.utils.math_utils import calculate_distance
        current_range = calculate_distance(player_ship.position, target_ship.position)

        # Update progress
        max_range = self.params.get("initial_range", required_range * 100)
        self.progress = max(0, 1.0 - (current_range - required_range) / max_range)

        # Check completion
        if current_range <= required_range:
            self.status = ObjectiveStatus.COMPLETED
            self.completion_time = sim.time
            logger.info(f"Objective {self.id} completed: Within {current_range:.0f}m of {target_id}")
            return True

        return False

    def _check_destroy_target(self, sim, player_ship) -> bool:
        """Check if target is destroyed."""
        target_id = self.params.get("target")

        # Check if target still exists
        if target_id not in sim.ships:
            self.status = ObjectiveStatus.COMPLETED
            self.completion_time = sim.time
            self.progress = 1.0
            logger.info(f"Objective {self.id} completed: {target_id} destroyed")
            return True

        # Update progress based on target damage (if implemented)
        target_ship = sim.ships[target_id]
        if hasattr(target_ship, "hull_integrity"):
            self.progress = 1.0 - (target_ship.hull_integrity / target_ship.max_hull_integrity)

        return False

    def _check_survive_time(self, sim, player_ship) -> bool:
        """Check if survived for required time."""
        required_time = self.params.get("time", 60)
        start_time = self.params.get("start_time", 0)

        elapsed = sim.time - start_time
        self.progress = min(1.0, elapsed / required_time)

        if elapsed >= required_time:
            self.status = ObjectiveStatus.COMPLETED
            self.completion_time = sim.time
            logger.info(f"Objective {self.id} completed: Survived {elapsed:.0f}s")
            return True

        # Check if player is still alive
        if hasattr(player_ship, "hull_integrity") and player_ship.hull_integrity <= 0:
            self.status = ObjectiveStatus.FAILED
            self.failure_reason = "Ship destroyed"
            return False

        return False

    def _check_protect_ship(self, sim, player_ship) -> bool:
        """Check if protected ship is still alive."""
        target_id = self.params.get("target")
        required_time = self.params.get("time", 60)
        start_time = self.params.get("start_time", 0)

        # Check if target still exists
        if target_id not in sim.ships:
            self.status = ObjectiveStatus.FAILED
            self.failure_reason = f"{target_id} was destroyed"
            return False

        # Check if time requirement met
        elapsed = sim.time - start_time
        self.progress = min(1.0, elapsed / required_time)

        if elapsed >= required_time:
            self.status = ObjectiveStatus.COMPLETED
            self.completion_time = sim.time
            logger.info(f"Objective {self.id} completed: Protected {target_id} for {elapsed:.0f}s")
            return True

        return False

    def _check_dock_with(self, sim, player_ship) -> bool:
        """Check if docked with target."""
        target_id = self.params.get("target")

        # Check if player has docking system
        if hasattr(player_ship, "docked_to"):
            if player_ship.docked_to == target_id:
                self.status = ObjectiveStatus.COMPLETED
                self.completion_time = sim.time
                self.progress = 1.0
                logger.info(f"Objective {self.id} completed: Docked with {target_id}")
                return True

        # Update progress based on range and velocity match
        target_ship = sim.ships.get(target_id)
        if target_ship:
            rel_motion = calculate_relative_motion(player_ship, target_ship)
            range_progress = max(0, 1.0 - rel_motion["range"] / 10000)
            vel_progress = max(0, 1.0 - magnitude(rel_motion["relative_velocity_vector"]) / 100)
            self.progress = (range_progress + vel_progress) / 2.0

        return False

    def _check_match_velocity(self, sim, player_ship) -> bool:
        """Check if matched velocity with target."""
        target_id = self.params.get("target")
        tolerance = self.params.get("tolerance", 1.0)  # m/s
        duration = self.params.get("duration", 5.0)  # seconds to maintain match

        target_ship = sim.ships.get(target_id)
        if not target_ship:
            self.status = ObjectiveStatus.FAILED
            self.failure_reason = f"Target {target_id} not found"
            return False

        rel_motion = calculate_relative_motion(player_ship, target_ship)
        rel_vel_mag = magnitude(rel_motion["relative_velocity_vector"])

        # Update progress
        self.progress = max(0, 1.0 - rel_vel_mag / (tolerance * 10))

        # Check if matched
        if rel_vel_mag <= tolerance:
            # Track how long we've been matched
            if not hasattr(self, "_match_start_time"):
                self._match_start_time = sim.time

            matched_duration = sim.time - self._match_start_time

            if matched_duration >= duration:
                self.status = ObjectiveStatus.COMPLETED
                self.completion_time = sim.time
                logger.info(f"Objective {self.id} completed: Velocity matched for {matched_duration:.0f}s")
                return True
        else:
            # Reset match timer if we drift apart
            if hasattr(self, "_match_start_time"):
                delattr(self, "_match_start_time")

        return False

    def _check_reach_position(self, sim, player_ship) -> bool:
        """Check if reached target position."""
        target_pos = self.params.get("position", {"x": 0, "y": 0, "z": 0})
        tolerance = self.params.get("tolerance", 100)  # meters

        from hybrid.utils.math_utils import calculate_distance
        distance = calculate_distance(player_ship.position, target_pos)

        # Update progress
        max_distance = self.params.get("initial_distance", tolerance * 100)
        self.progress = max(0, 1.0 - (distance - tolerance) / max_distance)

        if distance <= tolerance:
            self.status = ObjectiveStatus.COMPLETED
            self.completion_time = sim.time
            logger.info(f"Objective {self.id} completed: Reached position")
            return True

        return False

    def _check_scan_target(self, sim, player_ship) -> bool:
        """Check if target has been scanned with active sensors."""
        target_id = self.params.get("target")

        # Check if target is in sensor contacts with high confidence
        sensors = player_ship.systems.get("sensors")
        if sensors:
            contact = sensors.get_contact(target_id)
            if contact and hasattr(contact, "detection_method"):
                if contact.detection_method == "active" and contact.confidence > 0.9:
                    self.status = ObjectiveStatus.COMPLETED
                    self.completion_time = sim.time
                    self.progress = 1.0
                    logger.info(f"Objective {self.id} completed: Scanned {target_id}")
                    return True

                # Update progress
                self.progress = contact.confidence if contact else 0.0

        return False

    def _check_avoid_detection(self, sim, player_ship) -> bool:
        """Check if avoided detection for required time."""
        required_time = self.params.get("time", 60)
        start_time = self.params.get("start_time", 0)
        detection_range = self.params.get("detection_range", 50000)  # 50km

        elapsed = sim.time - start_time
        self.progress = min(1.0, elapsed / required_time)

        # Check if detected by any enemy ship
        # This would require checking enemy sensor systems
        # For now, simple range-based check
        for ship_id, ship in sim.ships.items():
            if ship_id == player_ship.id:
                continue

            from hybrid.utils.math_utils import calculate_distance
            distance = calculate_distance(player_ship.position, ship.position)

            if distance < detection_range:
                # Check if we've been detected (simplified)
                sensors = ship.systems.get("sensors")
                if sensors and hasattr(sensors, "get_contact"):
                    contact = sensors.get_contact(player_ship.id)
                    if contact and contact.confidence > 0.5:
                        self.status = ObjectiveStatus.FAILED
                        self.failure_reason = f"Detected by {ship_id}"
                        return False

        # Survived without detection
        if elapsed >= required_time:
            self.status = ObjectiveStatus.COMPLETED
            self.completion_time = sim.time
            logger.info(f"Objective {self.id} completed: Avoided detection for {elapsed:.0f}s")
            return True

        return False

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "type": self.type.value,
            "description": self.description,
            "status": self.status.value,
            "progress": self.progress,
            "required": self.required,
            "completion_time": self.completion_time,
            "failure_reason": self.failure_reason
        }


class ObjectiveTracker:
    """Tracks mission objectives and evaluates win/loss conditions."""

    def __init__(self, objectives: List[Objective]):
        """Initialize objective tracker.

        Args:
            objectives: List of objectives to track
        """
        self.objectives = {obj.id: obj for obj in objectives}
        self.mission_status = "in_progress"  # in_progress, success, failure
        self.completion_time = None

    def update(self, sim, player_ship):
        """Update all objectives.

        Args:
            sim: Simulator object
            player_ship: Player's ship
        """
        if self.mission_status != "in_progress":
            return

        # Check all objectives
        for obj in self.objectives.values():
            obj.check(sim, player_ship)

        # Evaluate win/loss conditions
        self._evaluate_mission_status(sim)

    def _evaluate_mission_status(self, sim):
        """Evaluate overall mission status."""
        required_objectives = [obj for obj in self.objectives.values() if obj.required]

        # Check for failure
        failed_required = [obj for obj in required_objectives if obj.status == ObjectiveStatus.FAILED]
        if failed_required:
            self.mission_status = "failure"
            self.completion_time = sim.time
            logger.info(f"Mission FAILED: {failed_required[0].failure_reason}")
            return

        # Check for success
        completed_required = [obj for obj in required_objectives if obj.status == ObjectiveStatus.COMPLETED]
        if len(completed_required) == len(required_objectives):
            self.mission_status = "success"
            self.completion_time = sim.time
            logger.info(f"Mission SUCCESS at {sim.time:.0f}s")
            return

    def get_status(self) -> Dict:
        """Get mission status.

        Returns:
            dict: Status summary
        """
        objectives_status = {obj_id: obj.to_dict() for obj_id, obj in self.objectives.items()}

        completed = len([obj for obj in self.objectives.values() if obj.status == ObjectiveStatus.COMPLETED])
        total = len([obj for obj in self.objectives.values() if obj.required])

        return {
            "mission_status": self.mission_status,
            "completion_time": self.completion_time,
            "objectives": objectives_status,
            "progress": f"{completed}/{total}",
            "all_objectives_complete": completed == total
        }
