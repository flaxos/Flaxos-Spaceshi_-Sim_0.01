import os
import sys
import json
import socket
import threading
import argparse
import logging

# Ensure project root is on sys.path for direct execution
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from hybrid_runner import HybridRunner
from hybrid.command_handler import route_command
from utils.logger import setup_logging

logger = logging.getLogger(__name__)


def _json_default(value):
    if isinstance(value, (set, tuple)):
        return list(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    try:
        import numpy as np

        if isinstance(value, (np.integer, np.floating, np.bool_)):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
    except Exception:
        pass
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return value.__dict__
    return str(value)


def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, default=_json_default)

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
    cmd = req.get("cmd") or req.get("command")
    if not cmd:
        return {"ok": False, "error": "missing cmd"}

    logger.info("Dispatching command", extra={"command": cmd, "ship": req.get("ship")})

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
        limit = int(req.get("limit", 100))
        if hasattr(runner.simulator, "get_recent_events"):
            events = runner.simulator.get_recent_events(limit=limit)
        elif hasattr(runner.simulator, "event_log"):
            events = list(runner.simulator.event_log)[-limit:]
        else:
            events = []
        for event in events:
            logger.info("Event", extra={"event": event})
        return {"ok": True, "events": events, "total_events": len(events)}

    if cmd == "list_scenarios":
        return {"ok": True, "scenarios": runner.list_scenarios()}

    if cmd == "load_scenario":
        scenario_name = req.get("scenario") or req.get("name") or req.get("file")
        if not scenario_name:
            return {"ok": False, "error": "missing scenario"}
        loaded = runner.load_scenario(scenario_name)
        if loaded <= 0:
            return {"ok": False, "error": f"Failed to load scenario {scenario_name}"}
        return {
            "ok": True,
            "scenario": scenario_name,
            "ships_loaded": loaded,
            "player_ship_id": runner.player_ship_id,
            "mission": runner.get_mission_status(),
        }

    if cmd == "get_mission":
        return {"ok": True, "mission": runner.get_mission_status()}

    if cmd == "get_mission_hints":
        clear = bool(req.get("clear", False))
        return {"ok": True, "hints": runner.get_mission_hints(clear=clear)}

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

    # Normalize set_thrust command to distinguish scalar throttle vs debug vector
    if cmd == "set_thrust":
        # Check if this is a legacy {x,y,z} vector command (debug-only)
        has_vector = any(k in req for k in ("x", "y", "z"))
        has_scalar = "thrust" in req
        
        if has_vector and not has_scalar:
            # Legacy debug mode: route to set_thrust_vector
            cmd = "set_thrust_vector"
        elif not has_scalar and not has_vector:
            # No params provided - default to scalar 0
            req["thrust"] = 0.0

    command_data = {"command": cmd, "ship": ship_id, **req}
    command_data.pop("cmd", None)
    result = route_command(ship, command_data, runner.simulator.ships)
    if isinstance(result, dict) and "error" in result:
        return {"ok": False, "error": result["error"], "response": result}
    return {"ok": True, "response": result}


def _serve(host: str, port: int, dt: float, fleet_dir: str) -> None:
    runner = HybridRunner(fleet_dir=fleet_dir, dt=dt)
    runner.load_ships()
    runner.start()
    logger.info("Server started", extra={"host": host, "port": port, "dt": dt})

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
                        err = _json_dumps({"ok": False, "error": "bad json"}) + "\n"
                        conn.sendall(err.encode("utf-8"))
                        continue
                    logger.info("Command received", extra={"request": req})
                    resp = dispatch(runner, req)
                    conn.sendall((_json_dumps(resp) + "\n").encode("utf-8"))
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
    ap.add_argument("--log-file", default=None)
    args = ap.parse_args()
    log_path = setup_logging(args.log_file)
    if log_path:
        logger.info("Logging to file", extra={"log_file": log_path})
    _serve(args.host, args.port, args.dt, args.fleet_dir)


if __name__ == "__main__":
    main()
