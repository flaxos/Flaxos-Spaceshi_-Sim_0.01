# rcs_controller.py — RCS system for smooth orientation changes over time

from base_system import BaseSystem

class RCSController(BaseSystem):
    def __init__(self, torque_rating):
        self.torque_rating = torque_rating
        self.target = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}

    def command(self, action, params):
        if action == "rotate":
            for axis in ["yaw", "pitch", "roll"]:
                if axis in params:
                    self.target[axis] = params[axis]

    def tick(self, dt, ship):
        max_speed = self.torque_rating / ship.mass  # degrees per second

        for axis in ["yaw", "pitch", "roll"]:
            current = ship.orientation[axis]
            target = self.target[axis]
            angle_diff = (target - current + 540) % 360 - 180  # shortest rotation path
            rotation_step = max(-max_speed * dt, min(angle_diff, max_speed * dt))
            ship.orientation[axis] += rotation_step

    def get_state(self):
        return {
            "torque_rating": self.torque_rating,
            "target_orientation": self.target
        }
