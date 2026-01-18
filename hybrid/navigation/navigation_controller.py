# hybrid/navigation/navigation_controller.py
"""Navigation controller managing manual vs autopilot control."""

import logging
from typing import Optional, Dict
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)

class NavigationController:
    """Manages navigation modes and autopilot programs."""

    def __init__(self, ship):
        """Initialize navigation controller.

        Args:
            ship: Ship object this controller manages
        """
        self.ship = ship
        self.mode = "manual"  # "manual", "manual_override", "autopilot"
        self.autopilot = None  # Current autopilot program instance
        self.manual_override_timeout = 5.0  # Seconds before autopilot resumes
        self.last_manual_input = 0.0
        self.autopilot_program_name = None
        self.target_id = None

    def set_manual_input(self, sim_time: float):
        """Record manual input from pilot.

        Args:
            sim_time: Current simulation time
        """
        self.last_manual_input = sim_time

        if self.mode == "autopilot":
            logger.info(f"Ship {self.ship.id}: Manual override engaged")
            self.mode = "manual_override"

    def engage_autopilot(self, program_name: str, target_id: Optional[str] = None, params: Dict = None) -> Dict:
        """Engage autopilot with specified program.

        Args:
            program_name: Name of autopilot program
            target_id: Target contact ID (if required)
            params: Additional parameters for autopilot

        Returns:
            dict: Success or error response
        """
        if params is None:
            params = {}

        # Import autopilot factory
        from hybrid.navigation.autopilot.factory import AutopilotFactory

        # Create autopilot instance
        try:
            self.autopilot = AutopilotFactory.create(
                program_name,
                self.ship,
                target_id,
                params
            )

            self.mode = "autopilot"
            self.autopilot_program_name = program_name
            self.target_id = target_id

            logger.info(f"Ship {self.ship.id}: Autopilot engaged - {program_name}")

            return success_dict(
                f"Autopilot engaged: {program_name}",
                program=program_name,
                target=target_id,
                mode=self.mode
            )

        except Exception as e:
            logger.error(f"Failed to engage autopilot {program_name}: {e}")
            return error_dict(
                "AUTOPILOT_ERROR",
                f"Failed to engage autopilot: {e}"
            )

    def disengage_autopilot(self) -> Dict:
        """Disengage autopilot and return to manual control.

        Returns:
            dict: Success response
        """
        if self.mode != "manual":
            logger.info(f"Ship {self.ship.id}: Autopilot disengaged")

        self.mode = "manual"
        self.autopilot = None
        self.autopilot_program_name = None

        return success_dict(
            "Autopilot disengaged",
            mode=self.mode
        )

    def update(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Update navigation controller and get thrust command.

        Args:
            dt: Time delta
            sim_time: Current simulation time

        Returns:
            dict: Thrust command {thrust, heading} or None for manual
        """
        # Manual mode - no autopilot control
        if self.mode == "manual":
            return None

        # Manual override - check timeout
        if self.mode == "manual_override":
            if sim_time - self.last_manual_input > self.manual_override_timeout:
                logger.info(f"Ship {self.ship.id}: Manual override timeout, resuming autopilot")
                self.mode = "autopilot"
            else:
                return None  # Still in manual override

        # Autopilot mode - execute program
        if self.autopilot:
            try:
                command = self.autopilot.compute(dt, sim_time)
                return command
            except Exception as e:
                logger.error(f"Autopilot error on {self.ship.id}: {e}", exc_info=True)
                # Disengage on error
                self.disengage_autopilot()
                return None

        return None

    def get_state(self) -> Dict:
        """Get current navigation state.

        Returns:
            dict: Navigation state
        """
        state = {
            "mode": self.mode,
            "autopilot_enabled": self.mode in ["autopilot", "manual_override"],
            "current_program": self.autopilot_program_name,
            "target_id": self.target_id
        }

        # Add autopilot state if active
        if self.autopilot and hasattr(self.autopilot, 'get_state'):
            state["autopilot_state"] = self.autopilot.get_state()

        # Add manual override info
        if self.mode == "manual_override":
            state["override_timeout_remaining"] = max(
                0,
                self.manual_override_timeout - (self.ship.sim_time - self.last_manual_input)
            ) if hasattr(self.ship, 'sim_time') else self.manual_override_timeout

        return state
