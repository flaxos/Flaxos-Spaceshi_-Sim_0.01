# ship.py
class Ship:
    def __init__(self, ship_id, position=None, velocity=None, orientation=None, angular_velocity=None, thrust=None, systems=None, mass=1.0):
        self.id = ship_id
        self.position = position or {"x": 0.0, "y": 0.0, "z": 0.0}
        self.velocity = velocity or {"x": 0.0, "y": 0.0, "z": 0.0}
        self.orientation = orientation or {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        self.angular_velocity = angular_velocity or {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        self.thrust = thrust or {"x": 0.0, "y": 0.0, "z": 0.0}
        self.systems = systems or {}
        self.mass = mass

    def state(self):
        return {
            "position": self.position,
            "velocity": self.velocity,
            "orientation": self.orientation,
            "angular_velocity": self.angular_velocity,
            "thrust": self.thrust,
            "systems": self.systems,
            "mass": self.mass,
        }
