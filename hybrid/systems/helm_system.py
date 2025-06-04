# hybrid/systems/helm_system.py
"""Helm system implementation for ship simulation.
Combines manual control with integration to navigation and power systems."""

from hybrid.base_system import BaseSystem
import math
import logging

logger = logging.getLogger(__name__)

class HelmSystem(BaseSystem):
    """Manages manual control of ship thrust and orientation."""

    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}

        # Manual control
        self.manual_override = config.get("manual_override", False)
        self.control_mode = config.get("control_mode", "standard")  # standard, precise, rapid
        self.dampening = config.get("dampening", 0.8)

        # Integration with other systems
        self.power_draw = config.get("power_draw", 2.0)
        self.mode = config.get("mode", "autopilot")  # autopilot or manual
        self.manual_thrust = config.get("manual_thrust", {"x": 0.0, "y": 0.0, "z": 0.0})

        self.status = "standby"

    def tick(self, dt, ship, event_bus):
        """Update helm system state."""
        if not self.enabled:
            self.status = "offline"
            return

        # Power request
        power_system = ship.systems.get("power")
        if power_system and not power_system.request_power(self.power_draw * dt, "helm"):
            return

        if self.manual_override or self.mode == "manual":
            self.status = "manual_control"
            propulsion = ship.systems.get("propulsion")
            if propulsion and hasattr(propulsion, 'set_thrust'):
                propulsion.set_thrust(self.manual_thrust)
        else:
            self.status = "standby"

        # Subscribe to navigation events (idempotent)
        event_bus.subscribe("navigation_autopilot_engaged", self._handle_autopilot_engaged)
        event_bus.subscribe("navigation_autopilot_disengaged", self._handle_autopilot_disengaged)

    def command(self, action, params):
        """Process helm system commands."""
        if action == "helm_override":
            return self._cmd_helm_override(params)
        if action == "set_thrust":
            return self._cmd_set_thrust(params, params.get("_ship"))
        if action == "set_dampening":
            return self._cmd_set_dampening(params)
        if action == "set_mode":
            return self._cmd_set_mode(params)
        if action == "set_manual_thrust":
            return self.set_manual_thrust(params)
        if action == "status":
            return self.get_state()
        if action == "power_on":
            return self.power_on()
        if action == "power_off":
            return self.power_off()
        return super().command(action, params)

    # --- Commands from first implementation ---
    def _cmd_helm_override(self, params):
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        if "enabled" not in params:
            return {"error": "Missing 'enabled' parameter"}
        try:
            self.manual_override = bool(params["enabled"])
            ship = params.get("_ship")
            if self.manual_override and ship and "navigation" in ship.systems:
                nav_system = ship.systems["navigation"]
                if hasattr(nav_system, "command") and callable(nav_system.command):
                    nav_system.command("autopilot", {"enabled": False})
            return {"status": f"Manual helm control {'enabled' if self.manual_override else 'disabled'}"}
        except (ValueError, TypeError):
            return {"error": f"Invalid value for 'enabled': {params['enabled']}"}

    def _cmd_set_thrust(self, params, ship):
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        if not self.manual_override:
            return {"error": "Manual helm control not active"}
        if not ship:
            return {"error": "Ship reference required"}

        max_thrust = 100.0
        if "propulsion" in ship.systems and hasattr(ship.systems["propulsion"], "get_state"):
            prop_state = ship.systems["propulsion"].get_state()
            max_thrust = prop_state.get("max_thrust", 100.0)

        thrust = ship.thrust.copy()
        for axis in ["x", "y", "z"]:
            if axis in params:
                try:
                    value = float(params[axis])
                    if abs(value) > max_thrust:
                        value = math.copysign(max_thrust, value)
                    thrust[axis] = value
                except (ValueError, TypeError):
                    return {"error": f"Invalid thrust value for {axis}: {params[axis]}"}
        ship.thrust = thrust
        self.manual_thrust = thrust
        return {"status": "Thrust updated", "thrust": thrust}

    def _cmd_set_dampening(self, params):
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        if "value" not in params:
            return {"error": "Missing 'value' parameter"}
        try:
            value = float(params["value"])
            if 0 <= value <= 1:
                self.dampening = value
                return {"status": "Dampening set", "value": self.dampening}
            return {"error": "Dampening value must be between 0 and 1"}
        except (ValueError, TypeError):
            return {"error": f"Invalid dampening value: {params['value']}"}

    def _cmd_set_mode(self, params):
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        mode = params.get("mode")
        if mode in ["standard", "precise", "rapid"]:
            self.control_mode = mode
            return {"status": "Control mode set", "mode": self.control_mode}
        return {"error": f"Invalid mode: {mode}. Must be 'standard', 'precise', or 'rapid'"}

    # --- Commands from second implementation ---
    def set_mode(self, params):
        if "enabled" in params:
            manual_enabled = bool(params["enabled"])
            self.mode = "manual" if manual_enabled else "autopilot"
        elif "mode" in params and params["mode"] in ["manual", "autopilot"]:
            self.mode = params["mode"]
        else:
            return {"error": "Invalid or missing mode"}
        return {"status": f"Helm mode set to {self.mode}", "mode": self.mode}

    def set_manual_thrust(self, params):
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        for axis in ["x", "y", "z"]:
            if axis in params:
                self.manual_thrust[axis] = float(params[axis])
        return {"status": "Manual thrust updated", "thrust": self.manual_thrust}

    def _handle_autopilot_engaged(self, event):
        self.mode = "autopilot"
        logger.info("Autopilot engaged, helm switching to autopilot mode")

    def _handle_autopilot_disengaged(self, event):
        logger.info("Autopilot disengaged")

    def get_state(self):
        state = super().get_state()
        state.update({
            "status": self.status,
            "manual_override": self.manual_override,
            "control_mode": self.control_mode,
            "dampening": self.dampening,
            "mode": self.mode,
            "manual_thrust": self.manual_thrust,
        })
        return state
