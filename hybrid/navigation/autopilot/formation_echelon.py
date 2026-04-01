# hybrid/navigation/autopilot/formation_echelon.py
"""Echelon formation autopilot with collision avoidance.

Extends the base FormationAutopilot with awareness of adjacent ships
to maintain proper spacing in diagonal echelon formations.  When an
adjacent ship gets too close, a repulsion vector blends into the
thrust heading to push the ship away.
"""

import logging
from typing import Dict, Optional

import numpy as np

from hybrid.navigation.autopilot.formation import FormationAutopilot
from hybrid.navigation.relative_motion import vector_to_heading

logger = logging.getLogger(__name__)


class EchelonFormationAutopilot(FormationAutopilot):
    """Specialized formation autopilot for echelon formations.

    Provides additional awareness of adjacent ships to maintain proper spacing.
    """

    def __init__(
        self,
        ship,
        target_id: Optional[str] = None,
        params: Optional[Dict] = None,
    ):
        """Initialize echelon formation autopilot.

        Args:
            ship: Ship under control.
            target_id: Flagship ID to follow.
            params: Formation parameters plus:
                - adjacent_ships: List of adjacent ship IDs.
                - min_separation: Minimum distance to adjacent ships (m),
                  default 500.0.
        """
        super().__init__(ship, target_id, params)

        self.adjacent_ships = (params or {}).get("adjacent_ships", [])
        self.min_separation = float((params or {}).get("min_separation", 500.0))

    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute thrust with collision avoidance for adjacent ships."""
        base_command = super().compute(dt, sim_time)
        if not base_command:
            return None

        avoidance_vector = self._compute_collision_avoidance()

        if np.linalg.norm(avoidance_vector) > 0.1:
            avoidance_heading = vector_to_heading({
                "x": float(avoidance_vector[0]),
                "y": float(avoidance_vector[1]),
                "z": float(avoidance_vector[2]),
            })
            blend = 0.3
            base_yaw = base_command["heading"].get("yaw", 0)
            avoid_yaw = avoidance_heading.get("yaw", 0)
            diff = avoid_yaw - base_yaw
            if diff > 180:
                diff -= 360
            if diff < -180:
                diff += 360
            blended_yaw = base_yaw + blend * diff
            base_command["heading"]["yaw"] = blended_yaw

            logger.debug("Formation: Collision avoidance active")

        return base_command

    def _compute_collision_avoidance(self) -> np.ndarray:
        """Compute avoidance vector for nearby ships.

        Sums repulsion forces from all adjacent ships that are closer
        than min_separation.  Force is inversely proportional to distance.

        Returns:
            Normalized avoidance vector, or zero vector if no avoidance needed.
        """
        avoidance = np.array([0.0, 0.0, 0.0])

        current_pos = np.array([
            self.ship.position["x"],
            self.ship.position["y"],
            self.ship.position["z"],
        ])

        all_ships = getattr(self.ship, "_all_ships_ref", [])
        ship_map = {getattr(s, "id", None): s for s in all_ships}

        for ship_id in self.adjacent_ships:
            adjacent = ship_map.get(ship_id)
            if not adjacent:
                continue

            adjacent_pos = np.array([
                adjacent.position["x"],
                adjacent.position["y"],
                adjacent.position["z"],
            ])

            separation = current_pos - adjacent_pos
            distance = float(np.linalg.norm(separation))

            if 0 < distance < self.min_separation:
                force = (self.min_separation - distance) / self.min_separation
                avoidance += (separation / distance) * force

        avoidance_mag = float(np.linalg.norm(avoidance))
        if avoidance_mag > 0:
            avoidance = avoidance / avoidance_mag

        return avoidance
