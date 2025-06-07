# sim/socket_listener.py
import socket
import json
import threading
import time
import argparse
from queue import Queue

from hybrid_runner import HybridRunner

runner: HybridRunner | None = None


def handle_command(cmd: str | None, ship_id: str, payload: dict) -> dict:
    """Route a command to the hybrid runner."""
    if cmd is None:
        return {"error": "Missing command_type"}

    if cmd == "get_state":
        return runner.get_ship_state(ship_id)
    if cmd == "get_position":
        state = runner.get_ship_state(ship_id)
        return {"position": state.get("position")}
    if cmd == "get_velocity":
        state = runner.get_ship_state(ship_id)
        return {"velocity": state.get("velocity")}

    if cmd == "helm_override":
        throttle = float(payload.get("throttle", 0))
        direction = float(payload.get("direction", 0))
        runner.send_command(ship_id, "set_thrust", {"x": throttle, "y": 0, "z": 0})
        runner.send_command(ship_id, "rotate", {"axis": "yaw", "value": direction})
        return {"status": "helm_override applied"}

    result = runner.send_command(ship_id, cmd, payload)
    if isinstance(result, dict) and result.get("success") and "result" in result:
        return result["result"]
    return result

def start_socket_listener(host: str, port: int, runner: HybridRunner | None = None, command_queue: Queue | None = None):
    """Start a TCP server that forwards commands to the simulation runner."""

    def handle_client(conn, addr):
        print(f"[INFO] Connection from {addr}")
        try:
            data = conn.recv(16384)
            if not data:
                return
            try:
                message = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError as e:
                error_msg = {"error": f"Invalid JSON: {e}"}
                conn.sendall(json.dumps(error_msg).encode("utf-8"))
                print(f"[ERROR] {error_msg['error']}")
                return

            if command_queue is not None:
                command_queue.put(message)

            cmd = message.get("command_type")
            payload = message.get("payload", {}) or {}
            ship_id = payload.get("ship")
            if not ship_id:
                resp = {"error": "Missing ship in payload"}
            else:
                current_runner = runner if runner is not None else globals().get("runner")
                if current_runner is None:
                    resp = {"error": "Server not initialized"}
                else:
                    # Set global runner if not set
                    if globals().get("runner") is None:
                        globals()["runner"] = current_runner
                    resp = handle_command(cmd, ship_id, payload)

            conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
        except Exception as e:
            print(f"[ERROR] Unexpected error with {addr}: {str(e)}")
        finally:
            conn.close()
            print(f"[INFO] Disconnected {addr}")

    def server_thread():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((host, port))
            server.listen()
            print(f"[LISTENING] on {host}:{port}")
            while True:
                conn, addr = server.accept()
                threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

    thread = threading.Thread(target=server_thread, daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spaceship Simulator Command Server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=9999, help="Bind port")
    parser.add_argument("--fleet-dir", default="hybrid_fleet", help="Directory of ship configs")
    args = parser.parse_args()

    runner = HybridRunner(fleet_dir=args.fleet_dir)
    runner.load_ships()
    runner.start()

    start_socket_listener(args.host, args.port, runner)
    print(f"Server running on {args.host}:{args.port}. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        runner.stop()
