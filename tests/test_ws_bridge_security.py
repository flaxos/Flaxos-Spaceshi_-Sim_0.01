"""Security regression coverage for the WebSocket bridge."""

from types import SimpleNamespace

from gui.ws_bridge import WSBridge


def make_websocket(origin: str | None):
    headers = {}
    if origin is not None:
        headers["Origin"] = origin
    return SimpleNamespace(
        remote_address=("100.64.0.10", 54321),
        request=SimpleNamespace(headers=headers),
    )


def test_origin_allowlist_accepts_matching_host():
    bridge = WSBridge(
        game_code="secret",
        allowed_origin_hosts={"localhost", "100.64.0.10"},
    )

    assert bridge._origin_allowed(make_websocket("http://100.64.0.10:3100")) is True


def test_origin_allowlist_rejects_mismatched_host():
    bridge = WSBridge(
        game_code="secret",
        allowed_origin_hosts={"localhost", "100.64.0.10"},
    )

    assert bridge._origin_allowed(make_websocket("http://evil.example:3100")) is False


def test_origin_allowlist_is_noop_when_unconfigured():
    bridge = WSBridge(game_code="secret")

    assert bridge._origin_allowed(make_websocket(None)) is True
