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
    MISSION_KILL = "mission_kill"
    AVOID_MISSION_KILL = "avoid_mission_kill"
    SURVIVE_TIME = "survive_time"
    PROTECT_SHIP = "protect_ship"
    DOCK_WITH = "dock_with"
    MATCH_VELOCITY = "match_velocity"
    REACH_POSITION = "reach_position"
    SCAN_TARGET = "scan_target"
    AVOID_DETECTION = "avoid_detection"
    COLLECT_ITEM = "collect_item"
    ESCAPE_RANGE = "escape_range"
    AMMO_DEPLETED = "ammo_depleted"
    BOARD_AND_CAPTURE = "board_and_capture"
    PLAYER_MOBILITY_KILL = "player_mobility_kill"


# Guard objective types: these auto-complete when all non-guard required
# objectives succeed.  Guards exist to fail the mission early (ammo gone,
# player destroyed, target escaped) but should not block each other from
# auto-completing when the primary win conditions are met.
GUARD_TYPES = {
    ObjectiveType.ESCAPE_RANGE,
    ObjectiveType.AMMO_DEPLETED,
    ObjectiveType.PLAYER_MOBILITY_KILL,
    ObjectiveType.AVOID_MISSION_KILL,
}

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

    def _primary_objectives_complete(self, tracker) -> bool:
        """Check if all non-guard required objectives have completed.

        Guard objectives (escape_range, ammo_depleted, player_mobility_kill,
        avoid_mission_kill) should auto-complete when the primary win
        conditions are met, without blocking on each other.
        """
        if not tracker:
            return False
        primary = [
            obj for obj in tracker.objectives.values()
            if obj.required and obj.id != self.id and obj.type not in GUARD_TYPES
        ]
        return bool(primary) and all(
            obj.status == ObjectiveStatus.COMPLETED for obj in primary
        )

    def check(self, sim, player_ship, tracker=None) -> bool:
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
        elif self.type == ObjectiveType.MISSION_KILL:
            return self._check_mission_kill(sim, player_ship)
        elif self.type == ObjectiveType.AVOID_MISSION_KILL:
            return self._check_avoid_mission_kill(sim, player_ship, tracker)
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
        elif self.type == ObjectiveType.ESCAPE_RANGE:
            return self._check_escape_range(sim, player_ship, tracker)
        elif self.type == ObjectiveType.AMMO_DEPLETED:
            return self._check_ammo_depleted(sim, player_ship, tracker)
        elif self.type == ObjectiveType.BOARD_AND_CAPTURE:
            return self._check_board_and_capture(sim, player_ship)
        elif self.type == ObjectiveType.PLAYER_MOBILITY_KILL:
            return self._check_player_mobility_kill(sim, player_ship, tracker)

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

    def _check_mission_kill(self, sim, player_ship) -> bool:
        """Check if target has suffered a mission kill."""
        target_id = self.params.get("target")

        target_ship = sim.ships.get(target_id)
        if not target_ship:
            self.status = ObjectiveStatus.COMPLETED
            self.completion_time = sim.time
            self.progress = 1.0
            logger.info(f"Objective {self.id} completed: {target_id} removed from simulation")
            return True

        if hasattr(target_ship, "is_destroyed") and target_ship.is_destroyed():
            self.status = ObjectiveStatus.COMPLETED
            self.completion_time = sim.time
            self.progress = 1.0
            logger.info(f"Objective {self.id} completed: {target_id} destroyed")
            return True

        damage_model = getattr(target_ship, "damage_model", None)
        if damage_model:
            self.progress = max(
                0.0,
                max(
                    1.0 - damage_model.get_degradation_factor("propulsion"),
                    1.0 - damage_model.get_degradation_factor("rcs"),
                    1.0 - damage_model.get_degradation_factor("weapons"),
                ),
            )

            if damage_model.is_mission_kill():
                self.status = ObjectiveStatus.COMPLETED
                self.completion_time = sim.time
                self.progress = 1.0
                logger.info(f"Objective {self.id} completed: {target_id} mission kill")
                return True

        if hasattr(target_ship, "hull_integrity") and target_ship.hull_integrity <= 0:
            self.status = ObjectiveStatus.COMPLETED
            self.completion_time = sim.time
            self.progress = 1.0
            logger.info(f"Objective {self.id} completed: {target_id} hull destroyed")
            return True

        return False

    def _check_avoid_mission_kill(self, sim, player_ship, tracker) -> bool:
        """Check if target avoids mission kill until other objectives complete."""
        target_id = self.params.get("target")

        target_ship = sim.ships.get(target_id)
        if not target_ship:
            self.status = ObjectiveStatus.FAILED
            self.failure_reason = f"Target {target_id} not found"
            return False

        if hasattr(target_ship, "is_destroyed") and target_ship.is_destroyed():
            self.status = ObjectiveStatus.FAILED
            self.failure_reason = f"{target_id} destroyed"
            return False

        damage_model = getattr(target_ship, "damage_model", None)
        if damage_model and damage_model.is_mission_kill():
            self.status = ObjectiveStatus.FAILED
            self.failure_reason = f"{target_id} mission killed"
            return False

        if hasattr(target_ship, "hull_integrity") and target_ship.hull_integrity <= 0:
            self.status = ObjectiveStatus.FAILED
            self.failure_reason = f"{target_id} hull destroyed"
            return False

        if self._primary_objectives_complete(tracker):
            self.status = ObjectiveStatus.COMPLETED
            self.completion_time = sim.time
            self.progress = 1.0
            logger.info(f"Objective {self.id} completed: {target_id} survived mission")
            return True

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
        """Check if target has been detected by sensors (passive or active).

        Accepts any detection method — passive detection at range counts as
        'scanned' for mission objectives.  Active scans complete at any
        confidence; passive scans need confidence > 0.3 to filter out
        momentary noise detections.
        """
        target_id = self.params.get("target")

        # Check if target is in sensor contacts via ContactTracker
        sensors = player_ship.systems.get("sensors")
        if not sensors or not hasattr(sensors, "get_contact"):
            return False

        contact = sensors.get_contact(target_id)
        if contact and hasattr(contact, "detection_method"):
            # Active scans complete immediately (high-confidence ping)
            if contact.detection_method == "active" and contact.confidence > 0.5:
                self.status = ObjectiveStatus.COMPLETED
                self.completion_time = sim.time
                self.progress = 1.0
                logger.info(f"Objective {self.id} completed: Active scan of {target_id}")
                return True

            # Passive detection completes once confidence stabilises above noise floor.
            # At 427km / 500km range, accuracy is ~0.24-0.49 so 0.3 is reachable.
            if contact.detection_method == "passive" and contact.confidence > 0.3:
                self.status = ObjectiveStatus.COMPLETED
                self.completion_time = sim.time
                self.progress = 1.0
                logger.info(f"Objective {self.id} completed: Passive detection of {target_id}")
                return True

            # Update progress based on confidence
            self.progress = contact.confidence

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

    def _check_escape_range(self, sim, player_ship, tracker=None) -> bool:
        """Check if target has escaped beyond the threshold range.

        This is a guard objective: it fails if the target escapes beyond
        ``escape_range``, and auto-completes when all other required
        objectives are completed (meaning the player won before the
        target could escape).  Without the auto-complete logic, guard
        objectives block mission success because _evaluate_mission_status
        requires ALL required objectives to be COMPLETED.
        """
        target_id = self.params.get("target")
        escape_range = self.params.get("escape_range", 500000)  # 500km default

        target_ship = sim.ships.get(target_id)
        if not target_ship:
            return False

        from hybrid.utils.math_utils import calculate_distance
        current_range = calculate_distance(player_ship.position, target_ship.position)

        self.progress = min(1.0, current_range / escape_range)

        if current_range >= escape_range:
            self.status = ObjectiveStatus.FAILED
            self.failure_reason = f"{target_id} escaped (range {current_range:.0f}m)"
            logger.info(f"Objective {self.id} failed: {target_id} escaped at {current_range:.0f}m")
            return False

        # Auto-complete when all primary (non-guard) required objectives
        # succeed -- the player won before the target could escape.
        if self._primary_objectives_complete(tracker):
            self.status = ObjectiveStatus.COMPLETED
            self.completion_time = sim.time
            self.progress = 1.0
            logger.info(f"Objective {self.id} completed: target contained")
            return True

        return False

    def _check_ammo_depleted(self, sim, player_ship, tracker=None) -> bool:
        """Check if ship has run out of ammunition.

        Guard objective: fails when the target ship's combat system
        reports zero ammo remaining.  Auto-completes when all other
        required objectives succeed (player won with ammo to spare).
        """
        target_id = self.params.get("target")
        target_ship = sim.ships.get(target_id)
        if not target_ship:
            return False

        combat = target_ship.systems.get("combat")
        if not combat:
            return False

        total_ammo = 0
        # Truth weapons (railguns, PDCs) — current combat system
        if hasattr(combat, "truth_weapons"):
            for weapon in combat.truth_weapons.values():
                if hasattr(weapon, "ammo"):
                    total_ammo += weapon.ammo
        # Torpedoes and missiles are tracked separately on the combat system
        total_ammo += getattr(combat, "torpedoes_loaded", 0)
        total_ammo += getattr(combat, "missiles_loaded", 0)
        # Legacy weapons list (older combat system variant)
        if hasattr(combat, "weapons"):
            for weapon in combat.weapons:
                if hasattr(weapon, "ammo"):
                    total_ammo += weapon.ammo

        if total_ammo <= 0:
            self.status = ObjectiveStatus.FAILED
            self.failure_reason = f"{target_id} ammunition depleted"
            logger.info(f"Objective {self.id} failed: {target_id} out of ammo")
            return False

        # Auto-complete when all primary (non-guard) required objectives
        # succeed -- the player won with ammo remaining.
        if self._primary_objectives_complete(tracker):
            self.status = ObjectiveStatus.COMPLETED
            self.completion_time = sim.time
            self.progress = 1.0
            logger.info(f"Objective {self.id} completed: ammo conserved")
            return True

        return False

    def _check_board_and_capture(self, sim, player_ship) -> bool:
        """Check if target ship's faction changed to player's faction.

        A boarding action succeeds when the boarding system on the player
        ship drives progress to 1.0 and flips the target's faction.
        This objective simply reads the result of that faction change.

        The boarding system on the player's ship also exposes progress
        that we mirror into objective progress for the HUD.
        """
        target_id = self.params.get("target")

        target_ship = sim.ships.get(target_id)
        if not target_ship:
            self.status = ObjectiveStatus.FAILED
            self.failure_reason = f"Target {target_id} not found"
            return False

        # Mirror boarding progress from the player's boarding system (if active)
        boarding = player_ship.systems.get("boarding")
        if boarding and hasattr(boarding, "progress"):
            self.progress = boarding.progress

        # Capture complete when target faction matches player faction
        player_faction = getattr(player_ship, "faction", None)
        target_faction = getattr(target_ship, "faction", None)
        if player_faction and target_faction == player_faction:
            self.status = ObjectiveStatus.COMPLETED
            self.completion_time = sim.time
            self.progress = 1.0
            logger.info(
                "Objective %s completed: %s captured (faction=%s)",
                self.id, target_id, target_faction,
            )
            return True

        return False

    def _check_player_mobility_kill(self, sim, player_ship, tracker=None) -> bool:
        """Check if player ship has lost mobility (propulsion destroyed).

        Guard objective: fails when the player's damage model reports a
        mobility kill (drive + RCS destroyed).  Auto-completes when all
        other required objectives succeed -- the player won before losing
        propulsion.
        """
        if player_ship and hasattr(player_ship, 'damage_model'):
            damage_model = player_ship.damage_model
            if damage_model and damage_model.is_mobility_kill():
                self.status = ObjectiveStatus.FAILED
                self.failure_reason = "Ship propulsion destroyed — mission failed"
                logger.info(f"Objective {self.id} failed: player mobility kill")
                return False

        # Auto-complete when all primary (non-guard) required objectives
        # succeed -- the player won before losing propulsion.
        if self._primary_objectives_complete(tracker):
            self.status = ObjectiveStatus.COMPLETED
            self.completion_time = sim.time
            self.progress = 1.0
            logger.info(f"Objective {self.id} completed: player survived")
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

        # Check all objectives.  Guard objectives (escape_range,
        # ammo_depleted, player_mobility_kill) auto-complete when all
        # OTHER required objectives complete.  When multiple guards
        # coexist, each sees the others as in_progress on the first
        # pass, creating a circular dependency.  We iterate until no
        # objective changes state (convergence), capped at 5 passes to
        # prevent infinite loops from buggy objective logic.
        for _ in range(5):
            changed = False
            for obj in self.objectives.values():
                prev_status = obj.status
                obj.check(sim, player_ship, tracker=self)
                if obj.status != prev_status:
                    changed = True
            if not changed:
                break

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
