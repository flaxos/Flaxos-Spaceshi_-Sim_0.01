# hybrid/systems/engineering_system.py
"""Engineering station system: reactor output, drive management, radiators, fuel, emergency vent.

Engineering manages the physical plant that keeps everything running.
Reactor output determines the available power budget — higher output means
more heat that must be dissipated through radiators. Drive output determines
available thrust. Both generate heat that engineering must manage.

Commands:
    set_reactor_output: Adjust reactor power generation level (0-100%)
    throttle_drive: Set drive output percentage (cap on helm throttle)
    manage_radiators: Extend/retract radiator panels, set dissipation priority
    monitor_fuel: Track reaction mass remaining, burn rate, delta-v budget
    emergency_vent: Dump heat rapidly by venting coolant (one-time use)
"""

from __future__ import annotations

import logging
import math
from typing import Dict, Any, Optional

from hybrid.core.base_system import BaseSystem

logger = logging.getLogger(__name__)

# Earth gravity for delta-v calculation
G0 = 9.81  # m/s²

# Default engineering configuration
DEFAULT_ENGINEERING_CONFIG = {
    "reactor_output": 1.0,          # 0-1 fraction of max reactor output
    "reactor_min_output": 0.1,      # Minimum safe reactor output
    "drive_limit": 1.0,             # 0-1 cap on drive throttle
    "radiators_deployed": True,     # Whether radiator panels are extended
    "radiator_priority": "balanced",  # balanced | cooling | stealth
    "emergency_vent_available": True,  # One-time coolant vent
    "emergency_vent_capacity": 200000.0,  # Joules dumped by emergency vent
    "emergency_vent_duration": 5.0,  # Seconds for vent to complete
}


