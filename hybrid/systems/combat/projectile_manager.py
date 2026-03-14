# hybrid/systems/combat/projectile_manager.py
"""Projectile manager for simulating in-flight projectiles.

Tracks fired projectiles as they travel through space, checking for
intercepts against ships each tick. This replaces instant-hit resolution
with proper ballistic simulation where projectiles have travel time.
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from hybrid.core.event_bus import EventBus
from hybrid.utils.math_utils import (
    magnitude, subtract_vectors, calculate_distance,
)

logger = logging.getLogger(__name__)

# Projectile hits within this radius of a ship center (meters)
DEFAULT_HIT_RADIUS = 50.0

# Maximum projectile lifetime before expiry (seconds)
MAX_PROJECTILE_LIFETIME = 60.0


@dataclass
class Projectile:
    """A projectile in flight."""
    id: str
    weapon_name: str
    weapon_mount: str
    shooter_id: str
    target_id: Optional[str]
    target_subsystem: Optional[str]

    # Kinematics
    position: Dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0, "z": 0})
    velocity: Dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0, "z": 0})

    # Properties
    damage: float = 10.0
    subsystem_damage: float = 5.0
    hit_probability: float = 0.5
    hit_radius: float = DEFAULT_HIT_RADIUS

    # Tracking
    spawn_time: float = 0.0
    lifetime: float = MAX_PROJECTILE_LIFETIME
    alive: bool = True


class ProjectileManager:
    """Manages in-flight projectiles and checks for intercepts.

    Each tick:
    1. Advance all projectile positions by velocity * dt
    2. Check each projectile against all ships for intercepts
    3. Apply damage on hit, remove expired projectiles
    """

    def __init__(self):
        self._projectiles: List[Projectile] = []
        self._next_id = 1
        self._event_bus = EventBus.get_instance()

    @property
    def active_count(self) -> int:
        """Number of projectiles currently in flight."""
        return len(self._projectiles)

    def spawn(
        self,
        weapon_name: str,
        weapon_mount: str,
        shooter_id: str,
        position: Dict[str, float],
        velocity: Dict[str, float],
        damage: float,
        subsystem_damage: float,
        hit_probability: float,
        sim_time: float,
        target_id: Optional[str] = None,
        target_subsystem: Optional[str] = None,
        hit_radius: float = DEFAULT_HIT_RADIUS,
    ) -> Projectile:
        """Spawn a new projectile.

        Args:
            weapon_name: Name of the weapon that fired
            weapon_mount: Mount ID (e.g. "railgun_1")
            shooter_id: Ship ID that fired
            position: Launch position {x, y, z}
            velocity: Projectile velocity in world frame {x, y, z}
            damage: Hull damage on hit
            subsystem_damage: Subsystem damage on hit
            hit_probability: Pre-rolled probability (used for hit check on intercept)
            sim_time: Current simulation time
            target_id: Intended target (for events)
            target_subsystem: Intended subsystem target
            hit_radius: Intercept distance threshold

        Returns:
            The spawned Projectile
        """
        proj = Projectile(
            id=f"proj_{self._next_id}",
            weapon_name=weapon_name,
            weapon_mount=weapon_mount,
            shooter_id=shooter_id,
            target_id=target_id,
            target_subsystem=target_subsystem,
            position=dict(position),
            velocity=dict(velocity),
            damage=damage,
            subsystem_damage=subsystem_damage,
            hit_probability=hit_probability,
            hit_radius=hit_radius,
            spawn_time=sim_time,
        )
        self._next_id += 1
        self._projectiles.append(proj)

        self._event_bus.publish("projectile_spawned", {
            "projectile_id": proj.id,
            "weapon": weapon_name,
            "shooter": shooter_id,
            "target": target_id,
            "position": proj.position,
        })

        return proj

    def tick(self, dt: float, sim_time: float, ships: dict) -> List[dict]:
        """Advance all projectiles and check for intercepts.

        Args:
            dt: Time step in seconds
            sim_time: Current simulation time
            ships: Dict of ship_id -> Ship objects

        Returns:
            List of intercept event dicts
        """
        events = []
        surviving = []

        for proj in self._projectiles:
            if not proj.alive:
                continue

            # Check lifetime
            age = sim_time - proj.spawn_time
            if age > proj.lifetime:
                proj.alive = False
                continue

            # Advance position
            proj.position["x"] += proj.velocity["x"] * dt
            proj.position["y"] += proj.velocity["y"] * dt
            proj.position["z"] += proj.velocity["z"] * dt

            # Check for intercepts against all ships (except shooter)
            hit_ship = self._check_intercepts(proj, ships)

            if hit_ship:
                event = self._apply_hit(proj, hit_ship, sim_time)
                events.append(event)
                proj.alive = False
            else:
                surviving.append(proj)

        self._projectiles = surviving
        return events

    def _check_intercepts(self, proj: Projectile, ships: dict):
        """Check if projectile is within hit radius of any ship.

        Uses closest-approach check: if the projectile passed through
        the ship's hit sphere during this tick, it counts as a hit.

        Args:
            proj: Projectile to check
            ships: Dict of ship_id -> Ship

        Returns:
            Ship object if intercepted, None otherwise
        """
        for ship_id, ship in ships.items():
            # Don't hit shooter
            if ship_id == proj.shooter_id:
                continue

            dist = calculate_distance(proj.position, ship.position)

            if dist <= proj.hit_radius:
                return ship

        return None

    def _apply_hit(self, proj: Projectile, target_ship, sim_time: float) -> dict:
        """Apply projectile hit to target ship.

        Args:
            proj: Projectile that hit
            target_ship: Ship that was hit
            sim_time: Current simulation time

        Returns:
            Hit event dict
        """
        import random

        # Use pre-rolled hit probability
        hit_roll = random.random()
        actual_hit = hit_roll < proj.hit_probability

        damage_result = None
        if actual_hit and hasattr(target_ship, "take_damage"):
            damage_result = target_ship.take_damage(
                proj.damage,
                source=f"{proj.shooter_id}:{proj.weapon_name}",
                target_subsystem=proj.target_subsystem,
            )

        event = {
            "type": "projectile_impact",
            "projectile_id": proj.id,
            "weapon": proj.weapon_name,
            "shooter": proj.shooter_id,
            "target": target_ship.id,
            "hit": actual_hit,
            "damage": proj.damage if actual_hit else 0,
            "sim_time": sim_time,
            "flight_time": sim_time - proj.spawn_time,
            "damage_result": damage_result,
        }

        self._event_bus.publish("projectile_impact", event)
        return event

    def get_state(self) -> List[dict]:
        """Get state of all active projectiles for telemetry.

        Returns:
            List of projectile state dicts
        """
        return [
            {
                "id": p.id,
                "weapon": p.weapon_name,
                "shooter": p.shooter_id,
                "target": p.target_id,
                "position": p.position,
                "velocity": p.velocity,
                "alive": p.alive,
            }
            for p in self._projectiles
            if p.alive
        ]

    def clear(self):
        """Remove all projectiles."""
        self._projectiles.clear()
