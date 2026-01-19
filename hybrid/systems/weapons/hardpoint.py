# hybrid/systems/weapons/hardpoint.py

from dataclasses import dataclass
from typing import Optional
from hybrid.systems.weapons.weapon_system import Weapon
import time

@dataclass
class Hardpoint:
    id: str
    mount_type: str  # e.g., "turret", "fixed", "missile_rack"
    weapon: Optional[Weapon] = None

    # S3 Aim Fidelity: Hardpoint physical positioning
    # Position offset from ship center of mass (meters)
    position_offset: dict = None  # {"x": 0.0, "y": 0.0, "z": 0.0}

    # Turret orientation relative to ship (degrees)
    # For fixed mounts, this is the fixed firing direction
    # For turrets, this is the current aim direction
    orientation: dict = None  # {"azimuth": 0.0, "elevation": 0.0}

    # Turret capabilities (only for mount_type="turret")
    max_rotation_rate: float = 0.0  # deg/s - how fast turret can slew
    azimuth_limits: tuple = None  # (min_deg, max_deg) - e.g., (-180, 180) for full rotation
    elevation_limits: tuple = None  # (min_deg, max_deg) - e.g., (-10, 80) for typical turret

    def __post_init__(self):
        """Initialize default values for optional fields."""
        if self.position_offset is None:
            self.position_offset = {"x": 0.0, "y": 0.0, "z": 0.0}
        if self.orientation is None:
            self.orientation = {"azimuth": 0.0, "elevation": 0.0}
        if self.mount_type == "turret":
            if self.max_rotation_rate == 0.0:
                self.max_rotation_rate = 30.0  # Default 30 deg/s
            if self.azimuth_limits is None:
                self.azimuth_limits = (-180.0, 180.0)  # Full rotation
            if self.elevation_limits is None:
                self.elevation_limits = (-10.0, 80.0)  # Typical turret limits
        elif self.mount_type == "fixed":
            # Fixed mounts can't rotate
            self.max_rotation_rate = 0.0

    def mount_weapon(self, weapon):
        if self.weapon is None:
            self.weapon = weapon
            return True
        return False

    def unmount_weapon(self):
        if self.weapon:
            self.weapon = None
            return True
        return False

    def fire(self, power_manager, target):
        if self.weapon:
            return self.weapon.fire(time.time(), power_manager, target)
        return False
