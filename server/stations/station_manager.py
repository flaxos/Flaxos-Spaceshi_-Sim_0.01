"""
Station claim management and client session tracking.

Manages which clients control which stations on each ship, enforcing
permissions and handling claim lifecycle.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Set, List, Tuple
from datetime import datetime
import logging

from .station_types import StationType, PermissionLevel, get_station_commands

logger = logging.getLogger(__name__)


@dataclass
class StationClaim:
    """Represents a client's claim on a station"""
    station: StationType
    client_id: str
    ship_id: str
    permission_level: PermissionLevel
    claimed_at: datetime
    last_activity: datetime
    is_active: bool = True

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            "station": self.station.value,
            "client_id": self.client_id,
            "ship_id": self.ship_id,
            "permission_level": self.permission_level.name,
            "claimed_at": self.claimed_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "is_active": self.is_active,
        }


@dataclass
class ClientSession:
    """Tracks a connected client"""
    client_id: str
    player_name: str
    ship_id: Optional[str] = None
    station: Optional[StationType] = None
    permission_level: PermissionLevel = PermissionLevel.OBSERVER
    connected_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            "client_id": self.client_id,
            "player_name": self.player_name,
            "ship_id": self.ship_id,
            "station": self.station.value if self.station else None,
            "permission_level": self.permission_level.name,
            "connected_at": self.connected_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat(),
        }


