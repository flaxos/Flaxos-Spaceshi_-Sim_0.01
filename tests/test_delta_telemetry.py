"""Tests for delta telemetry computation in UnifiedServer."""

import pytest
from server.main import UnifiedServer
from server.config import ServerConfig, ServerMode


@pytest.fixture
def server():
    """Create a minimal UnifiedServer without starting the network stack."""
    config = ServerConfig(mode=ServerMode.MINIMAL)
    srv = UnifiedServer(config)
    return srv


class TestComputeDelta:
    """Verify _compute_delta produces correct shallow diffs."""

    def test_first_request_returns_full_snapshot(self, server):
        snapshot = {"ok": True, "t": 1.0, "position": [0, 0, 0], "speed": 100}
        result = server._compute_delta("c1", "ship1", snapshot)
        # First request: no delta flag, full snapshot returned
        assert "_delta" not in result
        assert result == snapshot

    def test_identical_snapshot_returns_delta_only_marker(self, server):
        snapshot = {"ok": True, "t": 1.0, "position": [0, 0, 0]}
        # Seed the cache
        server._compute_delta("c1", "ship1", snapshot)
        # Same snapshot again
        result = server._compute_delta("c1", "ship1", snapshot)
        assert result["_delta"] is True
        # No changed keys beyond the marker
        assert set(result.keys()) == {"_delta"}

    def test_changed_key_included_in_delta(self, server):
        snap1 = {"ok": True, "t": 1.0, "speed": 100, "heading": 90}
        snap2 = {"ok": True, "t": 2.0, "speed": 200, "heading": 90}
        server._compute_delta("c1", "ship1", snap1)
        result = server._compute_delta("c1", "ship1", snap2)
        assert result["_delta"] is True
        # t and speed changed; heading and ok didn't
        assert "t" in result
        assert "speed" in result
        assert result["speed"] == 200
        assert "heading" not in result
        assert "ok" not in result

    def test_new_key_included_in_delta(self, server):
        snap1 = {"ok": True, "t": 1.0}
        snap2 = {"ok": True, "t": 1.0, "new_field": "hello"}
        server._compute_delta("c1", "ship1", snap1)
        result = server._compute_delta("c1", "ship1", snap2)
        assert result["_delta"] is True
        assert result["new_field"] == "hello"

    def test_full_resync_every_10th_request(self, server):
        snapshot = {"ok": True, "t": 1.0, "data": "same"}
        # Request 1: full (first)
        r1 = server._compute_delta("c1", "ship1", snapshot)
        assert "_delta" not in r1

        # Requests 2-9: deltas
        for i in range(2, 10):
            ri = server._compute_delta("c1", "ship1", snapshot)
            assert ri.get("_delta") is True, f"Request {i} should be delta"

        # Request 10: forced full resync
        r10 = server._compute_delta("c1", "ship1", snapshot)
        assert "_delta" not in r10
        assert r10 == snapshot

    def test_separate_clients_have_independent_caches(self, server):
        snap = {"ok": True, "t": 1.0, "x": 1}
        # Client A seeds cache
        server._compute_delta("cA", "ship1", snap)
        # Client B first request — should get full, not delta
        result = server._compute_delta("cB", "ship1", snap)
        assert "_delta" not in result

    def test_cleanup_removes_client_entries(self, server):
        snap = {"ok": True, "t": 1.0}
        server._compute_delta("c1", "ship1", snap)
        server._compute_delta("c1", "ship2", snap)
        server._compute_delta("c2", "ship1", snap)

        assert "c1:ship1" in server._telemetry_cache
        assert "c1:ship2" in server._telemetry_cache

        server._cleanup_telemetry_cache("c1")

        assert "c1:ship1" not in server._telemetry_cache
        assert "c1:ship2" not in server._telemetry_cache
        # c2 untouched
        assert "c2:ship1" in server._telemetry_cache
