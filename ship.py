# ship.py — Core ship logic including physics state and system integration

import math

class Ship:
    def __init__(self, ship_id, position, systems, mass=1000):
        self.id = ship_id
        self.position = position  # {"x": float, "y": float, "z": float}
        self.velocity = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.orientation = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}  # degrees
        self.systems = systems  # Dict[str, BaseSystem]
        self.orientation = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}  # degrees
        self.angular_velocity = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}  # degrees per second
        self.target_orientation = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}  # command goal
        self.mass = mass  # default mass

    def tick(self, delta_time):
        for system in self.systems.values():
            system.tick(delta_time, self)

    def get_state(self):
        return {
            "id": self.id,
            "position": self.position,
            "velocity": self.velocity,
            "orientation": self.orientation,
            "systems": {name: sys.get_state() for name, sys in self.systems.items()}
        }