class StationManager:
    """Manages station claims across all ships"""

    def __init__(self):
        # ship_id -> station -> claim
        self.claims: Dict[str, Dict[StationType, StationClaim]] = {}
        # client_id -> session
        self.sessions: Dict[str, ClientSession] = {}
        # Configuration
        self.claim_timeout_seconds = 300  # 5 min inactive = auto-release
        self.allow_multiple_stations = False  # One station per client
        # Counter for generating client IDs
        self._next_client_id = 1

    def generate_client_id(self) -> str:
        """Generate a unique client ID"""
        client_id = f"client_{self._next_client_id}"
        self._next_client_id += 1
        return client_id

    def register_client(self, client_id: str, player_name: str) -> ClientSession:
        """
        Register a new client connection.

        Args:
            client_id: Unique client identifier
            player_name: Display name for the player

        Returns:
            ClientSession object
        """
        session = ClientSession(
            client_id=client_id,
            player_name=player_name,
        )
        self.sessions[client_id] = session
        logger.info(f"Client registered: {client_id} ({player_name})")
        return session

    def unregister_client(self, client_id: str):
        """
        Client disconnected - release their claims.

        Args:
            client_id: Client to unregister
        """
        if client_id in self.sessions:
            session = self.sessions[client_id]
            if session.ship_id and session.station:
                self.release_station(client_id, session.ship_id, session.station)
            logger.info(f"Client unregistered: {client_id} ({session.player_name})")
            del self.sessions[client_id]

    def get_session(self, client_id: str) -> Optional[ClientSession]:
        """
        Get a client's session.

        Args:
            client_id: Client to look up

        Returns:
            ClientSession if found, None otherwise
        """
        return self.sessions.get(client_id)

    def assign_to_ship(self, client_id: str, ship_id: str) -> bool:
        """
        Assign a client to a ship (but not yet to a station).

        Args:
            client_id: Client to assign
            ship_id: Ship to assign to

        Returns:
            True if successful
        """
        if client_id not in self.sessions:
            logger.warning(f"Cannot assign unknown client {client_id} to ship {ship_id}")
            return False

        session = self.sessions[client_id]

        # Release any existing station claim on old ship
        if session.ship_id and session.station:
            self.release_station(client_id, session.ship_id, session.station)

        session.ship_id = ship_id
        session.station = None
        session.permission_level = PermissionLevel.OBSERVER

        # Initialize ship's station tracking if needed
        if ship_id not in self.claims:
            self.claims[ship_id] = {}

        logger.info(f"Client {client_id} assigned to ship {ship_id}")
        return True

    def claim_station(
        self,
        client_id: str,
        ship_id: str,
        station: StationType,
        permission_level: PermissionLevel = PermissionLevel.CREW
    ) -> Tuple[bool, str]:
        """
        Attempt to claim a station on a ship.

        Args:
            client_id: Client claiming the station
            ship_id: Ship the station is on
            station: Station type to claim
            permission_level: Permission level to grant

        Returns:
            Tuple of (success, message)
        """
        if client_id not in self.sessions:
            return False, "Client not registered"

        session = self.sessions[client_id]

        if session.ship_id != ship_id:
            return False, "Client not assigned to this ship"

        # Check if client already has a station (if not allowed multiple)
        if not self.allow_multiple_stations and session.station:
            if session.station != station:
                return False, f"Already controlling {session.station.value}. Release it first."

        # Initialize ship's claims if needed
        if ship_id not in self.claims:
            self.claims[ship_id] = {}

        ship_claims = self.claims[ship_id]

        # Check if station is already claimed
        if station in ship_claims:
            existing = ship_claims[station]
            if existing.is_active and existing.client_id != client_id:
                # Station is taken
                other_session = self.sessions.get(existing.client_id)
                other_name = other_session.player_name if other_session else "Unknown"
                return False, f"Station {station.value} is controlled by {other_name}"

        # Claim the station
        now = datetime.now()
        claim = StationClaim(
            station=station,
            client_id=client_id,
            ship_id=ship_id,
            permission_level=permission_level,
            claimed_at=now,
            last_activity=now,
            is_active=True,
        )

        ship_claims[station] = claim
        session.station = station
        session.permission_level = permission_level

        logger.info(f"Client {client_id} ({session.player_name}) claimed {station.value} on ship {ship_id}")
        return True, f"Station {station.value} claimed successfully"

    def release_station(
        self,
        client_id: str,
        ship_id: str,
        station: StationType
    ) -> Tuple[bool, str]:
        """
        Release a station claim.

        Args:
            client_id: Client releasing the station
            ship_id: Ship the station is on
            station: Station to release

        Returns:
            Tuple of (success, message)
        """
        if ship_id not in self.claims:
            return False, "Ship not found"

        ship_claims = self.claims[ship_id]

        if station not in ship_claims:
            return False, "Station not claimed"

        claim = ship_claims[station]

        if claim.client_id != client_id:
            # Check if requester is Captain (can force release)
            requester_session = self.sessions.get(client_id)
            if not requester_session or requester_session.permission_level < PermissionLevel.CAPTAIN:
                return False, "You don't control this station"

        # Release the claim
        claim.is_active = False
        del ship_claims[station]

        # Update session
        if client_id in self.sessions:
            session = self.sessions[client_id]
            if session.station == station:
                session.station = None
                session.permission_level = PermissionLevel.OBSERVER

        logger.info(f"Client {client_id} released {station.value} on ship {ship_id}")
        return True, f"Station {station.value} released"

    def get_station_owner(self, ship_id: str, station: StationType) -> Optional[str]:
        """
        Get the client_id controlling a station, if any.

        Args:
            ship_id: Ship to check
            station: Station to check

        Returns:
            Client ID if station is claimed, None otherwise
        """
        if ship_id not in self.claims:
            return None
        if station not in self.claims[ship_id]:
            return None
        claim = self.claims[ship_id][station]
        return claim.client_id if claim.is_active else None

    def get_ship_stations(self, ship_id: str) -> Dict[StationType, Optional[str]]:
        """
        Get status of all stations on a ship.

        Args:
            ship_id: Ship to check

        Returns:
            Dictionary mapping stations to player names (or None if unclaimed)
        """
        result = {st: None for st in StationType}
        if ship_id in self.claims:
            for station, claim in self.claims[ship_id].items():
                if claim.is_active:
                    session = self.sessions.get(claim.client_id)
                    result[station] = session.player_name if session else claim.client_id
        return result

    def get_all_ships_status(self) -> Dict[str, Dict[StationType, Optional[str]]]:
        """
        Get station status for all ships.

        Returns:
            Dictionary mapping ship_id -> station status
        """
        result = {}
        for ship_id in self.claims.keys():
            result[ship_id] = self.get_ship_stations(ship_id)
        return result

    def can_issue_command(
        self,
        client_id: str,
        ship_id: str,
        command: str
    ) -> Tuple[bool, str]:
        """
        Check if a client can issue a specific command.

        Args:
            client_id: Client attempting the command
            ship_id: Ship to issue command to
            command: Command name

        Returns:
            Tuple of (allowed, reason)
        """
        if client_id not in self.sessions:
            return False, "Client not registered"

        session = self.sessions[client_id]

        if session.ship_id != ship_id:
            return False, "Not assigned to this ship"

        if not session.station:
            return False, "No station claimed - claim a station first"

        # Get commands available to this station
        available_commands = get_station_commands(session.station)

        if command in available_commands:
            return True, "OK"

        # Check if another station owns this command
        from .station_types import get_station_for_command, STATION_DEFINITIONS
        owning_station = get_station_for_command(command)

        # Check if client's station can override the owning station
        if owning_station and session.station:
            station_def = STATION_DEFINITIONS.get(session.station)
            if station_def and owning_station in station_def.can_override:
                logger.info(f"{session.station.value} overriding {owning_station.value} command: {command}")
                return True, f"Override: {session.station.value} executing {owning_station.value} command"

        if owning_station:
            return False, f"Command '{command}' requires {owning_station.value} station"

        return False, f"Unknown command: {command}"

    def update_activity(self, client_id: str):
        """
        Update last activity timestamp for a client.

        Args:
            client_id: Client to update
        """
        if client_id in self.sessions:
            self.sessions[client_id].last_heartbeat = datetime.now()

            session = self.sessions[client_id]
            if session.ship_id and session.station:
                ship_claims = self.claims.get(session.ship_id, {})
                if session.station in ship_claims:
                    ship_claims[session.station].last_activity = datetime.now()

    def cleanup_stale_claims(self) -> List[str]:
        """
        Release stations from inactive clients.

        Returns:
            List of client IDs that were cleaned up
        """
        now = datetime.now()
        stale_clients = []

        for client_id, session in list(self.sessions.items()):
            elapsed = (now - session.last_heartbeat).total_seconds()
            if elapsed > self.claim_timeout_seconds:
                stale_clients.append(client_id)

        for client_id in stale_clients:
            logger.info(f"Cleaning up stale client: {client_id}")
            self.unregister_client(client_id)

        return stale_clients

    def get_clients_on_ship(self, ship_id: str) -> List[ClientSession]:
        """
        Get all clients currently assigned to a ship.

        Args:
            ship_id: Ship to check

        Returns:
            List of client sessions on this ship
        """
        return [
            session for session in self.sessions.values()
            if session.ship_id == ship_id
        ]

    def get_all_clients(self) -> List[ClientSession]:
        """
        Get all connected clients.

        Returns:
            List of all client sessions
        """
        return list(self.sessions.values())
