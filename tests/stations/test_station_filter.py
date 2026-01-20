"""Tests for station telemetry filtering entry point."""

from server.stations.station_manager import StationManager
from server.stations.station_types import StationType
from server.telemetry.station_filter import StationTelemetryFilter


def _sample_ship_telemetry():
    return {
        "id": "test_ship_001",
        "name": "Test Ship",
        "class": "frigate",
        "position": {"x": 1, "y": 2, "z": 3},
        "velocity": {"x": 0, "y": 1, "z": 0},
        "orientation": {"pitch": 0, "yaw": 0, "roll": 0},
        "fuel": {"mass": 100},
        "systems": {"propulsion": "online"},
        "weapons": {"status": "armed"},
        "timestamp": 123.4,
    }


def test_helm_filter_excludes_tactical_data():
    manager = StationManager()
    client_id = manager.generate_client_id()
    manager.register_client(client_id, "helm_player")
    manager.assign_to_ship(client_id, "test_ship_001")
    manager.claim_station(client_id, "test_ship_001", StationType.HELM)

    telemetry_filter = StationTelemetryFilter(manager)
    filtered = telemetry_filter.filter_ship_state_for_client(
        client_id,
        "test_ship_001",
        _sample_ship_telemetry(),
    )

    assert "position" in filtered
    assert "velocity" in filtered
    assert "orientation" in filtered
    assert "weapons" not in filtered


def test_captain_filter_includes_all_data():
    manager = StationManager()
    client_id = manager.generate_client_id()
    manager.register_client(client_id, "captain_player")
    manager.assign_to_ship(client_id, "test_ship_001")
    manager.claim_station(client_id, "test_ship_001", StationType.CAPTAIN)

    telemetry_filter = StationTelemetryFilter(manager)
    sample = _sample_ship_telemetry()
    filtered = telemetry_filter.filter_ship_state_for_client(
        client_id,
        "test_ship_001",
        sample,
    )

    assert filtered == sample
