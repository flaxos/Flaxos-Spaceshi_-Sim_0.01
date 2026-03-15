# hybrid/systems/fleet_coord_system.py
"""Fleet coordination system for command-capable vessels.

Provides fleet-level operations through the hybrid command system:
- Create and manage fleets/squadrons
- Formation control (line, wedge, wall, etc.)
- Fleet target designation and coordinated fire
- Fleet maneuvers (intercept, match velocity, hold, evasive)
- Tactical data link (shared contacts)
- Fleet status and tactical summaries

This system acts as a bridge between the hybrid per-ship command pattern
and the simulator-level FleetManager.  The FleetManager reference is
injected via ``set_fleet_manager()`` during simulator setup.

Commands:
    fleet_create: Create a new fleet/squadron
    fleet_add_ship: Add a ship to an existing fleet
    fleet_form: Form fleet into a formation
    fleet_break_formation: Break current formation
    fleet_target: Designate target for entire fleet
    fleet_fire: Order fleet to fire on designated target
    fleet_cease_fire: Order fleet to cease fire
    fleet_maneuver: Execute coordinated fleet maneuver
    fleet_status: Get comprehensive fleet status
    fleet_tactical: Get fleet tactical summary
    share_contact: Share a sensor contact via data link
"""

import logging
import time
from typing import Dict, Any, Optional

from hybrid.core.base_system import BaseSystem
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)

DEFAULT_FLEET_COORD_CONFIG = {
    "power_draw": 1.0,       # kW for data link equipment
    "command_capable": True,  # Whether this ship can command a fleet
}


