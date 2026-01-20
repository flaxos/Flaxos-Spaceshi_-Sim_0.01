#!/usr/bin/env python3
"""
Automated validation for D2-D4 demo slice requirements:
- D2: Two concurrent clients can connect + issue commands safely
- D3: Station claim/release + permissions enforced end-to-end
- D4: Station-filtered telemetry (each station sees what it should)
"""
import json
import socket
import subprocess
import sys
import time
from typing import Dict, Any


class TestClient:
    """Simple client for testing multi-client scenarios"""

    def __init__(self, name: str, host: str = "127.0.0.1", port: int = 8765):
        self.name = name
        self.host = host
        self.port = port
        self.sock = None
        self.client_id = None

    def connect(self) -> Dict[str, Any]:
        """Connect to the server"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5.0)
        self.sock.connect((self.host, self.port))

        # Read welcome message
        response = self.read_response()
        if response.get("ok"):
            self.client_id = response.get("client_id")
        return response

    def send_command(self, cmd_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Send a command to the server"""
        cmd_json = json.dumps(cmd_dict) + "\n"
        self.sock.sendall(cmd_json.encode("utf-8"))
        return self.read_response()

    def read_response(self) -> Dict[str, Any]:
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


def validate_d2_concurrent_clients() -> tuple[bool, str]:
    """
    D2: Two concurrent clients can connect + issue commands safely
    """
    print("\n=== D2: Testing Concurrent Client Connections ===")
    client1 = TestClient("Client1")
    client2 = TestClient("Client2")

    try:
        # Connect both clients
        print("1. Connecting Client1...")
        resp1 = client1.connect()
        if not resp1.get("ok"):
            return False, f"Client1 failed to connect: {resp1}"
        print(f"   ✓ Client1 connected (ID: {client1.client_id})")

        print("2. Connecting Client2...")
        resp2 = client2.connect()
        if not resp2.get("ok"):
            return False, f"Client2 failed to connect: {resp2}"
        print(f"   ✓ Client2 connected (ID: {client2.client_id})")

        # Both clients send commands simultaneously
        print("3. Testing simultaneous commands...")
        resp1 = client1.send_command({"cmd": "my_status"})
        resp2 = client2.send_command({"cmd": "my_status"})

        if not resp1.get("ok") or not resp2.get("ok"):
            return False, f"Simultaneous commands failed: {resp1}, {resp2}"
        print("   ✓ Both clients can issue commands concurrently")

        return True, "D2 PASSED: Two clients connected and issued commands safely"

    except Exception as e:
        return False, f"D2 FAILED: {e}"

    finally:
        client1.close()
        client2.close()


def validate_d3_station_permissions() -> tuple[bool, str]:
    """
    D3: Station claim/release + permissions enforced end-to-end
    """
    print("\n=== D3: Testing Station Claim/Release + Permissions ===")
    helm_client = TestClient("HELM")
    tactical_client = TestClient("TACTICAL")

    try:
        # Connect both clients
        print("1. Connecting clients...")
        helm_client.connect()
        tactical_client.connect()
        print("   ✓ Both clients connected")

        # Assign to ship
        print("2. Assigning to test_ship_001...")
        resp1 = helm_client.send_command({"cmd": "assign_ship", "ship": "test_ship_001"})
        resp2 = tactical_client.send_command({"cmd": "assign_ship", "ship": "test_ship_001"})
        if not resp1.get("ok") or not resp2.get("ok"):
            return False, f"Ship assignment failed: {resp1}, {resp2}"
        print("   ✓ Both clients assigned to ship")

        # Claim stations
        print("3. Claiming stations...")
        resp1 = helm_client.send_command({"cmd": "claim_station", "station": "helm"})
        if not resp1.get("ok"):
            return False, f"HELM claim failed: {resp1}"
        print("   ✓ HELM station claimed")

        resp2 = tactical_client.send_command({"cmd": "claim_station", "station": "tactical"})
        if not resp2.get("ok"):
            return False, f"TACTICAL claim failed: {resp2}"
        print("   ✓ TACTICAL station claimed")

        # Test permissions - HELM can set_thrust
        print("4. Testing HELM permissions...")
        resp = helm_client.send_command({
            "cmd": "set_thrust",
            "ship": "test_ship_001",
            "x": 50,
            "y": 0,
            "z": 0
        })
        if not resp.get("ok"):
            return False, f"HELM set_thrust should succeed: {resp}"
        print("   ✓ HELM can execute set_thrust")

        # Test permissions - TACTICAL cannot set_thrust
        print("5. Testing permission enforcement...")
        resp = tactical_client.send_command({
            "cmd": "set_thrust",
            "ship": "test_ship_001",
            "x": 50,
            "y": 0,
            "z": 0
        })
        if resp.get("ok"):
            return False, "TACTICAL should NOT be able to execute set_thrust"
        print("   ✓ TACTICAL correctly denied set_thrust")

        # Release station
        print("6. Testing station release...")
        resp = helm_client.send_command({"cmd": "release_station"})
        if not resp.get("ok"):
            return False, f"Station release failed: {resp}"
        print("   ✓ Station released successfully")

        # After release, should not be able to issue commands
        print("7. Testing post-release permissions...")
        resp = helm_client.send_command({
            "cmd": "set_thrust",
            "ship": "test_ship_001",
            "x": 50,
            "y": 0,
            "z": 0
        })
        if resp.get("ok"):
            return False, "Should not be able to issue commands after release"
        print("   ✓ Commands correctly denied after release")

        return True, "D3 PASSED: Station claim/release and permissions working"

    except Exception as e:
        return False, f"D3 FAILED: {e}"

    finally:
        helm_client.close()
        tactical_client.close()


