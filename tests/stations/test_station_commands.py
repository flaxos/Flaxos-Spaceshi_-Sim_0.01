"""Tests for station management commands."""

from types import SimpleNamespace

from server.stations.station_dispatch import StationAwareDispatcher
from server.stations.station_manager import StationManager
from server.stations.station_commands import register_station_commands


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
