# hybrid/systems/navigation/navigation.py
"""Enhanced navigation system with autopilot support."""

import logging
from hybrid.core.event_bus import EventBus
from hybrid.core.base_system import BaseSystem
from hybrid.navigation.navigation_controller import NavigationController
from hybrid.navigation.plan import FlightPlan
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
        self._last_autopilot_mode = None
        self._last_autopilot_program = None
        self._last_autopilot_phase = None
        self._last_course_phase = None
        self._course_completed = False

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

        self._publish_autopilot_events(ship, event_bus)
        self._publish_course_events(ship, event_bus)

    def _publish_autopilot_events(self, ship, event_bus):
        if not self.controller:
            return

        state = self.controller.get_state()
        current_mode = state.get("mode")
        current_program = state.get("current_program")
        autopilot_state = state.get("autopilot_state", {})
        current_phase = autopilot_state.get("phase")

        if current_program and current_program != self._last_autopilot_program:
            event_bus.publish("autopilot_engaged", {
                "ship_id": ship.id,
                "program": current_program,
                "target": state.get("target_id"),
                "mode": current_mode,
            })

        if self._last_autopilot_program and current_mode == "manual" and self._last_autopilot_mode != "manual":
            event_bus.publish("autopilot_complete", {
                "ship_id": ship.id,
                "program": self._last_autopilot_program,
                "mode": current_mode,
            })

        if current_phase and current_phase != self._last_autopilot_phase:
            event_bus.publish("autopilot_phase_change", {
                "ship_id": ship.id,
                "program": current_program,
                "phase": current_phase,
                "status": autopilot_state.get("status"),
            })

        self._last_autopilot_mode = current_mode
        self._last_autopilot_program = current_program
        self._last_autopilot_phase = current_phase

    def _publish_course_events(self, ship, event_bus):
        if not self.controller:
            return

        if self.controller.autopilot_program_name not in {"goto_position", "set_course", "course", "go_to_position"}:
            self._last_course_phase = None
            self._course_completed = False
            return

        state = self.controller.get_state()
        autopilot_state = state.get("autopilot_state", {})
        current_phase = autopilot_state.get("phase")

        if current_phase and current_phase != self._last_course_phase:
            event_bus.publish("course_phase_change", {
                "ship_id": ship.id,
                "phase": current_phase,
                "status": autopilot_state.get("status"),
                "destination": autopilot_state.get("destination"),
            })

        if autopilot_state.get("complete") and not self._course_completed:
            event_bus.publish("course_complete", {
                "ship_id": ship.id,
                "destination": autopilot_state.get("destination"),
                "distance": autopilot_state.get("distance"),
            })
            self._course_completed = True
        elif not autopilot_state.get("complete"):
            self._course_completed = False

        self._last_course_phase = current_phase

    def _apply_autopilot_command(self, ship, command: dict):
        """Apply autopilot command to ship.

        Expanse-style: uses scalar throttle for propulsion and RCS for attitude.
        Navigation directs helm - autopilot commands go through helm system.
        
        Args:
            ship: Ship object
            command: Command dict with thrust (0..1 scalar) and heading (attitude target)
        """
        thrust_value = command.get("thrust", 0.0)
        heading = command.get("heading")

        # Apply throttle to propulsion (scalar main drive)
        # Route through helm system for consistency, but helm allows autopilot control
        propulsion = ship.systems.get("propulsion")
        if propulsion and hasattr(propulsion, "set_throttle"):
            # thrust_value is 0..1 scalar
            propulsion.set_throttle({"thrust": thrust_value, "_ship": ship, "ship": ship})

        # Apply heading via RCS through helm (attitude target, not instant teleport)
        if heading:
            helm = ship.systems.get("helm")
            if helm and hasattr(helm, "_cmd_set_orientation_target"):
                # Use helm's orientation target command
                helm._cmd_set_orientation_target({
                    "pitch": heading.get("pitch", ship.orientation.get("pitch", 0)),
                    "yaw": heading.get("yaw", ship.orientation.get("yaw", 0)),
                    "roll": heading.get("roll", ship.orientation.get("roll", 0)),
                    "_ship": ship,
                    "ship": ship
                })
            else:
                # Fallback: direct RCS control
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
        elif action == "set_plan":
            return self._cmd_set_plan(params)
        elif action == "status":
            return self.get_state()

        return super().command(action, params)

    def set_autopilot(self, params: dict):
        """Compatibility wrapper for setting autopilot program."""
        return self.command("set_autopilot", params)

    def set_course(self, params: dict):
        """Compatibility wrapper for setting a navigation course."""
        return self.command("set_course", params)

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
            result = self.controller.disengage_autopilot()
            event_bus = params.get("event_bus")
            ship = params.get("ship")
            if event_bus and ship:
                event_bus.publish("autopilot_complete", {
                    "ship_id": ship.id,
                    "program": self._last_autopilot_program,
                    "mode": "manual",
                })
            return result

        result = self.controller.engage_autopilot(program, target, params)
        event_bus = params.get("event_bus")
        ship = params.get("ship")
        if event_bus and ship and not result.get("error"):
            event_bus.publish("autopilot_engaged", {
                "ship_id": ship.id,
                "program": program,
                "target": target,
                "mode": self.controller.mode,
            })
        return result

    def _cmd_set_course(self, params: dict):
        """Set navigation course to a fixed position.

        Args:
            params: Course parameters

        Returns:
            dict: Result
        """
        try:
            x = float(params.get("x"))
            y = float(params.get("y"))
            z = float(params.get("z"))
        except (TypeError, ValueError):
            return error_dict("INVALID_COORDINATES", "Course requires numeric x, y, z values")

        stop_value = params.get("stop", True)
        if isinstance(stop_value, str):
            stop = stop_value.strip().lower() in {"1", "true", "yes", "on"}
        else:
            stop = bool(stop_value)

        try:
            tolerance = float(params.get("tolerance", 50.0))
        except (TypeError, ValueError):
            return error_dict("INVALID_TOLERANCE", "Tolerance must be a number")

        def _parse_optional_float(value, label):
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                raise ValueError(f"{label} must be a number")

        try:
            max_thrust = _parse_optional_float(params.get("max_thrust"), "Max thrust")
            coast_speed = _parse_optional_float(params.get("coast_speed"), "Coast speed")
            max_speed = _parse_optional_float(params.get("max_speed"), "Max speed")
            brake_buffer = _parse_optional_float(params.get("brake_buffer"), "Brake buffer")
        except ValueError as exc:
            return error_dict("INVALID_COURSE_PARAM", str(exc))

        autopilot_params = {
            "x": x,
            "y": y,
            "z": z,
            "stop": stop,
            "tolerance": tolerance,
        }
        if max_thrust is not None:
            autopilot_params["max_thrust"] = max_thrust
        if coast_speed is not None:
            autopilot_params["coast_speed"] = coast_speed
        if max_speed is not None:
            autopilot_params["max_speed"] = max_speed
        if brake_buffer is not None:
            autopilot_params["brake_buffer"] = brake_buffer

        result = self.controller.engage_autopilot("goto_position", None, autopilot_params)
        if result.get("error"):
            return result

        event_bus = params.get("event_bus")
        ship = params.get("ship")
        if event_bus and ship:
            event_bus.publish("course_set", {
                "ship_id": ship.id,
                "destination": {"x": x, "y": y, "z": z},
                "stop": stop,
                "tolerance": tolerance,
            })

        self._last_course_phase = None
        self._course_completed = False

        return success_dict(
            "Course set",
            destination={"x": x, "y": y, "z": z},
            stop=stop,
            tolerance=tolerance,
        )

    def _cmd_set_plan(self, params: dict):
        """Set a queued flight plan.

        Args:
            params: Plan payload or wrapper with "plan" key

        Returns:
            dict: Result
        """
        plan_payload = params.get("plan") if isinstance(params, dict) else None
        if plan_payload is None:
            plan_payload = params

        try:
            plan = FlightPlan.from_dict(plan_payload)
        except ValueError as exc:
            return error_dict("INVALID_PLAN", str(exc))

        return self.controller.set_flight_plan(plan)

    def get_state(self) -> dict:
        """Get navigation system state.

        Returns:
            dict: Current state
        """
        state = super().get_state()

        if self.controller:
            state.update(self.controller.get_state())
            # Add navigation assistance data (makes manual control easier)
            if hasattr(self.controller, "get_nav_assistance"):
                state["nav_assistance"] = self.controller.get_nav_assistance()
        else:
            state["mode"] = "manual"
            state["autopilot_enabled"] = False

        return state
