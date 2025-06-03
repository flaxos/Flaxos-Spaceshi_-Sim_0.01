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
            # Create base state dictionary
            state = {
                "position": self.position,
                "velocity": self.velocity,
                "orientation": self.orientation,
                "angular_velocity": self.angular_velocity,
                "thrust": self.systems.get("propulsion", {}).get("main_drive", {}).get("thrust", {})
            }
            
            # Handle bio_monitor if available
            if "bio_monitor" in self.systems:
                bio_system = self.systems["bio_monitor"]
                if hasattr(bio_system, "get_state"):
                    state["bio_monitor"] = bio_system.get_state()
                else:
                    state["bio_monitor"] = bio_system
            
            # Handle sensors system properly
            if "sensors" in self.systems:
                sensors = self.systems["sensors"]
                # Check if sensors is an object with get_state method
                if hasattr(sensors, "get_state") and callable(sensors.get_state):
                    state["sensors"] = sensors.get_state()
                # Check if sensors is a dictionary
                elif isinstance(sensors, dict):
                    state["sensors"] = sensors
                else:
                    # Create a minimal valid sensor state
                    state["sensors"] = {
                        "enabled": True,
                        "passive": {"contacts": []},
                        "active": {"contacts": [], "last_ping_time": 0},
                        "contacts": []
                    }
                    
            return state
