#!/usr/bin/env python3
"""
Flaxos Spaceship Sim — Unified Launcher
========================================

QUICK START
  python tools/launch.py              # Interactive setup wizard (recommended for UAT)
  python tools/launch.py --quick      # Local-only, no prompts
  python tools/launch.py --quick --browser   # Local + auto-open browser

NON-INTERACTIVE (scripting / CI)
  python tools/launch.py --lan --rcon-password mysecret --browser
  python tools/launch.py --lan --allowed-origin-host 172.22.0.5 --game-code abc123

PARTIAL STACKS
  python tools/launch.py --server-only   # TCP sim server only, no GUI
  python tools/launch.py --no-server     # HTTP + WS bridge only (point at running server)

WHAT GETS STARTED (full stack)
  1. TCP sim server      — default 127.0.0.1:8765
  2. WebSocket bridge    — default 127.0.0.1:8081
  3. GUI HTTP server     — default 127.0.0.1:3100   (serves v3 bridge UI)

NETWORK MODES
  Local (default)  — all services bind 127.0.0.1. Only this machine can connect.
  LAN / ZeroTier   — WS and HTTP bind 0.0.0.0. Any LAN or ZT peer can connect.
                     Requires a real RCON password + game code (auto-generated).

SECURITY
  RCON password    — Admin console access. Default "admin" is insecure for LAN.
  Game code        — Appended to WS URL as a shared secret (?game_code=...).
                     Prevents unauthorised WebSocket connections.
  Origin allowlist — Restricts which hostnames the browser can connect from.
                     Localhost always included. Add ZT/LAN hosts when opening up.

ZeroTier
  Detected automatically from zt* network interfaces.
  Add your ZT IP to --allowed-origin-host when enabling LAN mode.
"""

from __future__ import annotations

import getpass
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STACK_SCRIPT = os.path.join(ROOT, "tools", "start_gui_stack.py")
VENV = os.path.join(ROOT, ".venv")

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from server.config import DEFAULT_TCP_PORT, DEFAULT_WS_PORT, DEFAULT_HTTP_PORT


# ─── Network discovery ───────────────────────────────────────────────────────

def _discover_ips() -> dict[str, str]:
    """Return {label: ip} mapping for reachable interfaces."""
    result: dict[str, str] = {"local": "127.0.0.1"}
    try:
        out = subprocess.run(
            ["ip", "-4", "addr", "show"],
            capture_output=True, text=True, timeout=3,
        ).stdout
        iface: str | None = None
        for line in out.splitlines():
            if line and not line[0].isspace():
                # "2: eth0: <..."  or  "3: ztabcdef01: <..."
                parts = line.split(":")
                iface = parts[1].strip().split("@")[0] if len(parts) >= 2 else None
            elif "inet " in line and iface:
                m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", line)
                if m and not m.group(1).startswith("127."):
                    ip = m.group(1)
                    if iface.startswith("zt"):
                        result[f"zerotier ({iface})"] = ip
                    else:
                        result.setdefault(f"lan ({iface})", ip)
    except Exception:
        pass
    return result


# ─── Environment checks ──────────────────────────────────────────────────────

def _check_venv() -> None:
    if not os.path.isfile(os.path.join(VENV, "bin", "python")):
        print("[warn] No .venv found — using system Python.")
        print("       Set one up: python -m venv .venv && .venv/bin/pip install -r requirements.txt")


def _check_updates() -> None:
    """Offer to pull from origin/main if behind."""
    try:
        subprocess.run(
            ["git", "fetch", "origin", "--quiet"],
            cwd=ROOT, capture_output=True, timeout=5,
        )
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            cwd=ROOT, capture_output=True, text=True, timeout=3,
        )
        count = int(result.stdout.strip() or "0")
        if count > 0:
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=ROOT, capture_output=True, text=True,
            ).stdout.strip()
            print(f"[update] {count} commit(s) available on origin/main (current: {branch})")
            ans = input("  Pull now? [Y/n]: ").strip().lower()
            if ans in ("", "y"):
                subprocess.run(["git", "pull", "origin", "main", "--ff-only"], cwd=ROOT, check=False)
    except Exception:
        pass  # Offline or not a git repo — skip silently


# ─── Interactive prompts ──────────────────────────────────────────────────────

def _prompt(label: str, default: str = "", secret: bool = False) -> str:
    hint = f"[{default}]" if default and not secret else ""
    try:
        if secret:
            val = getpass.getpass(f"  {label} {hint}: ") or default
        else:
            val = input(f"  {label} {hint}: ").strip() or default
    except (EOFError, KeyboardInterrupt):
        sys.exit(0)
    return val


