import argparse
import json
import socket

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9999

def send_command(host, port, ship_id, command):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    payload = {"ship": ship_id, **command}
    sock.send(json.dumps(payload).encode("utf-8"))
    response = sock.recv(4096).decode("utf-8")
    sock.close()
    print("[RESPONSE]", response)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)

    subparsers = parser.add_subparsers(dest="command_type", required=True)

    # Shared args
    def add_common_args(p):
        p.add_argument("--ship", required=True)

    # Command: set_thrust
    thrust_parser = subparsers.add_parser("set_thrust")
    add_common_args(thrust_parser)
    thrust_parser.add_argument("--x", type=float, default=0.0)
    thrust_parser.add_argument("--y", type=float, default=0.0)
    thrust_parser.add_argument("--z", type=float, default=0.0)

    # Command: set_orientation
    orient_parser = subparsers.add_parser("set_orientation")
    add_common_args(orient_parser)
    orient_parser.add_argument("--pitch", type=float, default=0.0)
    orient_parser.add_argument("--yaw", type=float, default=0.0)
    orient_parser.add_argument("--roll", type=float, default=0.0)

    # Command: set_angular_velocity
    angvel_parser = subparsers.add_parser("set_angular_velocity")
    add_common_args(angvel_parser)
    angvel_parser.add_argument("--pitch", type=float, default=0.0)
    angvel_parser.add_argument("--yaw", type=float, default=0.0)
    angvel_parser.add_argument("--roll", type=float, default=0.0)

    # Command: rotate
    rotate_parser = subparsers.add_parser("rotate")
    add_common_args(rotate_parser)
    rotate_parser.add_argument("--axis", choices=["pitch", "yaw", "roll"], required=True)
    rotate_parser.add_argument("--value", type=float, required=True)

    # Command: override_bio_monitor
    override_parser = subparsers.add_parser("override_bio_monitor")
    add_common_args(override_parser)

    # Info commands
    for name in ["get_state", "get_position", "get_velocity", "get_orientation", "status", "events"]:
        info_parser = subparsers.add_parser(name)
        add_common_args(info_parser)

    args = parser.parse_args()
    cmd_type = args.command_type

    # Dispatch logic
    if cmd_type == "set_thrust":
        command = {
            "command": "set_thrust",
            "x": args.x,
            "y": args.y,
            "z": args.z
        }
    elif cmd_type == "set_orientation":
        command = {
            "command": "set_orientation",
            "pitch": args.pitch,
            "yaw": args.yaw,
            "roll": args.roll
        }
    elif cmd_type == "set_angular_velocity":
        command = {
            "command": "set_angular_velocity",
            "pitch": args.pitch,
            "yaw": args.yaw,
            "roll": args.roll
        }
    elif cmd_type == "rotate":
        command = {
            "command": "rotate",
            "axis": args.axis,
            "value": args.value
        }
    elif cmd_type == "override_bio_monitor":
        command = {
            "command": "override_bio_monitor"
        }
    else:  # Info commands
        command = {"command": cmd_type}

    send_command(args.host, args.port, args.ship, command)
