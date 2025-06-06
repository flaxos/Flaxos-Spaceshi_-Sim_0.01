from dataclasses import dataclass, field, asdict
from typing import List, Dict
import math
import json
import os
from uuid import uuid4
from datetime import datetime

# Vector and Rotation Classes
@dataclass
class Vector3:
    x: float
    y: float
    z: float

    def add(self, other):
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def scale(self, factor: float):
        return Vector3(self.x * factor, self.y * factor, self.z * factor)

@dataclass
class Rotation:
    pitch: float
    yaw: float

# Ship System Components
@dataclass
class MainDrive:
    type: str
    status: str
    max_thrust: float
    current_throttle: float
    vector_control: Rotation

@dataclass
class ShipState:
    position: Vector3
    velocity: Vector3
    acceleration: Vector3
    rotation: Rotation
    angular_velocity: Rotation

@dataclass
class Event:
    id: str
    timestamp: str
    type: str
    severity: str
    message: str
    data: Dict

@dataclass
class HullSector:
    sector_id: str
    integrity: float
    breached: bool

@dataclass
class HullIntegrity:
    sectors: List[HullSector]

@dataclass
class Ship:
    id: str
    name: str
    state: ShipState
    propulsion: Dict[str, MainDrive]

@dataclass
class ShipWithEvents(Ship):
    hull_integrity: HullIntegrity = field(default_factory=lambda: HullIntegrity(sectors=[
        HullSector(sector_id="fore", integrity=100.0, breached=False),
        HullSector(sector_id="aft", integrity=100.0, breached=False)
    ]))
    event_log: List[Event] = field(default_factory=list)

    def tick(self, delta_t: float):
        drive = self.propulsion['main_drive']
        if drive.status != "online" or drive.current_throttle <= 0.0:
            return

        thrust = drive.max_thrust * drive.current_throttle
        pitch_rad = math.radians(drive.vector_control.pitch)
        yaw_rad = math.radians(drive.vector_control.yaw)

        accel_x = thrust * math.cos(pitch_rad) * math.cos(yaw_rad)
        accel_y = thrust * math.sin(pitch_rad)
        accel_z = thrust * math.cos(pitch_rad) * math.sin(yaw_rad)

        accel_vector = Vector3(accel_x, accel_y, accel_z)

        self.state.acceleration = accel_vector
        self.state.velocity = self.state.velocity.add(accel_vector.scale(delta_t))
        self.state.position = self.state.position.add(self.state.velocity.scale(delta_t))

        if self.state.position.x > 200 and not self.hull_integrity.sectors[0].breached:
            self.hull_integrity.sectors[0].integrity -= 50.0
            self.hull_integrity.sectors[0].breached = True
            event = Event(
                id=str(uuid4()),
                timestamp=datetime.utcnow().isoformat(),
                type="hull_breach",
                severity="critical",
                message="Hull breach detected in sector fore",
                data={"sector": "fore", "integrity": self.hull_integrity.sectors[0].integrity}
            )
            self.event_log.append(event)

# Initialize ship
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
            current_throttle=0.5,
            vector_control=Rotation(pitch=5.0, yaw=10.0)
        )
    }
)

# Run 5 simulation ticks
tick_outputs = []
for _ in range(500):
    ship.tick(delta_t=1.0)
    tick_outputs.append({
        "position": asdict(ship.state.position),
        "velocity": asdict(ship.state.velocity),
        "acceleration": asdict(ship.state.acceleration),
        "hull_fore_integrity": ship.hull_integrity.sectors[0].integrity,
        "hull_fore_breached": ship.hull_integrity.sectors[0].breached,
        "event_count": len(ship.event_log)
    })

# Print summary
for tick in tick_outputs:
    print(json.dumps(tick, indent=2))

# Save events to logs/event_log.json
os.makedirs("logs", exist_ok=True)
with open("logs/event_log.json", "w") as f:
    json.dump([asdict(e) for e in ship.event_log], f, indent=2)
