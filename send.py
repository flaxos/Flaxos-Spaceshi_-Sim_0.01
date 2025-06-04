import argparse
import socket
import json
import sys

def send_command(host: str, port: int, command: dict):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((host, port))
            message = json.dumps(command) + '\n'
            sock.sendall(message.encode('utf-8'))

            # Read response
            response = ''
            while True:
                data = sock.recv(1024)
                if not data:
                    break
                response += data.decode('utf-8')
                if '\n' in response:
                    break
            print("[RESPONSE]", response.strip())
    except ConnectionRefusedError:
        print(f"ERROR: Could not connect to {host}:{port}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="CLI for spaceship_sim commands")
    parser.add_argument('--host', default='127.0.0.1', help='Simulation server host')
    parser.add_argument('--port', type=int, default=9999, help='Simulation server port')
    parser.add_argument('--ship', required=True, help='Ship ID to control')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # Throttle command
    throttle_parser = subparsers.add_parser('set_thrust', help='Set main drive thrust')
    throttle_parser.add_argument('--x', type=float, default=0.0)
    throttle_parser.add_argument('--y', type=float, default=0.0)
    throttle_parser.add_argument('--z', type=float, default=0.0)

    # Orientation
    orient_parser = subparsers.add_parser('set_orientation')
    orient_parser.add_argument('--pitch', type=float)
    orient_parser.add_argument('--yaw', type=float)
    orient_parser.add_argument('--roll', type=float)

    angvel_parser = subparsers.add_parser('set_angular_velocity')
    angvel_parser.add_argument('--pitch', type=float)
    angvel_parser.add_argument('--yaw', type=float)
    angvel_parser.add_argument('--roll', type=float)

    # Rotation
    rotate_parser = subparsers.add_parser('rotate')
    rotate_parser.add_argument('--axis', choices=['pitch', 'yaw', 'roll'])
    rotate_parser.add_argument('--value', type=float)

    # Navigation
    course_parser = subparsers.add_parser('set_course')
    course_parser.add_argument('--x', type=float, required=True)
    course_parser.add_argument('--y', type=float, required=True)
    course_parser.add_argument('--z', type=float, required=True)

    autopilot_parser = subparsers.add_parser('autopilot')
    autopilot_parser.add_argument('--enabled', type=int, choices=[0, 1], required=True)
    helm_parser = subparsers.add_parser('helm_override')
    helm_parser.add_argument('--enabled', type=int, choices=[0, 1], required=True)

    # Ping sensors (active)
    ping_parser = subparsers.add_parser('ping_sensors', help='Trigger active sensor ping')

    subparsers.add_parser('reactor_start', help='Start the ship reactor')
    subparsers.add_parser('get_power_status', help='Get power system status')
    alloc_parser = subparsers.add_parser('set_power_allocation', help='Set bus power allocation')
    alloc_parser.add_argument('--primary', type=float, required=True)
    alloc_parser.add_argument('--secondary', type=float, required=True)
    alloc_parser.add_argument('--tertiary', type=float, required=True)
    toggle_parser = subparsers.add_parser('toggle_system', help='Toggle a ship system')
    toggle_parser.add_argument('--system', required=True)
    toggle_parser.add_argument('--state', type=int, choices=[0,1], required=True)

    # Misc
    subparsers.add_parser('get_position')
    subparsers.add_parser('get_velocity')
    subparsers.add_parser('get_orientation')
    subparsers.add_parser('get_state')
    subparsers.add_parser('get_contacts')
    subparsers.add_parser('status')
    subparsers.add_parser('events')
    subparsers.add_parser('override_bio_monitor')

    args = parser.parse_args()

    # Build command payload
    command = {"command": args.command, "ship": args.ship}

    if args.command in ["set_thrust", "set_orientation", "set_angular_velocity"]:
        for field in ["x", "y", "z", "pitch", "yaw", "roll"]:
            if hasattr(args, field):
                val = getattr(args, field, None)
                if val is not None:
                    command[field] = val

    elif args.command in ["rotate"]:
        command["axis"] = args.axis
        command["value"] = args.value

    elif args.command == "set_course":
        command["target"] = {"x": args.x, "y": args.y, "z": args.z}

    elif args.command in ["autopilot", "helm_override"]:
        command["enabled"] = bool(args.enabled)

    elif args.command == "set_power_allocation":
        command.update({
            "primary": args.primary,
            "secondary": args.secondary,
            "tertiary": args.tertiary,
        })

    elif args.command == "toggle_system":
        command["system"] = args.system
        command["state"] = bool(args.state)

    # reactor_start and get_power_status require no extra fields

    # ping_sensors has no extra payload

    send_command(args.host, args.port, command)

if __name__ == '__main__':
    main()
