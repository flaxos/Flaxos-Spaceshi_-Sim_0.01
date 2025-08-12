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


def serve(host: str, port: int, dt: float, fleet_dir: str, scenario: str | None = None) -> None:
    """Start a simple TCP server exposing hybrid simulator state."""
    runner = HybridRunner(fleet_dir=fleet_dir, dt=dt)
    if scenario:
        runner.load_scenario(scenario)
    else:
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
                if b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        req = json.loads(line.decode("utf-8"))
                    except Exception:
                        err = json.dumps({"ok": False, "error": "bad json"}) + "\n"
                        conn.sendall(err.encode("utf-8"))
                        break
                    resp = dispatch(runner, req)
                    conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                    break
        finally:
            conn.close()

    while True:
        client, _ = srv.accept()
        threading.Thread(target=handle, args=(client,), daemon=True).start()


def dispatch(runner: HybridRunner, req: dict) -> dict:
    cmd = req.get("cmd")
    if cmd == "get_state":
        ships = list(runner.get_all_ship_states().values())
        return {
            "ok": True,
            "ships": ships,
            "t": getattr(runner.simulator, "time", 0.0),
            "missiles": [],
        }
    if cmd == "pause":
        on = bool(req.get("on", True))
        if on:
            runner.stop()
        else:
            runner.start()
        return {"ok": True, "paused": on}
    if cmd in {"helm_override", "set_target", "fire_weapon", "ping_sensors"}:
        ship_id = req.get("ship")
        ship = runner.simulator.ships.get(ship_id)
        if not ship:
            return {"ok": False, "error": "ship not found"}
        params = {k: v for k, v in req.items() if k not in {"cmd", "ship"}}
        res = ship.command(cmd, params)
        if isinstance(res, dict) and "error" in res:
            return {"ok": False, "error": res["error"]}
        return {"ok": True, **({} if not isinstance(res, dict) else res)}
    if cmd == "get_events":
        return {"ok": True, "events": []}
    if cmd == "get_mission":
        return {"ok": True, "mission": {"status": "unknown", "objectives": []}}
    if cmd == "get_debrief":
        return {"ok": True, "debrief": {}}
    return {"ok": False, "error": "unknown cmd"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--dt", type=float, default=0.1)
    ap.add_argument("--fleet-dir", default="hybrid_fleet")
    ap.add_argument("--scenario", help="scenario name to load", default=None)
    args = ap.parse_args()
    serve(args.host, args.port, args.dt, args.fleet_dir, args.scenario)
