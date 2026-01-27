"""
WebSocket-TCP Bridge for Flaxos Spaceship Sim GUI.

Bridges WebSocket clients to the TCP simulation server.
Uses the standardized Protocol v1 envelope format.
"""

from __future__ import annotations

import asyncio
import json
import logging
import argparse
import os
import sys
from typing import Set, Optional

# Ensure project root is on sys.path for imports
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    import websockets
    from websockets.server import WebSocketServerProtocol
except ImportError:
    print("websockets library required: pip install websockets")
    raise

from server.config import (
    DEFAULT_TCP_PORT,
    DEFAULT_WS_PORT,
    DEFAULT_HOST,
    PROTOCOL_VERSION,
)
from server.protocol import WSEnvelope, MessageType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class TCPConnection:
    """Manages connection to the TCP simulation server."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.connected = False
        self._lock = asyncio.Lock()

    async def connect(self) -> bool:
        """Establish connection to TCP server."""
        async with self._lock:
            if self.connected:
                return True
            try:
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=5.0
                )
                self.connected = True
                logger.info(f"Connected to TCP server at {self.host}:{self.port}")
                return True
            except (ConnectionRefusedError, asyncio.TimeoutError, OSError) as e:
                logger.warning(f"TCP connection failed: {e}")
                self.connected = False
                return False

    async def disconnect(self):
        """Close TCP connection."""
        async with self._lock:
            if self.writer:
                try:
                    self.writer.close()
                    await self.writer.wait_closed()
                except Exception:
                    pass
            self.reader = None
            self.writer = None
            self.connected = False
            logger.info("TCP connection closed")

    async def send_receive(self, message: str) -> Optional[str]:
        """Send message and receive response from TCP server."""
        if not self.connected:
            if not await self.connect():
                return None

        async with self._lock:
            try:
                # Send message with newline delimiter
                self.writer.write((message + "\n").encode("utf-8"))
                await self.writer.drain()

                # Read response until newline
                response = await asyncio.wait_for(
                    self.reader.readline(),
                    timeout=10.0
                )
                return response.decode("utf-8").strip()
            except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError) as e:
                logger.warning(f"TCP communication error: {e}")
                self.connected = False
                return None


class WSBridge:
    """
    Bridges WebSocket clients to TCP simulation server.

    Uses Protocol v1 envelope format for all messages.

    Responsibilities:
    - Accept WebSocket connections on configurable port
    - Forward JSON messages to TCP server
    - Wrap responses in Protocol v1 WSEnvelope format
    - Broadcast server responses to connected WebSocket clients
    - Handle connection lifecycle and autodiscovery
    """

    def __init__(self, ws_host: str = "0.0.0.0", ws_port: int = DEFAULT_WS_PORT,
                 tcp_host: str = DEFAULT_HOST, tcp_port: int = DEFAULT_TCP_PORT):
        self.ws_host = ws_host
        self.ws_port = ws_port
        self.tcp = TCPConnection(tcp_host, tcp_port)
        self.clients: Set[WebSocketServerProtocol] = set()
        self._running = False
        self._last_tcp_connected = self.tcp.connected

    async def register(self, websocket: WebSocketServerProtocol):
        """Register a new WebSocket client."""
        self.clients.add(websocket)
        client_addr = websocket.remote_address
        logger.info(f"Client connected: {client_addr} (total: {len(self.clients)})")

        # Send connection status to client
        await self._send_status(websocket, "connected")

    async def unregister(self, websocket: WebSocketServerProtocol):
        """Unregister a WebSocket client."""
        self.clients.discard(websocket)
        client_addr = websocket.remote_address
        logger.info(f"Client disconnected: {client_addr} (total: {len(self.clients)})")

    def _build_status_message(self, status: str) -> str:
        """Build a connection status message payload using Protocol v1."""
        envelope = WSEnvelope.status(
            status=status,
            tcp_connected=self.tcp.connected,
            tcp_host=self.tcp.host,
            tcp_port=self.tcp.port,
        )
        return envelope.to_wire()

    async def _send_status(self, websocket: WebSocketServerProtocol, status: str):
        """Send connection status to a client."""
        msg = self._build_status_message(status)
        try:
            await websocket.send(msg)
        except Exception:
            pass

    async def _maybe_broadcast_tcp_status(self, status: Optional[str] = None):
        """Broadcast TCP connection status changes."""
        if self.tcp.connected == self._last_tcp_connected:
            return

        self._last_tcp_connected = self.tcp.connected
        if status is None:
            status = "tcp_connected" if self.tcp.connected else "tcp_disconnected"
        await self.broadcast(self._build_status_message(status))

    async def broadcast(self, message: str, exclude: Optional[WebSocketServerProtocol] = None):
        """Broadcast message to all connected clients."""
        if not self.clients:
            return
        tasks = []
        for client in self.clients.copy():
            if client != exclude:
                tasks.append(asyncio.create_task(self._safe_send(client, message)))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_send(self, websocket: WebSocketServerProtocol, message: str):
        """Send message to client, handling errors gracefully."""
        try:
            await websocket.send(message)
        except Exception:
            await self.unregister(websocket)

    async def handle_client(self, websocket: WebSocketServerProtocol):
        """Handle messages from a WebSocket client."""
        await self.register(websocket)
        try:
            async for message in websocket:
                await self._process_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister(websocket)

    async def _process_message(self, websocket: WebSocketServerProtocol, message: str):
        """Process incoming message from WebSocket client using Protocol v1."""
        # Validate JSON
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            error_envelope = WSEnvelope.error("Invalid JSON")
            await websocket.send(error_envelope.to_wire())
            return

        # Extract request ID for correlation (if present)
        request_id = data.get("_request_id")

        # Handle internal commands (bridge-level, not forwarded to TCP)
        cmd = data.get("cmd") or data.get("command")

        if cmd == "_ping":
            # Internal ping for latency measurement
            pong = WSEnvelope.pong(data.get("timestamp"))
            await websocket.send(pong.to_wire())
            return

        if cmd == "_status":
            # Return connection status
            await self._send_status(websocket, "connected" if self.tcp.connected else "disconnected")
            return

        if cmd == "_discover":
            # Discovery request - forward to TCP server for full info
            pass  # Let it fall through to TCP forwarding

        # Forward to TCP server
        response = await self.tcp.send_receive(message)
        await self._maybe_broadcast_tcp_status()

        if response is None:
            # TCP error - include request_id if present for proper correlation
            error_data = {"tcp_connected": False}
            if request_id is not None:
                error_data["_request_id"] = request_id
            error_envelope = WSEnvelope.error(
                "TCP server unavailable",
                error_data
            )
            await websocket.send(error_envelope.to_wire())
            # Notify all clients of TCP disconnect
            await self._maybe_broadcast_tcp_status(status="tcp_disconnected")
            return

        # Parse and wrap response using Protocol v1 envelope
        try:
            response_data = json.loads(response)
        except json.JSONDecodeError:
            response_data = {"raw": response}

        # Include request_id in response for client-side correlation
        if request_id is not None:
            response_data["_request_id"] = request_id

        wrapped = WSEnvelope.response(response_data)
        await websocket.send(wrapped.to_wire())

    async def start(self):
        """Start the WebSocket server."""
        self._running = True
        logger.info(f"Starting WebSocket bridge on ws://{self.ws_host}:{self.ws_port}")
        logger.info(f"TCP target: {self.tcp.host}:{self.tcp.port}")

        # Pre-connect to TCP server
        await self.tcp.connect()
        await self._maybe_broadcast_tcp_status()

        async with websockets.serve(
            self.handle_client,
            self.ws_host,
            self.ws_port,
            ping_interval=30,
            ping_timeout=10
        ):
            logger.info("WebSocket bridge running. Press Ctrl+C to stop.")
            while self._running:
                await asyncio.sleep(1)

    def stop(self):
        """Signal the bridge to stop."""
        self._running = False


async def main():
    parser = argparse.ArgumentParser(description="WebSocket-TCP Bridge for Flaxos Sim (Protocol v1)")
    parser.add_argument("--ws-host", default="0.0.0.0", help="WebSocket bind host")
    parser.add_argument("--ws-port", type=int, default=DEFAULT_WS_PORT, help="WebSocket port")
    parser.add_argument("--tcp-host", default=DEFAULT_HOST, help="TCP server host")
    parser.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT, help="TCP server port")
    args = parser.parse_args()

    logger.info(f"Protocol version: {PROTOCOL_VERSION}")

    bridge = WSBridge(
        ws_host=args.ws_host,
        ws_port=args.ws_port,
        tcp_host=args.tcp_host,
        tcp_port=args.tcp_port
    )

    try:
        await bridge.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        bridge.stop()
        await bridge.tcp.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
