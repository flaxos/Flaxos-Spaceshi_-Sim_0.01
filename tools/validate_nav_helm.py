#!/usr/bin/env python3
"""
Validate navigation + helm flows against the TCP server used by the GUI stack.

This script is intended to be run while `server.run_server` is active (e.g.
via `python tools/start_gui_stack.py`).
"""

import argparse
import json
import socket
import sys
import time
from typing import Any, Dict, Optional


class TcpClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket] = None

    def connect(self) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(5.0)
        self.socket.connect((self.host, self.port))

    def close(self) -> None:
        if self.socket:
            self.socket.close()
            self.socket = None

    def send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.socket:
            raise ConnectionError("TCP client not connected.")

        self.socket.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        return self._read_response()

    def _read_response(self) -> Dict[str, Any]:
        if not self.socket:
            raise ConnectionError("TCP client not connected.")

        buf = b""
        while b"\n" not in buf:
            data = self.socket.recv(4096)
            if not data:
                raise ConnectionError("Connection closed by server.")
            buf += data
        line, _ = buf.split(b"\n", 1)
        return json.loads(line.decode("utf-8"))


def _select_ship(state_payload: Dict[str, Any], preferred_ship: Optional[str]) -> Optional[str]:
    if preferred_ship:
        return preferred_ship

    ships = state_payload.get("ships", [])
    for ship in ships:
        if ship.get("id") == "player":
            return "player"
    if ships:
        return ships[0].get("id")
    return None


def _extract_contact_id(state_payload: Dict[str, Any], ship_id: str) -> Optional[str]:
    ship_state = state_payload.get("state", {})
    sensors = ship_state.get("systems", {}).get("sensors", {})
    contacts = sensors.get("contacts", [])
    for contact in contacts:
        contact_id = contact.get("id")
        if contact_id:
            return contact_id
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate nav/helm GUI flows.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--scenario", default="01_tutorial_intercept.yaml")
    parser.add_argument("--ship")
    parser.add_argument("--target")
    parser.add_argument("--skip-scenario", action="store_true")
    args = parser.parse_args()

    client = TcpClient(args.host, args.port)

    try:
        client.connect()

        if not args.skip_scenario:
            resp = client.send({"cmd": "load_scenario", "scenario": args.scenario})
            if not resp.get("ok"):
                print(f"[error] Failed to load scenario: {resp}")
                return 1
            print(f"[ok] Scenario loaded: {resp.get('scenario')}")

        state = client.send({"cmd": "get_state"})
        if not state.get("ok"):
            print(f"[error] Failed to get state: {state}")
            return 1

        ship_id = _select_ship(state, args.ship)
        if not ship_id:
            print("[error] Could not determine ship id.")
            return 1
        print(f"[ok] Using ship: {ship_id}")

        ping = client.send({"cmd": "ping_sensors", "ship": ship_id})
        if not ping.get("ok"):
            print(f"[error] Sensor ping failed: {ping}")
            return 1
        print("[ok] Sensors pinged.")

        time.sleep(0.5)
        ship_state = client.send({"cmd": "get_state", "ship": ship_id})
        if not ship_state.get("ok"):
            print(f"[error] Failed to get ship state: {ship_state}")
            return 1

        target_id = args.target or _extract_contact_id(ship_state, ship_id) or "C001"
        print(f"[ok] Using target: {target_id}")

        autopilot = client.send({
            "cmd": "autopilot",
            "ship": ship_id,
            "program": "intercept",
            "target": target_id
        })
        if not autopilot.get("ok"):
            print(f"[error] Autopilot intercept failed: {autopilot}")
            return 1
        print("[ok] Autopilot intercept engaged.")

        follow_up = client.send({"cmd": "get_state", "ship": ship_id})
        if not follow_up.get("ok"):
            print(f"[error] Failed to confirm state: {follow_up}")
            return 1
        print("[ok] State returned after autopilot command.")

        return 0
    except Exception as exc:
        print(f"[error] Validation failed: {exc}")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
