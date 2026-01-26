"""
Start the full GUI stack in a single terminal:
- TCP simulation server (unified entrypoint)
- WebSocket bridge
- GUI static file server

Uses the unified server.main entrypoint with --mode flag.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import webbrowser

# Add project root to path for imports
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from server.config import (
    DEFAULT_TCP_PORT,
    DEFAULT_WS_PORT,
    DEFAULT_HTTP_PORT,
    DEFAULT_HOST,
    DEFAULT_DT,
    DEFAULT_FLEET_DIR,
)


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
    parser.add_argument("--host", default=DEFAULT_HOST, help="TCP server host")
    parser.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT, help="TCP server port")
    parser.add_argument("--ws-host", default="0.0.0.0", help="WebSocket bind host")
    parser.add_argument("--ws-port", type=int, default=DEFAULT_WS_PORT, help="WebSocket port")
    parser.add_argument("--http-port", type=int, default=DEFAULT_HTTP_PORT, help="GUI HTTP port")
    parser.add_argument("--dt", type=float, default=DEFAULT_DT, help="Simulation timestep")
    parser.add_argument("--fleet-dir", default=DEFAULT_FLEET_DIR, help="Fleet directory")
    parser.add_argument(
        "--mode",
        choices=["minimal", "station"],
        default="station",
        help="Server mode: minimal (basic) or station (multi-crew, default)",
    )
    # Backwards compat alias
    parser.add_argument(
        "--server",
        choices=["run", "station"],
        default=None,
        help="(deprecated) Use --mode instead. run=minimal, station=station",
    )
    parser.add_argument("--lan", action="store_true", help="Enable LAN mode (bind to 0.0.0.0)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser")
    args = parser.parse_args()

    _ensure_websockets()

    # Handle backwards compat --server flag
    mode = args.mode
    if args.server:
        mode = "minimal" if args.server == "run" else "station"
        print(f"[warn] --server is deprecated, use --mode {mode} instead")

    python = sys.executable

    # Use unified server.main entrypoint
    server_cmd = [
        python,
        "-m",
        "server.main",
        "--mode",
        mode,
        "--host",
        args.host,
        "--port",
        str(args.tcp_port),
        "--dt",
        str(args.dt),
        "--fleet-dir",
        args.fleet_dir,
    ]

    if args.lan:
        server_cmd.append("--lan")

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
        print(f"[ready] Mode: {mode}")
        print(f"[ready] GUI: {gui_url}")
        print(f"[ready] WS bridge: ws://localhost:{args.ws_port}")
        print(f"[ready] TCP server: {args.host}:{args.tcp_port}")
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
