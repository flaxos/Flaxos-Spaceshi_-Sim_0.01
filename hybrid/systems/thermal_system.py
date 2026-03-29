# hybrid/systems/thermal_system.py
"""Ship-wide thermal management system.

Heat is a physical quantity in joules. Every active system generates heat:
reactor (continuous), drive (proportional to thrust), weapons (per firing),
sensors (active radar). Heat must be radiated through radiators which obey
Stefan-Boltzmann law: P = epsilon * sigma * A * (T^4 - T_bg^4).

Radiators are exposed and vulnerable to damage. When radiator health drops,
effective radiating area shrinks and heat builds. Overheating forces system
shutdowns — reactor scrams, weapons lock out, drives throttle down.

Heat signature is what makes ships visible on IR sensors — managing heat
IS managing stealth.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, Any, Optional

from hybrid.core.base_system import BaseSystem

logger = logging.getLogger(__name__)

# Physical constants
STEFAN_BOLTZMANN = 5.67e-8  # W/m^2/K^4
SPACE_BACKGROUND_TEMP = 2.7  # K (CMB)
ABSOLUTE_ZERO = 0.0

# Default configuration
DEFAULT_THERMAL_CONFIG = {
    "radiator_area": 80.0,          # m^2 of radiator surface
    "radiator_emissivity": 0.9,     # emissivity (0-1), 1.0 = perfect blackbody
    "hull_heat_capacity": 500000.0, # J/K total ship thermal mass
    "max_temperature": 500.0,       # K — emergency shutdown threshold
    "warning_temperature": 400.0,   # K — systems start throttling
    "nominal_temperature": 300.0,   # K — comfortable operating temp
    "initial_temperature": 300.0,   # K — starting hull temp
    "heat_sink_capacity": 0.0,      # J — expendable heat sink budget (0 = none)
    "heat_sink_rate": 50000.0,      # W — max heat sink dump rate
}

# Reactor baseline heat output (always-on waste heat, in watts)
REACTOR_IDLE_HEAT = 20000.0   # 20 kW idle
REACTOR_FULL_HEAT = 200000.0  # 200 kW at full load

# Active sensor ping heat (watts during active scan)
SENSOR_ACTIVE_HEAT = 5000.0   # 5 kW per active ping cycle

# Drive waste heat: fraction of thrust power that becomes hull heat
# Most energy goes into exhaust kinetic energy, but ~2% heats the ship
DRIVE_HEAT_FRACTION = 0.02    # 2% of thrust power → hull heat
DRIVE_MAX_HEAT = 100000.0     # 100 kW cap on drive heat input


class ThermalSystem(BaseSystem):
    """Manages ship-wide thermal state: heat generation, radiation, and overheating.

    The thermal system runs each tick after all other systems have reported
    their heat. It:
    1. Reads total subsystem heat from the damage model
    2. Converts subsystem heat to joules and adds to hull thermal budget
    3. Calculates radiative cooling via Stefan-Boltzmann
    4. Generates continuous reactor waste heat
    5. Updates hull temperature
    6. Modifies subsystem heat_dissipation rates based on radiator health
    7. Publishes overheat events and enforces shutdown thresholds
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        super().__init__(config)

        # Merge with defaults
        for key, default in DEFAULT_THERMAL_CONFIG.items():
            if key not in config:
                config[key] = default

        self.radiator_area = float(config.get("radiator_area", DEFAULT_THERMAL_CONFIG["radiator_area"]))
        self.radiator_emissivity = float(config.get("radiator_emissivity", DEFAULT_THERMAL_CONFIG["radiator_emissivity"]))
        self.hull_heat_capacity = float(config.get("hull_heat_capacity", DEFAULT_THERMAL_CONFIG["hull_heat_capacity"]))
        self.max_temperature = float(config.get("max_temperature", DEFAULT_THERMAL_CONFIG["max_temperature"]))
        self.warning_temperature = float(config.get("warning_temperature", DEFAULT_THERMAL_CONFIG["warning_temperature"]))
        self.nominal_temperature = float(config.get("nominal_temperature", DEFAULT_THERMAL_CONFIG["nominal_temperature"]))

        # Current hull temperature in Kelvin
        self.hull_temperature = float(config.get("initial_temperature", DEFAULT_THERMAL_CONFIG["initial_temperature"]))

        # Expendable heat sinks (one-shot heat dumps)
        self.heat_sink_capacity = float(config.get("heat_sink_capacity", DEFAULT_THERMAL_CONFIG["heat_sink_capacity"]))
        self.heat_sink_remaining = self.heat_sink_capacity
        self.heat_sink_rate = float(config.get("heat_sink_rate", DEFAULT_THERMAL_CONFIG["heat_sink_rate"]))
        self.heat_sink_active = False

        # Tracking
        self._radiator_factor = 1.0  # 0-1 based on radiator subsystem health
        self._heat_generated_this_tick = 0.0  # W
        self._heat_radiated_this_tick = 0.0   # W
        self._heat_sink_dumped_this_tick = 0.0  # W
        self._net_heat_rate = 0.0  # W (positive = heating, negative = cooling)
        self._reactor_heat_watts = 0.0
        self._drive_heat_watts = 0.0
        self._is_overheating = False
        self._is_emergency = False

    def tick(self, dt: float, ship=None, event_bus=None):
        """Update thermal state for this tick.

        Args:
            dt: Time step in seconds
            ship: Ship object
            event_bus: EventBus for publishing thermal events
        """
        if not self.enabled or ship is None or dt <= 0:
            return

        # Track cold-drift state for telemetry
        self._cold_drift_ship_flag = getattr(ship, "_cold_drift_active", False)

        # --- 1. Collect heat from all sources ---
        total_heat_input_watts = self._calculate_heat_input(ship)
        self._heat_generated_this_tick = total_heat_input_watts

        # --- 2. Calculate radiative cooling (Stefan-Boltzmann) ---
        radiator_health = self._get_radiator_factor(ship)
        self._radiator_factor = radiator_health
        # Engineering radiator modifier (deploy/retract, priority mode)
        eng_radiator_mod = getattr(self, "_engineering_radiator_modifier", 1.0)
        effective_area = self.radiator_area * radiator_health * self.radiator_emissivity * eng_radiator_mod

        # P_rad = epsilon * sigma * A * (T_hull^4 - T_space^4)
        if self.hull_temperature > SPACE_BACKGROUND_TEMP:
            radiated_power = (STEFAN_BOLTZMANN * effective_area *
                            (self.hull_temperature**4 - SPACE_BACKGROUND_TEMP**4))
        else:
            radiated_power = 0.0

        self._heat_radiated_this_tick = radiated_power

        # --- 3. Heat sink dump (if active and available) ---
        heat_sink_power = 0.0
        if self.heat_sink_active and self.heat_sink_remaining > 0:
            heat_sink_power = min(self.heat_sink_rate, self.heat_sink_remaining / dt)
            heat_sink_energy = heat_sink_power * dt
            self.heat_sink_remaining = max(0.0, self.heat_sink_remaining - heat_sink_energy)
            if self.heat_sink_remaining <= 0:
                self.heat_sink_active = False
                if event_bus:
                    event_bus.publish("heat_sink_depleted", {
                        "ship_id": ship.id if ship else None,
                    })
        self._heat_sink_dumped_this_tick = heat_sink_power

        # --- 4. Net heat and temperature update ---
        net_heat_watts = total_heat_input_watts - radiated_power - heat_sink_power
        self._net_heat_rate = net_heat_watts

        # dT = Q / C  where Q = power * dt (joules), C = heat capacity
        if self.hull_heat_capacity > 0:
            delta_temp = (net_heat_watts * dt) / self.hull_heat_capacity
            self.hull_temperature = max(SPACE_BACKGROUND_TEMP,
                                       self.hull_temperature + delta_temp)

        # --- 5. Modify subsystem heat dissipation based on radiator health ---
        self._update_subsystem_dissipation(ship, radiator_health)

        # --- 6. Check overheat thresholds ---
        was_overheating = self._is_overheating
        was_emergency = self._is_emergency

        self._is_overheating = self.hull_temperature >= self.warning_temperature
        self._is_emergency = self.hull_temperature >= self.max_temperature

        if event_bus and ship:
            # Warning threshold crossed
            if self._is_overheating and not was_overheating:
                event_bus.publish("thermal_warning", {
                    "ship_id": ship.id,
                    "temperature": round(self.hull_temperature, 1),
                    "max_temperature": self.max_temperature,
                    "message": "Hull temperature exceeding safe limits — reduce system load or activate heat sinks",
                })
                logger.warning(f"Ship {ship.id}: Thermal warning at {self.hull_temperature:.1f}K")

            # Emergency threshold crossed — force system shutdowns
            if self._is_emergency and not was_emergency:
                event_bus.publish("thermal_emergency", {
                    "ship_id": ship.id,
                    "temperature": round(self.hull_temperature, 1),
                    "max_temperature": self.max_temperature,
                    "message": "THERMAL EMERGENCY — reactor scram, weapons lockout, drive throttle-down",
                })
                logger.warning(f"Ship {ship.id}: THERMAL EMERGENCY at {self.hull_temperature:.1f}K")
                self._enforce_emergency_shutdown(ship, event_bus)

            # Cleared warning
            if was_overheating and not self._is_overheating:
                event_bus.publish("thermal_nominal", {
                    "ship_id": ship.id,
                    "temperature": round(self.hull_temperature, 1),
                    "message": "Hull temperature returning to nominal",
                })

    def _calculate_heat_input(self, ship) -> float:
        """Calculate total heat input from all sources in watts.

        Heat comes from:
        1. Reactor waste heat (continuous, scales with power output)
        2. All subsystem heat values (converted from damage_model)
        3. Active sensors (when pinging)
        """
        total_watts = 0.0

        # 1. Reactor waste heat (continuous, scaled by engineering reactor output)
        reactor_load = self._get_reactor_load_fraction(ship)
        eng_reactor_output = getattr(self, "_engineering_reactor_output", 1.0)
        reactor_watts = REACTOR_IDLE_HEAT + (reactor_load * eng_reactor_output) * (REACTOR_FULL_HEAT - REACTOR_IDLE_HEAT)
        self._reactor_heat_watts = reactor_watts
        total_watts += reactor_watts

        # 2. Sum subsystem heat generation rates
        # The damage model tracks per-subsystem heat that was added this tick
        # We read the current heat levels and convert to an approximate power
        if hasattr(ship, "damage_model"):
            for name, sub in ship.damage_model.subsystems.items():
                # Each subsystem's current heat level represents stored thermal energy
                # The heat_generation rate from systems gives instantaneous power
                # We just need to account for the heat that EXISTS as a source
                # of IR emission and thermal load on radiators
                if sub.heat > 0 and sub.max_heat > 0:
                    # Subsystem heat contributes to hull heating proportionally
                    # Convert subsystem heat units to watts (scaling factor)
                    heat_fraction = sub.heat / sub.max_heat
                    # Each subsystem at max heat contributes ~10kW to hull
                    total_watts += heat_fraction * 10000.0

        # 3. Drive waste heat (proportional to thrust power)
        # The drive is the ship's biggest energy consumer; a fraction of
        # thrust power becomes waste heat in the hull. Cutting engines
        # immediately stops this source — enabling thermal cooldown.
        thrust_magnitude = self._get_thrust_magnitude(ship)
        if thrust_magnitude > 0:
            propulsion = ship.systems.get("propulsion")
            if propulsion:
                exhaust_vel = getattr(propulsion, "isp", 3000.0) * 9.81
                # Thrust power = F * Ve / 2 (kinetic power of exhaust)
                thrust_power = thrust_magnitude * exhaust_vel / 2.0
                drive_heat = min(thrust_power * DRIVE_HEAT_FRACTION, DRIVE_MAX_HEAT)
            else:
                drive_heat = thrust_magnitude * 0.5  # Rough fallback
            total_watts += drive_heat
            self._drive_heat_watts = drive_heat
        else:
            self._drive_heat_watts = 0.0

        # 4. Active sensors
        sensors = ship.systems.get("sensors")
        if sensors and hasattr(sensors, "active"):
            active = sensors.active
            if hasattr(active, "is_scanning") and active.is_scanning:
                total_watts += SENSOR_ACTIVE_HEAT

        return total_watts

    def _get_thrust_magnitude(self, ship) -> float:
        """Get current thrust magnitude from ship state."""
        thrust = getattr(ship, "thrust", None)
        if thrust and isinstance(thrust, dict):
            x = thrust.get("x", 0)
            y = thrust.get("y", 0)
            z = thrust.get("z", 0)
            mag = (x**2 + y**2 + z**2) ** 0.5
            if mag > 0.01:
                return mag

        propulsion = ship.systems.get("propulsion")
        if propulsion:
            if hasattr(propulsion, "throttle") and hasattr(propulsion, "max_thrust"):
                return propulsion.throttle * propulsion.max_thrust
        return 0.0

    def _get_reactor_load_fraction(self, ship) -> float:
        """Get reactor power output as fraction of capacity (0-1)."""
        pm = ship.systems.get("power_management")
        if pm and hasattr(pm, "get_state"):
            state = pm.get_state()
            # PowerManagementSystem.get_state() returns "total_available", not "total_output"
            total_output = state.get("total_available", 0)
            total_capacity = state.get("total_capacity", 1)
            if total_capacity > 0:
                return min(1.0, total_output / total_capacity)

        # Fallback: estimate from reactor subsystem
        if hasattr(ship, "damage_model"):
            reactor = ship.damage_model.subsystems.get("reactor")
            if reactor:
                return 1.0 - (reactor.health / reactor.max_health) * 0.5 + 0.5
        return 0.5

    def _get_radiator_factor(self, ship) -> float:
        """Get radiator effectiveness from damage model (0-1).

        If a 'radiators' subsystem exists in damage model, use its health.
        Otherwise fall back to reactor health as proxy.
        """
        if hasattr(ship, "damage_model"):
            radiators = ship.damage_model.subsystems.get("radiators")
            if radiators:
                if radiators.is_failed():
                    return 0.1  # Minimal radiation even with destroyed radiators
                return max(0.1, radiators.health / radiators.max_health)

        return 1.0  # No radiator subsystem = full radiation

    def _update_subsystem_dissipation(self, ship, radiator_factor: float):
        """Scale subsystem heat dissipation rates based on radiator health.

        When radiators are damaged, all subsystems dissipate heat more slowly,
        causing heat to build up across the ship.
        """
        if not hasattr(ship, "damage_model"):
            return

        # Dissipation scales with radiator health: at 100% health, full dissipation.
        # At 10% health (minimum), only 10% dissipation.
        # This creates the thermal crisis: damaged radiators → heat buildup → shutdowns
        for name, sub in ship.damage_model.subsystems.items():
            if name == "radiators":
                continue  # Don't modify radiator's own dissipation

            # Store original dissipation on first access
            if not hasattr(sub, "_base_dissipation"):
                sub._base_dissipation = sub.heat_dissipation

            sub.heat_dissipation = sub._base_dissipation * radiator_factor

    def _enforce_emergency_shutdown(self, ship, event_bus=None):
        """Force system shutdowns during thermal emergency.

        At max temperature:
        - Reactor output drops (scram) via heat penalty
        - Weapons locked out via heat penalty
        - Drive throttled via heat penalty

        We force this by adding heat to critical subsystems to push them
        into overheat territory.
        """
        if not hasattr(ship, "damage_model"):
            return

        critical_systems = ["reactor", "weapons", "propulsion"]
        for sys_name in critical_systems:
            sub = ship.damage_model.subsystems.get(sys_name)
            if sub and not sub.is_overheated():
                # Push to overheat threshold
                heat_to_add = sub.max_heat * sub.overheat_threshold - sub.heat + 1.0
                if heat_to_add > 0:
                    ship.damage_model.add_heat(sys_name, heat_to_add, event_bus, ship.id)

    def command(self, action: str, params: dict = None) -> dict:
        """Handle thermal system commands.

        Commands:
            activate_heat_sink: Dump heat using expendable heat sinks
            deactivate_heat_sink: Stop heat sink dump
            cold_drift: Enter emergency cold-drift mode
            exit_cold_drift: Exit cold-drift and restart systems
            get_thermal_state: Get full thermal status
        """
        params = params or {}

        if action == "activate_heat_sink":
            if self.heat_sink_remaining <= 0:
                return {"ok": False, "error": "Heat sinks depleted"}
            self.heat_sink_active = True
            return {
                "ok": True,
                "heat_sink_active": True,
                "remaining": round(self.heat_sink_remaining, 0),
                "capacity": self.heat_sink_capacity,
            }

        elif action == "deactivate_heat_sink":
            self.heat_sink_active = False
            return {"ok": True, "heat_sink_active": False}

        elif action == "cold_drift":
            return self._cmd_cold_drift(params)

        elif action == "exit_cold_drift":
            return self._cmd_exit_cold_drift(params)

        elif action == "get_thermal_state":
            return self.get_state()

        return {"error": f"Unknown thermal command: {action}"}

    def _cmd_cold_drift(self, params: dict) -> dict:
        """Enter emergency cold-drift mode.

        Shuts down reactor, retracts radiators, disables active sensors,
        coasts on battery. The ship becomes nearly invisible on IR but is
        defenseless — no weapons, no drive, no active sensors.

        Physical basis: with reactor offline and radiators retracted, the
        only IR source is hull thermal mass cooling in vacuum. The ship
        bleeds down to near-background over minutes.

        Args:
            params: Command parameters with ship and event_bus

        Returns:
            dict: Cold-drift activation result
        """
        ship = params.get("ship") or params.get("_ship")
        event_bus = params.get("event_bus")

        if getattr(ship, "_cold_drift_active", False):
            return {"ok": False, "error": "Already in cold-drift mode"}

        # Mark ship as cold-drifting
        ship._cold_drift_active = True

        # Record pre-cold-drift state for restoration
        ship._pre_cold_drift = {}

        # Kill the drive — zero thrust
        propulsion = ship.systems.get("propulsion") if ship else None
        if propulsion:
            if hasattr(propulsion, "throttle"):
                ship._pre_cold_drift["throttle"] = propulsion.throttle
                propulsion.throttle = 0.0
            if hasattr(propulsion, "command"):
                propulsion.command("set_throttle", {"throttle": 0.0})

        # Retract radiators (set engineering modifier to 0)
        self._engineering_radiator_modifier = 0.0
        ship._pre_cold_drift["radiator_modifier"] = 1.0

        # Reduce reactor output to minimum (5% for battery trickle)
        self._engineering_reactor_output = 0.05
        ship._pre_cold_drift["reactor_output"] = getattr(
            self, "_engineering_reactor_output_prev", 1.0)
        self._engineering_reactor_output_prev = getattr(
            self, "_engineering_reactor_output", 1.0)

        if event_bus and ship:
            event_bus.publish("cold_drift_activated", {
                "ship_id": ship.id,
                "temperature": round(self.hull_temperature, 1),
                "message": ("COLD DRIFT — Reactor scram, radiators retracted, "
                           "coasting on battery. Ship defenseless but nearly "
                           "invisible on IR."),
            })

        logger.info(f"Ship {ship.id if ship else '?'}: Cold-drift activated")

        return {
            "ok": True,
            "cold_drift_active": True,
            "hull_temperature": round(self.hull_temperature, 1),
            "message": ("Cold-drift engaged. Reactor offline, radiators retracted. "
                       "Hull will cool over time. No weapons, drive, or active sensors."),
        }

    def _cmd_exit_cold_drift(self, params: dict) -> dict:
        """Exit cold-drift mode, restart systems.

        Restores reactor, deploys radiators, re-enables drive. Systems
        will take time to come back online — reactor needs warmup, sensors
        need calibration. The ship will briefly be vulnerable.

        Args:
            params: Command parameters with ship and event_bus

        Returns:
            dict: Cold-drift deactivation result
        """
        ship = params.get("ship") or params.get("_ship")
        event_bus = params.get("event_bus")

        if not getattr(ship, "_cold_drift_active", False):
            return {"ok": False, "error": "Not in cold-drift mode"}

        ship._cold_drift_active = False

        # Restore radiators
        self._engineering_radiator_modifier = 1.0

        # Restore reactor output
        prev = getattr(self, "_engineering_reactor_output_prev", 1.0)
        self._engineering_reactor_output = prev

        # Restore throttle to pre-cold-drift value
        saved = getattr(ship, "_pre_cold_drift", {})
        prev_throttle = saved.get("throttle", 0.0)
        if prev_throttle > 0:
            propulsion = ship.systems.get("propulsion") if ship else None
            if propulsion and hasattr(propulsion, "throttle"):
                propulsion.throttle = prev_throttle

        # Clear saved state
        if hasattr(ship, "_pre_cold_drift"):
            del ship._pre_cold_drift

        if event_bus and ship:
            event_bus.publish("cold_drift_deactivated", {
                "ship_id": ship.id,
                "temperature": round(self.hull_temperature, 1),
                "message": ("Exiting cold-drift. Reactor restarting, radiators "
                           "deploying. Systems coming online."),
            })

        logger.info(f"Ship {ship.id if ship else '?'}: Cold-drift deactivated")

        return {
            "ok": True,
            "cold_drift_active": False,
            "hull_temperature": round(self.hull_temperature, 1),
            "message": ("Cold-drift disengaged. Reactor restarting, radiators "
                       "deploying. Systems will be available shortly."),
        }

    def get_state(self) -> dict:
        """Get full thermal system state for telemetry."""
        temp_percent = 0.0
        if self.max_temperature > SPACE_BACKGROUND_TEMP:
            temp_percent = ((self.hull_temperature - SPACE_BACKGROUND_TEMP) /
                          (self.max_temperature - SPACE_BACKGROUND_TEMP)) * 100.0

        return {
            "enabled": self.enabled,
            "hull_temperature": round(self.hull_temperature, 1),
            "max_temperature": self.max_temperature,
            "warning_temperature": self.warning_temperature,
            "nominal_temperature": self.nominal_temperature,
            "temperature_percent": round(min(100.0, max(0.0, temp_percent)), 1),
            "is_overheating": self._is_overheating,
            "is_emergency": self._is_emergency,
            "radiator_area": self.radiator_area,
            "radiator_factor": round(self._radiator_factor, 2),
            "radiator_effective_area": round(self.radiator_area * self._radiator_factor * self.radiator_emissivity, 1),
            "heat_generated": round(self._heat_generated_this_tick, 0),
            "heat_radiated": round(self._heat_radiated_this_tick, 0),
            "heat_sink_dumped": round(self._heat_sink_dumped_this_tick, 0),
            "net_heat_rate": round(self._net_heat_rate, 0),
            "drive_heat": round(self._drive_heat_watts, 0),
            "reactor_heat": round(self._reactor_heat_watts, 0),
            "heat_sink_active": self.heat_sink_active,
            "heat_sink_remaining": round(self.heat_sink_remaining, 0),
            "heat_sink_capacity": self.heat_sink_capacity,
            "cold_drift_active": getattr(self, "_cold_drift_ship_flag", False),
            "status": self._get_status_string(),
        }

    def _get_status_string(self) -> str:
        """Get human-readable thermal status."""
        if self._is_emergency:
            return "EMERGENCY"
        if self._is_overheating:
            return "WARNING"
        if self.hull_temperature > self.nominal_temperature + 20:
            return "elevated"
        return "nominal"

    def get_hull_temperature(self) -> float:
        """Get current hull temperature in Kelvin."""
        return self.hull_temperature

    def get_radiator_ir_emission(self) -> float:
        """Calculate IR emission from radiators in watts.

        This replaces the fixed radiator/infrastructure IR in the emission model.
        Hotter ship = more IR = more visible.

        Returns:
            float: Radiator IR emission in watts
        """
        if self.hull_temperature <= SPACE_BACKGROUND_TEMP:
            return 0.0

        effective_area = self.radiator_area * self._radiator_factor * self.radiator_emissivity
        return (STEFAN_BOLTZMANN * effective_area *
                (self.hull_temperature**4 - SPACE_BACKGROUND_TEMP**4))
