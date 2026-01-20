"""Tests for station management commands."""

from types import SimpleNamespace

from server.stations.station_dispatch import StationAwareDispatcher
from server.stations.station_manager import StationManager
from server.stations.station_commands import register_station_commands
from server.stations.station_types import StationType


def test_list_ships_returns_metadata():
    """List ships should return available ship metadata when provided."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)

    ships = {
        "ship_alpha": SimpleNamespace(
            id="ship_alpha",
            name="Alpha",
            class_type="frigate",
            faction="neutral",
        ),
        "ship_bravo": SimpleNamespace(
            id="ship_bravo",
            name="Bravo",
            class_type="corvette",
        ),
    }

    register_station_commands(dispatcher, manager, ship_provider=lambda: ships)

    result = dispatcher.dispatch("client_1", "", "list_ships", {})

    assert result.success is True
    assert result.data is not None

    ship_entries = result.data["ships"]
    ship_ids = {entry["id"] for entry in ship_entries}

    assert ship_ids == {"ship_alpha", "ship_bravo"}
    assert any(entry.get("name") == "Alpha" for entry in ship_entries)
    assert any(entry.get("class") == "frigate" for entry in ship_entries)


def test_transfer_station_requires_officer_permission():
    """Crew members cannot transfer stations without officer permissions."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)
    register_station_commands(dispatcher, manager)

    manager.register_client("client_1", "Alpha")
    manager.register_client("client_2", "Bravo")

    manager.assign_to_ship("client_1", "ship_alpha")
    manager.assign_to_ship("client_2", "ship_alpha")
    manager.claim_station("client_1", "ship_alpha", StationType.HELM)

    result = dispatcher.dispatch(
        "client_1",
        "ship_alpha",
        "transfer_station",
        {"target_client": "client_2"},
    )

    assert result.success is False
    assert result.message == "Only OFFICER or CAPTAIN can transfer station control"
    assert manager.get_station_owner("ship_alpha", StationType.HELM) == "client_1"
