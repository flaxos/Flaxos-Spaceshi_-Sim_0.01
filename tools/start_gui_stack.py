"""
Start the full GUI stack in a single terminal:
- TCP simulation server
- WebSocket bridge
- GUI static file server
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import webbrowser


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_websockets() -> None:
    try:
        import websockets  # noqa: F401
    except Exception:
        print("Missing dependency: websockets")
        print("Install with: pip install websockets")
        sys.exit(1)


def _start_process(label: str, cmd: list[str], cwd: str) -> subprocess.Popen:
    print(f"[start] {label}: {' '.join(cmd)}")
    return subprocess.Popen(cmd, cwd=cwd)


def _terminate_processes(processes: list[subprocess.Popen]) -> None:
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()

    deadline = time.time() + 5
    for proc in processes:
        if proc.poll() is None:
            timeout = max(0.1, deadline - time.time())
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Flaxos GUI stack")
    parser.add_argument("--host", default="127.0.0.1", help="TCP server host")
    parser.add_argument("--tcp-port", type=int, default=8765, help="TCP server port")
    parser.add_argument("--ws-host", default="0.0.0.0", help="WebSocket bind host")
    parser.add_argument("--ws-port", type=int, default=8080, help="WebSocket port")
    parser.add_argument("--http-port", type=int, default=3000, help="GUI HTTP port")
    parser.add_argument("--dt", type=float, default=0.1, help="Simulation timestep")
    parser.add_argument("--fleet-dir", default="hybrid_fleet", help="Fleet directory")
    parser.add_argument(
        "--server",
        choices=["run", "station"],
        default="run",
        help="Server type: run=basic, station=multi-crew",
    )
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser")
    args = parser.parse_args()

    _ensure_websockets()

    python = sys.executable
    server_module = "server.run_server" if args.server == "run" else "server.station_server"

    server_cmd = [
        python,
        "-m",
        server_module,
        "--host",
        args.host,
        "--port",
        str(args.tcp_port),
        "--dt",
        str(args.dt),
        "--fleet-dir",
        args.fleet_dir,
    ]

    ws_bridge_cmd = [
        python,
        os.path.join(ROOT_DIR, "gui", "ws_bridge.py"),
        "--tcp-host",
        args.host,
        "--tcp-port",
        str(args.tcp_port),
        "--ws-host",
        args.ws_host,
        "--ws-port",
        str(args.ws_port),
    ]

    http_cmd = [
        python,
        "-m",
        "http.server",
        str(args.http_port),
    ]

    processes: list[subprocess.Popen] = []
    try:
        processes.append(_start_process("TCP server", server_cmd, ROOT_DIR))
        processes.append(_start_process("WebSocket bridge", ws_bridge_cmd, ROOT_DIR))
        processes.append(_start_process("GUI server", http_cmd, os.path.join(ROOT_DIR, "gui")))

        gui_url = f"http://localhost:{args.http_port}/"
        print(f"[ready] GUI: {gui_url}")
        print(f"[ready] WS bridge: ws://localhost:{args.ws_port}")
        print("Press Ctrl+C to stop all services.")

        if not args.no_browser:
            time.sleep(1.0)
            webbrowser.open(gui_url)

        while True:
            time.sleep(1.0)
            for proc in processes:
                if proc.poll() is not None:
                    raise RuntimeError("A subprocess exited unexpectedly.")
    except KeyboardInterrupt:
        print("\n[stop] Shutting down...")
    except Exception as exc:
        print(f"\n[error] {exc}")
    finally:
        _terminate_processes(processes)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
