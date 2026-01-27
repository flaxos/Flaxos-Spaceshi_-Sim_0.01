#!/usr/bin/env python3
"""
Flaxos Spaceship Sim - Unified Server Entrypoint.

This is the canonical server entrypoint. Use --mode to select operation mode:

  --mode minimal   Basic server, no station management (backwards compat)
  --mode station   Full multi-crew station-based control (default)

Examples:
  python -m server.main                     # Station mode, localhost
  python -m server.main --mode minimal      # Minimal mode for testing
  python -m server.main --lan               # Station mode, LAN accessible
  python -m server.main --port 9000         # Custom port
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import threading
from typing import Dict, Optional, Callable

# Ensure project root is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from server.config import (
    ServerConfig,
    ServerMode,
    DEFAULT_TCP_PORT,
    DEFAULT_HOST,
    DEFAULT_DT,
    DEFAULT_FLEET_DIR,
    PROTOCOL_VERSION,
)
from server.protocol import (
    Response,
    ErrorCode,
    _json_default,
    parse_request,
    make_error_response,
)
from hybrid_runner import HybridRunner
from utils.logger import setup_logging

logger = logging.getLogger(__name__)


class UnifiedServer:
    """
    Unified TCP server for Flaxos Spaceship Sim.

    Supports two operation modes:
    - MINIMAL: Basic command dispatch, no station management
    - STATION: Full multi-crew support with station permissions
    """

    def __init__(self, config: ServerConfig):
        self.config = config
        self.running = False

        # Initialize simulation
        self.runner = HybridRunner(fleet_dir=config.fleet_dir, dt=config.dt)

        # Station system (only initialized in STATION mode)
        self.station_manager = None
        self.crew_manager = None
        self.dispatcher = None
        self.telemetry_filter = None

        # Client tracking
        self.clients: Dict[str, socket.socket] = {}
        self.client_lock = threading.Lock()
        self.server_socket: Optional[socket.socket] = None

    def initialize(self) -> None:
        """Initialize server and load simulation."""
        logger.info(f"Initializing server in {self.config.mode.value} mode...")

        # Load ships
        self.runner.load_ships()
        self.runner.start()
        logger.info(f"Loaded {len(self.runner.simulator.ships)} ships")

        if self.config.mode == ServerMode.STATION:
            self._init_station_mode()

        logger.info(f"Server initialized (protocol v{PROTOCOL_VERSION})")

    def _init_station_mode(self) -> None:
        """Initialize station-based multi-crew system."""
        from server.stations import StationManager
        from server.stations.station_dispatch import (
            StationAwareDispatcher,
            register_legacy_commands,
        )
        from server.stations.station_commands import register_station_commands
        from server.stations.helm_commands import register_helm_commands
        from server.stations.fleet_commands import register_fleet_commands
        from server.telemetry.station_filter import StationTelemetryFilter
        from server.stations.crew_system import CrewManager

        self.station_manager = StationManager()
        self.crew_manager = CrewManager()
        self.dispatcher = StationAwareDispatcher(self.station_manager)
        self.telemetry_filter = StationTelemetryFilter(self.station_manager)

        # Register commands
        register_station_commands(
            self.dispatcher,
            self.station_manager,
            self.crew_manager,
            ship_provider=lambda: self.runner.simulator.ships,
        )
        register_helm_commands(
            self.dispatcher,
            ship_provider=lambda: self.runner.simulator.ships,
        )
        register_legacy_commands(self.dispatcher, self.runner)
        register_fleet_commands(
            self.dispatcher,
            self.station_manager,
            self.runner.simulator.fleet_manager,
        )

        logger.info("Station system initialized with multi-crew support")

    def dispatch(self, client_id: str, req: dict) -> dict:
        """
        Route a command to the appropriate handler.

        Args:
            client_id: Client identifier (used in station mode)
            req: Request dictionary with 'cmd' and parameters

        Returns:
            Response dictionary
        """
        cmd = req.get("cmd") or req.get("command")
        if not cmd:
            return Response.error("missing cmd", ErrorCode.MISSING_PARAM).to_dict()

        # Handle discover command (protocol v1)
        if cmd == "_discover":
            return {
                "ok": True,
                **self.config.to_discovery_info(),
            }

        if self.config.mode == ServerMode.STATION:
            return self._dispatch_station(client_id, cmd, req)
        else:
            return self._dispatch_minimal(cmd, req)

    def _dispatch_minimal(self, cmd: str, req: dict) -> dict:
        """
        Dispatch command in minimal mode (no station checks).

        This preserves the original run_server.py behavior.
        """
        from hybrid.command_handler import route_command

        if cmd == "get_state":
            return self._handle_get_state_minimal(req)

        if cmd == "get_events":
            return self._handle_get_events(req)

        if cmd == "list_scenarios":
            return {"ok": True, "scenarios": self.runner.list_scenarios()}

        if cmd == "load_scenario":
            return self._handle_load_scenario(req)

        if cmd == "get_mission":
            return {"ok": True, "mission": self.runner.get_mission_status()}

        if cmd == "get_mission_hints":
            clear = bool(req.get("clear", False))
            return {"ok": True, "hints": self.runner.get_mission_hints(clear=clear)}

        if cmd == "pause":
            on = bool(req.get("on", True))
            if on:
                self.runner.stop()
            else:
                self.runner.start()
            return {"ok": True, "paused": on}

        # Ship-specific commands
        ship_id = req.get("ship")
        if not ship_id:
            return Response.error("missing ship", ErrorCode.MISSING_PARAM).to_dict()

        ship = self.runner.simulator.ships.get(ship_id)
        if not ship:
            return Response.error(f"ship {ship_id} not found", ErrorCode.SHIP_NOT_FOUND).to_dict()

        # Normalize set_thrust command
        if cmd == "set_thrust":
            has_vector = any(k in req for k in ("x", "y", "z"))
            has_scalar = "thrust" in req
            if has_vector and not has_scalar:
                cmd = "set_thrust_vector"
            elif not has_scalar and not has_vector:
                req["thrust"] = 0.0

        command_data = {"command": cmd, "ship": ship_id, **req}
        command_data.pop("cmd", None)
        result = route_command(ship, command_data, self.runner.simulator.ships)

        if isinstance(result, dict) and "error" in result:
            return {"ok": False, "error": result["error"], "response": result}
        return {"ok": True, "response": result}

    def _dispatch_station(self, client_id: str, cmd: str, req: dict) -> dict:
        """
        Dispatch command in station mode (with permission checks).

        This provides the full multi-crew experience.
        """
        from server.stations.station_types import PermissionLevel

        session = self.station_manager.get_session(client_id)

        # Global commands (no station required)
        if cmd == "get_state":
            return self._handle_get_state_station(client_id, req)

        if cmd == "get_events":
            return self._handle_get_events_station(client_id, req)

        if cmd == "list_scenarios":
            return {"ok": True, "scenarios": self.runner.list_scenarios()}

        if cmd == "load_scenario":
            # Allow scenario loading - auto-assign client to player ship afterward
            # Permission check is relaxed for single-player experience
            result = self._handle_load_scenario(req)

            # If successful, auto-assign client to the player ship with captain control
            if result.get("ok") and result.get("player_ship_id"):
                player_ship_id = result["player_ship_id"]
                from server.stations.station_types import StationType

                # Assign client to player ship
                self.station_manager.assign_to_ship(client_id, player_ship_id)

                # Claim captain station for full ship control
                self.station_manager.claim_station(
                    client_id,
                    player_ship_id,
                    StationType.CAPTAIN
                )

                result["auto_assigned"] = True
                result["assigned_ship"] = player_ship_id
                result["station"] = "captain"
                logger.info(f"Auto-assigned {client_id} to {player_ship_id} as captain")

            return result

        if cmd == "get_mission":
            return {"ok": True, "mission": self.runner.get_mission_status()}

        if cmd == "get_mission_hints":
            clear = bool(req.get("clear", False))
            return {"ok": True, "hints": self.runner.get_mission_hints(clear=clear)}

        if cmd == "pause":
            if session and session.station and session.station.value == "captain":
                on = bool(req.get("on", True))
                if on:
                    self.runner.stop()
                else:
                    self.runner.start()
                return {"ok": True, "paused": on}
            return Response.error("Only captain can pause simulation", ErrorCode.PERMISSION_DENIED).to_dict()

        # Get ship_id from session or request
        ship_id = req.get("ship")
        metadata = self.dispatcher.command_metadata.get(cmd, {})
        requires_ship = metadata.get("requires_ship", True)

        if not ship_id and session and session.ship_id:
            ship_id = session.ship_id

        if requires_ship and not ship_id:
            return Response.error("missing ship", ErrorCode.MISSING_PARAM).to_dict()

        # Route through station-aware dispatcher
        args = {k: v for k, v in req.items() if k not in ("cmd", "command")}
        if ship_id:
            args["ship"] = ship_id

        result = self.dispatcher.dispatch(client_id, ship_id or "", cmd, args)
        return result.to_dict()

    def _handle_get_state_minimal(self, req: dict) -> dict:
        """Handle get_state in minimal mode."""
        ship_id = req.get("ship")
        states = self.runner.get_all_ship_states()

        payload = {
            "ok": True,
            "t": self.runner.simulator.time,
            "ships": [self._format_ship_state(state) for state in states.values()],
        }

        if ship_id:
            ship_state = self.runner.get_ship_state(ship_id)
            payload["ship"] = ship_id
            payload["state"] = ship_state
            if isinstance(ship_state, dict) and "error" in ship_state:
                payload["ok"] = False
                payload["error"] = ship_state["error"]

        return payload

    def _handle_get_state_station(self, client_id: str, req: dict) -> dict:
        """Handle get_state in station mode with telemetry filtering."""
        from hybrid.telemetry import get_ship_telemetry, get_telemetry_snapshot

        ship_id = req.get("ship")
        session = self.station_manager.get_session(client_id)

        if not session:
            return Response.error("Client not registered", ErrorCode.NOT_REGISTERED).to_dict()

        if not ship_id:
            # Get all ships
            full_telemetry = get_telemetry_snapshot(self.runner.simulator)
            filtered = self.telemetry_filter.filter_telemetry_for_client(
                client_id, full_telemetry
            )
            return {"ok": True, "t": self.runner.simulator.time, **filtered}

        # Get specific ship
        if not session.ship_id:
            return Response.error("Not assigned to a ship", ErrorCode.NOT_ASSIGNED).to_dict()

        if session.ship_id != ship_id:
            return Response.error("Can only view assigned ship", ErrorCode.PERMISSION_DENIED).to_dict()

        ship = self.runner.simulator.ships.get(ship_id)
        if not ship:
            return Response.error(f"Ship {ship_id} not found", ErrorCode.SHIP_NOT_FOUND).to_dict()

        ship_telemetry = get_ship_telemetry(ship, self.runner.simulator.time)
        filtered = self.telemetry_filter.filter_ship_state_for_client(
            client_id, ship_id, ship_telemetry
        )

        return {"ok": True, "ship": ship_id, "state": filtered, "t": self.runner.simulator.time}

    def _handle_get_events(self, req: dict) -> dict:
        """Handle get_events command (minimal mode)."""
        limit = int(req.get("limit", 100))
        events = self._get_events(limit)
        return {"ok": True, "events": events, "total_events": len(events)}

    def _handle_get_events_station(self, client_id: str, req: dict) -> dict:
        """Handle get_events with station-based filtering."""
        session = self.station_manager.get_session(client_id)

        if not session:
            return Response.error("Client not registered", ErrorCode.NOT_REGISTERED).to_dict()

        limit = int(req.get("limit", 100))
        all_events = self._get_events(limit)

        if not session.station:
            return {"ok": True, "events": [], "message": "Claim a station to view events"}

        # Import filter function from station_server
        from server.stations.station_types import StationType, get_station_displays

        filtered = self._filter_events_for_station(
            all_events, session.station, session.ship_id
        )

        return {
            "ok": True,
            "events": filtered,
            "station": session.station.value,
            "total_events": len(all_events),
            "filtered_count": len(filtered),
        }

    def _get_events(self, limit: int) -> list:
        """Get recent events from simulator."""
        if hasattr(self.runner.simulator, "get_recent_events"):
            return self.runner.simulator.get_recent_events(limit=limit)
        elif hasattr(self.runner.simulator, "event_log"):
            return list(self.runner.simulator.event_log)[-limit:]
        elif hasattr(self.runner.simulator, "recent_events"):
            return self.runner.simulator.recent_events[-limit:]
        return []

    def _filter_events_for_station(self, events: list, station, ship_id: str) -> list:
        """Filter events based on station permissions."""
        from server.stations.station_types import StationType, get_station_displays

        if station == StationType.CAPTAIN:
            return events

        allowed_displays = get_station_displays(station)

        event_categories = {
            "autopilot": ["nav_status", "autopilot_status"],
            "navigation": ["nav_status", "position", "velocity"],
            "propulsion": ["propulsion_status", "helm_status"],
            "weapon": ["weapons_status", "ammunition", "hardpoints"],
            "target": ["target_info", "targeting_status"],
            "sensor": ["sensor_status", "contacts"],
            "contact": ["contacts", "contact_details"],
            "power": ["power_grid", "power_management_status"],
            "reactor": ["reactor_status", "power_grid"],
            "damage": ["damage_report", "hull_integrity"],
            "comm": ["comm_log", "message_queue"],
            "fleet": ["fleet_status"],
            "critical": ["all"],
            "alert": ["all"],
            "mission": ["all"],
        }

        filtered = []
        for event in events:
            if not isinstance(event, dict):
                continue

            event_type = event.get("type", "")
            event_ship = event.get("ship_id", "")

            if event_ship and event_ship != ship_id:
                continue

            should_include = False
            for category, required_displays in event_categories.items():
                if category in event_type.lower():
                    if "all" in required_displays:
                        should_include = True
                        break
                    if any(display in allowed_displays for display in required_displays):
                        should_include = True
                        break

            if not should_include:
                if any(kw in event_type.lower() for kw in ["critical", "alert", "warning", "mission"]):
                    should_include = True

            if should_include:
                filtered.append(event)

        return filtered

    def _handle_load_scenario(self, req: dict) -> dict:
        """Handle load_scenario command."""
        scenario_name = req.get("scenario") or req.get("name") or req.get("file")
        if not scenario_name:
            return Response.error("missing scenario", ErrorCode.MISSING_PARAM).to_dict()

        loaded = self.runner.load_scenario(scenario_name)
        if loaded <= 0:
            return Response.error(
                f"Failed to load scenario {scenario_name}",
                ErrorCode.INTERNAL_ERROR
            ).to_dict()

        return {
            "ok": True,
            "scenario": scenario_name,
            "ships_loaded": loaded,
            "player_ship_id": self.runner.player_ship_id,
            "mission": self.runner.get_mission_status(),
        }

    @staticmethod
    def _format_ship_state(state: dict) -> dict:
        """Format ship state for API response."""
        return {
            "id": state.get("id"),
            "name": state.get("name", state.get("id")),
            "pos": state.get("position", {}),
            "vel": state.get("velocity", {}),
            "attitude": state.get("orientation", {}),
            "systems": state.get("systems", {}),
        }

    def handle_connection(self, conn: socket.socket, addr: tuple) -> None:
        """Handle a client connection."""
        client_id = f"client_{id(conn)}"

        if self.config.mode == ServerMode.STATION:
            client_id = self.station_manager.generate_client_id()
            player_name = f"Player_{client_id}"
            self.station_manager.register_client(client_id, player_name)

        with self.client_lock:
            self.clients[client_id] = conn

        logger.info(f"Client connected: {client_id} from {addr}")

        # Send welcome message (station mode only)
        if self.config.mode == ServerMode.STATION:
            welcome = {
                "ok": True,
                "message": "Connected to Flaxos Spaceship Sim",
                "client_id": client_id,
                "mode": self.config.mode.value,
                "version": PROTOCOL_VERSION,
                "instructions": {
                    "assign_ship": "Use assign_ship command to join a ship",
                    "claim_station": "Use claim_station command to claim a station",
                    "help": "Use my_status to see your current status",
                },
            }
            try:
                conn.sendall((json.dumps(welcome) + "\n").encode("utf-8"))
            except (OSError, BrokenPipeError):
                pass

        # Handle commands
        buf = b""
        try:
            while self.running:
                try:
                    if self.config.mode == ServerMode.STATION:
                        conn.settimeout(1.0)
                    data = conn.recv(4096)
                    if not data:
                        break

                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if not line.strip():
                            continue

                        try:
                            req = json.loads(line.decode("utf-8"))
                        except json.JSONDecodeError:
                            err = json.dumps({"ok": False, "error": "bad json"}) + "\n"
                            conn.sendall(err.encode("utf-8"))
                            continue

                        logger.debug(f"Request from {client_id}: {req}")
                        resp = self.dispatch(client_id, req)
                        conn.sendall(
                            (json.dumps(resp, default=_json_default) + "\n").encode("utf-8")
                        )

                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Error handling request from {client_id}: {e}")
                    break

        finally:
            logger.info(f"Client disconnected: {client_id}")
            with self.client_lock:
                self.clients.pop(client_id, None)
            if self.config.mode == ServerMode.STATION and self.station_manager:
                self.station_manager.unregister_client(client_id)
            conn.close()

    def start(self) -> None:
        """Start the server."""
        self.initialize()

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.config.host, self.config.tcp_port))
        self.server_socket.listen(8)
        self.running = True

        mode_str = "multi-crew" if self.config.mode == ServerMode.STATION else "minimal"
        logger.info(
            f"Server listening on {self.config.host}:{self.config.tcp_port} "
            f"(mode={mode_str}, dt={self.config.dt})"
        )

        try:
            while self.running:
                try:
                    client, addr = self.server_socket.accept()
                    thread = threading.Thread(
                        target=self.handle_connection,
                        args=(client, addr),
                        daemon=True,
                    )
                    thread.start()
                except Exception as e:
                    if self.running:
                        logger.error(f"Error accepting connection: {e}")

        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the server."""
        self.running = False

        with self.client_lock:
            for client_id, conn in list(self.clients.items()):
                try:
                    conn.close()
                except OSError:
                    pass
            self.clients.clear()

        self.runner.stop()

        if self.server_socket:
            self.server_socket.close()

        logger.info("Server stopped")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    ap = argparse.ArgumentParser(
        description="Flaxos Spaceship Sim - Unified Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m server.main                     # Station mode, localhost
  python -m server.main --mode minimal      # Minimal mode for testing
  python -m server.main --lan               # Station mode, LAN accessible
  python -m server.main --port 9000         # Custom port
        """,
    )
    ap.add_argument(
        "--mode",
        choices=["minimal", "station"],
        default="station",
        help="Server mode: minimal (no stations) or station (multi-crew, default)",
    )
    ap.add_argument("--host", default=DEFAULT_HOST, help="Host to bind to")
    ap.add_argument("--port", type=int, default=DEFAULT_TCP_PORT, help="Port to bind to")
    ap.add_argument("--dt", type=float, default=DEFAULT_DT, help="Simulation timestep")
    ap.add_argument("--fleet-dir", default=DEFAULT_FLEET_DIR, help="Fleet directory")
    ap.add_argument("--lan", action="store_true", help="Enable LAN mode (bind to 0.0.0.0)")
    ap.add_argument("--log-file", default=None, help="Log file path")
    return ap


def main() -> None:
    """Main entry point."""
    ap = build_arg_parser()
    args = ap.parse_args()

    # Setup logging
    log_path = setup_logging(args.log_file)
    if log_path:
        logger.info(f"Logging to file: {log_path}")

    # Build config
    config = ServerConfig(
        mode=ServerMode(args.mode),
        host=args.host,
        tcp_port=args.port,
        dt=args.dt,
        fleet_dir=args.fleet_dir,
        log_file=args.log_file,
        lan_mode=args.lan,
    )

    # Start server
    server = UnifiedServer(config)
    server.start()


if __name__ == "__main__":
    main()
