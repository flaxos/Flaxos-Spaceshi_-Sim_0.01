import socketserver
import json
import threading
from datetime import datetime

class CommandHandler(socketserver.BaseRequestHandler):
    def handle(self):
        data = self.request.recv(4096).decode()
        command = json.loads(data)

        ship_id = command.get("ship")
        cmd = command.get("command")
        ship = self.server.ships.get(ship_id)
        response = {}

        if not ship:
            response = {"error": f"Ship {ship_id} not found"}
        else:
            if cmd == "set_thrust":
                thrust = {
                    "x": command.get("x", 0.0),
                    "y": command.get("y", 0.0),
                    "z": command.get("z", 0.0)
                }
                # This is the correct place for setting thrust for manual control
                ship.systems["helm"]["manual_thrust"] = thrust
                response = {"status": f"Thrust updated for {ship_id}"}

            elif cmd == "set_orientation":
                for axis in ["pitch", "yaw", "roll"]:
                    ship.orientation[axis] = command.get(axis, ship.orientation.get(axis, 0.0))
                response = {"status": f"Orientation updated for {ship_id}"}

            elif cmd == "set_angular_velocity":
                ship.angular_velocity = {
                    "pitch": command.get("pitch", 0.0),
                    "yaw": command.get("yaw", 0.0),
                    "roll": command.get("roll", 0.0)
                }
                response = {"status": f"Angular velocity updated for {ship_id}"}

            elif cmd == "rotate":
                axis = command.get("axis")
                value = command.get("value", 0.0)
                ship.orientation[axis] += value
                response = {"status": f"Rotated {axis} by {value} for {ship_id}"}

            elif cmd == "set_course":
                ship.systems["navigation"]["target"] = command.get("target")
                ship.systems["navigation"]["autopilot"] = True
                response = {"status": f"Course set for {ship_id}"}

            elif cmd == "autopilot":
                ship.systems["navigation"]["autopilot"] = command.get("enabled", True)
                response = {"status": f"Autopilot {'enabled' if command.get('enabled') else 'disabled'} for {ship_id}"}

            elif cmd == "helm_override":
                ship.systems["helm"]["mode"] = "manual" if command.get("enabled", False) else "autopilot"
                response = {"status": f"Manual helm {'enabled' if command.get('enabled') else 'disabled'} for {ship_id}"}

            elif cmd == "ping_sensors":
                sensors = ship.systems.get("sensors", {}).get("active", None)
                if sensors is None:
                    response = {"error": "Active sensors not available on this ship."}
                elif sensors.get("cooldown", 0.0) > 0.0:
                    response = {"error": f"Active sensors cooling down: {sensors['cooldown']:.1f}s"}
                else:
                    now = datetime.utcnow().isoformat()
                    sensors["last_ping_time"] = now
                    sensors["processed"] = False
                    response = {
                        "status": f"Active sensor ping triggered on {ship_id}",
                        "cooldown_started": 10.0
                    }

            elif cmd == "get_position":
                response = ship.position

            elif cmd == "get_velocity":
                response = ship.velocity

            elif cmd == "get_orientation":
                response = ship.orientation

            elif cmd == "get_state":
                response = ship.get_state()

            elif cmd == "get_contacts":
                passive = ship.systems.get("sensors", {}).get("passive", {}).get("contacts", [])
                active = ship.systems.get("sensors", {}).get("active", {}).get("contacts", [])
                response = {"contacts": passive + active}

            elif cmd == "status":
                response = {"status": f"{ship_id} is online"}

            elif cmd == "override_bio_monitor":
                ship.systems["bio_monitor"]["override"] = True
                response = {"status": "Crew safety overridden on " + ship.id}

            elif cmd == "events":
                response = {"events": []}

            else:
                response = {"error": f"Unknown command: {cmd}"}

        self.request.sendall(json.dumps(response).encode("utf-8"))

class CommandServer:
    def __init__(self, ships, host="127.0.0.1", port=9999):
        self.ships = {ship.id: ship for ship in ships}
        self.host = host
        self.port = port
        self.server = socketserver.ThreadingTCPServer((self.host, self.port), CommandHandler)
        self.server.ships = self.ships

    def start(self):
        print(f"[LISTENING] on {self.host}:{self.port}")
        self.server.allow_reuse_address = True
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
