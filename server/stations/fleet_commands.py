"""
Fleet command handlers for FLEET_COMMANDER station.

Provides fleet-level commands for multi-ship coordination, formations,
and tactical operations.
"""

from typing import Dict, Any
import logging
import numpy as np

from .station_dispatch import CommandResult
from hybrid.fleet import FormationType

logger = logging.getLogger(__name__)


def register_fleet_commands(dispatcher, station_manager, fleet_manager):
    """
    Register fleet commands with the dispatcher.

    Args:
        dispatcher: StationAwareDispatcher instance
        station_manager: StationManager instance
        fleet_manager: FleetManager instance
    """

    def cmd_fleet_create(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Create a new fleet/squadron.

        Args:
            fleet_id: Unique fleet identifier
            name: Fleet name
            flagship: Flagship ship ID (optional, defaults to current ship)
            ships: List of ship IDs to add (optional)
        """
        fleet_id = args.get("fleet_id")
        name = args.get("name", f"Fleet {fleet_id}")
        flagship = args.get("flagship", ship_id)
        ships = args.get("ships", [])

        if not fleet_id:
            return CommandResult(
                success=False,
                message="Fleet ID required"
            )

        success = fleet_manager.create_fleet(fleet_id, name, flagship, ships)

        if success:
            return CommandResult(
                success=True,
                message=f"Fleet {name} created with flagship {flagship}",
                data={
                    "fleet_id": fleet_id,
                    "name": name,
                    "flagship": flagship,
                    "ships": ships
                }
            )
        else:
            return CommandResult(
                success=False,
                message="Failed to create fleet (ID may already exist)"
            )

    def cmd_fleet_add_ship(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Add a ship to a fleet.

        Args:
            fleet_id: Fleet to add ship to
            ship: Ship ID to add
        """
        fleet_id = args.get("fleet_id")
        target_ship = args.get("ship")

        if not fleet_id or not target_ship:
            return CommandResult(
                success=False,
                message="Fleet ID and ship ID required"
            )

        success = fleet_manager.add_ship_to_fleet(target_ship, fleet_id)

        if success:
            return CommandResult(
                success=True,
                message=f"Ship {target_ship} added to fleet {fleet_id}",
                data={"fleet_id": fleet_id, "ship_id": target_ship}
            )
        else:
            return CommandResult(
                success=False,
                message="Failed to add ship to fleet"
            )

    def cmd_fleet_form(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Form fleet into formation.

        Args:
            fleet_id: Fleet to form (optional, uses current ship's fleet)
            formation: Formation type (line, column, wall, sphere, wedge, echelon, diamond)
            spacing: Distance between ships in meters (optional, default 2000)
            wall_columns: Columns for wall formation (optional, default 3)
        """
        fleet_id = args.get("fleet_id")
        formation_name = args.get("formation", "line")
        spacing = float(args.get("spacing", 2000.0))

        # If no fleet_id, use current ship's fleet
        if not fleet_id:
            if ship_id in fleet_manager.ship_to_fleet:
                fleet_id = fleet_manager.ship_to_fleet[ship_id]
            else:
                return CommandResult(
                    success=False,
                    message="No fleet specified and ship not in a fleet"
                )

        # Parse formation type
        try:
            formation_type = FormationType(formation_name.lower())
        except ValueError:
            available = ", ".join([f.value for f in FormationType])
            return CommandResult(
                success=False,
                message=f"Invalid formation type. Available: {available}"
            )

        # Build formation params
        params = {}
        if formation_type == FormationType.WALL:
            params["wall_columns"] = int(args.get("wall_columns", 3))
        elif formation_type == FormationType.ECHELON:
            params["echelon_angle"] = float(args.get("echelon_angle", 30.0))
        elif formation_type == FormationType.SPHERE:
            params["sphere_radius"] = float(args.get("sphere_radius", spacing * 2))

        success = fleet_manager.form_fleet(fleet_id, formation_type, spacing, **params)

        if success:
            return CommandResult(
                success=True,
                message=f"Fleet {fleet_id} forming {formation_type.value} formation",
                data={
                    "fleet_id": fleet_id,
                    "formation": formation_type.value,
                    "spacing": spacing
                }
            )
        else:
            return CommandResult(
                success=False,
                message="Failed to form fleet"
            )

    def cmd_fleet_break_formation(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Break fleet formation.

        Args:
            fleet_id: Fleet to break (optional, uses current ship's fleet)
        """
        fleet_id = args.get("fleet_id")

        if not fleet_id:
            if ship_id in fleet_manager.ship_to_fleet:
                fleet_id = fleet_manager.ship_to_fleet[ship_id]
            else:
                return CommandResult(
                    success=False,
                    message="No fleet specified and ship not in a fleet"
                )

        success = fleet_manager.break_formation(fleet_id)

        if success:
            return CommandResult(
                success=True,
                message=f"Fleet {fleet_id} formation broken",
                data={"fleet_id": fleet_id}
            )
        else:
            return CommandResult(
                success=False,
                message="Failed to break formation"
            )

    def cmd_fleet_target(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Designate target for entire fleet.

        Args:
            fleet_id: Fleet to command (optional, uses current ship's fleet)
            contact: Contact ID to target
        """
        fleet_id = args.get("fleet_id")
        contact_id = args.get("contact")

        if not contact_id:
            return CommandResult(
                success=False,
                message="Contact ID required"
            )

        if not fleet_id:
            if ship_id in fleet_manager.ship_to_fleet:
                fleet_id = fleet_manager.ship_to_fleet[ship_id]
            else:
                return CommandResult(
                    success=False,
                    message="No fleet specified and ship not in a fleet"
                )

        success = fleet_manager.set_fleet_target(fleet_id, contact_id)

        if success:
            return CommandResult(
                success=True,
                message=f"Fleet {fleet_id} targeting {contact_id}",
                data={"fleet_id": fleet_id, "contact_id": contact_id}
            )
        else:
            return CommandResult(
                success=False,
                message="Failed to set fleet target"
            )

    def cmd_fleet_fire(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Order fleet to fire on designated target.

        Args:
            fleet_id: Fleet to command (optional, uses current ship's fleet)
            volley: True for coordinated volley, False for independent fire (optional, default False)
        """
        fleet_id = args.get("fleet_id")
        volley = args.get("volley", False)

        if not fleet_id:
            if ship_id in fleet_manager.ship_to_fleet:
                fleet_id = fleet_manager.ship_to_fleet[ship_id]
            else:
                return CommandResult(
                    success=False,
                    message="No fleet specified and ship not in a fleet"
                )

        result = fleet_manager.fleet_fire(fleet_id, volley=volley)

        if result.get("success"):
            fire_type = "volley" if volley else "independent"
            return CommandResult(
                success=True,
                message=f"Fleet {fleet_id} engaging ({fire_type} fire)",
                data=result
            )
        else:
            return CommandResult(
                success=False,
                message=result.get("error", "Failed to order fleet fire")
            )

    def cmd_fleet_cease_fire(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Order fleet to cease fire.

        Args:
            fleet_id: Fleet to command (optional, uses current ship's fleet)
        """
        fleet_id = args.get("fleet_id")

        if not fleet_id:
            if ship_id in fleet_manager.ship_to_fleet:
                fleet_id = fleet_manager.ship_to_fleet[ship_id]
            else:
                return CommandResult(
                    success=False,
                    message="No fleet specified and ship not in a fleet"
                )

        # Broadcast cease fire to fleet
        if fleet_id in fleet_manager.fleets:
            fleet_manager._broadcast_to_fleet(fleet_id, "command", {
                "type": "cease_fire"
            })

            return CommandResult(
                success=True,
                message=f"Fleet {fleet_id} cease fire ordered",
                data={"fleet_id": fleet_id}
            )
        else:
            return CommandResult(
                success=False,
                message="Fleet not found"
            )

    def cmd_fleet_maneuver(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Execute coordinated fleet maneuver.

        Args:
            fleet_id: Fleet to command (optional, uses current ship's fleet)
            maneuver: Maneuver type (intercept, match_velocity, hold, evasive)
            position: Target position [x, y, z] (optional)
            velocity: Target velocity [vx, vy, vz] (optional)
        """
        fleet_id = args.get("fleet_id")
        maneuver_type = args.get("maneuver", "hold")
        position = args.get("position")
        velocity = args.get("velocity")

        if not fleet_id:
            if ship_id in fleet_manager.ship_to_fleet:
                fleet_id = fleet_manager.ship_to_fleet[ship_id]
            else:
                return CommandResult(
                    success=False,
                    message="No fleet specified and ship not in a fleet"
                )

        # Convert to numpy arrays if provided
        target_pos = np.array(position) if position else None
        target_vel = np.array(velocity) if velocity else None

        success = fleet_manager.fleet_maneuver(fleet_id, maneuver_type, target_pos, target_vel)

        if success:
            return CommandResult(
                success=True,
                message=f"Fleet {fleet_id} executing {maneuver_type} maneuver",
                data={
                    "fleet_id": fleet_id,
                    "maneuver": maneuver_type
                }
            )
        else:
            return CommandResult(
                success=False,
                message="Failed to execute fleet maneuver"
            )

    def cmd_fleet_status(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Get comprehensive fleet status.

        Args:
            fleet_id: Fleet to query (optional, uses current ship's fleet)
        """
        fleet_id = args.get("fleet_id")

        if not fleet_id:
            if ship_id in fleet_manager.ship_to_fleet:
                fleet_id = fleet_manager.ship_to_fleet[ship_id]
            else:
                # Return list of all fleets
                all_fleets = []
                for fid, fleet in fleet_manager.fleets.items():
                    all_fleets.append({
                        "fleet_id": fid,
                        "name": fleet.name,
                        "flagship": fleet.flagship_id,
                        "ship_count": len(fleet.ship_ids),
                        "status": fleet.status.value
                    })

                return CommandResult(
                    success=True,
                    message=f"Found {len(all_fleets)} fleets",
                    data={"fleets": all_fleets}
                )

        status = fleet_manager.get_fleet_status(fleet_id)

        if status:
            return CommandResult(
                success=True,
                message=f"Fleet {fleet_id} status",
                data=status
            )
        else:
            return CommandResult(
                success=False,
                message="Fleet not found"
            )

    def cmd_fleet_tactical(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Get fleet tactical summary.

        Args:
            fleet_id: Fleet to query (optional, uses current ship's fleet)
        """
        fleet_id = args.get("fleet_id")

        if not fleet_id:
            if ship_id in fleet_manager.ship_to_fleet:
                fleet_id = fleet_manager.ship_to_fleet[ship_id]
            else:
                return CommandResult(
                    success=False,
                    message="No fleet specified and ship not in a fleet"
                )

        tactical = fleet_manager.get_fleet_tactical_summary(fleet_id)

        if tactical:
            return CommandResult(
                success=True,
                message=f"Fleet {fleet_id} tactical summary",
                data=tactical
            )
        else:
            return CommandResult(
                success=False,
                message="Fleet not found"
            )

    def cmd_share_contact(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Share a sensor contact with fleet via tactical data link.

        Args:
            contact: Contact ID to share
            hostile: Mark as hostile (optional, default False)
        """
        contact_id = args.get("contact")
        is_hostile = args.get("hostile", False)

        if not contact_id:
            return CommandResult(
                success=False,
                message="Contact ID required"
            )

        # Get contact from ship's sensors
        if not hasattr(fleet_manager, "simulator") or not fleet_manager.simulator:
            return CommandResult(
                success=False,
                message="Simulator not available"
            )

        ship = fleet_manager.simulator.ships.get(ship_id)
        if not ship:
            return CommandResult(
                success=False,
                message="Ship not found"
            )

        sensors = ship.systems.get("sensors")
        if not sensors:
            return CommandResult(
                success=False,
                message="Ship has no sensors"
            )

        # Get contact data
        contact = sensors.get_contact(contact_id) if hasattr(sensors, "get_contact") else None
        if not contact:
            return CommandResult(
                success=False,
                message="Contact not found"
            )

        # Extract position and velocity
        pos = contact.get("position", {})
        vel = contact.get("velocity", {})
        position = np.array([pos.get("x", 0), pos.get("y", 0), pos.get("z", 0)])
        velocity = np.array([vel.get("x", 0), vel.get("y", 0), vel.get("z", 0)])

        # Share contact
        success = fleet_manager.share_contact(
            contact_id=contact_id,
            reporting_ship=ship_id,
            position=position,
            velocity=velocity,
            classification=contact.get("classification", "unknown"),
            confidence=contact.get("confidence", 0.5),
            is_hostile=is_hostile
        )

        if success:
            return CommandResult(
                success=True,
                message=f"Contact {contact_id} shared with fleet",
                data={"contact_id": contact_id, "hostile": is_hostile}
            )
        else:
            return CommandResult(
                success=False,
                message="Failed to share contact"
            )

    # Register all commands
    dispatcher.register_command("fleet_create", cmd_fleet_create)
    dispatcher.register_command("fleet_add_ship", cmd_fleet_add_ship)
    dispatcher.register_command("fleet_form", cmd_fleet_form)
    dispatcher.register_command("fleet_break_formation", cmd_fleet_break_formation)
    dispatcher.register_command("fleet_target", cmd_fleet_target)
    dispatcher.register_command("fleet_fire", cmd_fleet_fire)
    dispatcher.register_command("fleet_cease_fire", cmd_fleet_cease_fire)
    dispatcher.register_command("fleet_maneuver", cmd_fleet_maneuver)
    dispatcher.register_command("fleet_status", cmd_fleet_status)
    dispatcher.register_command("fleet_tactical", cmd_fleet_tactical)
    dispatcher.register_command("share_contact", cmd_share_contact)

    logger.info("Fleet commands registered")
