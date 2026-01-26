"""
Contract tests for Flaxos Protocol v1.

These tests verify that the protocol envelope format is correct and stable.
Any breaking changes to these tests indicate a protocol version bump is needed.
"""

import json
import pytest
import time

from server.protocol import (
    PROTOCOL_VERSION,
    MessageType,
    ErrorCode,
    Request,
    Response,
    WSEnvelope,
    parse_request,
    make_error_response,
    wrap_legacy_response,
    _json_default,
)
from server.config import ServerConfig, ServerMode


class TestProtocolVersion:
    """Contract tests for protocol version."""

    def test_protocol_version_is_1_0(self):
        """Protocol version should be 1.0 for this implementation."""
        assert PROTOCOL_VERSION == "1.0"


class TestRequestEnvelope:
    """Contract tests for Request envelope."""

    def test_request_from_dict_basic(self):
        """Request should parse basic command."""
        req = Request.from_dict({"cmd": "get_state"})
        assert req.cmd == "get_state"
        assert req.params == {}
        assert req.request_id is None

    def test_request_from_dict_with_params(self):
        """Request should extract params from dict."""
        req = Request.from_dict({
            "cmd": "set_thrust",
            "ship": "alpha",
            "thrust": 0.5
        })
        assert req.cmd == "set_thrust"
        assert req.params["ship"] == "alpha"
        assert req.params["thrust"] == 0.5

    def test_request_from_dict_alternative_key(self):
        """Request should accept 'command' as alternative to 'cmd'."""
        req = Request.from_dict({"command": "get_state"})
        assert req.cmd == "get_state"

    def test_request_from_dict_with_request_id(self):
        """Request should extract _request_id for correlation."""
        req = Request.from_dict({
            "cmd": "get_state",
            "_request_id": "req-123"
        })
        assert req.cmd == "get_state"
        assert req.request_id == "req-123"
        # request_id should not be in params
        assert "_request_id" not in req.params

    def test_request_to_wire_format(self):
        """Request.to_wire() should produce JSON with newline."""
        req = Request(cmd="get_state", params={"ship": "alpha"})
        wire = req.to_wire()
        assert wire.endswith("\n")
        data = json.loads(wire.strip())
        assert data["cmd"] == "get_state"
        assert data["ship"] == "alpha"

    def test_request_to_wire_includes_request_id(self):
        """Request.to_wire() should include _request_id if set."""
        req = Request(cmd="get_state", request_id="req-456")
        wire = req.to_wire()
        data = json.loads(wire.strip())
        assert data["_request_id"] == "req-456"


class TestResponseEnvelope:
    """Contract tests for Response envelope."""

    def test_success_response_format(self):
        """Success response should have ok=True."""
        resp = Response.success(data={"value": 42}, message="Done")
        d = resp.to_dict()
        assert d["ok"] is True
        assert d["message"] == "Done"
        assert d["response"]["value"] == 42
        assert "error" not in d

    def test_error_response_format(self):
        """Error response should have ok=False and error details."""
        resp = Response.error("Not found", ErrorCode.SHIP_NOT_FOUND)
        d = resp.to_dict()
        assert d["ok"] is False
        assert d["error"] == "Not found"
        assert d["code"] == "SHIP_NOT_FOUND"

    def test_response_includes_request_id(self):
        """Response should echo back request_id if provided."""
        resp = Response.success(data={}, request_id="req-789")
        d = resp.to_dict()
        assert d["_request_id"] == "req-789"

    def test_response_to_wire_format(self):
        """Response.to_wire() should produce JSON with newline."""
        resp = Response.success(message="OK")
        wire = resp.to_wire()
        assert wire.endswith("\n")
        data = json.loads(wire.strip())
        assert data["ok"] is True


class TestWSEnvelope:
    """Contract tests for WebSocket envelope format."""

    def test_response_envelope_format(self):
        """WS response envelope should wrap data with type."""
        env = WSEnvelope.response({"ok": True, "value": 123})
        d = env.to_dict()
        assert d["type"] == "response"
        assert d["data"]["ok"] is True
        assert d["data"]["value"] == 123
        assert "version" in d
        assert "timestamp" in d

    def test_error_envelope_format(self):
        """WS error envelope should have type=error."""
        env = WSEnvelope.error("Connection failed", {"code": "TCP_ERROR"})
        d = env.to_dict()
        assert d["type"] == "error"
        assert d["data"]["error"] == "Connection failed"
        assert d["data"]["code"] == "TCP_ERROR"

    def test_status_envelope_format(self):
        """WS status envelope should contain connection info."""
        env = WSEnvelope.status(
            status="connected",
            tcp_connected=True,
            tcp_host="127.0.0.1",
            tcp_port=8765
        )
        d = env.to_dict()
        assert d["type"] == "connection_status"
        assert d["data"]["status"] == "connected"
        assert d["data"]["tcp_connected"] is True
        assert d["data"]["tcp_host"] == "127.0.0.1"
        assert d["data"]["tcp_port"] == 8765

    def test_pong_envelope_format(self):
        """WS pong envelope should contain timestamps."""
        client_ts = time.time()
        env = WSEnvelope.pong(client_ts)
        d = env.to_dict()
        assert d["type"] == "pong"
        assert d["data"]["timestamp"] == client_ts
        assert "server_time" in d["data"]

    def test_to_wire_is_valid_json(self):
        """WSEnvelope.to_wire() should produce valid JSON (no newline)."""
        env = WSEnvelope.response({"ok": True})
        wire = env.to_wire()
        # WebSocket messages don't need newline delimiter
        assert not wire.endswith("\n") or json.loads(wire) is not None
        data = json.loads(wire)
        assert data["type"] == "response"