def _yn(label: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    try:
        val = input(f"  {label} [{hint}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        sys.exit(0)
    return default if not val else val.startswith("y")


def _interactive_wizard(ips: dict[str, str]) -> list[str]:
    """
    Walk the user through setup options.
    Returns a list of args to pass to start_gui_stack.py.
    """
    args: list[str] = []

    # ── What to start ──
    print()
    print("  ── WHAT TO START ─────────────────────────────────")
    print("  1) Full stack   server + WS bridge + v3 GUI  [default]")
    print("  2) Server only  TCP sim server, no GUI")
    print("  3) GUI only     HTTP + WS bridge (assumes server running on localhost)")
    try:
        choice = input("  Choice [1]: ").strip() or "1"
    except (EOFError, KeyboardInterrupt):
        sys.exit(0)

    if choice == "2":
        args.append("--server-only")
    elif choice == "3":
        args.append("--no-server")

    # ── Network ──
    print()
    print("  ── NETWORK ────────────────────────────────────────")
    for label, ip in ips.items():
        print(f"    {label:<24} {ip}")

    lan = _yn("Enable LAN / ZeroTier mode?", default=False)
    if lan:
        args.append("--lan")
        zt_input = _prompt(
            "Hostnames to allowlist (comma-separated, blank=none)",
            default="",
        )
        for h in zt_input.split(","):
            h = h.strip()
            if h:
                args += ["--allowed-origin-host", h]

    # ── Security ──
    print()
    print("  ── SECURITY ───────────────────────────────────────")
    if lan:
        rcon = _prompt("RCON admin password (blank = auto-generate)", secret=True)
        if rcon:
            args += ["--rcon-password", rcon]
        gc = _prompt("WS game code (blank = auto-generate)", default="")
        if gc:
            args += ["--game-code", gc]
    else:
        print("  (Skipped — local-only mode is safe without extra auth)")

    # ── GUI ──
    print()
    print("  ── GUI ────────────────────────────────────────────")
    if "--server-only" not in args:
        if _yn("Open browser automatically?", default=True):
            args.append("--browser")

    return args


# ─── Endpoint summary ────────────────────────────────────────────────────────

def _print_endpoints(
    ips: dict[str, str],
    is_lan: bool,
    http_port: int,
    ws_port: int,
    tcp_port: int,
    game_code: str | None,
) -> None:
    """Print all accessible URLs before handing off to start_gui_stack.py."""
    print()
    print("─" * 54)
    print("  WILL BE ACCESSIBLE ON")
    print("─" * 54)

    active_ips = list(ips.items()) if is_lan else [("local", "127.0.0.1")]

    for label, ip in active_ips:
        url = f"http://{ip}:{http_port}/"
        if game_code:
            url += f"?game_code={game_code}"
        print(f"  GUI   {url:<40} [{label}]")
    print()
    for label, ip in active_ips:
        print(f"  WS    ws://{ip}:{ws_port}/  [{label}]")
    print(f"  TCP   {('0.0.0.0' if is_lan else '127.0.0.1')}:{tcp_port}")
    print("─" * 54)
    print()


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Flaxos Spaceship Sim — Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--quick", action="store_true",
        help="Skip interactive wizard, start locally with defaults")
    parser.add_argument("--no-update-check", action="store_true",
        help="Skip git update check")
    # Convenience pass-through flags (skip wizard when provided)
    parser.add_argument("--browser", action="store_true", help="Auto-open browser")
    parser.add_argument("--lan", action="store_true", help="Enable LAN/ZeroTier mode")
    parser.add_argument("--server-only", action="store_true",
        help="Start TCP server only (no GUI)")
    parser.add_argument("--no-server", action="store_true",
        help="Start GUI only (WS bridge + HTTP, no TCP server)")
    parser.add_argument("--rcon-password", default=None)
    parser.add_argument("--game-code", default=None)
    parser.add_argument("--allowed-origin-host", action="append", default=[],
        metavar="HOST")
    args, extra = parser.parse_known_args()

    # ── Banner ──
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=ROOT, capture_output=True, text=True,
        ).stdout.strip() or "unknown"
    except Exception:
        branch = "unknown"

    print("═" * 54)
    print("  FLAXOS SPACESHIP SIM — LAUNCHER")
    print(f"  Branch: {branch}")
    print("═" * 54)

    _check_venv()

    ips = _discover_ips()

    # Decide whether to run the wizard
    non_interactive = (
        args.quick
        or args.lan
        or args.server_only
        or args.no_server
        or args.rcon_password
        or args.game_code
        or args.allowed_origin_host
    )

    if not non_interactive and not args.no_update_check:
        _check_updates()

    if non_interactive:
        # Build args from flags directly
        stack_args: list[str] = []
        if args.lan:
            stack_args.append("--lan")
        if args.server_only:
            stack_args.append("--server-only")
        if args.no_server:
            stack_args.append("--no-server")
        if args.browser:
            stack_args.append("--browser")
        if args.rcon_password:
            stack_args += ["--rcon-password", args.rcon_password]
        if args.game_code:
            stack_args += ["--game-code", args.game_code]
        for h in args.allowed_origin_host:
            stack_args += ["--allowed-origin-host", h]
        stack_args += extra
    else:
        stack_args = _interactive_wizard(ips)
        stack_args += extra

    # ── Endpoint summary ──
    is_lan = "--lan" in stack_args
    gc = None
    for i, a in enumerate(stack_args):
        if a == "--game-code" and i + 1 < len(stack_args):
            gc = stack_args[i + 1]
    _print_endpoints(ips, is_lan, DEFAULT_HTTP_PORT, DEFAULT_WS_PORT, DEFAULT_TCP_PORT, gc)

    # ── Hand off to start_gui_stack.py ──
    cmd = [sys.executable, STACK_SCRIPT] + stack_args
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(sys.executable, cmd)
    return 0  # unreachable


if __name__ == "__main__":
    raise SystemExit(main())
