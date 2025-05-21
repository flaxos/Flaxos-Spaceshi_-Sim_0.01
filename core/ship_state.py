# core/ship_state.py
from dataclasses import dataclass, field, asdict
from typing import List, Dict
from uuid import uuid4
from datetime import datetime
import math

from core.vector import Vector3
from core.rotation import Rotation

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
class ShipWithEvents:
    id: str
    name: str
    state: ShipState
    propulsion: Dict[str, MainDrive]
    hull_integrity: HullIntegrity = field(default_factory=lambda: HullIntegrity(sectors=[
        HullSector(sector_id="fore", integrity=100.0, breached=False),
        HullSector(sector_id="aft", integrity=100.0, breached=False)
    ]))
    event_log: List[Event] = field(default_factory=list)

    def tick(self, delta_t: float):
        drive = self.propulsion["main_drive"]
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

    def handle_command(self, command: Dict) -> Dict:
        cmd = command.get("command_type")
        # 1) set_throttle
        if cmd == "set_throttle":
            t = command["payload"].get("throttle", 0.0)
            self.propulsion["main_drive"].current_throttle = max(0.0, min(1.0, t))
            return {"status": "throttle_set", "throttle": self.propulsion["main_drive"].current_throttle}

        # 2) adjust_vector
        if cmd == "adjust_vector":
            p = command["payload"].get("pitch", 0.0)
            y = command["payload"].get("yaw", 0.0)
            vc = self.propulsion["main_drive"].vector_control
            vc.pitch, vc.yaw = p, y
            return {"status": "vector_adjusted", "vector": vc.as_dict()}

        # 3) get_state
        if cmd == "get_state":
            return {"state": asdict(self.state)}

        # 4) get_events
        if cmd == "get_events":
            return {"events": [asdict(e) for e in self.event_log]}

        # unknown
        return {"error": f"Unknown command type: {cmd}"}