import socketserver
import json
import threading

class CommandHandler(socketserver.BaseRequestHandler):
    def handle(self):
        data = self.request.recv(4096).decode()
        command = json.loads(data)

        ship_id = command.get("ship")
        cmd = command.get("command")

        ship = self.server.ships.get(ship_id)
        response = {}

        if not ship:
            response["error"] = f"Ship {ship_id} not found"
        else:
            if cmd == "set_thrust":
                thrust = {
                    "x": command.get("x", 0.0),
                    "y": command.get("y", 0.0),
                    "z": command.get("z", 0.0)
                }

                # Ensure system path exists
                if "propulsion" not in ship.systems:
                    ship.systems["propulsion"] = {}
                if "main_drive" not in ship.systems["propulsion"]:
                    ship.systems["propulsion"]["main_drive"] = {
                        "thrust": {"x": 0.0, "y": 0.0, "z": 0.0},
                        "status": "online",
                        "throttle": 0.0,
                        "max_thrust": 100.0
                    }

                ship.systems["propulsion"]["main_drive"]["thrust"] = thrust
                response["status"] = f"Thrust updated for {ship_id}"

            elif cmd == "set_orientation":
                ship.orientation["pitch"] = command.get("pitch", ship.orientation.get("pitch", 0.0))
                ship.orientation["yaw"]   = command.get("yaw", ship.orientation.get("yaw", 0.0))
                ship.orientation["roll"]  = command.get("roll", ship.orientation.get("roll", 0.0))
                response["status"] = f"Orientation updated for {ship_id}"

            elif cmd == "set_angular_velocity":
                ship.angular_velocity = {
                    "pitch": command.get("pitch", 0.0),
                    "yaw": command.get("yaw", 0.0),
                    "roll": command.get("roll", 0.0)
                }
                response["status"] = f"Angular velocity updated for {ship_id}"

            elif cmd == "rotate":
                axis = command.get("axis")
                value = command.get("value", 0.0)
                ship.orientation[axis] += value
                response["status"] = f"Rotated {axis} by {value} for {ship_id}"

            elif cmd == "get_position":
                response = ship.position

            elif cmd == "get_velocity":
                response = ship.velocity

            elif cmd == "get_orientation":
                response = ship.orientation

            elif cmd == "get_state":
                response = {
                    "position": ship.position,
                    "velocity": ship.velocity,
                    "orientation": ship.orientation,
                    "thrust": ship.systems.get("propulsion", {}).get("main_drive", {}).get("thrust", {}),
                    "bio_monitor": ship.systems.get("bio_monitor", {}),
                    "angular_velocity": ship.angular_velocity
                }

            elif cmd == "status":
                response = {"status": f"{ship_id} is online"}

            elif cmd == "override_bio_monitor":
                # Ensure bio_monitor exists
                if "bio_monitor" not in ship.systems:
                    ship.systems["bio_monitor"] = {
                        "g_limit": 8.0,
                        "fail_timer": 0.0,
                        "current_g": 0.0,
                        "status": "nominal",
                        "crew_health": 1.0
                    }
                ship.systems["bio_monitor"]["override"] = True
                response = {"status": "Crew safety overridden on " + ship.id}


            elif cmd == "events":
                response = {"events": []}

            else:
                response["error"] = f"Unknown command: {cmd}"

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
