# hybrid/environment/hazard_zone.py
"""Spherical hazard zones with type-dependent effects.

Hazard zones are regions of space with environmental effects that
alter sensor performance, degrade guided munitions, or block
line-of-sight. They create tactical geometry -- a nebula between
you and the target means your torpedo loses datalink, forcing
dumb-fire or a flanking approach.

Types:
- radiation: Hot gas / stellar wind. Floods passive IR with noise,
  reducing detection range by 50-80% inside the zone.
- debris: Dense micro-debris field. Guided munitions take structural
  damage (5 HP/s) as particles sandblast guidance fins and optics.
- nebula: Dense gas cloud. Blocks sensor LOS entirely and severs
  torpedo datalink, forcing fire-and-forget.

Design: effects are continuous while inside the zone, not binary.
A ship skimming the edge gets the full effect because the zone
boundary is the physics boundary.
"""

import logging
from enum import Enum
from typing import Dict, Optional

from hybrid.utils.math_utils import calculate_distance

logger = logging.getLogger(__name__)


class HazardType(Enum):
    """Environmental hazard categories."""
    RADIATION = "radiation"
    DEBRIS = "debris"
    NEBULA = "nebula"


# Default sensor range multiplier for each hazard type.
# Applied to passive IR detection range when observer or target is inside.
SENSOR_MODIFIERS = {
    HazardType.RADIATION: 0.3,   # IR flooded by ambient radiation
    HazardType.DEBRIS: 1.0,      # Debris doesn't affect sensors much
    HazardType.NEBULA: 0.0,      # Opaque to passive IR
}

# Damage per second applied to guided munitions (torpedoes/missiles)
# inside the zone. Models micro-particle erosion of guidance surfaces.
DEBRIS_MUNITION_DPS = 5.0


class HazardZone:
    """A spherical region with environmental effects.

    Ships, projectiles, and guided munitions passing through the zone
    experience type-dependent penalties. The zone is static (no drift)
    because hazard zones represent large-scale phenomena that don't
    move on combat timescales.
    """

    def __init__(
        self,
        zone_id: str,
        center: Dict[str, float],
        radius: float,
        hazard_type: str,
        intensity: float = 1.0,
    ):
        """Create a hazard zone.

        Args:
            zone_id: Unique identifier
            center: Center position {x, y, z} in metres
            radius: Zone radius in metres
            hazard_type: One of "radiation", "debris", "nebula"
            intensity: Effect strength multiplier (0.0-1.0), default 1.0
        """
        self.zone_id = zone_id
        self.center = dict(center)
        self.radius = radius
        self.intensity = max(0.0, min(1.0, intensity))

        try:
            self.hazard_type = HazardType(hazard_type)
        except ValueError:
            logger.warning("Unknown hazard type '%s', defaulting to debris", hazard_type)
            self.hazard_type = HazardType.DEBRIS

    def contains(self, position: Dict[str, float]) -> bool:
        """Check if a position is inside this zone."""
        return calculate_distance(position, self.center) <= self.radius

    def get_sensor_modifier(self) -> float:
        """Return the passive sensor range multiplier for this zone.

        A modifier of 0.3 means detection range is reduced to 30%.
        Intensity scales the effect: at intensity 0.5, a radiation
        zone modifier becomes 0.3 + 0.7*0.5 = 0.65 (less severe).

        Returns:
            float: Multiplier for passive IR detection range (0.0-1.0)
        """
        base = SENSOR_MODIFIERS.get(self.hazard_type, 1.0)
        # Lerp between full effect and no effect based on intensity
        return base + (1.0 - base) * (1.0 - self.intensity)

    def get_munition_dps(self) -> float:
        """Return damage per second to guided munitions inside this zone.

        Only debris zones deal structural damage. Radiation and nebula
        affect sensors/datalink but don't physically damage ordnance.

        Returns:
            float: Damage per second (0 for non-debris zones)
        """
        if self.hazard_type == HazardType.DEBRIS:
            return DEBRIS_MUNITION_DPS * self.intensity
        return 0.0

    def blocks_los(self) -> bool:
        """Whether this zone blocks sensor line-of-sight.

        Nebulae are opaque: if the LOS path between observer and target
        passes through the zone, detection fails. Radiation and debris
        are semi-transparent (they reduce quality, not block it).

        Returns:
            bool: True if zone blocks LOS
        """
        return self.hazard_type == HazardType.NEBULA

    def blocks_datalink(self) -> bool:
        """Whether this zone severs torpedo/missile datalink.

        Nebulae block EM propagation, severing the ship-to-munition
        datalink. The torpedo/missile reverts to last-known target
        state (fire-and-forget with stale data).

        Returns:
            bool: True if zone blocks datalink
        """
        return self.hazard_type == HazardType.NEBULA

    def get_state(self) -> dict:
        """Serialise zone state for telemetry/GUI rendering."""
        return {
            "zone_id": self.zone_id,
            "center": self.center,
            "radius": self.radius,
            "hazard_type": self.hazard_type.value,
            "intensity": self.intensity,
        }
