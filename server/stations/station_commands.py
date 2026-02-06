"""
Station management commands.

Provides commands for clients to claim/release stations, check status,
and manage their session.
"""

from typing import Dict, Any, Optional, Callable, Iterable, Mapping, List
import logging

from .station_manager import StationManager
from .station_types import StationType, PermissionLevel
from .station_dispatch import CommandResult
from .crew_system import CrewManager, StationSkill

logger = logging.getLogger(__name__)


def register_station_commands(
    dispatcher,
    station_manager: StationManager,
    crew_manager: Optional[CrewManager] = None,
    ship_provider: Optional[Callable[[], Iterable[Any]]] = None,
):
    """
    Register station management commands with the dispatcher.

    Args:
        dispatcher: StationAwareDispatcher instance
        station_manager: StationManager instance
        ship_provider: Callable returning iterable of ships or ship registry
    """

    def _format_ship_list(ships: Iterable[Any]) -> List[Dict[str, Any]]:
        ship_entries: List[Dict[str, Any]] = []
        if isinstance(ships, Mapping):
            items = ships.items()
        else:
            items = ((None, ship) for ship in ships)

        for ship_id, ship in items:
            if isinstance(ship, str):
                ship_entries.append({"id": ship})
                continue

            resolved_id = ship_id or getattr(ship, "id", None)
            if not resolved_id:
                continue

            entry = {"id": resolved_id}
            name = getattr(ship, "name", None)
            if name:
                entry["name"] = name
            class_type = getattr(ship, "class_type", None)
            if class_type:
                entry["class"] = class_type
            faction = getattr(ship, "faction", None)
            if faction:
                entry["faction"] = faction
            ship_entries.append(entry)

        return ship_entries

    def _resolve_ship(target_ship_id: str):
        ships = ship_provider() if ship_provider else []
        if isinstance(ships, Mapping):
            return ships.get(target_ship_id)
        for ship in ships:
            if getattr(ship, "id", None) == target_ship_id:
                return ship
        return None

    def cmd_register_client(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Register a new client (called automatically on connection).

        Args:
            player_name: Display name for the player
        """
        player_name = args.get("player_name", f"Player_{client_id}")

        try:
            session = station_manager.register_client(client_id, player_name)
            return CommandResult(
                success=True,
                message=f"Client registered as {player_name}",
                data={
                    "client_id": client_id,
                    "player_name": player_name,
                    "session": session.to_dict()
                }
            )
        except Exception as e:
            logger.error(f"Error registering client {client_id}: {e}")
            return CommandResult(
                success=False,
                message=f"Registration failed: {str(e)}"
            )

    def cmd_assign_ship(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Assign client to a ship.

        Args:
            ship: Target ship ID
        """
        target_ship = args.get("ship", ship_id)

        if not target_ship:
            return CommandResult(
                success=False,
                message="Ship ID required"
            )

        success = station_manager.assign_to_ship(client_id, target_ship)

        if success:
            return CommandResult(
                success=True,
                message=f"Assigned to ship {target_ship}",
                data={"ship_id": target_ship}
            )
        else:
            return CommandResult(
                success=False,
                message="Failed to assign to ship"
            )

    def cmd_claim_station(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Claim a station on the assigned ship.

        Args:
            station: Station name (captain, helm, tactical, ops, engineering, comms)
        """
        station_name = args.get("station")

        if not station_name:
            return CommandResult(
                success=False,
                message="Station name required"
            )

        # Parse station type
        try:
            station = StationType(station_name.lower())
        except ValueError:
            valid_stations = [s.value for s in StationType]
            return CommandResult(
                success=False,
                message=f"Invalid station. Valid stations: {', '.join(valid_stations)}"
            )

        # Check if client is assigned to a ship
        session = station_manager.get_session(client_id)
        if not session or not session.ship_id:
            return CommandResult(
                success=False,
                message="Not assigned to a ship. Use assign_ship first."
            )

        # Attempt to claim
        success, message = station_manager.claim_station(
            client_id,
            session.ship_id,
            station,
            PermissionLevel.CREW
        )

        if success:
            from .station_types import get_station_commands
            available_commands = get_station_commands(station)

            return CommandResult(
                success=True,
                message=message,
                data={
                    "station": station.value,
                    "ship_id": session.ship_id,
                    "available_commands": list(available_commands)
                }
            )
        else:
            return CommandResult(
                success=False,
                message=message
            )

    def cmd_release_station(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Release current station claim.
        """
        session = station_manager.get_session(client_id)

        if not session or not session.station:
            return CommandResult(
                success=False,
                message="No station claimed"
            )

        success, message = station_manager.release_station(
            client_id,
            session.ship_id,
            session.station
        )

        return CommandResult(
            success=success,
            message=message
        )

    def cmd_station_status(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Get status of all stations on current ship.
        """
        session = station_manager.get_session(client_id)

        if not session or not session.ship_id:
            return CommandResult(
                success=False,
                message="Not assigned to a ship"
            )

        stations = station_manager.get_ship_stations(session.ship_id)

        status_list = []
        for station_type, player_name in stations.items():
            status_list.append({
                "station": station_type.value,
                "claimed": player_name is not None,
                "player": player_name
            })

        return CommandResult(
            success=True,
            message="Station status",
            data={
                "ship_id": session.ship_id,
                "stations": status_list
            }
        )

    def cmd_my_status(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Get current client's session status.
        """
        session = station_manager.get_session(client_id)

        if not session:
            return CommandResult(
                success=False,
                message="Client not registered"
            )

        data = session.to_dict()

        # Add available commands if station is claimed
        if session.station:
            from .station_types import get_station_commands
            available_commands = get_station_commands(session.station)
            data["available_commands"] = list(available_commands)

        return CommandResult(
            success=True,
            message="Session status",
            data=data
        )

    def cmd_list_ships(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        List all ships in the simulation.
        """
        ships = ship_provider() if ship_provider else []
        ship_entries = _format_ship_list(ships)

        return CommandResult(
            success=True,
            message="Ships list",
            data={
                "ships": ship_entries
            }
        )

    def cmd_set_power_profile(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Apply an engineering power profile to the assigned ship.
        """
        session = station_manager.get_session(client_id)
        if not session or not session.ship_id:
            return CommandResult(
                success=False,
                message="Not assigned to a ship"
            )

        target_ship_id = args.get("ship") or ship_id or session.ship_id
        if not target_ship_id:
            return CommandResult(
                success=False,
                message="Ship ID required"
            )

        profile = args.get("profile") or args.get("mode")
        if not profile:
            return CommandResult(
                success=False,
                message="Profile name required"
            )

        ship = _resolve_ship(target_ship_id)
        if not ship:
            return CommandResult(
                success=False,
                message=f"Ship not found: {target_ship_id}"
            )

        result = ship.command("set_power_profile", {"profile": profile})
        if "error" in result:
            return CommandResult(
                success=False,
                message=result["error"],
                data=result
            )

        return CommandResult(
            success=True,
            message=f"Power profile '{profile}' applied",
            data=result
        )

    def _cmd_power_passthrough(client_id: str, ship_id: str, args: Dict[str, Any], command_name: str, success_message: str) -> CommandResult:
        session = station_manager.get_session(client_id)
        if not session or not session.ship_id:
            return CommandResult(
                success=False,
                message="Not assigned to a ship"
            )

        target_ship_id = args.get("ship") or ship_id or session.ship_id
        if not target_ship_id:
            return CommandResult(
                success=False,
                message="Ship ID required"
            )

        ship = _resolve_ship(target_ship_id)
        if not ship:
            return CommandResult(
                success=False,
                message=f"Ship not found: {target_ship_id}"
            )

        payload = {k: v for k, v in args.items() if k != "ship"}
        result = ship.command(command_name, payload)
        if "error" in result:
            return CommandResult(
                success=False,
                message=result["error"],
                data=result
            )

        return CommandResult(
            success=True,
            message=success_message,
            data=result
        )

    def cmd_get_power_profiles(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        List available engineering power profiles for the assigned ship.
        """
        session = station_manager.get_session(client_id)
        if not session or not session.ship_id:
            return CommandResult(
                success=False,
                message="Not assigned to a ship"
            )

        target_ship_id = args.get("ship") or ship_id or session.ship_id
        if not target_ship_id:
            return CommandResult(
                success=False,
                message="Ship ID required"
            )

        ship = _resolve_ship(target_ship_id)
        if not ship:
            return CommandResult(
                success=False,
                message=f"Ship not found: {target_ship_id}"
            )

        result = ship.command("get_power_profiles", {})
        if "error" in result:
            return CommandResult(
                success=False,
                message=result["error"],
                data=result
            )

        return CommandResult(
            success=True,
            message="Power profiles retrieved",
            data=result
        )

    def cmd_set_power_allocation(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """Set engineering power allocation for the assigned ship."""
        return _cmd_power_passthrough(
            client_id,
            ship_id,
            args,
            command_name="set_power_allocation",
            success_message="Power allocation updated",
        )

    def cmd_get_power_telemetry(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """Get detailed engineering telemetry for the assigned ship."""
        return _cmd_power_passthrough(
            client_id,
            ship_id,
            args,
            command_name="get_power_telemetry",
            success_message="Power telemetry retrieved",
        )

    def cmd_get_draw_profile(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """Get grouped draw profile for enabled systems by configured power bus."""
        return _cmd_power_passthrough(
            client_id,
            ship_id,
            args,
            command_name="get_draw_profile",
            success_message="Power draw profile retrieved",
        )

    def cmd_heartbeat(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Heartbeat to keep session alive.
        """
        station_manager.update_activity(client_id)

        session = station_manager.get_session(client_id)

        return CommandResult(
            success=True,
            message="Heartbeat received",
            data={
                "client_id": client_id,
                "last_heartbeat": session.last_heartbeat.isoformat() if session else None
            }
        )

    def cmd_fleet_status(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Get status of all ships and their station claims.
        """
        all_ships = station_manager.get_all_ships_status()
        all_clients = station_manager.get_all_clients()

        return CommandResult(
            success=True,
            message="Fleet status",
            data={
                "ships": {
                    ship_id: [
                        {"station": st.value, "player": player}
                        for st, player in stations.items()
                        if player is not None
                    ]
                    for ship_id, stations in all_ships.items()
                },
                "clients": [
                    {
                        "client_id": c.client_id,
                        "player_name": c.player_name,
                        "ship_id": c.ship_id,
                        "station": c.station.value if c.station else None
                    }
                    for c in all_clients
                ]
            }
        )

    def cmd_promote_to_officer(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Promote a crew member to OFFICER rank (CAPTAIN only).

        Args:
            target_client: Client ID to promote
        """
        session = station_manager.get_session(client_id)

        # Only CAPTAIN can promote
        if not session or session.permission_level != PermissionLevel.CAPTAIN:
            return CommandResult(
                success=False,
                message="Only CAPTAIN can promote crew members"
            )

        target_client = args.get("target_client")
        if not target_client:
            return CommandResult(
                success=False,
                message="target_client required"
            )

        target_session = station_manager.get_session(target_client)
        if not target_session:
            return CommandResult(
                success=False,
                message=f"Client {target_client} not found"
            )

        if target_session.ship_id != session.ship_id:
            return CommandResult(
                success=False,
                message="Can only promote crew on your ship"
            )

        if not target_session.station:
            return CommandResult(
                success=False,
                message="Target must have a station claimed first"
            )

        # Update permission level
        target_session.permission_level = PermissionLevel.OFFICER

        # Update claim if exists
        if target_session.ship_id and target_session.station:
            ship_claims = station_manager.claims.get(target_session.ship_id, {})
            if target_session.station in ship_claims:
                ship_claims[target_session.station].permission_level = PermissionLevel.OFFICER

        logger.info(f"Client {target_client} promoted to OFFICER by {client_id}")

        return CommandResult(
            success=True,
            message=f"{target_session.player_name} promoted to OFFICER",
            data={
                "target_client": target_client,
                "station": target_session.station.value,
                "permission_level": "OFFICER"
            }
        )

    def cmd_demote_from_officer(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Demote an OFFICER back to CREW (CAPTAIN only).

        Args:
            target_client: Client ID to demote
        """
        session = station_manager.get_session(client_id)

        # Only CAPTAIN can demote
        if not session or session.permission_level != PermissionLevel.CAPTAIN:
            return CommandResult(
                success=False,
                message="Only CAPTAIN can demote crew members"
            )

        target_client = args.get("target_client")
        if not target_client:
            return CommandResult(
                success=False,
                message="target_client required"
            )

        target_session = station_manager.get_session(target_client)
        if not target_session:
            return CommandResult(
                success=False,
                message=f"Client {target_client} not found"
            )

        if target_session.ship_id != session.ship_id:
            return CommandResult(
                success=False,
                message="Can only demote crew on your ship"
            )

        # Update permission level
        target_session.permission_level = PermissionLevel.CREW

        # Update claim if exists
        if target_session.ship_id and target_session.station:
            ship_claims = station_manager.claims.get(target_session.ship_id, {})
            if target_session.station in ship_claims:
                ship_claims[target_session.station].permission_level = PermissionLevel.CREW

        logger.info(f"Client {target_client} demoted to CREW by {client_id}")

        return CommandResult(
            success=True,
            message=f"{target_session.player_name} demoted to CREW",
            data={
                "target_client": target_client,
                "permission_level": "CREW"
            }
        )

    def cmd_transfer_station(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Transfer station control to another crew member (OFFICER+ only).

        Args:
            target_client: Client ID to transfer to
        """
        session = station_manager.get_session(client_id)

        # Only OFFICER or CAPTAIN can transfer
        if not session or session.permission_level.value < PermissionLevel.OFFICER.value:
            return CommandResult(
                success=False,
                message="Only OFFICER or CAPTAIN can transfer station control"
            )

        if not session.station:
            return CommandResult(
                success=False,
                message="No station to transfer"
            )

        target_client = args.get("target_client")
        if not target_client:
            return CommandResult(
                success=False,
                message="target_client required"
            )

        target_session = station_manager.get_session(target_client)
        if not target_session:
            return CommandResult(
                success=False,
                message=f"Client {target_client} not found"
            )

        if target_session.ship_id != session.ship_id:
            return CommandResult(
                success=False,
                message="Can only transfer to crew on your ship"
            )

        # Release current station
        current_station = session.station
        station_manager.release_station(client_id, session.ship_id, current_station)

        # Claim for target
        success, message = station_manager.claim_station(
            target_client,
            target_session.ship_id,
            current_station,
            PermissionLevel.CREW
        )

        if success:
            logger.info(f"Station {current_station.value} transferred from {client_id} to {target_client}")
            return CommandResult(
                success=True,
                message=f"Station {current_station.value} transferred to {target_session.player_name}",
                data={
                    "station": current_station.value,
                    "from_client": client_id,
                    "to_client": target_client
                }
            )
        else:
            return CommandResult(
                success=False,
                message=f"Transfer failed: {message}"
            )

    def cmd_crew_status(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Get crew status for current ship.
        """
        if not crew_manager:
            return CommandResult(
                success=False,
                message="Crew system not available"
            )

        session = station_manager.get_session(client_id)
        if not session or not session.ship_id:
            return CommandResult(
                success=False,
                message="Not assigned to a ship"
            )

        crew_list = crew_manager.get_ship_crew(session.ship_id)

        return CommandResult(
            success=True,
            message=f"Crew status for {session.ship_id}",
            data={
                "ship_id": session.ship_id,
                "crew_count": len(crew_list),
                "crew": [member.to_dict() for member in crew_list]
            }
        )

    def cmd_my_crew_status(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Get personal crew status (skills, fatigue, performance).
        """
        if not crew_manager:
            return CommandResult(
                success=False,
                message="Crew system not available"
            )

        session = station_manager.get_session(client_id)
        if not session or not session.ship_id:
            return CommandResult(
                success=False,
                message="Not assigned to a ship"
            )

        crew_member = crew_manager.get_crew_by_client(client_id, session.ship_id)

        if not crew_member:
            return CommandResult(
                success=False,
                message="No crew member assigned to your client"
            )

        return CommandResult(
            success=True,
            message=f"Status for {crew_member.name}",
            data=crew_member.to_dict()
        )

    def cmd_crew_rest(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """
        Put crew member on rest (reduces fatigue, requires replacement).
        """
        if not crew_manager:
            return CommandResult(
                success=False,
                message="Crew system not available"
            )

        session = station_manager.get_session(client_id)
        if not session or not session.ship_id:
            return CommandResult(
                success=False,
                message="Not assigned to a ship"
            )

        crew_member = crew_manager.get_crew_by_client(client_id, session.ship_id)

        if not crew_member:
            return CommandResult(
                success=False,
                message="No crew member assigned"
            )

        hours = float(args.get("hours", 4.0))
        crew_member.rest(hours)

        return CommandResult(
            success=True,
            message=f"{crew_member.name} rested for {hours} hours",
            data={
                "crew_id": crew_member.crew_id,
                "fatigue": round(crew_member.fatigue, 2),
                "stress": round(crew_member.stress, 2)
            }
        )

    # Register all commands
    # These bypass normal permission checks since they're meta-commands
    dispatcher.register_command(
        "register_client",
        cmd_register_client,
        requires_ship=False,
        bypass_permission_check=True
    )

    dispatcher.register_command(
        "assign_ship",
        cmd_assign_ship,
        requires_ship=False,
        bypass_permission_check=True
    )

    dispatcher.register_command(
        "claim_station",
        cmd_claim_station,
        requires_ship=False,
        bypass_permission_check=True
    )

    dispatcher.register_command(
        "release_station",
        cmd_release_station,
        requires_ship=False,
        bypass_permission_check=True
    )

    dispatcher.register_command(
        "station_status",
        cmd_station_status,
        requires_ship=False,
        bypass_permission_check=True
    )

    dispatcher.register_command(
        "my_status",
        cmd_my_status,
        requires_ship=False,
        bypass_permission_check=True
    )

    dispatcher.register_command(
        "list_ships",
        cmd_list_ships,
        requires_ship=False,
        bypass_permission_check=True
    )

    dispatcher.register_command(
        "set_power_profile",
        cmd_set_power_profile,
        station=StationType.ENGINEERING
    )

    dispatcher.register_command(
        "get_power_profiles",
        cmd_get_power_profiles,
        station=StationType.ENGINEERING
    )

    dispatcher.register_command(
        "set_power_allocation",
        cmd_set_power_allocation,
        station=StationType.ENGINEERING
    )

    dispatcher.register_command(
        "get_power_telemetry",
        cmd_get_power_telemetry,
        station=StationType.ENGINEERING
    )

    dispatcher.register_command(
        "get_draw_profile",
        cmd_get_draw_profile,
        station=StationType.ENGINEERING
    )

    dispatcher.register_command(
        "heartbeat",
        cmd_heartbeat,
        requires_ship=False,
        bypass_permission_check=True
    )

    dispatcher.register_command(
        "fleet_status",
        cmd_fleet_status,
        requires_ship=False,
        bypass_permission_check=True
    )

    # Officer-related commands (require station checks)
    dispatcher.register_command(
        "promote_to_officer",
        cmd_promote_to_officer,
        station=StationType.CAPTAIN,
        requires_ship=False
    )

    dispatcher.register_command(
        "demote_from_officer",
        cmd_demote_from_officer,
        station=StationType.CAPTAIN,
        requires_ship=False
    )

    dispatcher.register_command(
        "transfer_station",
        cmd_transfer_station,
        requires_ship=False,
        bypass_permission_check=True  # Has internal permission check
    )

    # Crew management commands
    if crew_manager:
        dispatcher.register_command(
            "crew_status",
            cmd_crew_status,
            requires_ship=False,
            bypass_permission_check=True
        )

        dispatcher.register_command(
            "my_crew_status",
            cmd_my_crew_status,
            requires_ship=False,
            bypass_permission_check=True
        )

        dispatcher.register_command(
            "crew_rest",
            cmd_crew_rest,
            requires_ship=False,
            bypass_permission_check=True
        )

        logger.info("Registered 15 station management commands (with crew system)")
    else:
        logger.info("Registered 12 station management commands")
