# command_server.py — Listens for incoming ship commands and dispatches them

import socket
import threading
import json

HOST = "127.0.0.1"
PORT = 9999

class CommandServer:
    def __init__(self, ships):
        self.ships = {ship.id: ship for ship in ships}
        self.running = True

    def start(self):
        thread = threading.Thread(target=self._run_server, daemon=True)
        thread.start()
        print(f"[LISTENING] on {HOST}:{PORT}")

    def _run_server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((HOST, PORT))
            s.listen()
            while self.running:
                conn, addr = s.accept()
                with conn:
                    data = conn.recv(4096)
                    if not data:
                        continue
                    try:
                        request = json.loads(data.decode())
                        response = self.handle_command(request)
                    except Exception as e:
                        response = {"error": str(e)}
                    conn.sendall(json.dumps(response).encode())

    def handle_command(self, request):
        ship_id = request.get("ship_id")
        command_type = request.get("command_type")
        params = request.get("params", {})

        ship = self.ships.get(ship_id)
        if not ship:
            return {"error": f"Unknown ship ID: {ship_id}"}

        if command_type == "set_thrust":
            system = ship.systems.get("navigation")
            if system:
                system.command("set_thrust", params)
                return {"status": f"Thrust updated for {ship_id}"}
            return {"error": f"Ship {ship_id} has no navigation system"}

        elif command_type == "set_orientation":
            yaw = params.get("yaw")
            pitch = params.get("pitch")
            roll = params.get("roll")
            if yaw is not None:
                ship.orientation["yaw"] = yaw
            if pitch is not None:
                ship.orientation["pitch"] = pitch
            if roll is not None:
                ship.orientation["roll"] = roll
            return {"status": f"Orientation updated for {ship_id}"}

        elif command_type == "get_state":
            return ship.get_state()

        elif command_type == "get_position":
            return ship.get_state().get("position", {})

        elif command_type == "get_velocity":
            return ship.get_state().get("velocity", {})

        elif command_type == "get_orientation":
            return ship.get_state().get("orientation", {"pitch": 0.0, "yaw": 0.0, "roll": 0.0})

        elif command_type == "rotate":
            rcs = ship.systems.get("rcs")
            if rcs:
                rcs.command("rotate", params)
                return {"status": f"Rotation command sent to {ship_id}"}
            else:
                return {"error": f"No RCS system found on {ship_id}"}

        elif command_type == "status":
            return {
                "id": ship.id,
                "pos": ship.position,
                "vel": ship.velocity,
                "systems": list(ship.systems.keys())
            }

        elif command_type == "events":
            return {"events": ["event system not implemented"]}

        return {"error": f"Unknown command type: {command_type}"}