class EngineeringSystem(BaseSystem):
    """Manages reactor output, drive limits, radiators, fuel monitoring, and emergency venting.

    Ticked each frame to:
    1. Apply reactor output scaling to heat generation
    2. Enforce drive throttle limits
    3. Manage radiator deployment state
    4. Track emergency vent cooldown
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        super().__init__(config)

        # Reactor output: fraction of maximum power (0.0-1.0)
        self.reactor_output = float(config.get("reactor_output",
                                               DEFAULT_ENGINEERING_CONFIG["reactor_output"]))
        self.reactor_min_output = float(config.get("reactor_min_output",
                                                   DEFAULT_ENGINEERING_CONFIG["reactor_min_output"]))

        # Drive throttle limit: engineering can cap the maximum throttle
        self.drive_limit = float(config.get("drive_limit",
                                            DEFAULT_ENGINEERING_CONFIG["drive_limit"]))

        # Radiator state
        self.radiators_deployed = bool(config.get("radiators_deployed",
                                                  DEFAULT_ENGINEERING_CONFIG["radiators_deployed"]))
        self.radiator_priority = str(config.get("radiator_priority",
                                                DEFAULT_ENGINEERING_CONFIG["radiator_priority"]))

        # Emergency coolant vent (one-time use)
        self.emergency_vent_available = bool(config.get("emergency_vent_available",
                                                        DEFAULT_ENGINEERING_CONFIG["emergency_vent_available"]))
        self.emergency_vent_capacity = float(config.get("emergency_vent_capacity",
                                                        DEFAULT_ENGINEERING_CONFIG["emergency_vent_capacity"]))
        self.emergency_vent_duration = float(config.get("emergency_vent_duration",
                                                        DEFAULT_ENGINEERING_CONFIG["emergency_vent_duration"]))
        self._vent_active = False
        self._vent_remaining = 0.0  # seconds remaining in vent
        self._vent_rate = 0.0       # watts being vented this tick

        # Tracking
        self._fuel_burn_rate = 0.0   # kg/s estimated from last tick
        self._prev_fuel = None       # previous fuel level for burn rate calc

    def tick(self, dt: float, ship=None, event_bus=None):
        """Update engineering system each tick.

        Args:
            dt: Time step in seconds
            ship: Ship object
            event_bus: EventBus for publishing events
        """
        if not self.enabled or ship is None or dt <= 0:
            return

        # 1. Apply reactor output scaling to thermal system
        self._apply_reactor_output(ship)

        # 2. Enforce drive throttle limit
        self._enforce_drive_limit(ship)

        # 3. Apply radiator state
        self._apply_radiator_state(ship)

        # 4. Process emergency vent
        self._tick_emergency_vent(dt, ship, event_bus)

        # 5. Track fuel burn rate
        self._track_fuel(dt, ship)

    def _apply_reactor_output(self, ship):
        """Scale reactor heat output based on engineering-set output level.

        Higher reactor output = more available power but more waste heat.
        """
        thermal = ship.systems.get("thermal")
        if thermal and hasattr(thermal, "_reactor_output_scale"):
            thermal._reactor_output_scale = self.reactor_output

        # Store on thermal for its heat calculation to read
        if thermal:
            thermal._engineering_reactor_output = self.reactor_output

    def _enforce_drive_limit(self, ship):
        """Cap the propulsion throttle to the engineering-set limit."""
        propulsion = ship.systems.get("propulsion")
        if propulsion and hasattr(propulsion, "throttle"):
            if propulsion.throttle > self.drive_limit:
                propulsion.throttle = self.drive_limit

    def _apply_radiator_state(self, ship):
        """Apply radiator deployment state to thermal system."""
        thermal = ship.systems.get("thermal")
        if not thermal:
            return

        if not self.radiators_deployed:
            # Retracted radiators: only 10% effectiveness (hull radiation only)
            thermal._engineering_radiator_modifier = 0.1
        else:
            # Priority affects radiator performance
            if self.radiator_priority == "cooling":
                # Max cooling: radiators fully extended, angled for max area
                thermal._engineering_radiator_modifier = 1.2
            elif self.radiator_priority == "stealth":
                # Stealth: radiators at reduced angle to minimize IR signature
                thermal._engineering_radiator_modifier = 0.5
            else:
                # Balanced: normal operation
                thermal._engineering_radiator_modifier = 1.0

    def _tick_emergency_vent(self, dt: float, ship, event_bus=None):
        """Process emergency coolant vent if active."""
        if not self._vent_active:
            self._vent_rate = 0.0
            return

        self._vent_remaining -= dt
        if self._vent_remaining <= 0:
            self._vent_active = False
            self._vent_remaining = 0.0
            self._vent_rate = 0.0
            if event_bus:
                event_bus.publish("emergency_vent_complete", {
                    "ship_id": ship.id,
                    "message": "Emergency coolant vent complete",
                })
            logger.info(f"Ship {ship.id}: Emergency vent complete")
            return

        # Calculate vent rate (watts) for this tick
        vent_rate = self.emergency_vent_capacity / self.emergency_vent_duration
        self._vent_rate = vent_rate

        # Apply cooling directly to thermal system
        thermal = ship.systems.get("thermal")
        if thermal:
            # Reduce hull temperature directly
            energy_removed = vent_rate * dt
            if thermal.hull_heat_capacity > 0:
                temp_drop = energy_removed / thermal.hull_heat_capacity
                thermal.hull_temperature = max(2.7, thermal.hull_temperature - temp_drop)

    def _track_fuel(self, dt: float, ship):
        """Track fuel burn rate for monitoring."""
        propulsion = ship.systems.get("propulsion")
        if not propulsion or not hasattr(propulsion, "fuel_level"):
            return

        current_fuel = propulsion.fuel_level
        if self._prev_fuel is not None and dt > 0:
            self._fuel_burn_rate = max(0.0, (self._prev_fuel - current_fuel) / dt)
        self._prev_fuel = current_fuel

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def command(self, action: str, params: dict = None) -> dict:
        """Handle engineering system commands."""
        params = params or {}

        if action == "set_reactor_output":
            return self._cmd_set_reactor_output(params)
        elif action == "throttle_drive":
            return self._cmd_throttle_drive(params)
        elif action == "manage_radiators":
            return self._cmd_manage_radiators(params)
        elif action == "monitor_fuel":
            return self._cmd_monitor_fuel(params)
        elif action == "emergency_vent":
            return self._cmd_emergency_vent(params)

        return {"error": f"Unknown engineering command: {action}"}

    def _cmd_set_reactor_output(self, params: dict) -> dict:
        """Adjust reactor power generation level.

        Higher output = more power available = more heat generated.
        Lower output = less power = less heat but systems may brown out.

        Params:
            output (float): Reactor output as fraction (0.0-1.0) or percentage (0-100)
        """
        output = params.get("output")
        if output is None:
            return {"ok": False, "error": "Missing 'output' parameter (0-100 or 0.0-1.0)"}

        try:
            output_val = float(output)
        except (TypeError, ValueError):
            return {"ok": False, "error": f"Invalid output value: {output}"}

        # Accept percentage or fraction
        if output_val > 1.0:
            output_val = output_val / 100.0

        # Clamp to valid range
        output_val = max(self.reactor_min_output, min(1.0, output_val))

        old_output = self.reactor_output
        self.reactor_output = output_val

        event_bus = params.get("event_bus")
        ship = params.get("_ship") or params.get("ship")
        if event_bus and ship:
            event_bus.publish("reactor_output_changed", {
                "ship_id": ship.id,
                "old_output": round(old_output, 2),
                "new_output": round(output_val, 2),
                "message": f"Reactor output set to {output_val * 100:.0f}%",
            })

        return {
            "ok": True,
            "status": f"Reactor output set to {output_val * 100:.0f}%",
            "reactor_output": round(output_val, 3),
            "reactor_percent": round(output_val * 100, 1),
        }

    def _cmd_throttle_drive(self, params: dict) -> dict:
        """Set drive output percentage (cap on helm throttle).

        Engineering sets the maximum throttle the helm can use.
        This is a safety limit, not the current throttle setting.

        Params:
            limit (float): Drive limit as fraction (0.0-1.0) or percentage (0-100)
        """
        limit = params.get("limit")
        if limit is None:
            return {"ok": False, "error": "Missing 'limit' parameter (0-100 or 0.0-1.0)"}

        try:
            limit_val = float(limit)
        except (TypeError, ValueError):
            return {"ok": False, "error": f"Invalid limit value: {limit}"}

        # Accept percentage or fraction
        if limit_val > 1.0:
            limit_val = limit_val / 100.0

        limit_val = max(0.0, min(1.0, limit_val))
        old_limit = self.drive_limit
        self.drive_limit = limit_val

        event_bus = params.get("event_bus")
        ship = params.get("_ship") or params.get("ship")
        if event_bus and ship:
            event_bus.publish("drive_limit_changed", {
                "ship_id": ship.id,
                "old_limit": round(old_limit, 2),
                "new_limit": round(limit_val, 2),
                "message": f"Drive limit set to {limit_val * 100:.0f}%",
            })

        return {
            "ok": True,
            "status": f"Drive limit set to {limit_val * 100:.0f}%",
            "drive_limit": round(limit_val, 3),
            "drive_percent": round(limit_val * 100, 1),
        }

    def _cmd_manage_radiators(self, params: dict) -> dict:
        """Manage radiator panels: deploy/retract and set priority mode.

        Params:
            deployed (bool, optional): Deploy (true) or retract (false) radiators
            priority (str, optional): "balanced", "cooling", or "stealth"
        """
        deployed = params.get("deployed")
        priority = params.get("priority")

        if deployed is None and priority is None:
            return {
                "ok": False,
                "error": "Provide 'deployed' (bool) and/or 'priority' (balanced|cooling|stealth)",
            }

        if deployed is not None:
            if isinstance(deployed, str):
                deployed = deployed.lower() in ("true", "1", "yes", "on", "deploy", "extend")
            self.radiators_deployed = bool(deployed)

        if priority is not None:
            priority_str = str(priority).lower()
            valid_priorities = ("balanced", "cooling", "stealth")
            if priority_str not in valid_priorities:
                return {
                    "ok": False,
                    "error": f"Invalid priority '{priority}'. Must be: {', '.join(valid_priorities)}",
                }
            self.radiator_priority = priority_str

        event_bus = params.get("event_bus")
        ship = params.get("_ship") or params.get("ship")
        if event_bus and ship:
            event_bus.publish("radiator_state_changed", {
                "ship_id": ship.id,
                "deployed": self.radiators_deployed,
                "priority": self.radiator_priority,
            })

        return {
            "ok": True,
            "status": f"Radiators {'deployed' if self.radiators_deployed else 'retracted'}, "
                      f"priority: {self.radiator_priority}",
            "deployed": self.radiators_deployed,
            "priority": self.radiator_priority,
        }

    def _cmd_monitor_fuel(self, params: dict) -> dict:
        """Track reaction mass remaining, burn rate, and delta-v budget.

        Returns comprehensive fuel status including estimated time to empty.
        """
        ship = params.get("_ship") or params.get("ship")
        if not ship:
            return {"ok": False, "error": "Ship reference required"}

        propulsion = ship.systems.get("propulsion")
        if not propulsion:
            return {"ok": False, "error": "No propulsion system available"}

        fuel_level = getattr(propulsion, "fuel_level", 0.0)
        max_fuel = getattr(propulsion, "max_fuel", 0.0)
        fuel_percent = (fuel_level / max_fuel * 100) if max_fuel > 0 else 0.0

        # Calculate delta-v remaining
        delta_v = 0.0
        isp = getattr(propulsion, "isp", 3000.0)
        if hasattr(ship, "dry_mass") and ship.dry_mass > 0 and fuel_level > 0:
            # Tsiolkovsky: dv = Ve * ln(m_wet / m_dry)
            ve = isp * G0
            # wet mass = current total (dry + fuel + ammo), dry = everything minus fuel
            wet_mass = ship.mass
            dry_mass_estimate = ship.mass - fuel_level
            if dry_mass_estimate > 0:
                delta_v = ve * math.log(wet_mass / dry_mass_estimate)

        # Time to empty at current burn rate
        time_to_empty = None
        if self._fuel_burn_rate > 0.001:
            time_to_empty = fuel_level / self._fuel_burn_rate

        return {
            "ok": True,
            "fuel_level": round(fuel_level, 1),
            "max_fuel": round(max_fuel, 1),
            "fuel_percent": round(fuel_percent, 1),
            "burn_rate": round(self._fuel_burn_rate, 3),
            "delta_v_remaining": round(delta_v, 1),
            "isp": isp,
            "time_to_empty": round(time_to_empty, 0) if time_to_empty else None,
            "drive_limit": round(self.drive_limit, 3),
            "reactor_output": round(self.reactor_output, 3),
        }

    def _cmd_emergency_vent(self, params: dict) -> dict:
        """Dump heat rapidly by venting coolant (one-time use).

        This is a desperate measure — it rapidly cools the ship but
        the coolant is expended permanently.
        """
        if not self.emergency_vent_available:
            return {"ok": False, "error": "Emergency vent already used — coolant depleted"}

        if self._vent_active:
            return {"ok": False, "error": "Emergency vent already in progress"}

        self.emergency_vent_available = False
        self._vent_active = True
        self._vent_remaining = self.emergency_vent_duration

        event_bus = params.get("event_bus")
        ship = params.get("_ship") or params.get("ship")
        if event_bus and ship:
            event_bus.publish("emergency_vent_activated", {
                "ship_id": ship.id,
                "capacity": self.emergency_vent_capacity,
                "duration": self.emergency_vent_duration,
                "message": "EMERGENCY COOLANT VENT — dumping heat rapidly",
            })

        logger.warning("Emergency coolant vent activated")

        return {
            "ok": True,
            "status": "EMERGENCY COOLANT VENT ACTIVATED",
            "capacity": self.emergency_vent_capacity,
            "duration": self.emergency_vent_duration,
            "warning": "Coolant is non-recoverable — this is a one-time use",
        }

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Get engineering system state for telemetry."""
        return {
            "enabled": self.enabled,
            "status": "online",
            "reactor_output": round(self.reactor_output, 3),
            "reactor_percent": round(self.reactor_output * 100, 1),
            "reactor_min_output": self.reactor_min_output,
            "drive_limit": round(self.drive_limit, 3),
            "drive_limit_percent": round(self.drive_limit * 100, 1),
            "radiators_deployed": self.radiators_deployed,
            "radiator_priority": self.radiator_priority,
            "emergency_vent_available": self.emergency_vent_available,
            "emergency_vent_active": self._vent_active,
            "emergency_vent_remaining": round(self._vent_remaining, 1),
            "vent_rate": round(self._vent_rate, 0),
            "fuel_burn_rate": round(self._fuel_burn_rate, 3),
        }
