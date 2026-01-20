import argparse
import json
import os
import socket
import sys
import threading
import time


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


from hybrid_runner import HybridRunner
from server.run_server import dispatch


def _serve_once(host: str, port: int, dt: float, fleet_dir: str, ready: threading.Event, port_holder: dict) -> None:
    runner = HybridRunner(fleet_dir=fleet_dir, dt=dt)
    runner.load_ships()
    runner.start()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    port_holder["port"] = srv.getsockname()[1]
    srv.listen(1)
    ready.set()

    try:
        conn, _ = srv.accept()
        conn.settimeout(5)
        buf = b""
        data = conn.recv(4096)
        if data:
            buf += data
        line = buf.split(b"\n", 1)[0]
        if line:
            req = json.loads(line.decode("utf-8"))
            resp = dispatch(runner, req)
            conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
        conn.close()
    finally:
        runner.stop()
        srv.close()


def run_loopback(host: str, port: int, dt: float, fleet_dir: str, timeout: float) -> dict:
    ready = threading.Event()
    port_holder: dict = {"port": None}
    thread = threading.Thread(
        target=_serve_once,
        args=(host, port, dt, fleet_dir, ready, port_holder),
        daemon=True,
    )
    thread.start()
    if not ready.wait(timeout=timeout):
        raise TimeoutError("Server failed to start in time")

    actual_port = port_holder["port"]
    client = socket.create_connection((host, actual_port), timeout=timeout)
    client.sendall((json.dumps({"cmd": "get_state"}) + "\n").encode("utf-8"))
    response = client.recv(4096).decode("utf-8", "replace").strip()
    client.close()
    thread.join(timeout=timeout)

    return {
        "ok": True,
        "host": host,
        "port": actual_port,
        "response": response,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Android/Pydroid loopback socket smoke test (server + client)."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dt", type=float, default=0.1)
    parser.add_argument("--fleet-dir", default="hybrid_fleet")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    result = run_loopback(
        host=args.host,
        port=args.port,
        dt=args.dt,
        fleet_dir=args.fleet_dir,
        timeout=args.timeout,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
