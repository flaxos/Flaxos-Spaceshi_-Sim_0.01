"""
Station-aware TCP server for multi-crew ship control.

Extends the basic TCP server with station management, client tracking,
and permission-based command routing.
"""

import os
import sys
import json
import socket
import threading
import argparse
import logging
from typing import Dict, Optional

# Ensure project root is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from hybrid_runner import HybridRunner
from hybrid.telemetry import get_ship_telemetry, get_telemetry_snapshot

from server.stations import StationManager
from server.stations.station_dispatch import StationAwareDispatcher, CommandResult, register_legacy_commands
from server.stations.station_commands import register_station_commands
from server.stations.helm_commands import register_helm_commands
from server.stations.fleet_commands import register_fleet_commands
from server.telemetry.station_filter import StationTelemetryFilter
from server.stations.crew_system import CrewManager
from server.stations.station_types import PermissionLevel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StationServer:
    """
    Enhanced TCP server with station-based multi-crew control.
    """

    def __init__(self, host: str, port: int, dt: float, fleet_dir: str):
        self.host = host
        self.port = port
        self.dt = dt
        self.fleet_dir = fleet_dir

        # Initialize simulation
        self.runner = HybridRunner(fleet_dir=fleet_dir, dt=dt)

        # Initialize station system
        self.station_manager = StationManager()
        self.crew_manager = CrewManager()
        self.dispatcher = StationAwareDispatcher(self.station_manager)
        self.telemetry_filter = StationTelemetryFilter(self.station_manager)

        # Client tracking
        self.clients: Dict[str, socket.socket] = {}
        self.client_lock = threading.Lock()

        # Server socket
        self.server_socket: Optional[socket.socket] = None
        self.running = False

    def initialize(self):
        """Initialize the server and load ships"""
        logger.info("Initializing station server...")

        # Load ships
        self.runner.load_ships()
        self.runner.start()
        logger.info(f"Loaded {len(self.runner.simulator.ships)} ships")

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
        register_fleet_commands(self.dispatcher, self.station_manager, self.runner.simulator.fleet_manager)

        logger.info("Station server initialized with fleet support")

    def dispatch(self, client_id: str, req: dict) -> dict:
        """
        Dispatch a command from a client.

        Args:
            client_id: Client issuing the command
            req: Request dictionary

        Returns:
            Response dictionary
        """
        cmd = req.get("cmd") or req.get("command")
        if not cmd:
            return {"ok": False, "error": "missing cmd"}

        # Get client session
        session = self.station_manager.get_session(client_id)

        # Handle global commands (no station required)
        if cmd == "get_state":
            return self._handle_get_state(client_id, req)

        if cmd == "get_events":
            # Filter events based on station
            return self._handle_get_events(client_id, req)

        if cmd == "list_scenarios":
            return {"ok": True, "scenarios": self.runner.list_scenarios()}

        if cmd == "load_scenario":
            if not session or session.permission_level.value < PermissionLevel.CAPTAIN.value:
                return {"ok": False, "error": "Only captain can load scenarios"}
            scenario_name = req.get("scenario") or req.get("name") or req.get("file")
            if not scenario_name:
                return {"ok": False, "error": "missing scenario"}
            loaded = self.runner.load_scenario(scenario_name)
            if loaded <= 0:
                return {"ok": False, "error": f"Failed to load scenario {scenario_name}"}
            return {
                "ok": True,
                "scenario": scenario_name,
                "ships_loaded": loaded,
                "player_ship_id": self.runner.player_ship_id,
                "mission": self.runner.get_mission_status(),
            }

        if cmd == "get_mission":
            return {"ok": True, "mission": self.runner.get_mission_status()}

        if cmd == "get_mission_hints":
            clear = bool(req.get("clear", False))
            return {"ok": True, "hints": self.runner.get_mission_hints(clear=clear)}

        if cmd == "pause":
            # Only captain can pause
            if session and session.station and session.station.value == "captain":
                on = bool(req.get("on", True))
                if on:
                    self.runner.stop()
                else:
                    self.runner.start()
                return {"ok": True, "paused": on}
            return {"ok": False, "error": "Only captain can pause simulation"}

        # Get ship_id from session or request
        ship_id = req.get("ship")
        metadata = self.dispatcher.command_metadata.get(cmd, {})
        requires_ship = metadata.get("requires_ship", True)

        if not ship_id and session and session.ship_id:
            ship_id = session.ship_id

        if requires_ship and not ship_id:
            return {"ok": False, "error": "missing ship"}

        # Route through station-aware dispatcher
        args = {k: v for k, v in req.items() if k not in ["cmd", "command"]}
        if ship_id:
            args["ship"] = ship_id

        result = self.dispatcher.dispatch(client_id, ship_id or "", cmd, args)
        return result.to_dict()

    def _handle_get_state(self, client_id: str, req: dict) -> dict:
        """
        Handle get_state command with station-based filtering.

        Args:
            client_id: Client requesting state
            req: Request dictionary

        Returns:
            Filtered state response
        """
        ship_id = req.get("ship")
        session = self.station_manager.get_session(client_id)

        if not session:
            return {"ok": False, "error": "Client not registered"}

        # If no ship specified, get all ships
        if not ship_id:
            # Get full telemetry
            full_telemetry = get_telemetry_snapshot(self.runner.simulator)

            # Filter for client
            filtered = self.telemetry_filter.filter_telemetry_for_client(
                client_id,
                full_telemetry
            )

            return {
                "ok": True,
                "t": self.runner.simulator.time,
                **filtered
            }

        # Get specific ship
        if not session.ship_id:
            return {"ok": False, "error": "Not assigned to a ship"}

        if session.ship_id != ship_id:
            return {"ok": False, "error": "Can only view assigned ship"}

        ship = self.runner.simulator.ships.get(ship_id)
        if not ship:
            return {"ok": False, "error": f"Ship {ship_id} not found"}

        # Get ship telemetry
        ship_telemetry = get_ship_telemetry(ship, self.runner.simulator.time)

        # Filter based on station
        filtered = self.telemetry_filter.filter_ship_state_for_client(
            client_id,
            ship_id,
            ship_telemetry
        )

        return {
            "ok": True,
            "ship": ship_id,
            "state": filtered,
            "t": self.runner.simulator.time
        }

    def _handle_get_events(self, client_id: str, req: dict) -> dict:
        """
        Handle get_events command with station-based filtering.

        Events are filtered based on station type - each station only sees
        events relevant to their role and systems.

        Args:
            client_id: Client requesting events
            req: Request dictionary

        Returns:
            Filtered events response
        """
        session = self.station_manager.get_session(client_id)

        if not session:
            return {"ok": False, "error": "Client not registered"}

        # Get all events from simulator
        limit = int(req.get("limit", 100))
        all_events = []
        if hasattr(self.runner.simulator, "get_recent_events"):
            all_events = self.runner.simulator.get_recent_events(limit=limit)
        elif hasattr(self.runner.simulator, "event_log"):
            all_events = list(self.runner.simulator.event_log)[-limit:]
        elif hasattr(self.runner.simulator, "recent_events"):
            all_events = self.runner.simulator.recent_events[-limit:]

        # If no station claimed, return message
        if not session.station:
            return {"ok": True, "events": [], "message": "Claim a station to view events"}

        # Filter events based on station
        filtered_events = self._filter_events_for_station(
            all_events,
            session.station,
            session.ship_id
        )

        return {
            "ok": True,
            "events": filtered_events,
            "station": session.station.value,
            "total_events": len(all_events),
            "filtered_count": len(filtered_events)
        }

    def _filter_events_for_station(self, events: list, station, ship_id: str) -> list:
        """
        Filter events based on station permissions.

        Args:
            events: List of all events
            station: StationType enum
            ship_id: Ship ID the station is assigned to

        Returns:
            List of filtered events
        """
        from server.stations.station_types import StationType, get_station_displays

        # Captain sees all events
        if station == StationType.CAPTAIN:
            return events

        # Get displays this station can see
        allowed_displays = get_station_displays(station)

        # Define event category mappings
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
            "threat": ["threat_board"],

            # OPS events
            "sensor": ["sensor_status", "contacts"],
            "contact": ["contacts", "contact_details"],
            "detection": ["contacts", "detection_log"],
            "ping": ["sensor_status"],
            "ecm": ["ecm_status", "eccm_status"],
            "signature": ["signature_analysis"],

            # ENGINEERING events
            "power": ["power_grid", "power_management_status"],
            "reactor": ["reactor_status", "power_grid"],
            "damage": ["damage_report", "hull_integrity"],
            "repair": ["repair_queue", "damage_report"],
            "system": ["system_status"],
            "fuel": ["fuel_status"],

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
            "gimbal_lock": ["nav_status", "helm_status"],  # HELM needs to know
        }

        filtered = []
        for event in events:
            # Events should be dicts with type and data
            if not isinstance(event, dict):
                continue

            event_type = event.get("type", "")
            event_ship = event.get("ship_id", "")

            # Filter by ship - only show events for this ship (or global events)
            if event_ship and event_ship != ship_id:
                continue

            # Check if station can see this event type
            should_include = False

            # Check each event category
            for category, required_displays in event_categories.items():
                if category in event_type.lower():
                    # If "all", always include
                    if "all" in required_displays:
                        should_include = True
                        break

                    # Check if station has any of the required displays
                    if any(display in allowed_displays for display in required_displays):
                        should_include = True
                        break

            # If no specific category matched, check for general visibility
            if not should_include:
                # Some events are visible to all by default
                if any(keyword in event_type.lower() for keyword in ["critical", "alert", "warning", "mission"]):
                    should_include = True

            if should_include:
                filtered.append(event)

        return filtered

    def handle_connection(self, conn: socket.socket, addr: tuple):
        """
        Handle a client connection.

        Args:
            conn: Client socket
            addr: Client address tuple
        """
        # Generate client ID
        client_id = self.station_manager.generate_client_id()

        with self.client_lock:
            self.clients[client_id] = conn

        logger.info(f"Client connected: {client_id} from {addr}")

        # Auto-register client
        player_name = f"Player_{client_id}"
        self.station_manager.register_client(client_id, player_name)

        # Send welcome message
        welcome = {
            "ok": True,
            "message": "Connected to Flaxos Spaceship Sim - Station System",
            "client_id": client_id,
            "instructions": {
                "assign_ship": "Use assign_ship command to join a ship",
                "claim_station": "Use claim_station command to claim a station",
                "help": "Use my_status to see your current status"
            }
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

                        # Dispatch command
                        resp = self.dispatch(client_id, req)
                        conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))

                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Error handling request from {client_id}: {e}")
                    break

        finally:
            # Clean up
            logger.info(f"Client disconnected: {client_id}")
            with self.client_lock:
                self.clients.pop(client_id, None)
            self.station_manager.unregister_client(client_id)
            conn.close()

    def start(self):
        """Start the server"""
        self.initialize()

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(8)
        self.running = True

        logger.info(f"Station server listening on {self.host}:{self.port} (dt={self.dt})")
        logger.info("Multi-crew station control enabled")

        try:
            while self.running:
                try:
                    client, addr = self.server_socket.accept()
                    # Set socket timeout for periodic checks
                    client.settimeout(1.0)
                    thread = threading.Thread(
                        target=self.handle_connection,
                        args=(client, addr),
                        daemon=True
                    )
                    thread.start()
                except Exception as e:
                    if self.running:
                        logger.error(f"Error accepting connection: {e}")

        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            self.stop()

    def stop(self):
        """Stop the server"""
        self.running = False

        # Close all client connections
        with self.client_lock:
            for client_id, conn in list(self.clients.items()):
                try:
                    conn.close()
                except OSError:
                    pass
            self.clients.clear()

        # Stop simulation
        self.runner.stop()

        # Close server socket
        if self.server_socket:
            self.server_socket.close()

        logger.info("Server stopped")


def main():
    """Main entry point"""
    ap = argparse.ArgumentParser(description="Flaxos Station-Based Multi-Crew Server")
    ap.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    ap.add_argument("--port", type=int, default=8765, help="Port to bind to")
    ap.add_argument("--dt", type=float, default=0.1, help="Simulation timestep")
    ap.add_argument("--fleet-dir", default="hybrid_fleet", help="Directory containing ship JSON files")
    args = ap.parse_args()

    server = StationServer(args.host, args.port, args.dt, args.fleet_dir)
    server.start()


if __name__ == "__main__":
    main()
