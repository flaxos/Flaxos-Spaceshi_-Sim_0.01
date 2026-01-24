# hybrid/systems/navigation/navigation.py
"""Enhanced navigation system with autopilot support."""

import logging
from hybrid.core.event_bus import EventBus
from hybrid.core.base_system import BaseSystem
from hybrid.navigation.navigation_controller import NavigationController
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)

class NavigationSystem(BaseSystem):
    """Navigation system with autopilot and manual control modes."""

    def __init__(self, config: dict):
        """Initialize navigation system.

        Args:
            config: Configuration dict with navigation parameters
        """
        super().__init__(config)
        self.config = config

        # Navigation controller (initialized during first tick with ship reference)
        self.controller = None

        # Simulation time tracking
        self.sim_time = 0.0

    def tick(self, dt: float, ship, event_bus):
        """Update navigation system and apply autopilot if active.

        Args:
            dt: Delta time for this simulation step
            ship: Ship owning this system
            event_bus: Event bus for publishing events
        """
        if not self.enabled:
            return

        # Initialize controller on first tick
        if self.controller is None:
            self.controller = NavigationController(ship)
            logger.info(f"Navigation controller initialized for ship {ship.id}")

        # Update simulation time
        self.sim_time += dt

        # Store sim_time on ship for autopilot access
        ship.sim_time = self.sim_time

        # Get autopilot command
        autopilot_command = self.controller.update(dt, self.sim_time)

        # Apply autopilot command if active
        if autopilot_command:
            self._apply_autopilot_command(ship, autopilot_command)

        # Publish navigation tick event
        event_bus.publish("navigation_tick", {
            "dt": dt,
            "ship_id": ship.id,
            "mode": self.controller.mode,
            "autopilot": self.controller.autopilot_program_name
        })

    def _apply_autopilot_command(self, ship, command: dict):
        """Apply autopilot command to ship.

        Expanse-style: uses scalar throttle for propulsion and RCS for attitude.
        
        Args:
            ship: Ship object
            command: Command dict with thrust (0..1 scalar) and heading (attitude target)
        """
        thrust_value = command.get("thrust", 0.0)
        heading = command.get("heading")

        # Apply throttle to propulsion (scalar main drive)
        propulsion = ship.systems.get("propulsion")
        if propulsion and hasattr(propulsion, "set_throttle"):
            # thrust_value is 0..1 scalar
            propulsion.set_throttle({"thrust": thrust_value})

        # Apply heading via RCS (attitude target, not instant teleport)
        if heading:
            rcs = ship.systems.get("rcs")
            if rcs and hasattr(rcs, "set_attitude_target"):
                rcs.set_attitude_target({
                    "pitch": heading.get("pitch", ship.orientation.get("pitch", 0)),
                    "yaw": heading.get("yaw", ship.orientation.get("yaw", 0)),
                    "roll": heading.get("roll", ship.orientation.get("roll", 0))
                })

    def command(self, action: str, params: dict):
        """Handle navigation commands.

        Args:
            action: Command action
            params: Command parameters

        Returns:
            dict: Command result
        """
        if not self.controller:
            return error_dict("NOT_INITIALIZED", "Navigation system not initialized")

        if action == "set_autopilot":
            return self._cmd_set_autopilot(params)
        elif action == "disengage_autopilot":
            return self.controller.disengage_autopilot()
        elif action == "set_course":
            return self._cmd_set_course(params)
        elif action == "status":
            return self.get_state()

        return super().command(action, params)

    def _cmd_set_autopilot(self, params: dict):
        """Set autopilot program.

        Args:
            params: Parameters with:
                - program: Autopilot program name
                - target: Target contact ID (optional)

        Returns:
            dict: Result
        """
        program = params.get("program")
        target = params.get("target")

        if not program:
            return error_dict("MISSING_PROGRAM", "Autopilot program not specified")

        # Handle "off" special case
        if program.lower() == "off":
            return self.controller.disengage_autopilot()

        return self.controller.engage_autopilot(program, target, params)

    def _cmd_set_course(self, params: dict):
        """Set navigation course (not yet implemented).

        Args:
            params: Course parameters

        Returns:
            dict: Result
        """
        return error_dict("NOT_IMPLEMENTED", "Course setting not yet implemented")

    def get_state(self) -> dict:
        """Get navigation system state.

        Returns:
            dict: Current state
        """
        state = super().get_state()

        if self.controller:
            state.update(self.controller.get_state())
        else:
            state["mode"] = "manual"
            state["autopilot_enabled"] = False

        return state
