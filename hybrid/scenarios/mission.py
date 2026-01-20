# hybrid/scenarios/mission.py
"""Mission definition and management."""

from typing import Dict, List, Optional
from hybrid.scenarios.objectives import ObjectiveTracker, Objective

class Mission:
    """Represents a complete mission with objectives and metadata."""

    def __init__(self, name: str, description: str, objectives: List[Objective],
                 briefing: str = "", success_message: str = "", failure_message: str = "",
                 hints: List[Dict] = None, time_limit: Optional[float] = None):
        """Initialize mission.

        Args:
            name: Mission name
            description: Short description
            objectives: List of objectives
            briefing: Pre-mission briefing text
            success_message: Message shown on success
            failure_message: Message shown on failure
            hints: List of hint dicts with trigger and message
            time_limit: Optional time limit in seconds
        """
        self.name = name
        self.description = description
        self.briefing = briefing
        self.success_message = success_message or "Mission accomplished!"
        self.failure_message = failure_message or "Mission failed."
        self.hints = hints or []
        self.time_limit = time_limit

        self.tracker = ObjectiveTracker(objectives)
        self.start_time = None
        self.shown_hints = set()
        self.hint_queue = []  # Queue of hints to be displayed to player

    def start(self, sim_time: float):
        """Start the mission.

        Args:
            sim_time: Current simulation time
        """
        self.start_time = sim_time

        # Set start_time on time-based objectives
        for obj in self.tracker.objectives.values():
            if "start_time" in obj.params:
                obj.params["start_time"] = sim_time

    def update(self, sim, player_ship):
        """Update mission state.

        Args:
            sim: Simulator object
            player_ship: Player's ship
        """
        # Check time limit
        if self.time_limit and self.start_time:
            elapsed = sim.time - self.start_time
            if elapsed > self.time_limit and self.tracker.mission_status == "in_progress":
                self.tracker.mission_status = "failure"
                self.tracker.completion_time = sim.time

        # Update objectives
        self.tracker.update(sim, player_ship)

        # Check for triggered hints
        self._check_hints(sim, player_ship)

    def _check_hints(self, sim, player_ship):
        """Check if any hints should be shown.

        Args:
            sim: Simulator object
            player_ship: Player's ship
        """
        for hint in self.hints:
            hint_id = hint.get("id", hint.get("trigger"))
            if hint_id in self.shown_hints:
                continue

            trigger = hint.get("trigger")
            message = hint.get("message")

            # Check trigger conditions
            triggered = False

            if trigger == "start":
                triggered = True
            elif trigger.startswith("range <"):
                # Extract range value
                try:
                    target_range = float(trigger.split("<")[1].strip())
                    target_id = hint.get("target")
                    if target_id and target_id in sim.ships:
                        from hybrid.utils.math_utils import calculate_distance
                        distance = calculate_distance(player_ship.position, sim.ships[target_id].position)
                        if distance < target_range:
                            triggered = True
                except (KeyError, AttributeError, ValueError, TypeError, IndexError):
                    pass
            elif trigger.startswith("time >"):
                # Time-based trigger
                try:
                    trigger_time = float(trigger.split(">")[1].strip())
                    if self.start_time and (sim.time - self.start_time) > trigger_time:
                        triggered = True
                except (ValueError, IndexError, AttributeError):
                    pass

            if triggered:
                self.shown_hints.add(hint_id)
                # Add hint to queue for retrieval
                hint_data = {
                    "id": hint_id,
                    "message": message,
                    "time": sim.time,
                    "trigger": trigger
                }
                self.hint_queue.append(hint_data)

                # Publish hint event to player ship's event bus
                if player_ship and hasattr(player_ship, "event_bus"):
                    player_ship.event_bus.publish("hint", {
                        "type": "hint",
                        "ship_id": player_ship.id,
                        "hint_id": hint_id,
                        "message": message,
                        "sim_time": sim.time,
                        "trigger": trigger
                    })

                # Also log to console for debugging
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Mission hint triggered: {message}")

    def get_status(self) -> Dict:
        """Get mission status.

        Returns:
            dict: Mission status
        """
        status = self.tracker.get_status()
        status.update({
            "name": self.name,
            "description": self.description,
            "start_time": self.start_time,
            "time_limit": self.time_limit
        })

        if self.start_time:
            # Add time remaining if there's a limit
            if self.time_limit:
                import time
                current_time = time.time()  # This should use sim.time
                elapsed = current_time - self.start_time if self.start_time else 0
                status["time_remaining"] = max(0, self.time_limit - elapsed)

        return status

    def is_complete(self) -> bool:
        """Check if mission is complete (success or failure).

        Returns:
            bool: True if mission is complete
        """
        return self.tracker.mission_status in ["success", "failure"]

    def is_success(self) -> bool:
        """Check if mission succeeded.

        Returns:
            bool: True if mission succeeded
        """
        return self.tracker.mission_status == "success"

    def get_result_message(self) -> str:
        """Get result message for mission completion.

        Returns:
            str: Success or failure message
        """
        if self.is_success():
            return self.success_message
        else:
            return self.failure_message

    def get_hints(self, clear: bool = False) -> List[Dict]:
        """Get all hints that have been triggered.

        Args:
            clear: If True, clear the hint queue after retrieving

        Returns:
            List of hint dictionaries with id, message, time, trigger
        """
        hints = self.hint_queue.copy()
        if clear:
            self.hint_queue.clear()
        return hints

    def get_pending_hints(self) -> List[Dict]:
        """Get hints that haven't been shown yet.

        This is useful for UI integration - call this to get new hints,
        then they can be displayed and cleared.

        Returns:
            List of hint dictionaries
        """
        return self.hint_queue.copy()

    def clear_hint_queue(self):
        """Clear all hints from the queue.

        Call this after hints have been displayed to the user.
        """
        self.hint_queue.clear()
