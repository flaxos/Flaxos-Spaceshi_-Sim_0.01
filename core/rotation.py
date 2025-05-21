# core/rotation.py
from dataclasses import dataclass
import math

@dataclass
class Rotation:
    pitch: float  # in degrees
    yaw: float    # in degrees

    def to_radians(self):
        return math.radians(self.pitch), math.radians(self.yaw)

    def set(self, pitch: float = None, yaw: float = None):
        if pitch is not None:
            self.pitch = pitch
        if yaw is not None:
            self.yaw = yaw

    def as_dict(self):
        return {"pitch": self.pitch, "yaw": self.yaw}
