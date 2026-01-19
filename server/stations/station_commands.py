"""
Station management commands.

Provides commands for clients to claim/release stations, check status,
and manage their session.
"""

from typing import Dict, Any
import logging

from .station_manager import StationManager
from .station_types import StationType, PermissionLevel
from .station_dispatch import CommandResult

logger = logging.getLogger(__name__)


def register_station_commands(dispatcher, station_manager: StationManager):
    """
    Register station management commands with the dispatcher.

    Args:
        dispatcher: StationAwareDispatcher instance
        station_manager: StationManager instance
    """

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
        # This would need access to the simulator
        # For now, return a placeholder
        return CommandResult(
            success=True,
            message="Ships list",
            data={
                "message": "Ship listing not yet implemented",
                "ships": []
            }
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

    # Register all commands
    # These bypass normal permission checks since they're meta-commands
    dispatcher.register_command(
        "register_client",
        cmd_register_client,
        bypass_permission_check=True
    )

    dispatcher.register_command(
        "assign_ship",
        cmd_assign_ship,
        bypass_permission_check=True
    )

    dispatcher.register_command(
        "claim_station",
        cmd_claim_station,
        bypass_permission_check=True
    )

    dispatcher.register_command(
        "release_station",
        cmd_release_station,
        bypass_permission_check=True
    )

    dispatcher.register_command(
        "station_status",
        cmd_station_status,
        bypass_permission_check=True
    )

    dispatcher.register_command(
        "my_status",
        cmd_my_status,
        bypass_permission_check=True
    )

    dispatcher.register_command(
        "list_ships",
        cmd_list_ships,
        bypass_permission_check=True
    )

    dispatcher.register_command(
        "heartbeat",
        cmd_heartbeat,
        bypass_permission_check=True
    )

    dispatcher.register_command(
        "fleet_status",
        cmd_fleet_status,
        bypass_permission_check=True
    )

    logger.info("Registered 9 station management commands")
