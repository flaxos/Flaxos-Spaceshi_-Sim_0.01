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

    def add_common_args(p):
        p.add_argument("--ship", required=True)

    subparsers = parser.add_subparsers(dest="command_type", required=True)

    # Thrust commands (manual or autopilot)
    thrust_parser = subparsers.add_parser("set_thrust")
    add_common_args(thrust_parser)
    thrust_parser.add_argument("--x", type=float, default=0.0)
    thrust_parser.add_argument("--y", type=float, default=0.0)
    thrust_parser.add_argument("--z", type=float, default=0.0)

    # Orientation / angular commands
    orient_parser = subparsers.add_parser("set_orientation")
    add_common_args(orient_parser)
    orient_parser.add_argument("--pitch", type=float, default=0.0)
    orient_parser.add_argument("--yaw", type=float, default=0.0)
    orient_parser.add_argument("--roll", type=float, default=0.0)

    angvel_parser = subparsers.add_parser("set_angular_velocity")
    add_common_args(angvel_parser)
    angvel_parser.add_argument("--pitch", type=float, default=0.0)
    angvel_parser.add_argument("--yaw", type=float, default=0.0)
    angvel_parser.add_argument("--roll", type=float, default=0.0)

    rotate_parser = subparsers.add_parser("rotate")
    add_common_args(rotate_parser)
    rotate_parser.add_argument("--axis", choices=["pitch", "yaw", "roll"], required=True)
    rotate_parser.add_argument("--value", type=float, required=True)

    # Navigation
    nav_parser = subparsers.add_parser("set_course")
    add_common_args(nav_parser)
    nav_parser.add_argument("--x", type=float, required=True)
    nav_parser.add_argument("--y", type=float, required=True)
    nav_parser.add_argument("--z", type=float, required=True)

    nav_toggle = subparsers.add_parser("autopilot")
    add_common_args(nav_toggle)
    nav_toggle.add_argument("--enabled", type=int, choices=[0, 1], required=True)

    # Helm manual control
    helm_parser = subparsers.add_parser("helm_override")
    add_common_args(helm_parser)
    helm_parser.add_argument("--enabled", type=int, choices=[0, 1], required=True)

    # Info commands
    for name in ["get_state", "get_position", "get_velocity", "get_orientation", "status", "events", "override_bio_monitor"]:
        p = subparsers.add_parser(name)
        add_common_args(p)

    args = parser.parse_args()

    if args.command_type == "set_thrust":
        cmd = {"command": "set_thrust", "x": args.x, "y": args.y, "z": args.z}
    elif args.command_type == "set_orientation":
        cmd = {"command": "set_orientation", "pitch": args.pitch, "yaw": args.yaw, "roll": args.roll}
    elif args.command_type == "set_angular_velocity":
        cmd = {"command": "set_angular_velocity", "pitch": args.pitch, "yaw": args.yaw, "roll": args.roll}
    elif args.command_type == "rotate":
        cmd = {"command": "rotate", "axis": args.axis, "value": args.value}
    elif args.command_type == "set_course":
        cmd = {"command": "set_course", "target": {"x": args.x, "y": args.y, "z": args.z}}
    elif args.command_type == "autopilot":
        cmd = {"command": "autopilot", "enabled": bool(args.enabled)}
    elif args.command_type == "helm_override":
        cmd = {"command": "helm_override", "enabled": bool(args.enabled)}
    else:
        cmd = {"command": args.command_type}

    send_command(args.host, args.port, args.ship, cmd)
