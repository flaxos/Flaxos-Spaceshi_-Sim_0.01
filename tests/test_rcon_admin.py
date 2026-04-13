"""Regression coverage for RCON admin controls."""

from server.config import ServerConfig, ServerMode
from server.main import UnifiedServer


def make_server():
    config = ServerConfig(mode=ServerMode.MINIMAL, rcon_password="old-secret")
    server = UnifiedServer(config)
    server._rcon_tokens["admin"] = "token"
    return server


def test_handle_load_scenario_passes_force_to_runner(monkeypatch):
    server = make_server()
    captured = {}

    def fake_load_scenario(scenario_name, force=False):
        captured["scenario_name"] = scenario_name
        captured["force"] = force
        server.runner._current_scenario_name = "Skirmish"
        server.runner.player_ship_id = "player-1"
        return 1

    monkeypatch.setattr(server.runner, "load_scenario", fake_load_scenario)
    monkeypatch.setattr(server.runner, "get_mission_status", lambda: {"available": True})

    result = server._handle_load_scenario({"scenario": "skirmish", "force": True})

    assert result["ok"] is True
    assert captured == {"scenario_name": "skirmish", "force": True}
    assert server._mission_start_time is not None


def test_rcon_reload_uses_force_reload(monkeypatch):
    server = make_server()
    server.runner._current_scenario_name = "Skirmish"
    captured = {}

    def fake_handle_load(req):
        captured.update(req)
        return {"ok": True}

    monkeypatch.setattr(server, "_handle_load_scenario", fake_handle_load)

    result = server._handle_rcon("admin", "rcon_reload", {"token": "token"})

    assert result == {"ok": True}
    assert captured == {"scenario": "Skirmish", "force": True}


def test_rcon_set_password_revokes_existing_tokens():
    server = make_server()
    server._rcon_tokens["other"] = "other-token"

    result = server._handle_rcon(
        "admin",
        "rcon_set_password",
        {
            "token": "token",
            "current_password": "old-secret",
            "new_password": "new-secret-123",
        },
    )

    assert result["ok"] is True
    assert result["reauth_required"] is True
    assert result["persisted"] is False
    assert server.config.rcon_password == "new-secret-123"
    assert server._rcon_tokens == {}


def test_rcon_status_reports_server_and_mission_uptime(monkeypatch):
    server = make_server()
    server._start_time = 100.0
    server._mission_start_time = 150.0
    server.runner._current_scenario_name = "Skirmish"
    server.runner.running = True
    monkeypatch.setattr("server.main.time.time", lambda: 200.0)
    monkeypatch.setattr(server.runner, "get_mission_status", lambda: {"available": True, "mission_status": "active"})

    result = server._handle_rcon("admin", "rcon_status", {"token": "token"})

    assert result["ok"] is True
    assert result["server_uptime"] == 100.0
    assert result["uptime"] == 100.0
    assert result["mission_uptime"] == 50.0
    assert result["scenario"] == "Skirmish"
    assert result["mission"]["mission_status"] == "active"
