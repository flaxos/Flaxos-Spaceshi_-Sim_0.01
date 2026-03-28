# hybrid/missions/comms_choices.py
"""Comms-based player choice system for mission branching.

When a mission branch triggers a comms choice, the player is
presented with a set of options (e.g., "Accept surrender",
"Demand cargo", "Open fire").  The player responds via the
comms station, and the choice feeds back into the branching
condition system.

This is NOT a dialogue tree.  Each choice has mechanical
consequences through existing game systems: a surrender might
change the target's AI behavior, demanding cargo might trigger
a new objective, opening fire might change faction relations.

The choice manager is a pure data container.  It does not execute
consequences directly -- those flow through the branching system
(branch points with comms_choice conditions) and the existing
command pipeline.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CommsChoiceOption:
    """A single selectable option within a comms choice.

    Attributes:
        option_id: Unique ID for this option.
        label: Short display text (e.g., "Accept surrender").
        description: Longer description of likely consequences.
    """

    def __init__(self, option_id: str, label: str, description: str = ""):
        self.option_id = option_id
        self.label = label
        self.description = description

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for client display."""
        return {
            "option_id": self.option_id,
            "label": self.label,
            "description": self.description,
        }


class CommsChoice:
    """A choice prompt presented to the player via the comms station.

    A choice is associated with a contact (who you are talking to)
    and has a prompt message plus multiple options.
    """

    def __init__(
        self,
        choice_id: str,
        contact_id: str,
        prompt: str,
        options: List[CommsChoiceOption],
        timeout: Optional[float] = None,
        default_option: Optional[str] = None,
    ):
        """Initialize a comms choice.

        Args:
            choice_id: Unique identifier for this choice.
            contact_id: Ship/contact ID this conversation is with.
            prompt: The incoming message / question from the contact.
            options: Available response options.
            timeout: Seconds before auto-selecting default (None = wait forever).
            default_option: Option ID selected if timeout expires.
        """
        self.choice_id = choice_id
        self.contact_id = contact_id
        self.prompt = prompt
        self.options = options
        self.timeout = timeout
        self.default_option = default_option
        # When the choice was presented (set by manager)
        self.presented_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for client display."""
        return {
            "choice_id": self.choice_id,
            "contact_id": self.contact_id,
            "prompt": self.prompt,
            "options": [o.to_dict() for o in self.options],
            "timeout": self.timeout,
            "default_option": self.default_option,
            "presented_at": self.presented_at,
        }

    def get_option(self, option_id: str) -> Optional[CommsChoiceOption]:
        """Look up an option by ID."""
        for opt in self.options:
            if opt.option_id == option_id:
                return opt
        return None


class CommsChoiceManager:
    """Manages the lifecycle of comms choices for a mission.

    Choices are defined in the mission YAML alongside branch points.
    When a branch activates and references a comms_choice_id, the
    manager presents it.  The player responds via the comms station
    command, and the response is recorded on the BranchingMission.

    The manager also handles timeouts: if a choice has a timeout and
    the player doesn't respond, the default option is auto-selected.
    """

    def __init__(self) -> None:
        """Initialize the choice manager."""
        # All defined choices: choice_id -> CommsChoice
        self.choices: Dict[str, CommsChoice] = {}
        # Currently active (presented, awaiting response)
        self.active_choices: Dict[str, CommsChoice] = {}
        # Completed choices: choice_id -> selected option_id
        self.resolved: Dict[str, str] = {}

    def register_choice(self, choice: CommsChoice) -> None:
        """Register a choice definition (from YAML parsing).

        Args:
            choice: The comms choice to register.
        """
        self.choices[choice.choice_id] = choice

    def present_choice(self, choice_id: str, sim_time: float) -> Optional[Dict]:
        """Activate a choice for player response.

        Args:
            choice_id: ID of the choice to present.
            sim_time: Current simulation time (for timeout tracking).

        Returns:
            Choice dict for client display, or None if choice ID unknown.
        """
        choice = self.choices.get(choice_id)
        if not choice:
            logger.warning(f"Unknown comms choice ID: {choice_id}")
            return None

        choice.presented_at = sim_time
        self.active_choices[choice_id] = choice
        logger.info(
            f"Comms choice presented: {choice_id} "
            f"({len(choice.options)} options)"
        )
        return choice.to_dict()

    def resolve_choice(self, choice_id: str, option_id: str) -> Optional[str]:
        """Record the player's response to a comms choice.

        Args:
            choice_id: The choice being responded to.
            option_id: The selected option.

        Returns:
            The option_id if valid, None if invalid choice/option.
        """
        choice = self.active_choices.get(choice_id)
        if not choice:
            logger.warning(f"Cannot resolve inactive choice: {choice_id}")
            return None

        if not choice.get_option(option_id):
            logger.warning(
                f"Invalid option '{option_id}' for choice '{choice_id}'"
            )
            return None

        self.resolved[choice_id] = option_id
        del self.active_choices[choice_id]
        logger.info(f"Comms choice resolved: {choice_id} -> {option_id}")
        return option_id

    def check_timeouts(self, sim_time: float) -> List[Dict[str, str]]:
        """Check for timed-out choices and auto-resolve them.

        Args:
            sim_time: Current simulation time.

        Returns:
            List of dicts with choice_id and auto-selected option_id.
        """
        auto_resolved = []
        expired_ids = []

        for choice_id, choice in self.active_choices.items():
            if choice.timeout is None or choice.presented_at is None:
                continue
            elapsed = sim_time - choice.presented_at
            if elapsed >= choice.timeout and choice.default_option:
                self.resolved[choice_id] = choice.default_option
                expired_ids.append(choice_id)
                auto_resolved.append({
                    "choice_id": choice_id,
                    "option_id": choice.default_option,
                    "reason": "timeout",
                })
                logger.info(
                    f"Comms choice timed out: {choice_id} -> "
                    f"{choice.default_option}"
                )

        for cid in expired_ids:
            del self.active_choices[cid]

        return auto_resolved

    def get_active_choices(self) -> List[Dict[str, Any]]:
        """Get all currently active choices for client display.

        Returns:
            List of choice dicts.
        """
        return [c.to_dict() for c in self.active_choices.values()]

    def get_state(self) -> Dict[str, Any]:
        """Get full manager state for telemetry.

        Returns:
            dict with active, resolved, and total counts.
        """
        return {
            "total_choices": len(self.choices),
            "active_choices": self.get_active_choices(),
            "resolved_choices": dict(self.resolved),
        }
