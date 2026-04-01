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
    DEFAULT_TIME_SCALE,
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
from server.command_validator import validate_command_params
from server.rate_limiter import RateLimiter
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

    # Maximum bytes allowed in a single client's receive buffer before
    # the connection is forcibly closed.  Prevents OOM from a malicious
    # client that sends data without newlines.
    MAX_BUFFER_SIZE: int = 1_000_000  # 1 MB

    def __init__(self, config: ServerConfig):
        self.config = config
        self.running = False

        # Initialize simulation
        self.runner = HybridRunner(
            fleet_dir=config.fleet_dir,
            dt=config.dt,
            time_scale=config.time_scale,
        )

        # Station system (only initialized in STATION mode)
        self.station_manager = None
        self.crew_manager = None
        self.ai_crew_manager = None
        self.dispatcher = None
        self.telemetry_filter = None

        # Client tracking
        self.clients: Dict[str, socket.socket] = {}
        self.client_lock = threading.Lock()
        self.server_socket: Optional[socket.socket] = None

        # Rate limiter (20 commands/sec sustained, burst of 30)
        self.rate_limiter = RateLimiter(rate=20.0, burst=30)

    def initialize(self) -> None:
        """Initialize server and load simulation."""
        logger.info(f"Initializing server in {self.config.mode.value} mode...")

        # Verify command registration consistency
        from hybrid.command_registry_lint import check_on_startup
        check_on_startup()

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
        from server.stations.ai_crew import AICrewManager
        from server.stations.crew_binding import CrewStationBinder
        from hybrid.systems.crew_binding_system import CrewBindingSystem

        self.station_manager = StationManager()
        self.crew_manager = CrewManager()
        self.ai_crew_manager = AICrewManager(default_competence=0.7)

        # Wire up crew-station binding so crew skill multipliers affect gameplay.
        # CrewBindingSystem instances on each ship delegate to this shared binder.
        crew_binder = CrewStationBinder(self.crew_manager)
        CrewBindingSystem.set_shared_state(self.crew_manager, crew_binder)
        self.crew_binder = crew_binder
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

        # Start AI crew background tick thread
        self._ai_crew_thread = threading.Thread(
            target=self._ai_crew_tick_loop,
            daemon=True,
        )
        self._ai_crew_thread.start()

        # Periodic stale-claim cleanup (runs every 60 seconds)
        self._stale_claim_thread = threading.Thread(
            target=self._stale_claim_cleanup_loop,
            daemon=True,
        )
        self._stale_claim_thread.start()

        logger.info("Station system initialized with multi-crew support")

    def dispatch(self, client_id: str, req: dict) -> dict:
        """
        Route a command to the appropriate handler.

        Server-authoritative validation:
        1. Rate limiting per client
        2. Parameter validation and sanitization
        3. Mode-specific dispatch (station or minimal)

        Args:
            client_id: Client identifier (used in station mode)
            req: Request dictionary with 'cmd' and parameters

        Returns:
            Response dictionary
        """
        cmd = req.get("cmd") or req.get("command")
        if not cmd:
            return Response.error("missing cmd", ErrorCode.MISSING_PARAM).to_dict()

        # Heartbeat: fire-and-forget session keepalive
        if cmd == "heartbeat":
            if self.station_manager:
                self.station_manager.update_activity(client_id)
            return {"ok": True}

        # Rate limiting (skip for state polling and discovery)
        if cmd not in ("get_state", "get_events", "get_combat_log", "_discover", "_ping", "_resume_session", "list_ship_classes", "get_ship_classes_full"):
            if not self.rate_limiter.allow(client_id):
                return Response.error(
                    "Rate limited: too many commands", ErrorCode.BAD_REQUEST
                ).to_dict()

        # Handle discover command (protocol v1)
        if cmd == "_discover":
            return {
                "ok": True,
                **self.config.to_discovery_info(),
            }

        # Handle session resumption (ws_bridge reconnect)
        if cmd == "_resume_session":
            return self._handle_resume_session(client_id, req)

        # Server-authoritative parameter validation
        is_valid, error_msg, sanitized = validate_command_params(cmd, req)
        if not is_valid:
            return Response.error(error_msg, ErrorCode.INVALID_PARAM).to_dict()
        req = sanitized

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

        if cmd == "get_combat_log":
            return self._handle_get_combat_log(req)

        if cmd == "list_scenarios":
            return {"ok": True, "scenarios": self.runner.list_scenarios()}

        if cmd == "list_ship_classes":
            return self._handle_list_ship_classes()

        if cmd == "get_ship_classes_full":
            return self._handle_get_ship_classes_full()

        if cmd == "save_ship_class":
            return self._handle_save_ship_class(req)

        if cmd == "save_scenario":
            return self._handle_save_scenario(req)

        if cmd == "get_scenario_yaml":
            return self._handle_get_scenario_yaml(req)

        if cmd == "load_scenario":
            return self._handle_load_scenario(req)

        if cmd == "generate_skirmish":
            return self._handle_generate_skirmish(req)

        if cmd == "get_mission":
            return {"ok": True, "mission": self.runner.get_mission_status()}

        if cmd == "get_mission_hints":
            clear = bool(req.get("clear", False))
            return {"ok": True, "hints": self.runner.get_mission_hints(clear=clear)}

        # Campaign management commands (meta-level, runner-scoped)
        if cmd in ("campaign_new", "campaign_save", "campaign_load", "campaign_status"):
            return self._handle_campaign_command(cmd, req)

        if cmd == "get_tick_metrics":
            return {"ok": True, **self.runner.simulator.get_tick_metrics()}

        if cmd == "set_time_scale":
            scale = float(req.get("time_scale", req.get("scale", 1.0)))
            scale = max(0.01, min(10.0, scale))
            self.runner.simulator.time_scale = scale
            return {"ok": True, "time_scale": scale}

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

        if cmd == "get_combat_log":
            return self._handle_get_combat_log(req)

        if cmd == "list_scenarios":
            return {"ok": True, "scenarios": self.runner.list_scenarios()}

        if cmd == "list_ship_classes":
            return self._handle_list_ship_classes()

        if cmd == "get_ship_classes_full":
            return self._handle_get_ship_classes_full()

        if cmd == "save_ship_class":
            return self._handle_save_ship_class(req)

        if cmd == "save_scenario":
            return self._handle_save_scenario(req)

        if cmd == "get_scenario_yaml":
            return self._handle_get_scenario_yaml(req)

        if cmd == "load_scenario":
            from server.stations.station_types import StationType

            has_active_ships = len(self.runner.simulator.ships) > 0
            is_captain = (
                session
                and session.station == StationType.CAPTAIN
            )
            is_only_client = len(self.station_manager.sessions) <= 1

            # Guard: if a mission is already running, only the captain
            # (or the sole connected client) may reload
            if has_active_ships and not is_captain and not is_only_client:
                return Response.error(
                    "Mission already in progress — only the captain can reload",
                    ErrorCode.PERMISSION_DENIED,
                ).to_dict()

            result = self._handle_load_scenario(req)

            # Purge stale station claims from the previous simulation
            if result.get("ok") and self.station_manager:
                active_ids = set(self.runner.simulator.ships.keys())
                self.station_manager.purge_claims_for_missing_ships(active_ids)

            # Auto-assign loading client to player ship as captain
            if result.get("ok") and result.get("player_ship_id"):
                player_ship_id = result["player_ship_id"]

                self.station_manager.assign_to_ship(client_id, player_ship_id)
                self.station_manager.claim_station(
                    client_id,
                    player_ship_id,
                    StationType.CAPTAIN,
                )

                result["auto_assigned"] = True
                result["assigned_ship"] = player_ship_id
                result["station"] = "captain"
                logger.info(f"Auto-assigned {client_id} to {player_ship_id} as captain")

            # Auto-reassign connected-but-unassigned clients to
            # the player ship after scenario reload purges their claims.
            if result.get("ok") and result.get("player_ship_id"):
                self._auto_reassign_orphaned_clients(result["player_ship_id"])

            # Register AI crew for all ships in the scenario
            if result.get("ok") and self.ai_crew_manager:
                for sid in self.runner.simulator.ships:
                    self.ai_crew_manager.register_ship(sid)

            return result

        if cmd == "generate_skirmish":
            from server.stations.station_types import StationType

            has_active_ships = len(self.runner.simulator.ships) > 0
            is_captain = (
                session
                and session.station == StationType.CAPTAIN
            )
            is_only_client = len(self.station_manager.sessions) <= 1

            if has_active_ships and not is_captain and not is_only_client:
                return Response.error(
                    "Mission already in progress — only the captain can generate a skirmish",
                    ErrorCode.PERMISSION_DENIED,
                ).to_dict()

            result = self._handle_generate_skirmish(req)

            if result.get("ok") and self.station_manager:
                active_ids = set(self.runner.simulator.ships.keys())
                self.station_manager.purge_claims_for_missing_ships(active_ids)

            if result.get("ok") and result.get("player_ship_id"):
                player_ship_id = result["player_ship_id"]
                self.station_manager.assign_to_ship(client_id, player_ship_id)
                self.station_manager.claim_station(
                    client_id, player_ship_id, StationType.CAPTAIN,
                )
                result["auto_assigned"] = True
                result["assigned_ship"] = player_ship_id
                result["station"] = "captain"

            if result.get("ok") and result.get("player_ship_id"):
                self._auto_reassign_orphaned_clients(result["player_ship_id"])

            if result.get("ok") and self.ai_crew_manager:
                for sid in self.runner.simulator.ships:
                    self.ai_crew_manager.register_ship(sid)

            return result

        if cmd == "get_mission":
            return {"ok": True, "mission": self.runner.get_mission_status()}

        if cmd == "get_mission_hints":
            clear = bool(req.get("clear", False))
            return {"ok": True, "hints": self.runner.get_mission_hints(clear=clear)}

        # Campaign commands -- captain-only for new/save/load, status is open
        if cmd in ("campaign_new", "campaign_save", "campaign_load", "campaign_status"):
            # campaign_status is read-only, allow from any station
            if cmd != "campaign_status":
                is_captain = session and session.station and session.station.value == "captain"
                is_only_client = len(self.station_manager.sessions) <= 1
                if not is_captain and not is_only_client:
                    return Response.error(
                        "Only captain can manage campaign state",
                        ErrorCode.PERMISSION_DENIED,
                    ).to_dict()
            return self._handle_campaign_command(cmd, req)

        if cmd == "get_tick_metrics":
            return {"ok": True, **self.runner.simulator.get_tick_metrics()}

        if cmd == "set_time_scale":
            if session and session.station and session.station.value == "captain":
                scale = float(req.get("time_scale", req.get("scale", 1.0)))
                scale = max(0.01, min(10.0, scale))
                self.runner.simulator.time_scale = scale
                return {"ok": True, "time_scale": scale}
            return Response.error("Only captain can change time scale", ErrorCode.PERMISSION_DENIED).to_dict()

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

        # Capture station before release (release clears session.station)
        _pre_release_station = None
        _pre_release_ship = None
        if cmd == "release_station" and self.ai_crew_manager:
            pre_session = self.station_manager.get_session(client_id)
            if pre_session and pre_session.station and pre_session.ship_id:
                _pre_release_station = pre_session.station
                _pre_release_ship = pre_session.ship_id

        result = self.dispatcher.dispatch(client_id, ship_id or "", cmd, args)

        # Notify AI crew manager when stations are claimed/released
        if self.ai_crew_manager and result.success:
            if cmd == "claim_station":
                station_name = args.get("station", "")
                from server.stations.station_types import StationType
                try:
                    st = StationType(station_name.lower())
                    sess = self.station_manager.get_session(client_id)
                    if sess and sess.ship_id:
                        self.ai_crew_manager.deactivate_station(sess.ship_id, st)
                except ValueError:
                    pass
            elif cmd == "release_station" and _pre_release_station and _pre_release_ship:
                self.ai_crew_manager.activate_station(_pre_release_ship, _pre_release_station)

        return result.to_dict()

    def _auto_reassign_orphaned_clients(self, player_ship_id: str) -> None:
        """
        After a scenario reload, re-assign connected clients that lost
        their ship/station to the player ship.

        Each client is re-assigned to the player ship and re-claims
        their previous station type (stored before the purge cleared it).
        If no previous station is known, CAPTAIN is attempted.

        Args:
            player_ship_id: The player-controlled ship in the new scenario.
        """
        from server.stations.station_types import StationType

        for session in self.station_manager.get_all_clients():
            # Skip clients that already have a valid ship assignment
            if session.ship_id:
                continue

            self.station_manager.assign_to_ship(session.client_id, player_ship_id)

            # Try to reclaim previous station, fall back to CAPTAIN
            station = session.station or StationType.CAPTAIN
            success, _ = self.station_manager.claim_station(
                session.client_id, player_ship_id, station,
            )

            if success:
                logger.info(
                    f"Auto-reassigned orphaned client {session.client_id} "
                    f"to {player_ship_id} as {station.value}"
                )
            else:
                logger.info(
                    f"Could not auto-claim {station.value} for "
                    f"{session.client_id} on {player_ship_id}"
                )

    def _handle_resume_session(self, client_id: str, req: dict) -> dict:
        """
        Handle session resumption after ws_bridge TCP reconnect.

        When the ws_bridge loses its TCP connection and reconnects, the
        server assigns a new client_id. This command lets the bridge
        send its old client_id so the server can migrate the old
        session state (ship assignment, station claim) to the new ID,
        preventing orphan sessions.

        Args:
            client_id: The new client_id assigned on this connection
            req: Request with 'old_client_id' field

        Returns:
            Response indicating whether migration succeeded
        """
        if not self.station_manager:
            return {"ok": False, "error": "Session resume only available in station mode"}

        old_client_id = req.get("old_client_id")
        if not old_client_id:
            return Response.error("missing old_client_id", ErrorCode.MISSING_PARAM).to_dict()

        if old_client_id == client_id:
            return {"ok": True, "message": "Same session, no migration needed"}

        migrated = self.station_manager.migrate_session(old_client_id, client_id)

        if migrated:
            session = self.station_manager.get_session(client_id)
            return {
                "ok": True,
                "message": "Session resumed",
                "client_id": client_id,
                "ship_id": session.ship_id if session else None,
                "station": session.station.value if session and session.station else None,
            }

        return {
            "ok": True,
            "message": "No previous session to resume",
            "client_id": client_id,
        }

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
            result = {"ok": True, "t": self.runner.simulator.time, **filtered}
            # Include active scenario metadata so clients can detect mission state
            if self.runner._current_scenario_name:
                result["active_scenario"] = self.runner._current_scenario_name
            result["ship_count"] = len(self.runner.simulator.ships)
            return result

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

        result = {"ok": True, "ship": ship_id, "state": filtered, "t": self.runner.simulator.time}

        # Include simulation-wide projectiles and torpedoes for stations
        # that need them (TACTICAL, CAPTAIN).  These live on the simulator,
        # not per-ship, so get_ship_telemetry() doesn't include them.
        from server.stations.station_types import StationType
        if session.station in (StationType.TACTICAL, StationType.CAPTAIN):
            sim = self.runner.simulator
            result["projectiles"] = (
                sim.projectile_manager.get_state()
                if hasattr(sim, "projectile_manager") else []
            )
            result["torpedoes"] = (
                sim.torpedo_manager.get_state()
                if hasattr(sim, "torpedo_manager") else []
            )

        return result

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

        # Filter events based on station permissions
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

    def _handle_get_combat_log(self, req: dict) -> dict:
        """Handle get_combat_log command — return causal chain combat entries."""
        limit = int(req.get("limit", 50))
        since_id = int(req.get("since_id", 0))
        event_type = req.get("event_type")
        weapon = req.get("weapon")
        target = req.get("target")

        combat_log = getattr(self.runner.simulator, "combat_log", None)
        if not combat_log:
            return {"ok": True, "entries": [], "latest_id": 0}

        entries = combat_log.get_entries(
            limit=limit,
            since_id=since_id,
            event_type=event_type,
            weapon=weapon,
            target=target,
        )
        return {
            "ok": True,
            "entries": entries,
            "latest_id": combat_log.get_latest_id(),
        }

    def _filter_events_for_station(self, events: list, station, ship_id: str) -> list:
        """Filter events based on station permissions."""
        from server.stations.station_types import StationType, get_station_displays

        if station == StationType.CAPTAIN:
            return events

        allowed_displays = get_station_displays(station)

        event_categories = {
            # HELM events
            "autopilot": ["nav_status", "autopilot_status"],
            "navigation": ["nav_status", "position", "velocity"],
            "propulsion": ["propulsion_status", "helm_status"],
            "course": ["nav_status", "course_plot"],
            "docking": ["docking_guidance"],

            # TACTICAL events
            "weapon": ["weapons_status", "ammunition", "hardpoints"],
            "target": ["target_info", "targeting_status"],
            "fire": ["weapons_status", "firing_solution"],
            "pdc": ["pdc_status", "weapons_status"],
            "torpedo": ["weapons_status", "ammunition", "hardpoints"],
            "threat": ["threat_board"],

            # OPS events
            "sensor": ["sensor_status", "contacts"],
            "contact": ["contacts", "contact_details"],
            "detection": ["contacts", "detection_log"],
            "ping": ["sensor_status"],
            "ecm": ["ecm_status", "eccm_status"],
            "signature": ["signature_analysis"],
            "crew": ["crew_fatigue_status", "crew_station_status"],

            # ENGINEERING events
            "power": ["power_grid", "power_management_status"],
            "reactor": ["reactor_status", "power_grid"],
            "damage": ["damage_report", "hull_integrity"],
            "repair": ["repair_queue", "damage_report"],
            "system": ["system_status"],
            "fuel": ["fuel_status"],
            "engineering": ["engineering_status", "system_status"],

            # COMMS events
            "comm": ["comm_log", "message_queue"],
            "fleet": ["fleet_status"],
            "hail": ["comm_log"],
            "message": ["message_queue"],
            "iff": ["iff_contacts"],

            # FLEET_COMMANDER events
            "fleet_tactical": ["fleet_tactical_display", "threat_board"],
            "fleet_formation": ["fleet_formation_view"],
            "fleet_status": ["fleet_status_board"],
            "engagement": ["engagement_summary"],

            # System-wide events (all stations see these)
            "critical": ["all"],
            "alert": ["all"],
            "mission": ["all"],
            "mission_update": ["all"],
            "mission_complete": ["all"],
            "hint": ["all"],
            "gimbal_lock": ["nav_status", "helm_status"],
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

    def _handle_list_ship_classes(self) -> dict:
        """Handle list_ship_classes command."""
        from hybrid.ship_class_registry import get_registry
        registry = get_registry()
        return {"ok": True, "ship_classes": registry.list_classes()}

    def _handle_get_ship_classes_full(self) -> dict:
        """Handle get_ship_classes_full command — returns full configs for editor."""
        from hybrid.commands.editor_commands import get_ship_classes_full
        return get_ship_classes_full()

    def _handle_save_ship_class(self, req: dict) -> dict:
        """Handle save_ship_class command — persist a ship class JSON to disk."""
        from hybrid.commands.editor_commands import save_ship_class
        from hybrid.ship_class_registry import get_registry

        config = req.get("config")
        if not config:
            return {"ok": False, "error": "Missing 'config' parameter"}

        result = save_ship_class(config)
        # Reload the registry so the new class is immediately available
        if result.get("ok"):
            registry = get_registry()
            registry._load_all()
        return result

    def _handle_save_scenario(self, req: dict) -> dict:
        """Handle save_scenario command -- write YAML content to scenarios/ directory."""
        import re

        filename = req.get("filename", "").strip()
        yaml_content = req.get("yaml_content", "")

        if not filename:
            return {"ok": False, "error": "Missing 'filename' parameter"}
        if not yaml_content:
            return {"ok": False, "error": "Missing 'yaml_content' parameter"}

        # Sanitize filename: only allow alphanumeric, underscores, hyphens, dots
        if not re.match(r'^[\w\-]+\.ya?ml$', filename):
            return {"ok": False, "error": f"Invalid filename: {filename}"}

        scenarios_dir = self.runner.scenarios_dir
        filepath = os.path.join(scenarios_dir, filename)

        try:
            os.makedirs(scenarios_dir, exist_ok=True)
            with open(filepath, "w") as f:
                f.write(yaml_content)
            logger.info(f"Scenario saved: {filepath}")
            return {"ok": True, "filepath": filepath}
        except Exception as e:
            logger.error(f"Failed to save scenario: {e}")
            return {"ok": False, "error": str(e)}

    def _handle_get_scenario_yaml(self, req: dict) -> dict:
        """Handle get_scenario_yaml command -- read and parse a scenario file for editor."""
        import yaml as _yaml

        scenario_id = req.get("scenario", "").strip()
        if not scenario_id:
            return {"ok": False, "error": "Missing 'scenario' parameter"}

        scenarios_dir = self.runner.scenarios_dir
        # Try with and without .yaml extension
        candidates = [
            os.path.join(scenarios_dir, scenario_id + ".yaml"),
            os.path.join(scenarios_dir, scenario_id + ".yml"),
            os.path.join(scenarios_dir, scenario_id),
        ]

        filepath = None
        for c in candidates:
            if os.path.isfile(c):
                filepath = c
                break

        if not filepath:
            return {"ok": False, "error": f"Scenario not found: {scenario_id}"}

        try:
            with open(filepath, "r") as f:
                data = _yaml.safe_load(f)
            return {"ok": True, "data": data}
        except Exception as e:
            logger.error(f"Failed to read scenario {filepath}: {e}")
            return {"ok": False, "error": str(e)}

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
            "scenario_name": self.runner._current_scenario_name or scenario_name,
            "ships_loaded": loaded,
            "player_ship_id": self.runner.player_ship_id,
            "mission": self.runner.get_mission_status(),
        }

    def _handle_generate_skirmish(self, req: dict) -> dict:
        """Handle generate_skirmish command.

        Generates a scenario from parameters and loads it directly
        into the runner without writing to disk.
        """
        from hybrid.scenarios.skirmish_generator import generate_skirmish

        try:
            scenario_data = generate_skirmish(req)
        except (ValueError, TypeError) as e:
            return Response.error(str(e), ErrorCode.INVALID_PARAM).to_dict()
        except Exception as e:
            logger.error(f"Skirmish generation failed: {e}", exc_info=True)
            return Response.error(
                f"Failed to generate skirmish: {e}",
                ErrorCode.INTERNAL_ERROR,
            ).to_dict()

        loaded = self.runner.load_scenario_dict(scenario_data)
        if loaded <= 0:
            return Response.error(
                "Generated scenario produced no ships",
                ErrorCode.INTERNAL_ERROR,
            ).to_dict()

        return {
            "ok": True,
            "scenario": "generated_skirmish",
            "scenario_name": scenario_data.get("name", "Generated Skirmish"),
            "ships_loaded": loaded,
            "player_ship_id": self.runner.player_ship_id,
            "mission": self.runner.get_mission_status(),
        }

    def _handle_campaign_command(self, cmd: str, req: dict) -> dict:
        """Route campaign management commands to their handlers.

        Campaign commands are runner-scoped (not ship-scoped) because
        campaign state lives on the runner, not on any individual ship.
        """
        from hybrid.commands.campaign_commands import (
            cmd_campaign_new,
            cmd_campaign_save,
            cmd_campaign_load,
            cmd_campaign_status,
        )

        handlers = {
            "campaign_new": cmd_campaign_new,
            "campaign_save": cmd_campaign_save,
            "campaign_load": cmd_campaign_load,
            "campaign_status": cmd_campaign_status,
        }
        handler = handlers.get(cmd)
        if not handler:
            return Response.error(f"Unknown campaign command: {cmd}", ErrorCode.INVALID_PARAM).to_dict()
        try:
            return handler(self.runner, req)
        except Exception as exc:
            logger.error("Campaign command %s failed: %s", cmd, exc, exc_info=True)
            return Response.error(str(exc), ErrorCode.INTERNAL_ERROR).to_dict()

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

                    # Guard against unbounded buffer growth (OOM protection)
                    if len(buf) > self.MAX_BUFFER_SIZE:
                        logger.warning(
                            f"Client {client_id} exceeded buffer limit "
                            f"({len(buf)} bytes), disconnecting"
                        )
                        break

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

            # Capture station/ship before unregister clears them
            _released_station = None
            _released_ship = None
            if self.config.mode == ServerMode.STATION and self.station_manager:
                session = self.station_manager.get_session(client_id)
                if session:
                    _released_station = session.station
                    _released_ship = session.ship_id

            with self.client_lock:
                self.clients.pop(client_id, None)
            self.rate_limiter.remove_client(client_id)

            if self.config.mode == ServerMode.STATION and self.station_manager:
                self.station_manager.unregister_client(client_id)

                # Auto-promote a new captain if the departing client held
                # CAPTAIN.  Without this, pause / time-scale / load-scenario
                # become permanently locked out.
                if (
                    _released_station is not None
                    and _released_station.value == "captain"
                    and _released_ship
                ):
                    self.station_manager.elect_new_captain(_released_ship)

            conn.close()

    def _ai_crew_tick_loop(self) -> None:
        """Background loop for AI crew behaviors."""
        import time as _time
        while self.running:
            try:
                if self.ai_crew_manager and self.runner.simulator.ships:
                    self.ai_crew_manager.tick(
                        self.runner.simulator.ships,
                        self.config.dt,
                    )
            except Exception as e:
                logger.debug(f"AI crew tick error: {e}")
            _time.sleep(2.0)  # AI acts every 2 seconds

    def _stale_claim_cleanup_loop(self) -> None:
        """Periodically release stations held by clients that stopped heartbeating.

        The StationManager.cleanup_stale_claims() method already exists but
        was never invoked.  This daemon thread calls it every 60 seconds so
        that inactive clients do not permanently block stations.
        """
        import time as _time
        while self.running:
            _time.sleep(60.0)
            try:
                if self.station_manager:
                    removed = self.station_manager.cleanup_stale_claims()
                    if removed:
                        logger.info(
                            f"Stale-claim cleanup released {len(removed)} "
                            f"client(s): {removed}"
                        )
            except Exception as e:
                logger.debug(f"Stale-claim cleanup error: {e}")

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
    ap.add_argument(
        "--time-scale", type=float, default=DEFAULT_TIME_SCALE,
        help="Time scale multiplier (1.0=real-time, 2.0=double speed)"
    )
    ap.add_argument("--fleet-dir", default=DEFAULT_FLEET_DIR, help="Fleet directory")
    ap.add_argument("--lan", action="store_true", help="Enable LAN mode (bind to 0.0.0.0)")
    ap.add_argument("--log-file", default=None, help="Log file path")
    ap.add_argument(
        "--campaign", default=None, metavar="SAVE.json",
        help="Load a campaign save file at startup (enables campaign mode)",
    )
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
        time_scale=args.time_scale,
        fleet_dir=args.fleet_dir,
        log_file=args.log_file,
        lan_mode=args.lan,
    )

    # Start server
    server = UnifiedServer(config)

    # Load campaign save if specified on the command line
    if args.campaign:
        from hybrid.campaign.campaign_state import CampaignState
        import os
        campaign_path = args.campaign
        if not os.path.isabs(campaign_path):
            campaign_path = os.path.join(ROOT_DIR, campaign_path)
        try:
            state = CampaignState.load(campaign_path)
            server.runner._campaign_state = state
            logger.info("Campaign loaded from CLI: %s", campaign_path)
        except FileNotFoundError:
            logger.error("Campaign file not found: %s", campaign_path)
            sys.exit(1)
        except Exception as exc:
            logger.error("Failed to load campaign: %s", exc)
            sys.exit(1)

    server.start()


if __name__ == "__main__":
    main()
