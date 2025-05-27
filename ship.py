from systems_schema import build_default_systems

class Ship:
    def __init__(
        self,
        ship_id,
        position,
        velocity=None,
        orientation=None,
        angular_velocity=None,
        mass=1.0,
        systems=None
    ):
        self.id = ship_id
        self.position = position

        # Physics state
        self.velocity = velocity or {"x": 0.0, "y": 0.0, "z": 0.0}
        self.orientation = orientation or {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        self.angular_velocity = angular_velocity or {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        self.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.mass = mass

        # Systems scaffold
        self.systems = systems if systems is not None else build_default_systems()

    def __repr__(self):
        return f"<Ship {self.id} @ {self.position}>"

    def get_state(self):
        """Return a snapshot of the ship's current state."""
        return {
            "position": self.position,
            "velocity": self.velocity,
            "orientation": self.orientation,
            "thrust": self.systems.get("propulsion", {}).get("main_drive", {}).get("thrust", {}),
            "angular_velocity": self.angular_velocity,
            "bio_monitor": self.systems.get("bio_monitor", {})
        }
