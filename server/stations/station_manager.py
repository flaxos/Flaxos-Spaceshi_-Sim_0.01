"""
Station claim management and client session tracking.

Manages which clients control which stations on each ship, enforcing
permissions and handling claim lifecycle.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Set, List, Tuple
from datetime import datetime
import logging
import threading

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
        self.claim_timeout_seconds = 900  # 15 min inactive = auto-release
        self.allow_multiple_stations = False  # One station per client
        # Counter for generating client IDs
        self._next_client_id = 1
        # Lock to prevent race conditions in captain election
        self._election_lock = threading.Lock()

    def generate_client_id(self) -> str:
        """Generate a unique client ID"""
        client_id = f"client_{self._next_client_id}"
        self._next_client_id += 1
        return client_id

    def register_client(self, client_id: str, player_name: str) -> ClientSession:
        """
        Register a new client connection.

        Idempotent: if the client is already registered, returns the existing
        session (preserving ship assignment and station claim) instead of
        creating a blank one.

        Args:
            client_id: Unique client identifier
            player_name: Display name for the player

        Returns:
            ClientSession object
        """
        existing = self.sessions.get(client_id)
        if existing is not None:
            existing.player_name = player_name
            logger.info(f"Client re-registered (session preserved): {client_id} ({player_name})")
            return existing

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

        # Already assigned to this ship — preserve existing station claim
        if session.ship_id == ship_id:
            logger.info(
                f"Client {client_id} already assigned to ship {ship_id}"
                f" (station={session.station.value if session.station else 'none'}"
                f") — skipping re-assignment"
            )
            # Ensure ship's station tracking is initialized
            if ship_id not in self.claims:
                self.claims[ship_id] = {}
            return True

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

        # Ensure captains always receive captain-level permissions
        if station == StationType.CAPTAIN:
            permission_level = PermissionLevel.CAPTAIN

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
            if (
                not requester_session
                or requester_session.permission_level.value < PermissionLevel.CAPTAIN.value
            ):
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

    def migrate_session(self, old_client_id: str, new_client_id: str) -> bool:
        """
        Migrate an old client session's state to a new client ID.

        Used when a ws_bridge TCP connection drops and reconnects: the
        reconnected socket gets a new client_id from generate_client_id(),
        but should inherit the old session's ship assignment and station
        claim so the player doesn't lose their seat.

        Args:
            old_client_id: Previous client ID whose session state to transfer
            new_client_id: New client ID to receive the state

        Returns:
            True if migration succeeded, False if old session not found
        """
        old_session = self.sessions.get(old_client_id)
        new_session = self.sessions.get(new_client_id)

        if not old_session:
            logger.info(f"Session migration: old session {old_client_id} not found")
            return False

        if not new_session:
            logger.warning(f"Session migration: new session {new_client_id} not found")
            return False

        # Transfer ship and station state
        new_session.ship_id = old_session.ship_id
        new_session.station = old_session.station
        new_session.permission_level = old_session.permission_level
        new_session.player_name = old_session.player_name

        # Update station claims to point to the new client_id
        if old_session.ship_id and old_session.station:
            ship_claims = self.claims.get(old_session.ship_id, {})
            claim = ship_claims.get(old_session.station)
            if claim and claim.client_id == old_client_id:
                claim.client_id = new_client_id
                logger.info(
                    f"Migrated station claim {old_session.station.value} "
                    f"on ship {old_session.ship_id}: "
                    f"{old_client_id} -> {new_client_id}"
                )

        # Remove old session (don't call unregister_client — that releases
        # the station claim, which we just transferred)
        del self.sessions[old_client_id]

        logger.info(
            f"Session migrated: {old_client_id} -> {new_client_id} "
            f"(ship={new_session.ship_id}, "
            f"station={new_session.station.value if new_session.station else 'none'})"
        )
        return True

    def purge_claims_for_missing_ships(self, active_ship_ids: set) -> List[str]:
        """
        Remove station claims that reference ships no longer in the simulation.

        Called after a scenario reload to clean up stale claims from the
        previous simulation. Also clears ship_id/station on affected sessions.

        Args:
            active_ship_ids: Set of ship IDs currently in the simulation.

        Returns:
            List of ship IDs whose claims were purged.
        """
        stale_ship_ids = [
            ship_id for ship_id in self.claims
            if ship_id not in active_ship_ids
        ]

        for ship_id in stale_ship_ids:
            del self.claims[ship_id]

        # Clear session state for clients that were on purged ships
        for session in self.sessions.values():
            if session.ship_id and session.ship_id not in active_ship_ids:
                logger.info(
                    f"Clearing stale ship assignment for {session.client_id} "
                    f"(was on {session.ship_id})"
                )
                session.ship_id = None
                session.station = None
                session.permission_level = PermissionLevel.OBSERVER

        if stale_ship_ids:
            logger.info(f"Purged claims for {len(stale_ship_ids)} removed ships: {stale_ship_ids}")
        return stale_ship_ids

    def elect_new_captain(self, ship_id: str) -> Optional[str]:
        """
        Auto-promote the longest-connected active client on a ship to CAPTAIN.

        Thread-safe: acquires ``_election_lock`` to prevent race conditions
        when two clients disconnect simultaneously on the same ship.

        Called when the current captain disconnects or releases their station,
        so that pause, time-scale, and scenario-load commands remain available
        to the crew.

        Args:
            ship_id: Ship that lost its captain

        Returns:
            client_id of the newly promoted captain, or None if no eligible
            client exists on the ship.
        """
        with self._election_lock:
            # Gather clients on this ship that are still active (have a session)
            candidates = [
                s for s in self.sessions.values()
                if s.ship_id == ship_id
            ]
            if not candidates:
                logger.info(f"No clients on ship {ship_id} to promote to captain")
                return None

            # Pick the longest-connected session (earliest connected_at)
            candidates.sort(key=lambda s: s.connected_at)
            successor = candidates[0]

            # Release their current station first (if any) so claim_station
            # does not reject with "already controlling X"
            if successor.station:
                self.release_station(successor.client_id, ship_id, successor.station)

            success, msg = self.claim_station(
                successor.client_id,
                ship_id,
                StationType.CAPTAIN,
                PermissionLevel.CAPTAIN,
            )
            if success:
                logger.info(
                    f"Captain succession on ship {ship_id}: "
                    f"{successor.client_id} ({successor.player_name}) promoted to CAPTAIN"
                )
                return successor.client_id

            logger.warning(
                f"Captain succession failed on ship {ship_id}: {msg}"
            )
            return None

    def get_all_clients(self) -> List[ClientSession]:
        """
        Get all connected clients.

        Returns:
            List of all client sessions
        """
        return list(self.sessions.values())
