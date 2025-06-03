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
#!/usr/bin/env python3
# Command sender for hybrid simulator
# This script sends commands to ships in the simulator

import argparse
import json
import requests
import sys
import socket
import time

# Default parameters
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 7979  # Default server port

def send_command(ship_id, command, args, host=DEFAULT_HOST, port=DEFAULT_PORT):
    """
    Send a command to a ship via the command server
    
    Args:
        ship_id (str): ID of the ship to send command to
        command (str): Command to send
        args (dict): Command arguments
        host (str): Server hostname or IP
        port (int): Server port
        
    Returns:
        dict: Command response
    """
    try:
        # Create a socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        
        # Create command message
        message = {
            "ship_id": ship_id,
            "command": command,
            "args": args
        }
        
        # Send the command
        sock.sendall(json.dumps(message).encode() + b'\n')
        
        # Wait for response
        response = b''
        while True:
            data = sock.recv(4096)
            if not data:
                break
            response += data
            if b'\n' in data:
                break
        
        # Close the socket
        sock.close()
        
        # Parse and return the response
        return json.loads(response.decode())
    
    except ConnectionRefusedError:
        # Try local fallback using hybrid_runner directly
        try:
            from hybrid_runner import HybridRunner
            runner = HybridRunner()
            runner.load_ships()
            result = runner.send_command(ship_id, command, args)
            return result
        except Exception as e:
            return {"error": f"Connection refused and fallback failed: {str(e)}"}
    
    except Exception as e:
        return {"error": str(e)}

def main():
    """Parse command line arguments and send the command"""
    parser = argparse.ArgumentParser(description="Send commands to ships in the hybrid simulator")
    
    parser.add_argument("command", help="Command to send")
    parser.add_argument("--ship", required=True, help="Ship ID")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Server hostname (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Server port (default: {DEFAULT_PORT})")
    
    # Common command arguments
    parser.add_argument("--x", type=float, help="X coordinate")
    parser.add_argument("--y", type=float, help="Y coordinate")
    parser.add_argument("--z", type=float, help="Z coordinate")
    parser.add_argument("--pitch", type=float, help="Pitch angle")
    parser.add_argument("--yaw", type=float, help="Yaw angle")
    parser.add_argument("--roll", type=float, help="Roll angle")
    parser.add_argument("--enabled", type=int, help="Enable/disable flag (0/1)")
    parser.add_argument("--mode", help="Mode setting")
    parser.add_argument("--duration", type=float, help="Duration in seconds")
    parser.add_argument("--system", help="System name")
    parser.add_argument("--direction", type=float, help="Direction in degrees")
    parser.add_argument("--power", type=int, help="Power setting (0-100)")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Extract command arguments
    command_args = {}
    for arg in ["x", "y", "z", "pitch", "yaw", "roll", "enabled", "mode", 
                "duration", "system", "direction", "power"]:
        if hasattr(args, arg) and getattr(args, arg) is not None:
            command_args[arg] = getattr(args, arg)
    
    # Send the command
    response = send_command(args.ship, args.command, command_args, args.host, args.port)
    
    # Print the response
    print("[RESPONSE]")
    print(json.dumps(response, indent=2))

if __name__ == "__main__":
    main()
    helm_parser = subparsers.add_parser('helm_override')
    helm_parser.add_argument('--enabled', type=int, choices=[0, 1], required=True)

    # Ping sensors (active)
    ping_parser = subparsers.add_parser('ping_sensors', help='Trigger active sensor ping')

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

    # ping_sensors has no extra payload

    send_command(args.host, args.port, command)

if __name__ == '__main__':
    main()
