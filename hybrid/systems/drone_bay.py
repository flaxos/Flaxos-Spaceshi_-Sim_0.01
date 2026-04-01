# hybrid/systems/drone_bay.py
"""Drone bay system for launching, controlling, and recovering drones.

Drones are full Ship objects in the simulator with stripped-down systems.
They extend the parent ship's capabilities without risking crew:

  - sensor drone:  remote passive sensor platform
  - combat drone:  expendable PDC screen for point defense
  - decoy drone:   inflated IR + jammer to draw fire

Design notes:
  - Each drone is a real Ship with ai_enabled=True — the simulator ticks
    it like any other ship, so physics/sensors/weapons all work naturally.
  - Drones track their parent via `parent_ship_id` on the Ship object.
  - The bay monitors active drones each tick and prunes destroyed ones.
  - Drone positions on launch are offset 50m from the parent to avoid
    collision with the parent's own hitbox.
"""

from __future__ import annotations

import logging
import math
import uuid
from typing import Dict, List, Optional, Any

from hybrid.core.base_system import BaseSystem
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)

# Valid drone types — must match class_id in ship_classes/*.json
DRONE_TYPES = {"drone_sensor", "drone_combat", "drone_decoy"}

# AI role mapping per drone type — determines behavior profile
DRONE_ROLE_MAP = {
    "drone_sensor": "patrol",    # loiter near parent, passive sensors
    "drone_combat": "defender",  # station-keep, engage close threats with PDC
    "drone_decoy": "decoy",     # fly toward enemy, jammer on, die loudly
}


