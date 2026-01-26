"""
Flaxos Protocol v1 - Message Envelope Definitions.

This module formalizes the wire protocol for client-server communication.
All messages follow a consistent envelope format for reliable parsing
and forward compatibility.

Protocol: Newline-delimited JSON over TCP (NDJSON)
Transport: TCP socket or WebSocket (via bridge)
"""

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Dict, Optional, Union
import json
import time


# Protocol version identifier
PROTOCOL_VERSION = "1.0"


class MessageType(Enum):
    """Types of messages in the protocol."""
    REQUEST = "request"
    RESPONSE = "response"
    ERROR = "error"
    EVENT = "event"
    STATUS = "connection_status"
    PONG = "pong"


class ErrorCode(Enum):
    """Standardized error codes for protocol responses."""
    # Client errors (4xx equivalent)
    BAD_REQUEST = "BAD_REQUEST"             # Malformed request
    MISSING_PARAM = "MISSING_PARAM"         # Required parameter missing
    INVALID_PARAM = "INVALID_PARAM"         # Parameter value invalid
    UNKNOWN_COMMAND = "UNKNOWN_COMMAND"     # Command not recognized
    PERMISSION_DENIED = "PERMISSION_DENIED" # Station/role doesn't allow command
    NOT_REGISTERED = "NOT_REGISTERED"       # Client not registered
    NOT_ASSIGNED = "NOT_ASSIGNED"           # Not assigned to ship
    SHIP_NOT_FOUND = "SHIP_NOT_FOUND"       # Referenced ship doesn't exist
    STATION_OCCUPIED = "STATION_OCCUPIED"   # Station already claimed

    # Server errors (5xx equivalent)
    INTERNAL_ERROR = "INTERNAL_ERROR"       # Unexpected server error
    SIMULATION_ERROR = "SIMULATION_ERROR"   # Simulation engine error
    TIMEOUT = "TIMEOUT"                     # Operation timed out


@dataclass
class ProtocolEnvelope:
    """
    Base envelope for all protocol messages.

    Every message (request or response) is wrapped in this envelope
    for consistent handling and versioning.
    """
    type: MessageType
    version: str = PROTOCOL_VERSION
    timestamp: Optional[float] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


@dataclass
class Request:
    """
    Client request envelope.

    Requests from clients follow this format. The 'cmd' field identifies
    the command, and additional parameters are command-specific.
    """
    cmd: str
    params: Dict[str, Any] = None
    request_id: Optional[str] = None  # Optional client-provided ID for correlation

    def __post_init__(self):
        if self.params is None:
            self.params = {}

    def to_wire(self) -> str:
        """Serialize to wire format (JSON + newline)."""
        data = {"cmd": self.cmd, **self.params}
        if self.request_id:
            data["_request_id"] = self.request_id
        return json.dumps(data) + "\n"

    @classmethod
    def from_dict(cls, data: dict) -> "Request":
        """Parse request from dictionary."""
        cmd = data.get("cmd") or data.get("command")
        request_id = data.pop("_request_id", None)
        params = {k: v for k, v in data.items() if k not in ("cmd", "command")}
        return cls(cmd=cmd, params=params, request_id=request_id)


