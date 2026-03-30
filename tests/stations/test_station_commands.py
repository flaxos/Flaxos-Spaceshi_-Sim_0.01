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


# ---------------------------------------------------------------------------
# assign_ship — ship-existence validation (Fix 1)
# ---------------------------------------------------------------------------

def test_assign_ship_rejects_unknown_ship_id():
    """assign_ship must return ok=False when the ship ID does not exist."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)

    # Only one known ship in the simulation
    ships = {
        "real_ship": SimpleNamespace(id="real_ship", name="Real", class_type="corvette"),
    }
    register_station_commands(dispatcher, manager, ship_provider=lambda: ships)
    manager.register_client("client_1", "Pilot")

    result = dispatcher.dispatch("client_1", "", "assign_ship", {"ship": "ghost_ship"})

    assert result.success is False
    assert "ghost_ship" in result.message
    # Session must not have been mutated
    session = manager.get_session("client_1")
    assert session.ship_id is None


def test_assign_ship_accepts_known_ship_id():
    """assign_ship must succeed when the ship ID exists in the simulation."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)

    ships = {
        "real_ship": SimpleNamespace(id="real_ship", name="Real", class_type="corvette"),
    }
    register_station_commands(dispatcher, manager, ship_provider=lambda: ships)
    manager.register_client("client_1", "Pilot")

    result = dispatcher.dispatch("client_1", "", "assign_ship", {"ship": "real_ship"})

    assert result.success is True
    session = manager.get_session("client_1")
    assert session.ship_id == "real_ship"


def test_assign_ship_without_ship_provider_still_assigns():
    """
    When no ship_provider is registered, the existence check is skipped and
    assign_ship falls back to its original behaviour (station_manager decides).
    """
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)
    # No ship_provider — existence validation must be skipped
    register_station_commands(dispatcher, manager, ship_provider=None)
    manager.register_client("client_1", "Pilot")

    result = dispatcher.dispatch("client_1", "", "assign_ship", {"ship": "any_ship"})

    # station_manager.assign_to_ship creates the ship slot on-demand, so this
    # should succeed without a provider.
    assert result.success is True


def test_assign_ship_missing_ship_id_returns_error():
    """assign_ship with no ship argument must return a descriptive error."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)
    ships = {"ship_a": SimpleNamespace(id="ship_a")}
    register_station_commands(dispatcher, manager, ship_provider=lambda: ships)
    manager.register_client("client_1", "Pilot")

    # No 'ship' arg and no implicit ship_id
    result = dispatcher.dispatch("client_1", "", "assign_ship", {})

    assert result.success is False


def test_assign_ship_empty_string_ship_id_returns_error():
    """assign_ship with an empty string ship ID must return an error."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)
    ships = {"ship_a": SimpleNamespace(id="ship_a")}
    register_station_commands(dispatcher, manager, ship_provider=lambda: ships)
    manager.register_client("client_1", "Pilot")

    result = dispatcher.dispatch("client_1", "", "assign_ship", {"ship": ""})

    assert result.success is False
