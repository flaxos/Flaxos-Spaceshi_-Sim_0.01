# send.py — CLI tool to issue commands to the running simulation

import argparse
import socket
import json

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9999

VALID_COMMANDS = [
    "set_thrust",
    "set_orientation",
    "rotate",
    "get_state",
    "get_position",
    "get_velocity",
    "get_orientation",
    "status",
    "events"
]


def send_command(host, port, command_type, ship_id, params):
    payload = {
        "command_type": command_type,
        "ship_id": ship_id,
        "params": params or {}
    }
    message = json.dumps(payload).encode()

    if args.command_type in ["set_orientation", "rotate"] and args.value is not None:
        params["yaw"] = args.value

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        s.sendall(message)
        response = s.recv(4096)
        print("[RESPONSE]", response.decode())

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send command to simulated ship.")
    parser.add_argument("command_type", choices=VALID_COMMANDS, help="Type of command to send")
    parser.add_argument("--ship", required=True, help="Target ship ID")
    parser.add_argument("--value", type=float, help="Value for thrust, yaw, or other input")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)

    args = parser.parse_args()

    params = {}
    if args.command_type in ["set_orientation", "rotate"] and args.value is not None:
        params["yaw"] = args.value
    elif args.value is not None:
        params["value"] = args.value

    send_command(args.host, args.port, args.command_type, args.ship, params)
