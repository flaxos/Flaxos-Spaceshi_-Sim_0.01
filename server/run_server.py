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


def serve(host: str, port: int, dt: float, fleet_dir: str) -> None:
    """Start a simple TCP server exposing hybrid simulator state."""
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
        return {"ok": True, "ships": runner.get_all_ship_states()}
    if cmd == "pause":
        on = bool(req.get("on", True))
        if on:
            runner.stop()
        else:
            runner.start()
        return {"ok": True, "paused": on}
    return {"ok": False, "error": "unknown cmd"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--dt", type=float, default=0.1)
    ap.add_argument("--fleet-dir", default="hybrid_fleet")
    args = ap.parse_args()
    serve(args.host, args.port, args.dt, args.fleet_dir)
