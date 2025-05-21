# impulse_drive.py — Navigation system that applies directional thrust

from base_system import BaseSystem
import math

class ImpulseDrive(BaseSystem):
    def __init__(self, max_thrust):
        self.max_thrust = max_thrust
        self.current_thrust = 0

    def command(self, action, params):
        if action == "set_thrust":
            self.current_thrust = max(0, min(params.get("value", 0), self.max_thrust))

    def tick(self, delta_time, ship):
        acceleration = self.current_thrust / 1000.0  # Fixed mass approximation
        yaw_rad = math.radians(ship.orientation.get("yaw", 0))
        pitch_rad = math.radians(ship.orientation.get("pitch", 0))

        # Apply thrust in direction based on yaw + pitch (3D vector)
        thrust_x = math.cos(pitch_rad) * math.cos(yaw_rad)
        thrust_y = math.sin(pitch_rad)
        thrust_z = math.cos(pitch_rad) * math.sin(yaw_rad)

        ship.velocity["x"] += thrust_x * acceleration * delta_time
        ship.velocity["y"] += thrust_y * acceleration * delta_time
        ship.velocity["z"] += thrust_z * acceleration * delta_time

        ship.position["x"] += ship.velocity["x"] * delta_time
        ship.position["y"] += ship.velocity["y"] * delta_time
        ship.position["z"] += ship.velocity["z"] * delta_time

    def get_state(self):
        return {
            "max_thrust": self.max_thrust,
            "current_thrust": self.current_thrust
        }
