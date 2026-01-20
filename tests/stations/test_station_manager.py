"""Tests for station manager"""

import pytest
import time
from datetime import datetime, timedelta
from server.stations.station_manager import StationManager, ClientSession, StationClaim
from server.stations.station_types import StationType, PermissionLevel


@pytest.fixture
def manager():
    """Create a fresh StationManager for each test"""
    return StationManager()


def test_register_client(manager):
    """Test client registration"""
    client_id = manager.generate_client_id()
    session = manager.register_client(client_id, "test_player")

    assert session is not None
    assert session.client_id == client_id
    assert session.player_name == "test_player"
    assert session.ship_id is None
    assert session.station is None


def test_register_multiple_clients(manager):
    """Test multiple client registrations"""
    client1_id = manager.generate_client_id()
    client2_id = manager.generate_client_id()

    session1 = manager.register_client(client1_id, "player1")
    session2 = manager.register_client(client2_id, "player2")

    assert client1_id != client2_id
    assert session1 is not None
    assert session2 is not None


def test_assign_to_ship(manager):
    """Test ship assignment"""
    client_id = manager.generate_client_id()
    manager.register_client(client_id, "test_player")

    result = manager.assign_to_ship(client_id, "test_ship_001")

    assert result is True

    session = manager.sessions[client_id]
    assert session.ship_id == "test_ship_001"


def test_assign_nonexistent_client(manager):
    """Test assigning nonexistent client to ship fails"""
    result = manager.assign_to_ship("nonexistent_client", "test_ship_001")
    assert result is False


def test_claim_station(manager):
    """Test station claiming"""
    client_id = manager.generate_client_id()
    manager.register_client(client_id, "test_player")
    manager.assign_to_ship(client_id, "test_ship_001")

    success, message = manager.claim_station(client_id, "test_ship_001", StationType.HELM)

    assert success is True

    session = manager.sessions[client_id]
    assert session.station == StationType.HELM


def test_claim_station_without_ship_assignment(manager):
    """Test claiming station without ship assignment fails"""
    client_id = manager.generate_client_id()
    manager.register_client(client_id, "test_player")

    success, message = manager.claim_station(client_id, "test_ship_001", StationType.HELM)
    assert success is False


def test_claim_already_claimed_station(manager):
    """Test claiming already claimed station fails"""
    client1_id = manager.generate_client_id()
    client2_id = manager.generate_client_id()

    manager.register_client(client1_id, "player1")
    manager.register_client(client2_id, "player2")

    manager.assign_to_ship(client1_id, "test_ship_001")
    manager.assign_to_ship(client2_id, "test_ship_001")

    # First claim should succeed
    success1, msg1 = manager.claim_station(client1_id, "test_ship_001", StationType.HELM)
    assert success1 is True

    # Second claim of same station should fail
    success2, msg2 = manager.claim_station(client2_id, "test_ship_001", StationType.HELM)
    assert success2 is False


def test_release_station(manager):
    """Test releasing a station"""
    client_id = manager.generate_client_id()
    manager.register_client(client_id, "test_player")
    manager.assign_to_ship(client_id, "test_ship_001")
    manager.claim_station(client_id, "test_ship_001", StationType.HELM)

    success, message = manager.release_station(client_id, "test_ship_001", StationType.HELM)

    assert success is True

    session = manager.sessions[client_id]
    assert session.station is None

    # Station should be available again
    owner = manager.get_station_owner("test_ship_001", StationType.HELM)
    assert owner is None


def test_get_station_status(manager):
    """Test getting station status for a ship"""
    client1_id = manager.generate_client_id()
    client2_id = manager.generate_client_id()

    manager.register_client(client1_id, "player1")
    manager.register_client(client2_id, "player2")

    manager.assign_to_ship(client1_id, "test_ship_001")
    manager.assign_to_ship(client2_id, "test_ship_001")

    manager.claim_station(client1_id, "test_ship_001", StationType.HELM)
    manager.claim_station(client2_id, "test_ship_001", StationType.TACTICAL)

    status = manager.get_ship_stations("test_ship_001")

    # Check that helm and tactical stations are claimed
    # status is a Dict[StationType, Optional[str]]
    assert isinstance(status, dict)
    assert status[StationType.HELM] == "player1"
    assert status[StationType.TACTICAL] == "player2"


def test_can_issue_command(manager):
    """Test command permission checking"""
    client_id = manager.generate_client_id()
    manager.register_client(client_id, "test_player")
    manager.assign_to_ship(client_id, "test_ship_001")
    manager.claim_station(client_id, "test_ship_001", StationType.HELM)

    # HELM should be able to issue helm commands
    allowed, reason = manager.can_issue_command(client_id, "test_ship_001", "set_thrust")
    assert allowed is True

    # HELM should NOT be able to fire weapons
    allowed, reason = manager.can_issue_command(client_id, "test_ship_001", "fire")
    assert allowed is False


def test_captain_can_issue_any_command(manager):
    """Test CAPTAIN can issue any command"""
    client_id = manager.generate_client_id()
    manager.register_client(client_id, "captain_player")
    manager.assign_to_ship(client_id, "test_ship_001")
    manager.claim_station(client_id, "test_ship_001", StationType.CAPTAIN)

    # CAPTAIN should be able to issue any command
    allowed1, _ = manager.can_issue_command(client_id, "test_ship_001", "set_thrust")
    allowed2, _ = manager.can_issue_command(client_id, "test_ship_001", "fire")
    allowed3, _ = manager.can_issue_command(client_id, "test_ship_001", "ping_sensors")
    assert allowed1 is True
    assert allowed2 is True
    assert allowed3 is True


def test_update_heartbeat(manager):
    """Test heartbeat updates session activity"""
    client_id = manager.generate_client_id()
    manager.register_client(client_id, "test_player")

    session = manager.sessions[client_id]
    initial_time = session.last_heartbeat

    time.sleep(0.01)  # Small delay
    manager.update_activity(client_id)

    session = manager.sessions[client_id]
    assert session.last_heartbeat > initial_time


def test_cleanup_stale_claims(manager):
    """Test cleanup of stale session claims"""
    client_id = manager.generate_client_id()
    manager.register_client(client_id, "test_player")
    manager.assign_to_ship(client_id, "test_ship_001")
    manager.claim_station(client_id, "test_ship_001", StationType.HELM)

    # Manually set last_heartbeat to old time
    session = manager.sessions[client_id]
    session.last_heartbeat = datetime.now() - timedelta(seconds=400)  # 400 seconds ago

    # Run cleanup (uses default timeout of 300 seconds from manager.claim_timeout_seconds)
    removed = manager.cleanup_stale_claims()

    # Session should be removed
    assert client_id in removed
    assert client_id not in manager.sessions

    # Station should be released
    owner = manager.get_station_owner("test_ship_001", StationType.HELM)
    assert owner is None


def test_disconnect_client(manager):
    """Test client disconnection"""
    client_id = manager.generate_client_id()
    manager.register_client(client_id, "test_player")
    manager.assign_to_ship(client_id, "test_ship_001")
    manager.claim_station(client_id, "test_ship_001", StationType.HELM)

    manager.unregister_client(client_id)

    # Session should be removed
    assert client_id not in manager.sessions

    # Station should be released
    owner = manager.get_station_owner("test_ship_001", StationType.HELM)
    assert owner is None
