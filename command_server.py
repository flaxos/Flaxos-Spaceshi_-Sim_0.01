import socketserver
import json
import logging
import threading
import traceback
from datetime import datetime

# Setup logging
logger = logging.getLogger(__name__)


class CommandHandler(socketserver.BaseRequestHandler):
    """Handler for ship command requests"""

    def handle(self):
        """Process incoming command requests"""
        client_ip = self.client_address[0]
        logger.info(f"Connection from {client_ip}")

        try:
            # Receive data
            data = self.request.recv(4096).decode('utf-8')
            if not data:
                logger.warning(f"Empty request from {client_ip}")
                return

            # Parse command
            try:
                command = json.loads(data)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON from {client_ip}: {data}")
                self._send_error("Invalid JSON request")
                return

            # Extract command details
            ship_id = command.get("ship")
            cmd = command.get("command")

            if not ship_id:
                self._send_error("Missing ship ID")
                return

            if not cmd:
                self._send_error("Missing command")
                return

            # Get ship
            ship = self.server.ships.get(ship_id)
            if not ship:
                self._send_error(f"Ship {ship_id} not found")
                return

            # Process command
            logger.debug(f"Processing command: {cmd} for ship: {ship_id}")
            response = self._process_command(ship, ship_id, cmd, command)

            # Send response
            self.request.sendall(json.dumps(response).encode("utf-8") + b'\n')
            logger.debug(f"Response sent to {client_ip}")

        except ConnectionError as e:
            logger.error(f"Connection error with {client_ip}: {e}")
        except Exception as e:
            logger.error(f"Unhandled error: {e}\n{traceback.format_exc()}")
            try:
                self._send_error(f"Server error: {str(e)}")
            except:
                pass

    def _send_error(self, message):
        """Send error response to client"""
        try:
            response = {"error": message, "timestamp": datetime.utcnow().isoformat()}
            self.request.sendall(json.dumps(response).encode("utf-8") + b'\n')
        except:
            # If we can't send the error, there's not much we can do
            pass

    def _process_command(self, ship, ship_id, cmd, command):
        """Process the command for the specified ship"""
        response = {}

        try:
            if cmd == "set_thrust":
                response = self._handle_set_thrust(ship, ship_id, command)
            elif cmd == "set_orientation":
                response = self._handle_set_orientation(ship, ship_id, command)
            elif cmd == "set_angular_velocity":
                response = self._handle_set_angular_velocity(ship, ship_id, command)
            elif cmd == "rotate":
                response = self._handle_rotate(ship, ship_id, command)
            elif cmd == "set_course":
                response = self._handle_set_course(ship, ship_id, command)
            elif cmd == "autopilot":
                response = self._handle_autopilot(ship, ship_id, command)
            elif cmd == "helm_override":
                response = self._handle_helm_override(ship, ship_id, command)
            elif cmd == "ping_sensors":
                response = self._handle_ping_sensors(ship, ship_id)
            elif cmd == "get_position":
                response = ship.position
            elif cmd == "get_velocity":
                response = ship.velocity
            elif cmd == "get_orientation":
                response = ship.orientation
            elif cmd == "get_state":
                response = ship.get_state()
            elif cmd == "get_contacts":
                response = self._handle_get_contacts(ship)
            elif cmd == "status":
                response = {"status": f"{ship_id} is online", "timestamp": datetime.utcnow().isoformat()}
            elif cmd == "override_bio_monitor":
                response = self._handle_override_bio(ship, ship_id)
            elif cmd == "events":
                response = {"events": []}
            else:
                response = {"error": f"Unknown command: {cmd}"}
        except KeyError as e:
            # Handle missing keys in ship data structure
            logger.error(f"KeyError in command {cmd} for ship {ship_id}: {e}")
            response = {"error": f"Ship system error: {str(e)}"}
        except Exception as e:
            # Handle other exceptions
            logger.error(f"Error in command {cmd} for ship {ship_id}: {e}\n{traceback.format_exc()}")
            response = {"error": f"Command processing error: {str(e)}"}

        return response

    def _handle_set_thrust(self, ship, ship_id, command):
        """Handle set_thrust command"""
        thrust = {
            "x": float(command.get("x", 0.0)),
            "y": float(command.get("y", 0.0)),
            "z": float(command.get("z", 0.0))
        }
        # Set thrust for manual control
        ship.systems["helm"]["manual_thrust"] = thrust
        return {
            "status": f"Thrust updated for {ship_id}",
            "thrust": thrust
        }

    def _handle_set_orientation(self, ship, ship_id, command):
        """Handle set_orientation command"""
        for axis in ["pitch", "yaw", "roll"]:
            if axis in command:
                ship.orientation[axis] = float(command.get(axis))
        return {
            "status": f"Orientation updated for {ship_id}",
            "orientation": ship.orientation
        }

    def _handle_set_angular_velocity(self, ship, ship_id, command):
        """Handle set_angular_velocity command"""
        ship.angular_velocity = {
            "pitch": float(command.get("pitch", 0.0)),
            "yaw": float(command.get("yaw", 0.0)),
            "roll": float(command.get("roll", 0.0))
        }
        return {
            "status": f"Angular velocity updated for {ship_id}",
            "angular_velocity": ship.angular_velocity
        }

    def _handle_rotate(self, ship, ship_id, command):
        """Handle rotate command"""
        axis = command.get("axis")
        if not axis or axis not in ["pitch", "yaw", "roll"]:
            return {"error": "Invalid or missing rotation axis"}

        value = float(command.get("value", 0.0))
        ship.orientation[axis] = (ship.orientation.get(axis, 0.0) + value) % 360
        return {
            "status": f"Rotated {axis} by {value} for {ship_id}",
            "orientation": ship.orientation
        }

    def _handle_set_course(self, ship, ship_id, command):
        """Handle set_course command"""
        target = command.get("target")
        if not target:
            return {"error": "Missing target coordinates"}

        ship.systems["navigation"]["target"] = target
        ship.systems["navigation"]["autopilot"] = True
        return {
            "status": f"Course set for {ship_id}",
            "target": target
        }

    def _handle_autopilot(self, ship, ship_id, command):
        """Handle autopilot command"""
        enabled = bool(command.get("enabled", True))
        ship.systems["navigation"]["autopilot"] = enabled
        return {
            "status": f"Autopilot {'enabled' if enabled else 'disabled'} for {ship_id}"
        }

    def _handle_helm_override(self, ship, ship_id, command):
        """Handle helm_override command"""
        enabled = bool(command.get("enabled", False))
        ship.systems["helm"]["mode"] = "manual" if enabled else "autopilot"
        return {
            "status": f"Manual helm {'enabled' if enabled else 'disabled'} for {ship_id}"
        }

    def _handle_ping_sensors(self, ship, ship_id):
        """Handle ping_sensors command"""
        sensors = ship.systems.get("sensors", {}).get("active", None)
        if sensors is None:
            return {"error": "Active sensors not available on this ship."}

        cooldown = sensors.get("cooldown", 0.0)
        if cooldown > 0.0:
            return {
                "error": f"Active sensors cooling down",
                "cooldown": round(cooldown, 1)
            }

        now = datetime.utcnow().isoformat()
        sensors["last_ping_time"] = now
        sensors["processed"] = False
        return {
            "status": f"Active sensor ping triggered on {ship_id}",
            "cooldown_started": 10.0,
            "timestamp": now
        }

    def _handle_get_contacts(self, ship):
        """Handle get_contacts command"""
        sensors = ship.systems.get("sensors", {})

        # Check if sensors is a SensorSystem object or a dict
        if hasattr(sensors, 'get_contacts'):
            # It's an object with a get_contacts method
            return sensors.get_contacts()

        # It's a dictionary, extract contacts manually
        passive = sensors.get("passive", {}).get("contacts", [])
        active = sensors.get("active", {}).get("contacts", [])

        # Merge contacts and sort by distance
        contacts = passive + active
        contacts.sort(key=lambda c: c.get("distance", float("inf")))

        # Add timestamp to each contact if missing
        now = datetime.utcnow().isoformat()
        for contact in contacts:
            if "detected_at" not in contact:
                contact["detected_at"] = now

            # Add method if missing
            if "method" not in contact:
                contact["method"] = "unknown"

        return {
            "contacts": contacts,
            "contact_count": len(contacts),
            "timestamp": now
        }


def _handle_override_bio(self, ship, ship_id):
    """Handle override_bio_monitor command"""
    ship.systems["bio_monitor"]["override"] = True
    return {
        "status": f"Crew safety overridden on {ship_id}",
        "timestamp": datetime.utcnow().isoformat()
    }


class CommandServer:
    """TCP server for ship command processing"""

    def __init__(self, ships, host="127.0.0.1", port=9999):
        """Initialize the command server"""
        self.ships = {ship.id: ship for ship in ships}
        self.host = host
        self.port = port
        self.server = None
        self.server_thread = None

    def start(self):
        """Start the command server"""
        try:
            self.server = socketserver.ThreadingTCPServer((self.host, self.port), CommandHandler)
            self.server.ships = self.ships
            self.server.allow_reuse_address = True
            self.server.daemon_threads = True

            logger.info(f"Starting command server on {self.host}:{self.port}")
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            logger.info(f"Command server listening on {self.host}:{self.port}")

            return True
        except Exception as e:
            logger.error(f"Failed to start command server: {e}\n{traceback.format_exc()}")
            return False

    def stop(self):
        """Stop the command server"""
        if self.server:
            logger.info("Stopping command server")
            self.server.shutdown()
            self.server.server_close()
            logger.info("Command server stopped")
