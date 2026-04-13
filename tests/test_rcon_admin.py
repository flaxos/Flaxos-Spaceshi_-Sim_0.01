"""Regression coverage for RCON admin controls."""

import time

from hybrid_runner import HybridRunner
from server.config import ServerConfig, ServerMode
from server.main import UnifiedServer


def make_server():
    config = ServerConfig(mode=ServerMode.MINIMAL, rcon_password="old-secret")
    server = UnifiedServer(config)
    server._rcon_tokens["admin"] = ("token", time.time() + 3600)
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
    server._rcon_tokens["other"] = ("other-token", time.time() + 3600)

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
    assert result["rcon_token_ttl"] > 0


def test_rcon_auth_is_rate_limited_after_repeated_failures():
    config = ServerConfig(mode=ServerMode.MINIMAL, rcon_password="old-secret")
    server = UnifiedServer(config)

    responses = [
        server._handle_rcon("admin", "rcon_auth", {"password": "wrong-secret"})
        for _ in range(4)
    ]

    assert responses[0]["error"] == "Unauthorized"
    assert responses[-1]["error"] == "Too many authentication attempts"


def test_expired_rcon_token_is_rejected(monkeypatch):
    server = make_server()
    server._rcon_tokens["admin"] = ("token", 120.0)
    monkeypatch.setattr("server.main.time.time", lambda: 121.0)

    result = server._handle_rcon("admin", "rcon_status", {"token": "token"})

    assert result == {"ok": False, "error": "Unauthorized"}
    assert "admin" not in server._rcon_tokens


def test_resolve_scenario_path_rejects_paths_outside_scenarios(tmp_path):
    runner = HybridRunner()
    runner.scenarios_dir = str(tmp_path / "scenarios")
    (tmp_path / "scenarios").mkdir()
    inside = tmp_path / "scenarios" / "valid.yaml"
    inside.write_text("name: safe\n", encoding="utf-8")
    outside = tmp_path / "outside.yaml"
    outside.write_text("name: unsafe\n", encoding="utf-8")

    assert runner._resolve_scenario_path("valid") == str(inside.resolve())
    assert runner._resolve_scenario_path(str(outside)) is None
    assert runner._resolve_scenario_path("../outside.yaml") is None
