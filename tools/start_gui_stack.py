"""
Start the full GUI stack in a single terminal:
- TCP simulation server (unified entrypoint)
- WebSocket bridge
- Bridge UI v3 (`gui-svelte` build by default, legacy `gui/` still available as a deprecated fallback)

Uses the unified server.main entrypoint with --mode flag.
"""

from __future__ import annotations

import argparse
import os
import secrets
import signal
import subprocess
import sys
import time
import webbrowser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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


def _start_process(
    label: str,
    cmd: list[str],
    cwd: str,
    env: dict[str, str] | None = None,
) -> subprocess.Popen:
    print(f"[start] {label}: {' '.join(cmd)}")
    return subprocess.Popen(cmd, cwd=cwd, env=env)


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


def _handle_shutdown_signal(signum, _frame) -> None:
    raise KeyboardInterrupt(f"signal {signum}")


def _generate_secret(length: int = 24) -> str:
    """Generate a URL-safe shared secret for WS/RCON auth."""
    return secrets.token_urlsafe(length)


def _append_query_param(url: str, key: str, value: str) -> str:
    """Append or replace a query parameter on a URL."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[key] = value
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        )
    )


def _resolve_rcon_password(cli_value: str | None) -> str:
    """Resolve RCON password with CLI taking precedence over inherited env."""
    env_value = os.environ.get("FLAXOS_RCON_PASSWORD")
    if cli_value:
        return cli_value
    if env_value:
        return env_value
    return "admin"


def _resolve_allowed_origin_hosts(hosts: list[str] | None) -> list[str]:
    """Normalize allowlist entries and preserve loopback origins when enabled."""
    normalized: set[str] = set()
    for raw_value in hosts or []:
        if not raw_value:
            continue
        for candidate in raw_value.split(","):
            host = candidate.strip().lower()
            if host:
                normalized.add(host)

    if normalized:
        normalized.update({"localhost", "127.0.0.1", "::1"})

    return sorted(normalized)


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    signal.signal(signal.SIGINT, _handle_shutdown_signal)

    parser = argparse.ArgumentParser(description="Start Flaxos GUI stack")
    parser.add_argument("--host", default=DEFAULT_HOST, help="TCP server host")
    parser.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT, help="TCP server port")
    parser.add_argument("--ws-host", default="127.0.0.1", help="WebSocket bind host (use --lan for 0.0.0.0)")
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
    parser.add_argument(
        "--ui",
        choices=["legacy", "svelte", "dev", "v3"],
        default="v3",
        help=(
            "Frontend to serve: "
            "v3 (default, builds gui-svelte/ then serves dist/), "
            "svelte (alias for v3), "
            "legacy (deprecated fallback serving gui/), "
            "dev (starts vite dev server for the v3 UI on :5174 alongside the game servers)"
        ),
    )
    parser.add_argument("--no-browser", action="store_true", default=True, help="Do not open browser (default)")
    parser.add_argument("--browser", action="store_true", help="Open browser on start")
    parser.add_argument(
        "--razorback",
        action="store_true",
        help="Open the Razorback cockpit client instead of the standard bridge UI",
    )
    parser.add_argument("--editor-port", type=int, default=3200, help="(deprecated, asset editor removed)")
    parser.add_argument("--no-editor", action="store_true", help="(deprecated, asset editor removed)")
    parser.add_argument(
        "--game-code",
        default=None,
        help="Shared secret for WS authentication (recommended for remote access)",
    )
    parser.add_argument(
        "--rcon-password",
        default=None,
        help="RCON password for admin commands (defaults to FLAXOS_RCON_PASSWORD or admin)",
    )
    parser.add_argument(
        "--allowed-origin-host",
        action="append",
        default=[],
        help="Optional browser Origin hostname allowlist entry for the WS bridge (repeatable)",
    )
    args = parser.parse_args()

    _ensure_websockets()

    # Handle backwards compat --server flag
    mode = args.mode
    if args.server:
        mode = "minimal" if args.server == "run" else "station"
        print(f"[warn] --server is deprecated, use --mode {mode} instead")

    args.rcon_password = _resolve_rcon_password(args.rcon_password)
    args.allowed_origin_host = _resolve_allowed_origin_hosts(args.allowed_origin_host)

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
        args.ws_host = "0.0.0.0"
        if not args.game_code:
            args.game_code = _generate_secret(18)
            print(f"[auth] Generated WS game code for remote access: {args.game_code}")
        if args.rcon_password == "admin":
            args.rcon_password = _generate_secret(18)
            print(f"[auth] Generated RCON password for remote access: {args.rcon_password}")
        if not args.allowed_origin_host:
            print("[warn] No --allowed-origin-host provided; WS origin filtering remains open.")

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
    if args.game_code:
        ws_bridge_cmd.extend(["--game-code", args.game_code])
    for origin_host in args.allowed_origin_host:
        ws_bridge_cmd.extend(["--allowed-origin-host", origin_host])

    http_bind = "0.0.0.0" if args.lan else "127.0.0.1"
    ui_mode = "svelte" if args.ui == "v3" else args.ui  # legacy | svelte | dev

    # Resolve which directory to serve for HTTP
    if ui_mode == "svelte":
        # Build the Svelte project first
        svelte_dir = os.path.join(ROOT_DIR, "gui-svelte")
        dist_dir = os.path.join(svelte_dir, "dist")
        print("[build] Building Svelte frontend...")
        try:
            node_paths = [
                os.path.expanduser("~/.nvm/versions/node/v24.14.0/bin"),
                os.path.expanduser("~/.nvm/versions/node/v22.22.1/bin"),
                "/usr/local/bin",
                "/usr/bin",
            ]
            npm_bin = None
            for p in node_paths:
                candidate = os.path.join(p, "npm")
                if os.path.isfile(candidate):
                    npm_bin = candidate
                    break
            if not npm_bin:
                import shutil
                npm_bin = shutil.which("npm")
            if not npm_bin:
                raise RuntimeError("npm not found; install Node.js to use --ui svelte")
            build_env = os.environ.copy()
            build_env["PATH"] = os.path.dirname(npm_bin) + ":" + build_env.get("PATH", "")
            result = subprocess.run(
                [npm_bin, "run", "build"],
                cwd=svelte_dir,
                env=build_env,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f"[error] Svelte build failed:\n{result.stderr}")
                return 1
            print("[build] Svelte build complete.")
        except Exception as exc:
            print(f"[error] Svelte build error: {exc}")
            return 1
        gui_dir = dist_dir
    else:
        gui_dir = os.path.join(ROOT_DIR, "gui")

    http_cmd = [
        python,
        os.path.join(ROOT_DIR, "tools", "gui_http_server.py"),
        "--bind",
        http_bind,
        "--directory",
        gui_dir,
        str(args.http_port),
    ]

    # RCON password warning and environment setup
    if args.rcon_password == "admin":
        print("[warn] Using default RCON password 'admin' -- change with --rcon-password")
    env = os.environ.copy()
    env["FLAXOS_RCON_PASSWORD"] = args.rcon_password

    processes: list[subprocess.Popen] = []
    try:
        processes.append(_start_process("TCP server", server_cmd, ROOT_DIR, env=env))
        processes.append(_start_process("WebSocket bridge", ws_bridge_cmd, ROOT_DIR))

        if ui_mode == "dev":
            # Launch vite dev server instead of static file server
            svelte_dir = os.path.join(ROOT_DIR, "gui-svelte")
            node_paths = [
                os.path.expanduser("~/.nvm/versions/node/v24.14.0/bin"),
                os.path.expanduser("~/.nvm/versions/node/v22.22.1/bin"),
                "/usr/local/bin",
                "/usr/bin",
            ]
            npm_bin = None
            for p in node_paths:
                candidate = os.path.join(p, "npm")
                if os.path.isfile(candidate):
                    npm_bin = candidate
                    break
            if not npm_bin:
                import shutil as _shutil
                npm_bin = _shutil.which("npm") or "npm"
            dev_env = os.environ.copy()
            dev_env["PATH"] = os.path.dirname(npm_bin) + ":" + dev_env.get("PATH", "")
            processes.append(_start_process(
                "Vite dev server",
                [npm_bin, "run", "dev"],
                svelte_dir,
                env=dev_env,
            ))
            gui_url = "http://localhost:5174/"
            razorback_url = gui_url
        else:
            processes.append(_start_process("GUI server", http_cmd, ROOT_DIR))
            gui_url = f"http://localhost:{args.http_port}/"
            razorback_url = f"http://localhost:{args.http_port}/razorback.html"

        if ui_mode == "legacy":
            print("[warn] Legacy GUI selected. The supported default is the v3 bridge UI.")

        if args.game_code:
            gui_url = _append_query_param(gui_url, "game_code", args.game_code)
            razorback_url = _append_query_param(
                razorback_url,
                "game_code",
                args.game_code,
            )

        display_ui_mode = "v3" if ui_mode in {"svelte", "dev"} else "legacy"
        print(f"[ready] Mode: {mode} | UI: {display_ui_mode}")
        print(f"[ready] GUI: {gui_url}")
        if ui_mode == "legacy":
            print(f"[ready] Razorback cockpit: {razorback_url}")
        if ui_mode == "dev":
            print(f"[ready] Vite dev server (v3): {gui_url} (hot reload)")
        print(f"[ready] WS bridge: ws://localhost:{args.ws_port}")
        print(f"[ready] TCP server: {args.host}:{args.tcp_port}")
        if args.game_code:
            print(f"[ready] WS game code: {args.game_code}")
        if args.rcon_password:
            print(f"[ready] RCON password: {args.rcon_password}")
        if args.allowed_origin_host:
            print(
                "[ready] Allowed origin hosts: "
                + ", ".join(args.allowed_origin_host)
            )
        print("Press Ctrl+C to stop all services.")

        if args.browser:
            time.sleep(1.0)
            open_url = razorback_url if (args.razorback and ui_mode == "legacy") else gui_url
            webbrowser.open(open_url)

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
