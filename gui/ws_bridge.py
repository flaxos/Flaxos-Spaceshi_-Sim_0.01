"""
WebSocket-TCP Bridge for Flaxos Spaceship Sim GUI.

Bridges WebSocket clients to the TCP simulation server.
Each WebSocket client gets its own TCP connection, enabling true
multiplayer: each browser session has an independent server-side
client_id, station claim, and telemetry filter.

Uses the standardized Protocol v1 envelope format.
"""

from __future__ import annotations

import asyncio
import json
import logging
import argparse
import os
import sys
from typing import Dict, Optional, Set

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
    """Manages a single connection to the TCP simulation server."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.connected = False
        self._lock = asyncio.Lock()
        self.client_id: Optional[str] = None
        self.welcome_data: Optional[dict] = None

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

                # Station mode sends a welcome message on connect
                try:
                    welcome = await asyncio.wait_for(
                        self.reader.readline(), timeout=2.0
                    )
                    if welcome:
                        self.welcome_data = json.loads(welcome.decode("utf-8"))
                        self.client_id = self.welcome_data.get("client_id")
                        logger.info(
                            f"TCP welcome: {self.welcome_data.get('message', 'ok')} "
                            f"(mode={self.welcome_data.get('mode', 'unknown')}, "
                            f"client_id={self.client_id})"
                        )
                except (asyncio.TimeoutError, json.JSONDecodeError):
                    # Minimal mode doesn't send a welcome -- timeout is fine
                    pass

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
            self.client_id = None
            self.welcome_data = None

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

    Each WebSocket client gets its own dedicated TCP connection to the
    server, so each browser session has an independent client_id, station
    claim, and telemetry stream.  This enables true multiplayer where
    multiple browsers connect simultaneously and each claims a different
    crew station.

    Uses Protocol v1 envelope format for all messages.
    """

    def __init__(self, ws_host: str = "0.0.0.0", ws_port: int = DEFAULT_WS_PORT,
                 tcp_host: str = DEFAULT_HOST, tcp_port: int = DEFAULT_TCP_PORT):
        self.ws_host = ws_host
        self.ws_port = ws_port
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port
        # Per-WS-client TCP connections: websocket -> TCPConnection
        self._client_tcp: Dict[WebSocketServerProtocol, TCPConnection] = {}
        self.clients: Set[WebSocketServerProtocol] = set()
        self._running = False

    async def register(self, websocket: WebSocketServerProtocol):
        """Register a new WebSocket client with its own TCP connection."""
        self.clients.add(websocket)
        client_addr = websocket.remote_address
        logger.info(f"WS client connected: {client_addr} (total: {len(self.clients)})")

        # Create a dedicated TCP connection for this WS client
        tcp = TCPConnection(self.tcp_host, self.tcp_port)
        self._client_tcp[websocket] = tcp

        connected = await tcp.connect()
        if connected:
            # Send connection status with the server-assigned client_id
            status_data = {
                "status": "connected",
                "tcp_connected": True,
                "tcp_host": tcp.host,
                "tcp_port": tcp.port,
            }
            if tcp.client_id:
                status_data["client_id"] = tcp.client_id
            if tcp.welcome_data:
                status_data["server_mode"] = tcp.welcome_data.get("mode")

            envelope = WSEnvelope.status(**status_data)
            try:
                await websocket.send(envelope.to_wire())
            except Exception:
                pass
        else:
            await self._send_status(websocket, "tcp_disconnected", tcp)

    async def unregister(self, websocket: WebSocketServerProtocol):
        """Unregister a WebSocket client and close its TCP connection."""
        self.clients.discard(websocket)
        client_addr = websocket.remote_address

        # Close dedicated TCP connection
        tcp = self._client_tcp.pop(websocket, None)
        if tcp:
            await tcp.disconnect()

        logger.info(f"WS client disconnected: {client_addr} (total: {len(self.clients)})")

    def _build_status_message(self, status: str, tcp: Optional[TCPConnection] = None) -> str:
        """Build a connection status message payload using Protocol v1."""
        host = tcp.host if tcp else self.tcp_host
        port = tcp.port if tcp else self.tcp_port
        connected = tcp.connected if tcp else False
        envelope = WSEnvelope.status(
            status=status,
            tcp_connected=connected,
            tcp_host=host,
            tcp_port=port,
        )
        return envelope.to_wire()

    async def _send_status(self, websocket: WebSocketServerProtocol, status: str,
                           tcp: Optional[TCPConnection] = None):
        """Send connection status to a client."""
        if tcp is None:
            tcp = self._client_tcp.get(websocket)
        msg = self._build_status_message(status, tcp)
        try:
            await websocket.send(msg)
        except Exception:
            pass

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
            tcp = self._client_tcp.get(websocket)
            status = "connected" if (tcp and tcp.connected) else "disconnected"
            await self._send_status(websocket, status, tcp)
            return

        if cmd == "_discover":
            # Discovery request - forward to TCP server for full info
            pass  # Let it fall through to TCP forwarding

        # Get this client's dedicated TCP connection
        tcp = self._client_tcp.get(websocket)
        if not tcp:
            error_data = {"tcp_connected": False}
            if request_id is not None:
                error_data["_request_id"] = request_id
            error_envelope = WSEnvelope.error("No TCP connection", error_data)
            await websocket.send(error_envelope.to_wire())
            return

        # Reconnect TCP if needed
        if not tcp.connected:
            connected = await tcp.connect()
            if not connected:
                error_data = {"tcp_connected": False}
                if request_id is not None:
                    error_data["_request_id"] = request_id
                error_envelope = WSEnvelope.error("TCP server unavailable", error_data)
                await websocket.send(error_envelope.to_wire())
                return

        # Forward to this client's TCP connection
        response = await tcp.send_receive(message)

        if response is None:
            # TCP error
            error_data = {"tcp_connected": False}
            if request_id is not None:
                error_data["_request_id"] = request_id
            error_envelope = WSEnvelope.error(
                "TCP server unavailable",
                error_data
            )
            await websocket.send(error_envelope.to_wire())
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

    async def _tcp_health_loop(self):
        """Periodically check TCP health and reconnect dead connections."""
        while self._running:
            for ws, tcp in list(self._client_tcp.items()):
                if not tcp.connected:
                    connected = await tcp.connect()
                    if connected:
                        await self._send_status(ws, "tcp_connected", tcp)
            await asyncio.sleep(5)

    async def start(self):
        """Start the WebSocket server."""
        self._running = True
        logger.info(f"Starting WebSocket bridge on ws://{self.ws_host}:{self.ws_port}")
        logger.info(f"TCP target: {self.tcp_host}:{self.tcp_port}")
        logger.info("Mode: per-client TCP connections (multiplayer)")

        async with websockets.serve(
            self.handle_client,
            self.ws_host,
            self.ws_port,
            ping_interval=30,
            ping_timeout=10
        ):
            logger.info("WebSocket bridge running. Press Ctrl+C to stop.")
            health_task = asyncio.create_task(self._tcp_health_loop())
            try:
                while self._running:
                    await asyncio.sleep(1)
            finally:
                health_task.cancel()

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
        # Disconnect all per-client TCP connections
        for tcp in list(bridge._client_tcp.values()):
            await tcp.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