class FleetCoordSystem(BaseSystem):
    """Fleet coordination system for command ships.

    Provides fleet-level command and control through the standard
    hybrid system interface.  Delegates actual fleet operations to
    the simulator's FleetManager.
    """

    def __init__(self, config: Optional[dict] = None):
        config = config if config is not None else {}

        for key, default in DEFAULT_FLEET_COORD_CONFIG.items():
            if key not in config:
                config[key] = default

        super().__init__(config)

        self.command_capable: bool = bool(config.get("command_capable", True))
        self._fleet_manager = None
        self._sim_time: float = 0.0

    def set_fleet_manager(self, fleet_manager):
        """Inject the simulator's FleetManager reference.

        Called by the simulator during setup so that fleet commands
        can delegate to the central fleet manager.
        """
        self._fleet_manager = fleet_manager

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def tick(self, dt: float, ship=None, event_bus=None):
        """Update fleet coordination system each tick."""
        if not self.enabled or ship is None or dt <= 0:
            return
        self._sim_time += dt

    # ------------------------------------------------------------------
    # Command dispatcher
    # ------------------------------------------------------------------

    def command(self, action: str, params: dict = None) -> dict:
        """Dispatch fleet commands."""
        params = params or {}

        dispatch = {
            "fleet_create": self._cmd_fleet_create,
            "fleet_add_ship": self._cmd_fleet_add_ship,
            "fleet_form": self._cmd_fleet_form,
            "fleet_break_formation": self._cmd_fleet_break_formation,
            "fleet_target": self._cmd_fleet_target,
            "fleet_fire": self._cmd_fleet_fire,
            "fleet_cease_fire": self._cmd_fleet_cease_fire,
            "fleet_maneuver": self._cmd_fleet_maneuver,
            "fleet_status": self._cmd_fleet_status,
            "fleet_tactical": self._cmd_fleet_tactical,
            "share_contact": self._cmd_share_contact,
        }

        handler = dispatch.get(action)
        if handler:
            return handler(params)
        return error_dict("UNKNOWN_COMMAND", f"Unknown fleet command: {action}")

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    def _cmd_fleet_create(self, params: dict) -> dict:
        """Create a new fleet/squadron."""
        fm = self._fleet_manager
        if not fm:
            return error_dict("NO_FLEET_MANAGER", "Fleet manager not available")

        ship = params.get("ship") or params.get("_ship")
        fleet_id = params.get("fleet_id")
        name = params.get("name", f"Fleet {fleet_id}")
        flagship = params.get("flagship")
        ships = params.get("ships", [])

        if not fleet_id:
            return error_dict("MISSING_PARAM", "Fleet ID required")

        # Default flagship to the commanding ship
        if not flagship and ship:
            flagship = ship.id

        success = fm.create_fleet(fleet_id, name, flagship, ships if ships else None)

        if success:
            return success_dict(
                f"Fleet '{name}' created with flagship {flagship}",
                fleet_id=fleet_id,
                name=name,
                flagship=flagship,
                ships=list(fm.fleets[fleet_id].ship_ids),
            )
        return error_dict("CREATE_FAILED", "Failed to create fleet (ID may already exist)")

    def _cmd_fleet_add_ship(self, params: dict) -> dict:
        """Add a ship to an existing fleet."""
        fm = self._fleet_manager
        if not fm:
            return error_dict("NO_FLEET_MANAGER", "Fleet manager not available")

        fleet_id = params.get("fleet_id")
        target_ship = params.get("target_ship") or params.get("ship_to_add")

        if not fleet_id or not target_ship:
            return error_dict("MISSING_PARAM", "Fleet ID and ship ID required")

        success = fm.add_ship_to_fleet(target_ship, fleet_id)

        if success:
            return success_dict(
                f"Ship {target_ship} added to fleet {fleet_id}",
                fleet_id=fleet_id,
                ship_id=target_ship,
            )
        return error_dict("ADD_FAILED", "Failed to add ship to fleet")

    def _cmd_fleet_form(self, params: dict) -> dict:
        """Form fleet into a formation."""
        fm = self._fleet_manager
        if not fm:
            return error_dict("NO_FLEET_MANAGER", "Fleet manager not available")

        ship = params.get("ship") or params.get("_ship")
        fleet_id = params.get("fleet_id")
        formation_name = params.get("formation", "line")
        spacing = float(params.get("spacing", 2000.0))

        # If no fleet_id, use current ship's fleet
        if not fleet_id and ship:
            fleet_id = fm.ship_to_fleet.get(ship.id)

        if not fleet_id:
            return error_dict("NO_FLEET", "No fleet specified and ship not in a fleet")

        from hybrid.fleet import FormationType
        try:
            formation_type = FormationType(formation_name.lower())
        except ValueError:
            available = ", ".join([f.value for f in FormationType])
            return error_dict("INVALID_FORMATION",
                              f"Invalid formation type. Available: {available}")

        # Build extra params
        extra = {}
        if params.get("wall_columns"):
            extra["wall_columns"] = int(params["wall_columns"])
        if params.get("echelon_angle"):
            extra["echelon_angle"] = float(params["echelon_angle"])
        if params.get("sphere_radius"):
            extra["sphere_radius"] = float(params["sphere_radius"])

        success = fm.form_fleet(fleet_id, formation_type, spacing, **extra)

        if success:
            return success_dict(
                f"Fleet {fleet_id} forming {formation_type.value} formation",
                fleet_id=fleet_id,
                formation=formation_type.value,
                spacing=spacing,
            )
        return error_dict("FORM_FAILED", "Failed to form fleet")

    def _cmd_fleet_break_formation(self, params: dict) -> dict:
        """Break fleet formation."""
        fm = self._fleet_manager
        if not fm:
            return error_dict("NO_FLEET_MANAGER", "Fleet manager not available")

        ship = params.get("ship") or params.get("_ship")
        fleet_id = params.get("fleet_id")

        if not fleet_id and ship:
            fleet_id = fm.ship_to_fleet.get(ship.id)

        if not fleet_id:
            return error_dict("NO_FLEET", "No fleet specified and ship not in a fleet")

        success = fm.break_formation(fleet_id)

        if success:
            return success_dict(
                f"Fleet {fleet_id} formation broken",
                fleet_id=fleet_id,
            )
        return error_dict("BREAK_FAILED", "Failed to break formation")

    def _cmd_fleet_target(self, params: dict) -> dict:
        """Designate target for entire fleet."""
        fm = self._fleet_manager
        if not fm:
            return error_dict("NO_FLEET_MANAGER", "Fleet manager not available")

        ship = params.get("ship") or params.get("_ship")
        fleet_id = params.get("fleet_id")
        contact_id = params.get("contact")

        if not contact_id:
            return error_dict("NO_TARGET", "Contact ID required")

        if not fleet_id and ship:
            fleet_id = fm.ship_to_fleet.get(ship.id)

        if not fleet_id:
            return error_dict("NO_FLEET", "No fleet specified and ship not in a fleet")

        success = fm.set_fleet_target(fleet_id, contact_id)

        if success:
            return success_dict(
                f"Fleet {fleet_id} targeting {contact_id}",
                fleet_id=fleet_id,
                contact_id=contact_id,
            )
        return error_dict("TARGET_FAILED", "Failed to set fleet target")

    def _cmd_fleet_fire(self, params: dict) -> dict:
        """Order fleet to fire on designated target."""
        fm = self._fleet_manager
        if not fm:
            return error_dict("NO_FLEET_MANAGER", "Fleet manager not available")

        ship = params.get("ship") or params.get("_ship")
        fleet_id = params.get("fleet_id")
        volley = bool(params.get("volley", False))

        if not fleet_id and ship:
            fleet_id = fm.ship_to_fleet.get(ship.id)

        if not fleet_id:
            return error_dict("NO_FLEET", "No fleet specified and ship not in a fleet")

        result = fm.fleet_fire(fleet_id, volley=volley)

        if result.get("success"):
            fire_type = "volley" if volley else "independent"
            return success_dict(
                f"Fleet {fleet_id} engaging ({fire_type} fire)",
                fleet_id=fleet_id,
                fire_type=fire_type,
                target=result.get("target"),
                ships=result.get("ships", 0),
            )
        return error_dict("FIRE_FAILED", result.get("error", "Failed to order fleet fire"))

    def _cmd_fleet_cease_fire(self, params: dict) -> dict:
        """Order fleet to cease fire."""
        fm = self._fleet_manager
        if not fm:
            return error_dict("NO_FLEET_MANAGER", "Fleet manager not available")

        ship = params.get("ship") or params.get("_ship")
        fleet_id = params.get("fleet_id")

        if not fleet_id and ship:
            fleet_id = fm.ship_to_fleet.get(ship.id)

        if not fleet_id:
            return error_dict("NO_FLEET", "No fleet specified and ship not in a fleet")

        if fleet_id in fm.fleets:
            fm._broadcast_to_fleet(fleet_id, "command", {"type": "cease_fire"})
            return success_dict(
                f"Fleet {fleet_id} cease fire ordered",
                fleet_id=fleet_id,
            )
        return error_dict("FLEET_NOT_FOUND", "Fleet not found")

    def _cmd_fleet_maneuver(self, params: dict) -> dict:
        """Execute coordinated fleet maneuver."""
        fm = self._fleet_manager
        if not fm:
            return error_dict("NO_FLEET_MANAGER", "Fleet manager not available")

        ship = params.get("ship") or params.get("_ship")
        fleet_id = params.get("fleet_id")
        maneuver_type = params.get("maneuver", "hold")

        if not fleet_id and ship:
            fleet_id = fm.ship_to_fleet.get(ship.id)

        if not fleet_id:
            return error_dict("NO_FLEET", "No fleet specified and ship not in a fleet")

        import numpy as np
        target_pos = None
        target_vel = None
        if params.get("position"):
            pos = params["position"]
            if isinstance(pos, dict):
                target_pos = np.array([pos.get("x", 0), pos.get("y", 0), pos.get("z", 0)])
            elif isinstance(pos, (list, tuple)):
                target_pos = np.array(pos)
        if params.get("velocity"):
            vel = params["velocity"]
            if isinstance(vel, dict):
                target_vel = np.array([vel.get("x", 0), vel.get("y", 0), vel.get("z", 0)])
            elif isinstance(vel, (list, tuple)):
                target_vel = np.array(vel)

        success = fm.fleet_maneuver(fleet_id, maneuver_type, target_pos, target_vel)

        if success:
            return success_dict(
                f"Fleet {fleet_id} executing {maneuver_type} maneuver",
                fleet_id=fleet_id,
                maneuver=maneuver_type,
            )
        return error_dict("MANEUVER_FAILED", "Failed to execute fleet maneuver")

    def _cmd_fleet_status(self, params: dict) -> dict:
        """Get comprehensive fleet status."""
        fm = self._fleet_manager
        if not fm:
            return error_dict("NO_FLEET_MANAGER", "Fleet manager not available")

        ship = params.get("ship") or params.get("_ship")
        fleet_id = params.get("fleet_id")

        if not fleet_id and ship:
            fleet_id = fm.ship_to_fleet.get(ship.id)

        if not fleet_id:
            # Return list of all fleets
            all_fleets = []
            for fid, fleet in fm.fleets.items():
                all_fleets.append({
                    "fleet_id": fid,
                    "name": fleet.name,
                    "flagship": fleet.flagship_id,
                    "ship_count": len(fleet.ship_ids),
                    "status": fleet.status.value,
                })
            return success_dict(
                f"Found {len(all_fleets)} fleets",
                fleets=all_fleets,
            )

        status = fm.get_fleet_status(fleet_id)
        if status:
            return success_dict(
                f"Fleet {fleet_id} status",
                fleet=status,
            )
        return error_dict("FLEET_NOT_FOUND", "Fleet not found")

    def _cmd_fleet_tactical(self, params: dict) -> dict:
        """Get fleet tactical summary."""
        fm = self._fleet_manager
        if not fm:
            return error_dict("NO_FLEET_MANAGER", "Fleet manager not available")

        ship = params.get("ship") or params.get("_ship")
        fleet_id = params.get("fleet_id")

        if not fleet_id and ship:
            fleet_id = fm.ship_to_fleet.get(ship.id)

        if not fleet_id:
            return error_dict("NO_FLEET", "No fleet specified and ship not in a fleet")

        tactical = fm.get_fleet_tactical_summary(fleet_id)
        if tactical:
            return success_dict(
                f"Fleet {fleet_id} tactical summary",
                tactical=tactical,
            )
        return error_dict("FLEET_NOT_FOUND", "Fleet not found")

    def _cmd_share_contact(self, params: dict) -> dict:
        """Share a sensor contact with fleet via tactical data link."""
        fm = self._fleet_manager
        if not fm:
            return error_dict("NO_FLEET_MANAGER", "Fleet manager not available")

        ship = params.get("ship") or params.get("_ship")
        contact_id = params.get("contact")
        is_hostile = bool(params.get("hostile", False))

        if not contact_id:
            return error_dict("NO_CONTACT", "Contact ID required")

        if not ship:
            return error_dict("NO_SHIP", "Ship reference not available")

        # Get contact from ship's sensors
        sensors = ship.systems.get("sensors") if hasattr(ship, "systems") else None
        if not sensors:
            return error_dict("NO_SENSORS", "Ship has no sensors")

        contact = sensors.get_contact(contact_id) if hasattr(sensors, "get_contact") else None
        if not contact:
            return error_dict("CONTACT_NOT_FOUND", f"Contact {contact_id} not found")

        import numpy as np
        pos = contact.get("position", {})
        vel = contact.get("velocity", {})
        position = np.array([pos.get("x", 0), pos.get("y", 0), pos.get("z", 0)])
        velocity = np.array([vel.get("x", 0), vel.get("y", 0), vel.get("z", 0)])

        success = fm.share_contact(
            contact_id=contact_id,
            reporting_ship=ship.id,
            position=position,
            velocity=velocity,
            classification=contact.get("classification", "unknown"),
            confidence=contact.get("confidence", 0.5),
            is_hostile=is_hostile,
        )

        if success:
            return success_dict(
                f"Contact {contact_id} shared with fleet",
                contact_id=contact_id,
                hostile=is_hostile,
            )
        return error_dict("SHARE_FAILED", "Failed to share contact")

    # ------------------------------------------------------------------
    # State / telemetry
    # ------------------------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        """Return serializable fleet coordination telemetry."""
        fm = self._fleet_manager
        state = {
            "enabled": self.enabled,
            "power_draw": self.power_draw,
            "command_capable": self.command_capable,
            "fleet_count": 0,
            "fleets": [],
            "status": "offline" if not fm else "active",
        }

        if fm:
            state["fleet_count"] = len(fm.fleets)
            state["fleets"] = [
                {
                    "fleet_id": fid,
                    "name": fleet.name,
                    "flagship": fleet.flagship_id,
                    "ship_count": len(fleet.ship_ids),
                    "status": fleet.status.value,
                    "target": fleet.target_contact,
                }
                for fid, fleet in fm.fleets.items()
            ]
            state["shared_contacts"] = len(fm.shared_contacts)

        return state
