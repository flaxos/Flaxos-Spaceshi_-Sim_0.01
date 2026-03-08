# hybrid/systems/weapons/hardpoint.py
"""Hardpoint mount system for weapon placement and tracking.

Hardpoints define the physical location and orientation constraints
of weapon mounts on a ship hull. Turret-type mounts can rotate within
arc limits; fixed mounts fire along a single axis.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Union
from hybrid.systems.weapons.weapon_system import Weapon
import time


@dataclass
class Hardpoint:
    """A physical weapon mount on the ship hull.

    Attributes:
        id: Unique identifier for this hardpoint.
        mount_type: Mount classification (``turret``, ``fixed``, ``missile_rack``).
        weapon: Currently mounted weapon, if any.
        position_offset: Position offset from ship center of mass in meters.
        orientation: Current turret orientation in degrees.
        max_rotation_rate: Maximum turret slew rate in degrees/second.
        azimuth_limits: (min, max) azimuth arc in degrees.
        elevation_limits: (min, max) elevation arc in degrees.
    """

    id: str
    mount_type: str  # e.g., "turret", "fixed", "missile_rack"
    weapon: Optional[Weapon] = None

    # S3 Aim Fidelity: Hardpoint physical positioning
    # Position offset from ship center of mass (meters)
    position_offset: Optional[Dict[str, float]] = None

    # Turret orientation relative to ship (degrees)
    orientation: Optional[Dict[str, float]] = None

    # Turret capabilities (only for mount_type="turret")
    max_rotation_rate: float = 0.0  # deg/s
    azimuth_limits: Optional[tuple] = None
    elevation_limits: Optional[tuple] = None

    def __post_init__(self) -> None:
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

    def mount_weapon(self, weapon: Weapon) -> bool:
        """Mount a weapon to this hardpoint.

        Args:
            weapon: Weapon instance to mount.

        Returns:
            True if mounted successfully, False if a weapon is already mounted.
        """
        if self.weapon is None:
            self.weapon = weapon
            return True
        return False

    def unmount_weapon(self) -> bool:
        """Remove the currently mounted weapon.

        Returns:
            True if a weapon was removed, False if the hardpoint was empty.
        """
        if self.weapon:
            self.weapon = None
            return True
        return False

    def fire(self, power_manager, target) -> Union[dict, bool]:
        """Fire the mounted weapon at a target.

        Args:
            power_manager: Power system for power draw.
            target: Target ship object.

        Returns:
            dict with fire result if weapon is mounted, False otherwise.
        """
        if self.weapon:
            return self.weapon.fire(time.time(), power_manager, target)
        return False
