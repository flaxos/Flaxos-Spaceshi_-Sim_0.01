# hybrid/systems/docking_system.py
"""Docking system implementation for proximity-based docking."""

import logging

from hybrid.core.base_system import BaseSystem
from hybrid.navigation.relative_motion import calculate_relative_motion

logger = logging.getLogger(__name__)


class DockingSystem(BaseSystem):
    """Tracks docking requests and validates docking conditions."""

    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}

        self.docking_range = float(config.get("docking_range", config.get("max_range", 50.0)))
        self.max_relative_velocity = float(
            config.get("max_relative_velocity", config.get("docking_velocity", 1.0))
        )

        self.target_id = None
        self.target_ship = None
        self.status = "idle"
        self.last_check = {}
        # Populated on station dock with repair/resupply summary
        self._last_service_report = None

    def tick(self, dt, ship=None, event_bus=None):
        """Evaluate docking criteria each tick when a request is active."""
        if not self.enabled:
            self.status = "offline"
            return

        if not ship:
            self.status = "idle"
            return

        if getattr(ship, "docked_to", None):
            self.status = "docked"
            # Lock position to docking target and suppress all motion
            if self.target_ship:
                target_pos = self.target_ship.position if hasattr(self.target_ship, 'position') else None
                if target_pos:
                    ship.position = dict(target_pos)
            ship.velocity = {"x": 0.0, "y": 0.0, "z": 0.0}
            ship.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
            return

        if not self.target_ship and not self.target_id:
            self.status = "idle"
            return

        target_ship = self.target_ship
        target_id = self.target_id
        if not target_ship:
            self.status = "target_lost"
            return

        rel_motion = calculate_relative_motion(ship, target_ship)
        relative_speed = rel_motion.get("relative_velocity_magnitude", 0.0)
        range_to_target = rel_motion.get("range", 0.0)
        self.last_check = {
            "range": range_to_target,
            "relative_velocity": relative_speed,
        }

        if range_to_target <= self.docking_range and relative_speed <= self.max_relative_velocity:
            ship.docked_to = target_id or getattr(target_ship, "id", None)
            self.status = "docked"
            # Zero motion so the ship doesn't drift while docked
            ship.velocity = {"x": 0.0, "y": 0.0, "z": 0.0}
            ship.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
            # Disengage any active autopilot — docked ships shouldn't navigate
            nav = ship.systems.get("navigation")
            if nav and hasattr(nav, 'controller') and nav.controller:
                nav.controller.disengage_autopilot()
            if event_bus:
                event_bus.publish(
                    "docked",
                    {
                        "ship": ship.id,
                        "target": ship.docked_to,
                        "range": range_to_target,
                        "relative_velocity": relative_speed,
                    },
                )
            logger.info("Ship %s docked with %s", ship.id, ship.docked_to)
            if getattr(target_ship, "class_type", None) == "station":
                self._handle_station_dock(ship, event_bus, target_ship)
        else:
            self.status = "approaching"

    def command(self, action, params):
        """Handle docking commands."""
        if action == "request_docking":
            return self._cmd_request_docking(params)
        elif action == "cancel_docking":
            return self._cmd_cancel_docking()
        elif action == "undock":
            return self._cmd_undock(params)
        elif action == "status":
            return self.get_state()
        elif action == "power_on":
            return self.power_on()
        elif action == "power_off":
            return self.power_off()
        return super().command(action, params)

    def _cmd_undock(self, params):
        """Detach from the currently docked target."""
        if self.status != "docked":
            return {"ok": False, "error": "Not currently docked"}
        ship = params.get("_ship") or params.get("ship")
        event_bus = params.get("event_bus")
        if ship:
            ship.docked_to = None
        self.status = "idle"
        self.target_id = None
        self.target_ship = None
        self._last_service_report = None
        if event_bus and ship:
            event_bus.publish("undocked", {"ship_id": ship.id})
        return {"ok": True, "status": "Undocked"}

    def _cmd_request_docking(self, params):
        if not self.enabled:
            return {"error": "Docking system is disabled"}

        ship = params.get("_ship") or params.get("ship")
        if ship and getattr(ship, "docked_to", None):
            return {"error": f"Ship already docked to {ship.docked_to}"}

        target_ship = params.get("target_ship")
        target_id = params.get("target_id") or params.get("target")
        if target_ship and not target_id:
            target_id = getattr(target_ship, "id", None)
        if not target_ship and hasattr(target_id, "id"):
            target_ship = target_id
            target_id = getattr(target_ship, "id", None)
        if not target_ship:
            all_ships = params.get("all_ships")
            if isinstance(all_ships, dict):
                target_ship = all_ships.get(target_id)
            elif all_ships:
                for candidate in all_ships:
                    if getattr(candidate, "id", None) == target_id:
                        target_ship = candidate
                        break

        if ship and target_id == ship.id:
            return {"error": "Cannot dock with self"}

        if not target_id:
            return {"error": "Missing target for docking"}

        self.target_id = target_id
        self.target_ship = target_ship
        self.status = "docking_initiated"

        event_bus = params.get("event_bus")
        if event_bus and ship:
            event_bus.publish(
                "docking_initiated",
                {
                    "ship": ship.id,
                    "target": target_id,
                    "range": self.last_check.get("range"),
                    "relative_velocity": self.last_check.get("relative_velocity"),
                },
            )

        return {
            "status": "docking_requested",
            "target": target_id,
            "docking_range": self.docking_range,
            "max_relative_velocity": self.max_relative_velocity,
        }

    def _cmd_cancel_docking(self):
        self.target_id = None
        self.target_ship = None
        self.status = "idle"
        return {"status": "docking_cancelled"}

    def _handle_station_dock(self, ship, event_bus, target_ship):
        """Perform full repair, refuel, and resupply when docking at a station.

        Stations provide instant servicing:
        1. Hull restored to max
        2. All subsystem health restored and heat cleared
        3. Fuel topped off
        4. All weapon ammo replenished (legacy + truth/combat weapons)

        Publishes repair_complete and resupply_complete events so the GUI
        and combat log can report what changed.
        """
        station_id = getattr(target_ship, "id", None)

        # --- 1. Hull repair ---
        hull_before = ship.hull_integrity
        if ship.hull_integrity < ship.max_hull_integrity:
            ship.hull_integrity = ship.max_hull_integrity

        # --- 2. Subsystem repair + heat reset ---
        repair_reports = []
        if hasattr(ship, "damage_model"):
            for name, data in ship.damage_model.subsystems.items():
                amount = data.max_health - data.health
                if amount > 0:
                    repair_reports.append(ship.damage_model.repair_subsystem(name, amount))
                # Station coolant service: reset accumulated heat
                if data.heat > 0:
                    data.heat = 0.0

        # --- 3. Refuel ---
        fuel_before = 0.0
        fuel_after = 0.0
        propulsion = ship.systems.get("propulsion")
        if propulsion and hasattr(propulsion, "fuel_level"):
            fuel_before = propulsion.fuel_level
            propulsion.fuel_level = propulsion.max_fuel
            fuel_after = propulsion.fuel_level

        # --- 4. Resupply ammo (legacy weapon system) ---
        weapon_reports = []
        weapon_system = ship.systems.get("weapons")
        if weapon_system and hasattr(weapon_system, "resupply"):
            result = weapon_system.resupply()
            weapon_reports.extend(result.get("weapons", []))

        # --- 4b. Resupply ammo (truth weapons in combat system) ---
        combat_system = ship.systems.get("combat")
        if combat_system and hasattr(combat_system, "resupply"):
            result = combat_system.resupply()
            weapon_reports.extend(result.get("weapons", []))

        # --- 5. Store servicing summary for telemetry ---
        self._last_service_report = {
            "hull_repaired": ship.hull_integrity - hull_before,
            "subsystems_repaired": len(repair_reports),
            "fuel_added": fuel_after - fuel_before,
            "weapons_resupplied": len(weapon_reports),
        }

        # --- 6. Publish events ---
        if event_bus:
            event_bus.publish(
                "repair_complete",
                {
                    "ship": ship.id,
                    "target": station_id,
                    "hull_before": hull_before,
                    "hull_after": ship.hull_integrity,
                    "subsystems": repair_reports,
                },
            )
            event_bus.publish(
                "resupply_complete",
                {
                    "ship": ship.id,
                    "target": station_id,
                    "fuel_before": fuel_before,
                    "fuel_after": fuel_after,
                    "weapons": weapon_reports,
                },
            )

        logger.info(
            "Station dock servicing for %s: hull +%.0f, %d subsystems repaired, "
            "fuel +%.0f, %d weapons resupplied",
            ship.id,
            ship.hull_integrity - hull_before,
            len(repair_reports),
            fuel_after - fuel_before,
            len(weapon_reports),
        )

    def get_state(self):
        state = {
            **super().get_state(),
            "status": self.status,
            "target": self.target_id,
            "docking_range": self.docking_range,
            "max_relative_velocity": self.max_relative_velocity,
            "last_check": self.last_check,
        }
        # Include servicing report when docked at a station so the GUI
        # can show what was repaired/resupplied
        if self._last_service_report and self.status == "docked":
            state["service_report"] = self._last_service_report
        return state
