import os
import sys
import json
import socket
import threading
import argparse

# Ensure project root is on sys.path for direct execution
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from hybrid_runner import HybridRunner
from hybrid.command_handler import route_command

"""
Protocol: newline-delimited JSON over TCP.

Each request is a single JSON object terminated by "\n". Responses mirror
the request framing with one JSON object per line. Clients should send a
payload like:

  {"cmd": "get_state"}
  {"cmd": "ping_sensors", "ship": "alpha"}
"""


def _format_ship_state(state: dict) -> dict:
    pos = state.get("position", {})
    return {
        "id": state.get("id"),
        "name": state.get("name", state.get("id")),
        "pos": pos,
        "vel": state.get("velocity", {}),
        "attitude": state.get("orientation", {}),
        "systems": state.get("systems", {}),
    }


def dispatch(runner: HybridRunner, req: dict) -> dict:
    cmd = req.get("cmd")
    if not cmd:
        return {"ok": False, "error": "missing cmd"}

    if cmd == "get_state":
        ship_id = req.get("ship")
        states = runner.get_all_ship_states()
        payload = {
            "ok": True,
            "t": runner.simulator.time,
            "ships": [_format_ship_state(state) for state in states.values()],
        }
        if ship_id:
            ship_state = runner.get_ship_state(ship_id)
            payload["ship"] = ship_id
            payload["state"] = ship_state
            if isinstance(ship_state, dict) and "error" in ship_state:
                payload["ok"] = False
                payload["error"] = ship_state["error"]
        return payload

    if cmd == "get_events":
        return {"ok": True, "events": []}

    if cmd == "get_mission":
        return {"ok": True, "mission": {"status": "unknown", "objectives": []}}

    if cmd == "pause":
        on = bool(req.get("on", True))
        if on:
            runner.stop()
        else:
            runner.start()
        return {"ok": True, "paused": on}

    ship_id = req.get("ship")
    if not ship_id:
        return {"ok": False, "error": "missing ship"}
    ship = runner.simulator.ships.get(ship_id)
    if not ship:
        return {"ok": False, "error": f"ship {ship_id} not found"}

    command_data = {"command": cmd, "ship": ship_id, **req}
    command_data.pop("cmd", None)
    result = route_command(ship, command_data)
    if isinstance(result, dict) and "error" in result:
        return {"ok": False, "error": result["error"], "response": result}
    return {"ok": True, "response": result}


def _serve(host: str, port: int, dt: float, fleet_dir: str) -> None:
    runner = HybridRunner(fleet_dir=fleet_dir, dt=dt)
    runner.load_ships()
    runner.start()
    print(f"Server on {host}:{port} dt={dt}")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(8)

    def handle(conn: socket.socket) -> None:
        buf = b""
        try:
            while True:
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
                    resp = dispatch(runner, req)
                    conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
        finally:
            conn.close()

    try:
        while True:
            client, _ = srv.accept()
            threading.Thread(target=handle, args=(client,), daemon=True).start()
    finally:
        runner.stop()
        srv.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--dt", type=float, default=0.1)
    ap.add_argument("--fleet-dir", default="hybrid_fleet")
    args = ap.parse_args()
    _serve(args.host, args.port, args.dt, args.fleet_dir)


if __name__ == "__main__":
    main()
