# cli/send.py
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
            print(response.strip())
    except ConnectionRefusedError:
        print(f"ERROR: Could not connect to {host}:{port}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="CLI for spaceship_sim commands")
    parser.add_argument('--host', default='127.0.0.1', help='Simulation server host')
    parser.add_argument('--port', type=int, default=8765, help='Simulation server port')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # Throttle command
    throttle_parser = subparsers.add_parser('throttle', help='Set main drive throttle')
    throttle_parser.add_argument('value', type=float, help='Throttle value between 0.0 and 1.0')

    # Vector command
    vector_parser = subparsers.add_parser('vector', help='Adjust thrust vector')
    vector_parser.add_argument('pitch', type=float, help='Pitch angle in degrees')
    vector_parser.add_argument('yaw', type=float, help='Yaw angle in degrees')

    # Status command
    status_parser = subparsers.add_parser('status', help='Get current ship state')

    # Events command
    events_parser = subparsers.add_parser('events', help='Get recent event log')

    args = parser.parse_args()

    # Build command payload
    if args.command == 'throttle':
        command = {'command_type': 'set_throttle', 'payload': {'throttle': args.value}}
    elif args.command == 'vector':
        command = {'command_type': 'adjust_vector', 'payload': {'pitch': args.pitch, 'yaw': args.yaw}}
    elif args.command == 'status':
        command = {'command_type': 'get_state', 'payload': {}}
    elif args.command == 'events':
        command = {'command_type': 'get_events', 'payload': {}}
    else:
        parser.error(f"Unknown command: {args.command}")

    send_command(args.host, args.port, command)


if __name__ == '__main__':
    main()
