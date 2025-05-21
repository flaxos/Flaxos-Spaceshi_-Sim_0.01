# core/vector.py
from dataclasses import dataclass
import math

@dataclass
class Vector3:
    x: float
    y: float
    z: float

    def add(self, other: 'Vector3') -> 'Vector3':
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def scale(self, factor: float) -> 'Vector3':
        return Vector3(self.x * factor, self.y * factor, self.z * factor)

    def magnitude(self) -> float:
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)

    def normalize(self) -> 'Vector3':
        mag = self.magnitude()
        if mag == 0:
            return Vector3(0, 0, 0)
        return self.scale(1 / mag)

# core/rotation.py
from dataclasses import dataclass

@dataclass
class Rotation:
    pitch: float  # in degrees
    yaw: float    # in degrees

# core/command.py
from dataclasses import dataclass
from typing import Dict

@dataclass
class Command:
    command_type: str
    payload: Dict
    source: str = "unknown"
    timestamp: str = ""

# Extend ShipWithEvents with command handling
# core/ship_state.py (partial)
def handle_command(self, command):
    if command["command_type"] == "set_throttle":
        target_throttle = command["payload"].get("throttle", 0.0)
        self.propulsion["main_drive"].current_throttle = max(0.0, min(1.0, target_throttle))
    elif command["command_type"] == "adjust_vector":
        pitch = command["payload"].get("pitch", 0.0)
        yaw = command["payload"].get("yaw", 0.0)
        self.propulsion["main_drive"].vector_control.pitch = pitch
        self.propulsion["main_drive"].vector_control.yaw = yaw
    else:
        print(f"Unknown command type: {command['command_type']}")