class TestErrorCodes:
    """Contract tests for standardized error codes."""

    def test_all_error_codes_are_strings(self):
        """All error codes should serialize to strings."""
        for code in ErrorCode:
            assert isinstance(code.value, str)

    def test_error_codes_required_set(self):
        """These error codes must exist for protocol compliance."""
        required_codes = [
            "BAD_REQUEST",
            "MISSING_PARAM",
            "INVALID_PARAM",
            "UNKNOWN_COMMAND",
            "PERMISSION_DENIED",
            "NOT_REGISTERED",
            "NOT_ASSIGNED",
            "SHIP_NOT_FOUND",
            "STATION_OCCUPIED",
            "INTERNAL_ERROR",
            "SIMULATION_ERROR",
            "TIMEOUT",
        ]
        actual_codes = [c.value for c in ErrorCode]
        for code in required_codes:
            assert code in actual_codes, f"Missing required error code: {code}"


class TestParseRequest:
    """Contract tests for request parsing."""

    def test_parse_valid_request(self):
        """Should parse valid JSON request."""
        line = b'{"cmd": "get_state", "ship": "alpha"}'
        req = parse_request(line)
        assert req.cmd == "get_state"
        assert req.params["ship"] == "alpha"

    def test_parse_invalid_json_raises(self):
        """Should raise ValueError for invalid JSON."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_request(b"not json")

    def test_parse_missing_cmd_raises(self):
        """Should raise ValueError when cmd is missing."""
        with pytest.raises(ValueError, match="Missing 'cmd'"):
            parse_request(b'{"ship": "alpha"}')


class TestLegacyCompatibility:
    """Contract tests for backwards compatibility."""

    def test_wrap_legacy_success_response(self):
        """Should wrap legacy dict with ok=True."""
        legacy = {"ok": True, "value": 42, "message": "Done"}
        resp = wrap_legacy_response(legacy)
        assert resp.ok is True
        assert resp.message == "Done"
        assert resp.data["value"] == 42

    def test_wrap_legacy_error_response(self):
        """Should wrap legacy dict with ok=False."""
        legacy = {"ok": False, "error": "Ship not found"}
        resp = wrap_legacy_response(legacy)
        assert resp.ok is False
        assert resp.error_msg == "Ship not found"

    def test_wrap_legacy_raw_data(self):
        """Should wrap raw data dict without ok field."""
        legacy = {"ships": [{"id": "alpha"}]}
        resp = wrap_legacy_response(legacy)
        assert resp.ok is True
        assert resp.data["ships"][0]["id"] == "alpha"


class TestJsonDefault:
    """Contract tests for JSON serialization of special types."""

    def test_serialize_set(self):
        """Sets should serialize to lists."""
        assert _json_default({1, 2, 3}) == [1, 2, 3]

    def test_serialize_tuple(self):
        """Tuples should serialize to lists."""
        assert _json_default((1, 2, 3)) == [1, 2, 3]

    def test_serialize_bytes(self):
        """Bytes should decode to string."""
        assert _json_default(b"hello") == "hello"

    def test_serialize_enum(self):
        """Enums should serialize to their value."""
        assert _json_default(MessageType.RESPONSE) == "response"


class TestServerConfig:
    """Contract tests for server configuration."""

    def test_default_ports(self):
        """Default ports should match documented values."""
        from server.config import (
            DEFAULT_TCP_PORT,
            DEFAULT_WS_PORT,
            DEFAULT_HTTP_PORT,
        )
        assert DEFAULT_TCP_PORT == 8765
        assert DEFAULT_WS_PORT == 8080
        assert DEFAULT_HTTP_PORT == 3000

    def test_discovery_info_format(self):
        """Discovery info should contain required fields."""
        config = ServerConfig()
        info = config.to_discovery_info()

        assert "version" in info
        assert "mode" in info
        assert "endpoints" in info
        assert "features" in info

        # Endpoints structure
        assert "tcp" in info["endpoints"]
        assert "ws" in info["endpoints"]
        assert "http" in info["endpoints"]

        for endpoint in info["endpoints"].values():
            assert "host" in endpoint
            assert "port" in endpoint

    def test_server_modes(self):
        """Both server modes should be available."""
        assert ServerMode.MINIMAL.value == "minimal"
        assert ServerMode.STATION.value == "station"


class TestMessageTypes:
    """Contract tests for message types."""

    def test_required_message_types(self):
        """These message types must exist."""
        required = ["request", "response", "error", "connection_status", "pong"]
        actual = [t.value for t in MessageType]
        for msg_type in required:
            assert msg_type in actual, f"Missing message type: {msg_type}"
