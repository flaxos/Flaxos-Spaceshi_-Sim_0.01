"""Desktop demo smoke test for the TCP server.

Starts the server, connects a client, and prints the get_state response.
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time


def _probe_server(host: str, port: int, timeout: float) -> str:
    with socket.create_connection((host, port), timeout) as sock:
        payload = json.dumps({"cmd": "get_state"}) + "\n"
        sock.sendall(payload.encode("utf-8"))
        return sock.recv(4096).decode("utf-8", "replace").strip()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Desktop demo smoke test.")
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=8765, help="Server port")
    parser.add_argument(
        "--startup-wait",
        type=float,
        default=1.5,
        help="Seconds to wait for the server to start",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Socket timeout in seconds",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "server.run_server",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    try:
        time.sleep(args.startup_wait)
        response = _probe_server(args.host, args.port, args.timeout)
        print(
            json.dumps(
                {"ok": True, "host": args.host, "port": args.port, "response": response},
                indent=2,
            )
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
