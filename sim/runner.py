# sim/runner.py
import time
import queue
from datetime import datetime
from core.vector import Vector3
from core.rotation import Rotation
from core.command import Command
from sim.socket_listener import start_socket_listener
from core.ship_state import ShipWithEvents, ShipState, MainDrive  # ✅ CORRECT

# Create the command queue
command_queue = queue.Queue()

# Initialize the ship
ship = ShipWithEvents(
    id="ship-001",
    name="Tachi",
    state=ShipState(
        position=Vector3(0.0, 0.0, 0.0),
        velocity=Vector3(0.0, 0.0, 0.0),
        acceleration=Vector3(0.0, 0.0, 0.0),
        rotation=Rotation(0.0, 0.0),
        angular_velocity=Rotation(0.0, 0.0)
    ),
    propulsion={
        "main_drive": MainDrive(
            type="fusion_torch",
            status="online",
            max_thrust=100.0,
            current_throttle=0.0,
            vector_control=Rotation(pitch=0.0, yaw=0.0)
        )
    }
)

# Seed a test command
command_queue.put({
    "command_type": "set_throttle",
    "payload": {"throttle": 0.5},
    "source": "test_console",
    "timestamp": datetime.utcnow().isoformat()
})

# Main simulation loop (runs indefinitely)
TICK_RATE = 1.0  # seconds

def main_loop():
    while True:
        # Process commands
        while not command_queue.empty():
            command = command_queue.get()
            ship.handle_command(command)

        # Run simulation tick
        ship.tick(delta_t=TICK_RATE)

        # Output current position (placeholder broadcast)
        print(f"[{datetime.utcnow().isoformat()}] Position: {ship.state.position}, Velocity: {ship.state.velocity}")

        time.sleep(TICK_RATE)
start_socket_listener("127.0.0.1", 8765, command_queue)

if __name__ == "__main__":
    main_loop()