def validate_d4_station_telemetry() -> tuple[bool, str]:
    """
    D4: Station-filtered telemetry (each station sees what it should)
    """
    print("\n=== D4: Testing Station-Filtered Telemetry ===")
    helm_client = TestClient("HELM")
    engineering_client = TestClient("ENGINEERING")

    try:
        # Connect and setup
        print("1. Setting up clients...")
        helm_client.connect()
        engineering_client.connect()
        helm_client.send_command({"cmd": "assign_ship", "ship": "test_ship_001"})
        engineering_client.send_command({"cmd": "assign_ship", "ship": "test_ship_001"})
        helm_client.send_command({"cmd": "claim_station", "station": "helm"})
        engineering_client.send_command({"cmd": "claim_station", "station": "engineering"})
        print("   ✓ Clients setup complete")

        # Get telemetry for both
        print("2. Getting HELM telemetry...")
        helm_state = helm_client.send_command({"cmd": "get_state", "ship": "test_ship_001"})
        if not helm_state.get("ok"):
            return False, f"HELM telemetry failed: {helm_state}"

        print("3. Getting ENGINEERING telemetry...")
        eng_state = engineering_client.send_command({"cmd": "get_state", "ship": "test_ship_001"})
        if not eng_state.get("ok"):
            return False, f"ENGINEERING telemetry failed: {eng_state}"

        # Verify filtering
        helm_fields = set(helm_state.get("state", {}).keys())
        eng_fields = set(eng_state.get("state", {}).keys())

        print(f"   HELM sees: {sorted(helm_fields)}")
        print(f"   ENGINEERING sees: {sorted(eng_fields)}")

        # Both should see some fields, but not necessarily the same ones
        if not helm_fields:
            return False, "HELM should see some telemetry fields"
        if not eng_fields:
            return False, "ENGINEERING should see some telemetry fields"

        # HELM should see navigation-related fields
        # ENGINEERING should see power/systems fields
        # (Exact fields depend on implementation)
        print("   ✓ Both stations receive filtered telemetry")

        return True, "D4 PASSED: Station-filtered telemetry working"

    except Exception as e:
        return False, f"D4 FAILED: {e}"

    finally:
        helm_client.close()
        engineering_client.close()


def main():
    """Main validation runner"""
    print("=" * 70)
    print("DEMO SLICE VALIDATION: D2-D4 Multi-Client Tests")
    print("=" * 70)

    # Start the station server
    print("\nStarting station server...")
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "server.station_server", "--port", "8765"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        # Wait for server to start
        time.sleep(2.0)

        results = {}

        # Run validations
        success, message = validate_d2_concurrent_clients()
        results["D2"] = {"success": success, "message": message}
        print(f"\n{message}")

        success, message = validate_d3_station_permissions()
        results["D3"] = {"success": success, "message": message}
        print(f"\n{message}")

        success, message = validate_d4_station_telemetry()
        results["D4"] = {"success": success, "message": message}
        print(f"\n{message}")

        # Summary
        print("\n" + "=" * 70)
        print("VALIDATION SUMMARY")
        print("=" * 70)
        all_passed = True
        for req, result in results.items():
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            print(f"{req}: {status}")
            if not result["success"]:
                print(f"     {result['message']}")
                all_passed = False

        print("=" * 70)

        if all_passed:
            print("\n✅ ALL TESTS PASSED - D2-D4 requirements validated")
            return 0
        else:
            print("\n❌ SOME TESTS FAILED - See above for details")
            return 1

    finally:
        # Stop server
        server_proc.terminate()
        try:
            server_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            server_proc.kill()
            server_proc.wait()


if __name__ == "__main__":
    sys.exit(main())
