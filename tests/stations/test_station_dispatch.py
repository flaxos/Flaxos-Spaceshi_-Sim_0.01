"""Tests for station dispatcher legacy command wrapper behavior."""

from types import SimpleNamespace

from server.stations.station_dispatch import create_legacy_command_wrapper


def _make_runner_with_ship(ship_id: str = "ship_1"):
    """Create minimal runner stub with a single ship registered."""
    ship = SimpleNamespace(id=ship_id)
    ships = {ship_id: ship}
    runner = SimpleNamespace(simulator=SimpleNamespace(ships=ships))
    return runner


def test_legacy_wrapper_treats_error_key_as_failure(monkeypatch):
    """Responses with an explicit error field should be failures."""
    runner = _make_runner_with_ship()

    def fake_route_command(ship, command_data):
        return {"error": "navigation offline"}

    monkeypatch.setattr("hybrid.command_handler.route_command", fake_route_command)

    wrapper = create_legacy_command_wrapper(runner, "set_course")
    result = wrapper("client_1", "ship_1", {})

    assert result.success is False
    assert result.message == "navigation offline"


def test_legacy_wrapper_treats_error_status_as_failure(monkeypatch):
    """Responses with status=error should be failures."""
    runner = _make_runner_with_ship()

    def fake_route_command(ship, command_data):
        return {"status": "error", "message": "ignored", "detail": "bad route"}

    monkeypatch.setattr("hybrid.command_handler.route_command", fake_route_command)

    wrapper = create_legacy_command_wrapper(runner, "set_course")
    result = wrapper("client_1", "ship_1", {})

    assert result.success is False
    assert result.message == "Command failed"


def test_legacy_wrapper_treats_successful_dict_as_success(monkeypatch):
    """Responses without error indicators should be treated as success."""
    runner = _make_runner_with_ship()

    def fake_route_command(ship, command_data):
        return {"status": "queued", "message": "Course set"}

    monkeypatch.setattr("hybrid.command_handler.route_command", fake_route_command)

    wrapper = create_legacy_command_wrapper(runner, "set_course")
    result = wrapper("client_1", "ship_1", {})

    assert result.success is True
    assert result.message == "Course set"