class DroneBaySystem(BaseSystem):
    """Manages drone storage, launch, recall, and status monitoring.

    The drone bay holds a fixed number of drone airframes. Launching a
    drone creates a Ship in the simulator; recalling sets the drone's
    autopilot to return to the parent. Destroyed drones are automatically
    pruned each tick.

    Config keys:
        capacity (int): Max drones the bay can hold (default 4)
        stored_drones (list[dict]): Initial drone inventory, each
            {"drone_type": str, "label": str?}
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        super().__init__(config)

        self.capacity: int = int(config.get("capacity", 4))

        # Stored drones waiting to be launched
        # Each entry: {"drone_type": str, "label": str}
        self.stored_drones: List[Dict[str, str]] = []
        for entry in config.get("stored_drones", []):
            if isinstance(entry, dict) and entry.get("drone_type") in DRONE_TYPES:
                self.stored_drones.append({
                    "drone_type": entry["drone_type"],
                    "label": entry.get("label", entry["drone_type"]),
                })

        # Active drones in the sim — maps drone_ship_id -> metadata
        self.active_drones: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Tick: prune destroyed/missing drones
    # ------------------------------------------------------------------

    def tick(self, dt: float, ship=None, event_bus=None) -> None:
        """Monitor active drones and remove destroyed ones.

        Called every sim tick. Checks each tracked drone against the
        simulator's ship list (via ship._all_ships_ref) and removes
        entries for drones that no longer exist (destroyed or despawned).
        """
        if ship is None:
            return

        all_ships = getattr(ship, "_all_ships_ref", None) or []
        live_ids = {s.id for s in all_ships}

        dead = [
            did for did in self.active_drones
            if did not in live_ids
        ]
        for did in dead:
            meta = self.active_drones.pop(did)
            logger.info(
                f"Drone {did} ({meta.get('drone_type', '?')}) destroyed or "
                f"removed — pruned from {ship.id}'s drone bay"
            )
            if event_bus:
                event_bus.publish("drone_lost", {
                    "ship_id": ship.id,
                    "drone_id": did,
                    "drone_type": meta.get("drone_type"),
                })

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def command(self, action: str, params: dict) -> dict:
        """Route drone bay commands."""
        handlers = {
            "launch_drone": self._cmd_launch_drone,
            "recall_drone": self._cmd_recall_drone,
            "set_drone_behavior": self._cmd_set_drone_behavior,
            "drone_status": self._cmd_drone_status,
        }
        handler = handlers.get(action)
        if handler:
            return handler(params)
        return {"error": f"Unknown drone_bay action: {action}"}

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------

    def _cmd_launch_drone(self, params: dict) -> dict:
        """Launch a drone from stored inventory into the simulator.

        Creates a Ship from the drone's class JSON, positions it 50m
        from the parent, enables AI with the appropriate role profile,
        and adds it to the running simulation.

        Params:
            drone_type (str): One of drone_sensor, drone_combat, drone_decoy
            ship (Ship): Parent ship object (injected by command handler)
        """
        ship = params.get("ship") or params.get("_ship")
        if not ship:
            return error_dict("NO_SHIP", "Ship context required for launch")

        drone_type = params.get("drone_type")
        if drone_type not in DRONE_TYPES:
            return error_dict(
                "INVALID_TYPE",
                f"Unknown drone type: {drone_type}. "
                f"Valid: {', '.join(sorted(DRONE_TYPES))}",
            )

        # Check bay has this drone type in storage
        slot_idx = None
        for i, slot in enumerate(self.stored_drones):
            if slot["drone_type"] == drone_type:
                slot_idx = i
                break

        if slot_idx is None:
            return error_dict(
                "NOT_IN_BAY",
                f"No {drone_type} available in drone bay. "
                f"Stored: {[s['drone_type'] for s in self.stored_drones]}",
            )

        # Resolve the drone's ship class config
        from hybrid.ship_class_registry import get_registry
        registry = get_registry()
        class_data = registry.get_class(drone_type)
        if class_data is None:
            return error_dict(
                "CLASS_NOT_FOUND",
                f"Ship class '{drone_type}' not found in registry",
            )

        # Build ship config from class
        config = registry._build_from_class(class_data)

        # Generate unique drone ID
        drone_id = f"drone_{drone_type}_{uuid.uuid4().hex[:6]}"
        config["name"] = f"{ship.name}'s {class_data.get('class_name', drone_type)}"
        config["faction"] = ship.faction
        config["ai_enabled"] = True

        # Position 50m offset from parent along a spread direction.
        # Each successive drone gets a different offset angle so they
        # don't stack on top of each other.
        offset_angle = len(self.active_drones) * (2 * math.pi / max(self.capacity, 1))
        offset_x = 50.0 * math.cos(offset_angle)
        offset_y = 50.0 * math.sin(offset_angle)
        config["position"] = {
            "x": ship.position["x"] + offset_x,
            "y": ship.position["y"] + offset_y,
            "z": ship.position["z"],
        }

        # Match parent velocity so the drone doesn't instantly drift away
        config["velocity"] = dict(ship.velocity)

        # Set AI behavior for the drone type
        role = DRONE_ROLE_MAP.get(drone_type, "patrol")
        config["ai_behavior"] = {"role": role}

        # Create the Ship object
        from hybrid.ship import Ship
        drone_ship = Ship(drone_id, config)
        drone_ship.parent_ship_id = ship.id

        # Add to the simulator — need to find the simulator reference.
        # The simulator is accessible through _all_ships_ref indirectly,
        # but the most reliable path is via params (injected by runner).
        sim = params.get("_simulator")
        if sim is None:
            # Fallback: add to the all_ships list so the runner picks it up
            return error_dict(
                "NO_SIMULATOR",
                "Simulator reference not available — cannot spawn drone",
            )

        sim.add_ship(drone_id, config)

        # Remove from stored inventory
        self.stored_drones.pop(slot_idx)

        # Track as active
        self.active_drones[drone_id] = {
            "drone_type": drone_type,
            "label": class_data.get("class_name", drone_type),
            "parent_ship_id": ship.id,
        }

        # Tag the sim ship with parent reference
        sim_drone = sim.get_ship(drone_id)
        if sim_drone:
            sim_drone.parent_ship_id = ship.id

        logger.info(
            f"Launched {drone_type} as {drone_id} from {ship.id} "
            f"at offset ({offset_x:.0f}, {offset_y:.0f}) m"
        )

        return success_dict(
            f"Launched {drone_type}",
            drone_id=drone_id,
            drone_type=drone_type,
            active_count=len(self.active_drones),
            stored_count=len(self.stored_drones),
        )

    # ------------------------------------------------------------------
    # Recall
    # ------------------------------------------------------------------

    def _cmd_recall_drone(self, params: dict) -> dict:
        """Set a drone's autopilot to return to the parent ship.

        Params:
            drone_id (str): ID of the drone to recall
            ship (Ship): Parent ship object
        """
        ship = params.get("ship") or params.get("_ship")
        drone_id = params.get("drone_id")

        if drone_id not in self.active_drones:
            return error_dict(
                "DRONE_NOT_FOUND",
                f"Drone '{drone_id}' is not tracked by this bay. "
                f"Active: {list(self.active_drones.keys())}",
            )

        sim = params.get("_simulator")
        if sim is None:
            return error_dict("NO_SIMULATOR", "Simulator reference not available")

        drone_ship = sim.get_ship(drone_id)
        if drone_ship is None:
            # Already destroyed — clean up
            self.active_drones.pop(drone_id, None)
            return error_dict("DRONE_DESTROYED", f"Drone {drone_id} no longer exists")

        # Set autopilot to return to parent using the navigation system.
        # The rendezvous autopilot will fly the drone back to the parent.
        nav = drone_ship.systems.get("navigation")
        if nav and hasattr(nav, "command"):
            nav.command("set_autopilot", {
                "program": "rendezvous",
                "target": ship.id if ship else "",
                "ship": drone_ship,
                "_ship": drone_ship,
                "_from_autopilot": True,
            })

        logger.info(f"Recalling drone {drone_id} to {ship.id if ship else '?'}")

        return success_dict(
            f"Recalling drone {drone_id}",
            drone_id=drone_id,
        )

    # ------------------------------------------------------------------
    # Behavior change
    # ------------------------------------------------------------------

    def _cmd_set_drone_behavior(self, params: dict) -> dict:
        """Change a drone's AI behavior profile.

        Params:
            drone_id (str): Drone to modify
            behavior (str): New behavior role (patrol, defender, decoy, combat, etc.)
        """
        drone_id = params.get("drone_id")
        behavior = params.get("behavior")

        if drone_id not in self.active_drones:
            return error_dict(
                "DRONE_NOT_FOUND",
                f"Drone '{drone_id}' not tracked",
            )

        sim = params.get("_simulator")
        if sim is None:
            return error_dict("NO_SIMULATOR", "Simulator reference not available")

        drone_ship = sim.get_ship(drone_id)
        if drone_ship is None:
            self.active_drones.pop(drone_id, None)
            return error_dict("DRONE_DESTROYED", f"Drone {drone_id} no longer exists")

        if not drone_ship.ai_controller:
            return error_dict("NO_AI", f"Drone {drone_id} has no AI controller")

        from hybrid.fleet.npc_behavior import get_profile
        profile = get_profile(behavior or "patrol")
        drone_ship.ai_controller.profile = profile
        drone_ship.ai_controller.engagement_range = profile.engagement_range

        logger.info(f"Set drone {drone_id} behavior to '{behavior}'")

        return success_dict(
            f"Drone {drone_id} behavior set to '{behavior}'",
            drone_id=drone_id,
            behavior=behavior,
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _cmd_drone_status(self, params: dict) -> dict:
        """Return bay capacity, stored drones, and active drone details.

        Active drone details include fuel percentage, distance from
        parent, and current AI role.
        """
        ship = params.get("ship") or params.get("_ship")
        sim = params.get("_simulator")

        active_details = []
        for drone_id, meta in self.active_drones.items():
            entry = {
                "drone_id": drone_id,
                "drone_type": meta.get("drone_type"),
                "label": meta.get("label"),
            }

            if sim:
                drone_ship = sim.get_ship(drone_id)
                if drone_ship:
                    # Fuel percentage
                    prop = drone_ship.systems.get("propulsion")
                    if prop and hasattr(prop, "fuel_level") and hasattr(prop, "max_fuel"):
                        max_f = prop.max_fuel or 1.0
                        entry["fuel_pct"] = round(prop.fuel_level / max_f * 100, 1)
                    else:
                        entry["fuel_pct"] = 0.0

                    # Distance from parent
                    if ship:
                        dx = drone_ship.position["x"] - ship.position["x"]
                        dy = drone_ship.position["y"] - ship.position["y"]
                        dz = drone_ship.position["z"] - ship.position["z"]
                        entry["distance_m"] = round(math.sqrt(dx*dx + dy*dy + dz*dz), 1)

                    # AI role
                    if drone_ship.ai_controller and hasattr(drone_ship.ai_controller, "profile"):
                        entry["ai_role"] = drone_ship.ai_controller.profile.role
                    else:
                        entry["ai_role"] = "unknown"

                    entry["hull_pct"] = round(
                        drone_ship.hull_integrity / max(drone_ship.max_hull_integrity, 1) * 100, 1
                    )
                else:
                    entry["status"] = "lost"

            active_details.append(entry)

        return success_dict(
            "Drone bay status",
            capacity=self.capacity,
            stored_count=len(self.stored_drones),
            stored_drones=[dict(s) for s in self.stored_drones],
            active_count=len(self.active_drones),
            active_drones=active_details,
        )

    # ------------------------------------------------------------------
    # State for telemetry
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Return serialisable state for telemetry/GUI."""
        return {
            "enabled": self.enabled,
            "capacity": self.capacity,
            "stored_count": len(self.stored_drones),
            "stored_drones": [dict(s) for s in self.stored_drones],
            "active_count": len(self.active_drones),
            "active_drone_ids": list(self.active_drones.keys()),
        }
