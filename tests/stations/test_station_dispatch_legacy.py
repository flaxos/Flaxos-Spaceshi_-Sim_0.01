"""Tests for legacy station dispatch wrappers."""

from types import SimpleNamespace

from server.stations.station_dispatch import (
    create_legacy_command_wrapper,
    register_legacy_commands,
    StationAwareDispatcher,
)
from server.stations.station_manager import StationManager


def test_create_legacy_command_wrapper_forwards_all_ships_callable(monkeypatch):
    """Legacy wrapper should pass all_ships from provider to route_command."""
    ship = SimpleNamespace(id="ship_alpha")
    all_ships = {"ship_alpha": ship, "ship_bravo": SimpleNamespace(id="ship_bravo")}
    runner = SimpleNamespace(simulator=SimpleNamespace(ships={}))

    captured = {}

    def fake_route_command(target_ship, command_data, provided_all_ships):
        captured["target_ship"] = target_ship
        captured["command_data"] = command_data
        captured["all_ships"] = provided_all_ships
        return {"status": "ok", "cross_ship_visible": "ship_bravo" in provided_all_ships}

    monkeypatch.setattr("hybrid.command_handler.route_command", fake_route_command)

    wrapper = create_legacy_command_wrapper(
        runner,
        "set_thrust",
        ship_map_provider=lambda: all_ships,
    )

    result = wrapper("client_1", "ship_alpha", {"ship": "ship_alpha", "value": 0.75})

    assert result.success is True
    assert result.data["cross_ship_visible"] is True
    assert captured["target_ship"] is ship
    assert captured["all_ships"] is all_ships
    assert captured["command_data"]["command"] == "set_thrust"


def test_register_legacy_commands_wires_dynamic_ship_provider(monkeypatch):
    """Registered wrappers should resolve all_ships at execution time."""
    ship_alpha = SimpleNamespace(id="ship_alpha")
    ships = {"ship_alpha": ship_alpha}
    runner = SimpleNamespace(simulator=SimpleNamespace(ships=ships))
    dispatcher = StationAwareDispatcher(StationManager())

    captured = {}

    def fake_route_command(target_ship, command_data, provided_all_ships):
        captured["target_ship"] = target_ship
        captured["command_data"] = command_data
        captured["all_ships"] = provided_all_ships
        return {"status": "ok"}

    monkeypatch.setattr("hybrid.command_handler.route_command", fake_route_command)

    register_legacy_commands(dispatcher, runner)

    # Add ship after registration; callable provider should expose updated map
    ship_bravo = SimpleNamespace(id="ship_bravo")
    ships["ship_bravo"] = ship_bravo

    handler = dispatcher.handlers["set_thrust"]
    result = handler("client_1", "ship_bravo", {"ship": "ship_bravo", "value": 0.5})

    assert result.success is True
    assert captured["target_ship"] is ship_bravo
    assert captured["all_ships"] is ships
    assert "ship_alpha" in captured["all_ships"]
    assert "ship_bravo" in captured["all_ships"]
