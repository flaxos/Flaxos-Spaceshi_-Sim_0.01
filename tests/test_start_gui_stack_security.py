"""Regression coverage for secure launcher handling."""

from tools.start_gui_stack import (
    _append_query_param,
    _resolve_allowed_origin_hosts,
    _resolve_rcon_password,
)


def test_append_query_param_adds_new_value():
    assert (
        _append_query_param("http://localhost:3100/", "game_code", "abc123")
        == "http://localhost:3100/?game_code=abc123"
    )


def test_append_query_param_replaces_existing_value():
    assert (
        _append_query_param(
            "http://localhost:3100/?game_code=old&foo=bar",
            "game_code",
            "new",
        )
        == "http://localhost:3100/?game_code=new&foo=bar"
    )


def test_resolve_rcon_password_prefers_cli(monkeypatch):
    monkeypatch.setenv("FLAXOS_RCON_PASSWORD", "env-secret")
    assert _resolve_rcon_password("cli-secret") == "cli-secret"


def test_resolve_rcon_password_uses_env_when_cli_missing(monkeypatch):
    monkeypatch.setenv("FLAXOS_RCON_PASSWORD", "env-secret")
    assert _resolve_rcon_password(None) == "env-secret"


def test_resolve_rcon_password_falls_back_to_admin(monkeypatch):
    monkeypatch.delenv("FLAXOS_RCON_PASSWORD", raising=False)
    assert _resolve_rcon_password(None) == "admin"


def test_resolve_allowed_origin_hosts_adds_loopback_hosts():
    assert _resolve_allowed_origin_hosts(["100.64.10.24"]) == [
        "100.64.10.24",
        "127.0.0.1",
        "::1",
        "localhost",
    ]


def test_resolve_allowed_origin_hosts_splits_and_normalizes_values():
    assert _resolve_allowed_origin_hosts([" LOCALHOST, 100.64.10.24 ", "zt-host.local"]) == [
        "100.64.10.24",
        "127.0.0.1",
        "::1",
        "localhost",
        "zt-host.local",
    ]


def test_resolve_allowed_origin_hosts_keeps_empty_config_open():
    assert _resolve_allowed_origin_hosts([]) == []
