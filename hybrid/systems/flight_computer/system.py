# hybrid/systems/flight_computer/system.py
"""FlightComputer BaseSystem implementation.

Accepts high-level commands (navigate_to, intercept, orbit, evasive, etc.),
computes burn plans, engages the underlying autopilot via the navigation
system, and reports status each tick.
"""

import logging
from typing import Dict, Optional

from hybrid.core.base_system import BaseSystem
from hybrid.utils.errors import success_dict, error_dict
from hybrid.utils.math_utils import magnitude, subtract_vectors

from hybrid.systems.flight_computer.models import BurnPlan, FlightComputerStatus
from hybrid.systems.flight_computer.planning import (
    plan_goto, plan_intercept, plan_match, plan_orbit,
)

logger = logging.getLogger(__name__)


class FlightComputer(BaseSystem):
    """Unified flight computer that wraps the autopilot layer.

    Registered as ``ship.systems["flight_computer"]``.
    """

    def __init__(self, config: dict = None):
        """Initialise the flight computer.

        Args:
            config: Optional configuration dict.
        """
        super().__init__(config or {})

        self._command_name: str = ""
        self._burn_plan: Optional[BurnPlan] = None
        self._mode: str = "idle"  # "idle", "executing", "manual"
        self._initial_metric: float = 0.0
        self._command_params: dict = {}

    # ------------------------------------------------------------------
    # BaseSystem tick
    # ------------------------------------------------------------------

    def tick(self, dt: float, ship, event_bus) -> None:
        """Per-frame update.

        Args:
            dt: Simulation time step.
            ship: Owning ship.
            event_bus: Ship event bus.
        """
        if not self.enabled or self._mode != "executing":
            return

        nav = ship.systems.get("navigation")
        if nav is None or nav.controller is None:
            return

        ctrl = nav.controller

        if ctrl.mode == "manual" and self._mode == "executing":
            self._mode = "idle"
            self._command_name = ""
            self._burn_plan = None
            event_bus.publish("flight_computer_complete", {
                "ship_id": ship.id,
                "reason": "autopilot_disengaged",
            })
            return

        ap_state = ctrl.autopilot.get_state() if ctrl.autopilot else {}
        if ap_state.get("complete"):
            event_bus.publish("flight_computer_complete", {
                "ship_id": ship.id,
                "command": self._command_name,
            })
            self._mode = "idle"

    # ------------------------------------------------------------------
    # High-level manoeuvre commands
    # ------------------------------------------------------------------

    def navigate_to(self, ship, position: Dict[str, float],
                    params: dict = None) -> dict:
        """Fly to a position.  Wraps GoToPositionAutopilot."""
        params = dict(params or {})
        params.update({"x": position["x"], "y": position["y"], "z": position["z"]})

        plan = plan_goto(ship, position, params)
        if plan.confidence <= 0:
            return error_dict(
                "CANNOT_COMPLY",
                plan.warnings[0] if plan.warnings else "Cannot comply",
            )

        result = self._engage(ship, "goto_position", None, params)
        if not result.get("ok"):
            return result

        self._set_active("navigate_to", plan,
                         magnitude(subtract_vectors(position, ship.position)))
        result["burn_plan"] = plan.to_dict()
        return result

    def intercept(self, ship, target_id: str,
                  params: dict = None) -> dict:
        """Compute intercept course to a contact."""
        params = dict(params or {})
        plan = plan_intercept(ship, target_id, params)

        result = self._engage(ship, "intercept", target_id, params)
        if not result.get("ok"):
            return result

        self._set_active("intercept", plan,
                         plan.delta_v if plan.delta_v > 0 else 1.0)
        result["burn_plan"] = plan.to_dict()
        return result

    def match_velocity(self, ship, target_id: str) -> dict:
        """Match velocity with target."""
        plan = plan_match(ship, target_id)

        result = self._engage(ship, "match", target_id, {})
        if not result.get("ok"):
            return result

        self._set_active("match_velocity", plan,
                         plan.delta_v if plan.delta_v > 0 else 1.0)
        result["burn_plan"] = plan.to_dict()
        return result

    def hold_position(self, ship) -> dict:
        """Station-keeping at current position."""
        plan = BurnPlan(
            command="hold_position",
            delta_v=magnitude(ship.velocity),
            confidence=1.0,
            phases=["hold"],
        )
        result = self._engage(ship, "hold", None, {})
        if not result.get("ok"):
            return result

        self._set_active("hold_position", plan, 0.0)
        result["burn_plan"] = plan.to_dict()
        return result

    def orbit(self, ship, center: Dict[str, float], radius: float,
              params: dict = None) -> dict:
        """Maintain circular orbit around a point."""
        params = dict(params or {})
        params["center"] = center
        params["radius"] = radius

        plan = plan_orbit(ship, center, radius, params)
        result = self._engage(ship, "orbit", None, params)
        if not result.get("ok"):
            return result

        self._set_active("orbit", plan,
                         magnitude(subtract_vectors(center, ship.position)))
        result["burn_plan"] = plan.to_dict()
        return result

    def evasive(self, ship, params: dict = None) -> dict:
        """Begin evasive jink pattern."""
        params = dict(params or {})
        plan = BurnPlan(
            command="evasive",
            estimated_time=float(params.get("duration", 0)) or 0.0,
            confidence=1.0,
            phases=["evading"],
        )
        result = self._engage(ship, "evasive", None, params)
        if not result.get("ok"):
            return result

        self._set_active("evasive", plan, 0.0)
        result["burn_plan"] = plan.to_dict()
        return result

    def manual_override(self, ship) -> dict:
        """Disengage flight computer, pass-through to manual control."""
        nav = ship.systems.get("navigation")
        if nav and nav.controller:
            nav.controller.disengage_autopilot()

        self._mode = "manual"
        self._command_name = ""
        self._burn_plan = None
        return success_dict("Manual override engaged", mode="manual")

    def abort(self, ship) -> dict:
        """Emergency stop current program."""
        propulsion = ship.systems.get("propulsion")
        if propulsion and hasattr(propulsion, "emergency_stop"):
            propulsion.emergency_stop()

        nav = ship.systems.get("navigation")
        if nav and nav.controller:
            nav.controller.disengage_autopilot()

        self._mode = "idle"
        self._command_name = ""
        self._burn_plan = None
        return success_dict("Abort complete - all stop", mode="idle")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_flight_status(self, ship) -> FlightComputerStatus:
        """Build a status snapshot.

        Args:
            ship: Ship object.

        Returns:
            FlightComputerStatus dataclass.
        """
        status = FlightComputerStatus(
            mode=self._mode,
            command=self._command_name,
            burn_plan=self._burn_plan,
        )

        if self._mode != "executing":
            status.status_text = (
                "Manual control" if self._mode == "manual"
                else "Flight computer standing by"
            )
            return status

        nav = ship.systems.get("navigation")
        if nav and nav.controller and nav.controller.autopilot:
            ap_state = nav.controller.autopilot.get_state()
            status.phase = ap_state.get("phase", "")
            ap_status = ap_state.get("status", "")
            status.progress = self._compute_progress(ship, ap_state)

            if self._burn_plan and self._burn_plan.estimated_time > 0:
                status.eta = max(
                    0, self._burn_plan.estimated_time * (1.0 - status.progress)
                )

            status.status_text = _status_text(ap_status, status.phase)

        return status

    # ------------------------------------------------------------------
    # BaseSystem command interface
    # ------------------------------------------------------------------

    def command(self, action: str, params: dict) -> dict:
        """Handle flight computer commands.

        Args:
            action: Command action name.
            params: Command parameters (must include '_ship' or 'ship').

        Returns:
            dict: Result.
        """
        ship = params.get("_ship") or params.get("ship")
        if ship is None:
            return error_dict("NO_SHIP", "Ship reference required")

        dispatch = {
            "navigate_to": lambda: self.navigate_to(ship, {
                "x": float(params.get("x", 0)),
                "y": float(params.get("y", 0)),
                "z": float(params.get("z", 0)),
            }, params),
            "intercept": lambda: self._cmd_with_target(
                self.intercept, ship, params),
            "match_velocity": lambda: self._cmd_with_target(
                self.match_velocity, ship, params),
            "hold_position": lambda: self.hold_position(ship),
            "orbit": lambda: self.orbit(
                ship,
                params.get("center") or {
                    "x": float(params.get("center_x", 0)),
                    "y": float(params.get("center_y", 0)),
                    "z": float(params.get("center_z", 0)),
                },
                float(params.get("radius", 1000)),
                params,
            ),
            "evasive": lambda: self.evasive(ship, params),
            "manual": lambda: self.manual_override(ship),
            "abort": lambda: self.abort(ship),
            "status": lambda: self.get_flight_status(ship).to_dict(),
        }

        handler = dispatch.get(action)
        if handler is None:
            return error_dict(
                "UNKNOWN_ACTION",
                f"Unknown flight_computer action: {action}",
            )
        return handler()

    # ------------------------------------------------------------------
    # State reporting
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Get system state for telemetry."""
        state = super().get_state()
        state.update({
            "mode": self._mode,
            "command": self._command_name,
            "burn_plan": self._burn_plan.to_dict() if self._burn_plan else None,
        })
        return state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_active(self, name: str, plan: BurnPlan, metric: float) -> None:
        """Record that a command is now executing."""
        self._command_name = name
        self._burn_plan = plan
        self._mode = "executing"
        self._initial_metric = metric

    def _engage(self, ship, program: str, target_id, params: dict) -> dict:
        """Engage an autopilot program via the navigation system."""
        nav = ship.systems.get("navigation")
        if nav is None:
            return error_dict("NO_NAV", "Navigation system not available")
        return nav.set_autopilot({
            "program": program,
            "target": target_id,
            **params,
        })

    def _compute_progress(self, ship, ap_state: dict) -> float:
        """Estimate 0-1 progress toward command completion."""
        if self._initial_metric <= 0:
            return 0.0

        if self._command_name in ("navigate_to", "orbit"):
            dest = ap_state.get("destination") or ap_state.get("center")
            if dest:
                remaining = magnitude(subtract_vectors(dest, ship.position))
                return max(0.0, min(1.0, 1.0 - remaining / self._initial_metric))

        if self._command_name in ("intercept", "match_velocity"):
            rel_vel = ap_state.get("relative_velocity")
            if rel_vel is not None:
                return max(0.0, min(1.0, 1.0 - rel_vel / self._initial_metric))

        if ap_state.get("complete"):
            return 1.0
        return 0.0

    @staticmethod
    def _cmd_with_target(method, ship, params):
        """Helper for commands that require a target parameter."""
        target = params.get("target")
        if not target:
            return error_dict("MISSING_TARGET", "Target ID required")
        # match_velocity takes 2 args, intercept takes 3
        import inspect
        sig = inspect.signature(method)
        if len(sig.parameters) > 2:
            return method(ship, target, params)
        return method(ship, target)


def _status_text(ap_status: str, phase: str) -> str:
    """Generate human-readable status text."""
    text_map = {
        "accelerating": "Accelerating to target",
        "coasting": "Coasting - on course",
        "braking": "Braking for arrival",
        "holding": "On station",
        "correcting": "Correcting drift",
        "intercepting": "Intercept burn active",
        "approaching": "Closing on target",
        "matching": "Matching velocity",
        "matched": "Velocity matched",
        "circularizing": "Circularising orbit",
        "orbiting": "In orbit - steady state",
        "evading": "Evasive maneuvers active",
        "complete": "Maneuver complete",
    }
    return text_map.get(ap_status, f"{ap_status or phase or 'Processing'}")
