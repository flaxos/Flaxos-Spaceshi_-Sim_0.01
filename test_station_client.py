#!/usr/bin/env python3
"""
Test client for the station-based control system.

This demonstrates how to connect to the station server, claim a station,
and issue commands.
"""

import socket
import json
import time
import sys


class StationClient:
    """Simple client for testing the station server"""

    def __init__(self, host="127.0.0.1", port=8765):
        self.host = host
        self.port = port
        self.sock = None
        self.client_id = None

    def connect(self):
        """Connect to the server"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        print(f"Connected to {self.host}:{self.port}")

        # Read welcome message
        response = self.read_response()
        if response.get("ok"):
            self.client_id = response.get("client_id")
            print(f"Welcome! Client ID: {self.client_id}")
            print(f"Instructions: {response.get('instructions')}")
        else:
            print(f"Connection failed: {response}")
        return response

    def send_command(self, cmd_dict):
        """Send a command to the server"""
        cmd_json = json.dumps(cmd_dict) + "\n"
        self.sock.sendall(cmd_json.encode("utf-8"))
        return self.read_response()

    def read_response(self):
        """Read a response from the server"""
        buf = b""
        while b"\n" not in buf:
            data = self.sock.recv(4096)
            if not data:
                raise ConnectionError("Connection closed by server")
            buf += data

        line, _ = buf.split(b"\n", 1)
        return json.loads(line.decode("utf-8"))

    def close(self):
        """Close the connection"""
        if self.sock:
            self.sock.close()
            print("Connection closed")


def test_basic_workflow():
    """Test the basic station workflow"""
    print("=== Testing Basic Station Workflow ===\n")

    client = StationClient()

    try:
        # Connect
        client.connect()
        time.sleep(0.5)

        # Check status
        print("\n1. Checking initial status...")
        resp = client.send_command({"cmd": "my_status"})
        print(f"   Status: {json.dumps(resp, indent=2)}")
        time.sleep(0.5)

        # Assign to ship
        print("\n2. Assigning to ship...")
        resp = client.send_command({"cmd": "assign_ship", "ship": "test_ship_001"})
        print(f"   Response: {resp.get('message')}")
        time.sleep(0.5)

        # Claim helm station
        print("\n3. Claiming HELM station...")
        resp = client.send_command({"cmd": "claim_station", "station": "helm"})
        if resp.get("ok"):
            print(f"   Success! {resp.get('message')}")
            available_cmds = resp.get("response", {}).get("available_commands", [])
            print(f"   Available commands: {len(available_cmds)} commands")
            print(f"   Sample: {available_cmds[:5]}")
        else:
            print(f"   Failed: {resp.get('message')}")
        time.sleep(0.5)

        # Check station status
        print("\n4. Checking station status...")
        resp = client.send_command({"cmd": "station_status"})
        if resp.get("ok"):
            stations = resp.get("response", {}).get("stations", [])
            print("   Station Status:")
            for station in stations:
                status = "CLAIMED" if station.get("claimed") else "Available"
                player = f" by {station.get('player')}" if station.get("player") else ""
                print(f"     - {station.get('station')}: {status}{player}")
        time.sleep(0.5)

        # Test helm command
        print("\n5. Testing HELM command (set_thrust)...")
        resp = client.send_command({
            "cmd": "set_thrust",
            "ship": "test_ship_001",
            "x": 50,
            "y": 0,
            "z": 0
        })
        print(f"   Response: {json.dumps(resp, indent=2)}")
        time.sleep(0.5)

        # Test unauthorized command (should fail)
        print("\n6. Testing unauthorized command (fire - requires TACTICAL)...")
        resp = client.send_command({
            "cmd": "fire",
            "ship": "test_ship_001"
        })
        print(f"   Response: {resp.get('message')}")
        time.sleep(0.5)

        # Get filtered state
        print("\n7. Getting filtered telemetry...")
        resp = client.send_command({
            "cmd": "get_state",
            "ship": "test_ship_001"
        })
        if resp.get("ok"):
            state = resp.get("state", {})
            print("   Available telemetry fields:")
            for field in state.keys():
                print(f"     - {field}")
        time.sleep(0.5)

        # Release station
        print("\n8. Releasing station...")
        resp = client.send_command({"cmd": "release_station"})
        print(f"   Response: {resp.get('message')}")

        print("\n=== Test Complete ===")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

    finally:
        client.close()


def test_multi_station():
    """Test multiple stations on same ship (simulated)"""
    print("\n=== Testing Multi-Station Scenario ===\n")

    # Create two clients
    helm_client = StationClient()
    tactical_client = StationClient()

    try:
        # Connect both
        print("1. Connecting HELM client...")
        helm_client.connect()
        time.sleep(0.5)

        print("2. Connecting TACTICAL client...")
        tactical_client.connect()
        time.sleep(0.5)

        # Assign both to same ship
        print("\n3. Assigning both to test_ship_001...")
        helm_client.send_command({"cmd": "assign_ship", "ship": "test_ship_001"})
        tactical_client.send_command({"cmd": "assign_ship", "ship": "test_ship_001"})
        time.sleep(0.5)

        # Claim different stations
        print("\n4. Claiming stations...")
        resp1 = helm_client.send_command({"cmd": "claim_station", "station": "helm"})
        print(f"   HELM: {resp1.get('message')}")

        resp2 = tactical_client.send_command({"cmd": "claim_station", "station": "tactical"})
        print(f"   TACTICAL: {resp2.get('message')}")
        time.sleep(0.5)

        # Check fleet status
        print("\n5. Checking fleet status...")
        resp = helm_client.send_command({"cmd": "fleet_status"})
        if resp.get("ok"):
            ships = resp.get("response", {}).get("ships", {})
            clients = resp.get("response", {}).get("clients", [])
            print(f"   Ships: {len(ships)}")
            print(f"   Connected clients: {len(clients)}")
            for client_info in clients:
                print(f"     - {client_info.get('player_name')} on {client_info.get('station')}")
        time.sleep(0.5)

        # Test station-specific commands
        print("\n6. Testing station-specific commands...")
        resp = helm_client.send_command({
            "cmd": "set_thrust",
            "ship": "test_ship_001",
            "x": 100,
            "y": 0,
            "z": 0
        })
        print(f"   HELM set_thrust: {resp.get('ok')}")

        # Try helm command from tactical (should fail)
        resp = tactical_client.send_command({
            "cmd": "set_thrust",
            "ship": "test_ship_001",
            "x": 50,
            "y": 0,
            "z": 0
        })
        print(f"   TACTICAL set_thrust (should fail): {resp.get('message')}")

        print("\n=== Multi-Station Test Complete ===")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

    finally:
        helm_client.close()
        tactical_client.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "multi":
        test_multi_station()
    else:
        test_basic_workflow()

    print("\nTo test multi-station scenario, run:")
    print("  python test_station_client.py multi")