@dataclass
class Response:
    """
    Server response envelope.

    All server responses follow this format. The 'ok' field indicates
    success/failure, and 'data' contains the response payload.
    """
    ok: bool
    data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    error_msg: Optional[str] = None  # Renamed to avoid conflict with classmethod
    code: Optional[ErrorCode] = None
    request_id: Optional[str] = None  # Echo back client's request ID if provided

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        result = {"ok": self.ok}
        if self.message is not None:
            result["message"] = self.message
        if self.data is not None:
            result["response"] = self.data
        if self.error_msg is not None:
            result["error"] = self.error_msg
        if self.code is not None:
            result["code"] = self.code.value if isinstance(self.code, ErrorCode) else self.code
        if self.request_id is not None:
            result["_request_id"] = self.request_id
        return result

    def to_wire(self) -> str:
        """Serialize to wire format (JSON + newline)."""
        return json.dumps(self.to_dict(), default=_json_default) + "\n"

    @classmethod
    def success(
        cls,
        data: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> "Response":
        """Create a success response."""
        return cls(ok=True, data=data, message=message, request_id=request_id)

    @classmethod
    def error(
        cls,
        error: str,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        data: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None
    ) -> "Response":
        """Create an error response."""
        return cls(ok=False, error_msg=error, code=code, data=data, request_id=request_id)


@dataclass
class WSEnvelope:
    """
    WebSocket bridge envelope.

    The WS bridge wraps TCP responses in this envelope to add
    message typing for the browser client.
    """
    type: MessageType
    data: Dict[str, Any]
    timestamp: Optional[float] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "version": PROTOCOL_VERSION,
        }

    def to_wire(self) -> str:
        """Serialize to wire format (JSON)."""
        return json.dumps(self.to_dict(), default=_json_default)

    @classmethod
    def response(cls, data: dict) -> "WSEnvelope":
        """Wrap a TCP response for WebSocket delivery."""
        return cls(type=MessageType.RESPONSE, data=data)

    @classmethod
    def error(cls, error: str, details: Optional[dict] = None) -> "WSEnvelope":
        """Create an error envelope."""
        data = {"error": error}
        if details:
            data.update(details)
        return cls(type=MessageType.ERROR, data=data)

    @classmethod
    def status(cls, status: str, tcp_connected: bool, tcp_host: str, tcp_port: int) -> "WSEnvelope":
        """Create a connection status envelope."""
        return cls(
            type=MessageType.STATUS,
            data={
                "status": status,
                "tcp_host": tcp_host,
                "tcp_port": tcp_port,
                "tcp_connected": tcp_connected,
            }
        )

    @classmethod
    def pong(cls, client_timestamp: Optional[float] = None) -> "WSEnvelope":
        """Create a pong response for latency measurement."""
        return cls(
            type=MessageType.PONG,
            data={"timestamp": client_timestamp, "server_time": time.time()}
        )


def _json_default(value: Any) -> Any:
    """
    Default JSON serializer for complex types.

    Handles numpy arrays, dataclasses, sets, and other common types.
    """
    if isinstance(value, (set, tuple)):
        return list(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, Enum):
        return value.value
    try:
        import numpy as np
        if isinstance(value, (np.integer, np.floating, np.bool_)):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
    except ImportError:
        pass
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return value.__dict__
    return str(value)


def parse_request(line: bytes) -> Request:
    """
    Parse a request from wire format.

    Args:
        line: Raw bytes from TCP socket (without newline)

    Returns:
        Parsed Request object

    Raises:
        ValueError: If JSON is invalid or cmd is missing
    """
    try:
        data = json.loads(line.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"Invalid JSON: {e}")

    cmd = data.get("cmd") or data.get("command")
    if not cmd:
        raise ValueError("Missing 'cmd' field")

    return Request.from_dict(data)


def make_error_response(error: str, code: ErrorCode = ErrorCode.BAD_REQUEST) -> str:
    """
    Create a wire-format error response.

    Convenience function for quick error responses.
    """
    return Response.error(error, code).to_wire()


# Compatibility layer for existing code
def wrap_legacy_response(result: dict) -> Response:
    """
    Wrap a legacy response dict in a Response envelope.

    This helps migrate existing handlers that return raw dicts.
    """
    if "ok" in result:
        if result["ok"]:
            data = {k: v for k, v in result.items() if k not in ("ok", "message")}
            return Response.success(data=data, message=result.get("message"))
        else:
            return Response.error(
                error=result.get("error", "Unknown error"),
                code=ErrorCode.INTERNAL_ERROR,
                data=result.get("response")
            )
    # Raw data without ok field
    return Response.success(data=result)
