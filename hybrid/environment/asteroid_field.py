# hybrid/environment/asteroid_field.py
"""Asteroid field generation and collision physics.

Asteroids are inert objects distributed within a spherical region.
They drift slowly and serve as physical obstacles for ships and
projectiles. Ship collision damage scales with relative velocity --
a drifting brush is minor, a head-on at 2 km/s is lethal.

Design notes:
- Asteroids are NOT contacts on the sensor system (too numerous).
  They are environmental geometry rendered by the tactical map.
- Collision uses bounding-sphere overlap. Ships are small enough
  relative to asteroids that this is physically reasonable.
- Asteroid density is tuned for tactical gameplay, not realism.
  Real asteroid belts are absurdly sparse; ours are dense enough
  to force routing decisions.
"""

import math
import random
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from hybrid.utils.math_utils import calculate_distance, subtract_vectors, magnitude

logger = logging.getLogger(__name__)


@dataclass
class Asteroid:
    """A single asteroid with position, velocity, and physical properties."""
    id: str
    position: Dict[str, float]
    velocity: Dict[str, float]
    radius: float       # metres (10-500m)
    mass: float          # kg, derived from radius assuming ~2000 kg/m^3 rock density

    def tick(self, dt: float) -> None:
        """Advance asteroid position by its drift velocity."""
        self.position["x"] += self.velocity["x"] * dt
        self.position["y"] += self.velocity["y"] * dt
        self.position["z"] += self.velocity["z"] * dt


class AsteroidField:
    """A cluster of asteroids within a spherical region.

    Generated procedurally from a center, radius, and count.
    Each asteroid drifts slowly (0-20 m/s) to feel alive without
    making collision prediction impossible for the player.
    """

    def __init__(
        self,
        field_id: str,
        center: Dict[str, float],
        radius: float,
        count: int,
        seed: Optional[int] = None,
    ):
        """Create an asteroid field.

        Args:
            field_id: Unique identifier for this field
            center: Center position {x, y, z} in metres
            radius: Spherical region radius in metres
            count: Number of asteroids to generate
            seed: RNG seed for reproducible generation (tests, replays)
        """
        self.field_id = field_id
        self.center = dict(center)
        self.radius = radius
        self.count = count
        self.asteroids: List[Asteroid] = []

        self._generate(seed)

    def _generate(self, seed: Optional[int] = None) -> None:
        """Populate the field with randomly placed asteroids.

        Uses rejection sampling inside the bounding sphere.
        Asteroid radii follow a power-law distribution -- many small
        rocks, few large boulders -- matching real asteroid populations.
        """
        rng = random.Random(seed)

        for i in range(self.count):
            # Uniform random point inside sphere (rejection sampling)
            while True:
                x = rng.uniform(-self.radius, self.radius)
                y = rng.uniform(-self.radius, self.radius)
                z = rng.uniform(-self.radius, self.radius)
                if x * x + y * y + z * z <= self.radius * self.radius:
                    break

            pos = {
                "x": self.center["x"] + x,
                "y": self.center["y"] + y,
                "z": self.center["z"] + z,
            }

            # Slow drift: 0-20 m/s in random direction
            drift_speed = rng.uniform(0.0, 20.0)
            theta = rng.uniform(0, 2 * math.pi)
            phi = rng.uniform(-math.pi / 2, math.pi / 2)
            vel = {
                "x": drift_speed * math.cos(phi) * math.cos(theta),
                "y": drift_speed * math.sin(phi),
                "z": drift_speed * math.cos(phi) * math.sin(theta),
            }

            # Power-law radius: exponent 2.5 gives many small, few large.
            # Range: 10m (pebble) to 500m (significant obstacle).
            u = rng.random()
            asteroid_radius = 10.0 + (500.0 - 10.0) * (u ** 2.5)

            # Mass from volume * density (rocky: ~2000 kg/m^3)
            volume = (4.0 / 3.0) * math.pi * asteroid_radius ** 3
            asteroid_mass = volume * 2000.0

            self.asteroids.append(Asteroid(
                id=f"{self.field_id}_ast_{i}",
                position=pos,
                velocity=vel,
                radius=asteroid_radius,
                mass=asteroid_mass,
            ))

    def tick(self, dt: float) -> None:
        """Advance all asteroid positions."""
        for asteroid in self.asteroids:
            asteroid.tick(dt)

    def check_ship_collision(
        self, ship_position: Dict[str, float], ship_velocity: Dict[str, float],
        ship_radius: float = 25.0,
    ) -> Optional[Tuple[Asteroid, float]]:
        """Check if a ship overlaps any asteroid this tick.

        Uses bounding-sphere intersection: ship sphere vs asteroid sphere.
        Returns the first collision found with the relative impact speed,
        which determines hull damage.

        Args:
            ship_position: Ship center {x, y, z}
            ship_velocity: Ship velocity {x, y, z} (for damage calculation)
            ship_radius: Ship bounding sphere radius (metres)

        Returns:
            (asteroid, relative_speed) if collision, None otherwise
        """
        for asteroid in self.asteroids:
            dist = calculate_distance(ship_position, asteroid.position)
            collision_dist = ship_radius + asteroid.radius

            if dist <= collision_dist:
                # Relative velocity for damage scaling
                rel_vel = subtract_vectors(ship_velocity, asteroid.velocity)
                rel_speed = magnitude(rel_vel)
                return (asteroid, rel_speed)

        return None

    def check_projectile_obstruction(
        self,
        old_pos: Dict[str, float],
        new_pos: Dict[str, float],
    ) -> Optional[Asteroid]:
        """Check if a projectile path intersects any asteroid.

        Uses closest-approach-on-segment, same math as the projectile
        manager's ship intercept check. A railgun slug that passes
        through an asteroid is absorbed -- hard sci-fi, rocks are
        opaque to kinetic impactors.

        Args:
            old_pos: Projectile position at start of tick
            new_pos: Projectile position at end of tick

        Returns:
            The obstructing Asteroid, or None
        """
        seg = {
            "x": new_pos["x"] - old_pos["x"],
            "y": new_pos["y"] - old_pos["y"],
            "z": new_pos["z"] - old_pos["z"],
        }
        seg_len_sq = seg["x"] ** 2 + seg["y"] ** 2 + seg["z"] ** 2

        for asteroid in self.asteroids:
            to_ast = {
                "x": asteroid.position["x"] - old_pos["x"],
                "y": asteroid.position["y"] - old_pos["y"],
                "z": asteroid.position["z"] - old_pos["z"],
            }

            if seg_len_sq < 1e-10:
                dist = calculate_distance(new_pos, asteroid.position)
            else:
                t = (
                    to_ast["x"] * seg["x"]
                    + to_ast["y"] * seg["y"]
                    + to_ast["z"] * seg["z"]
                ) / seg_len_sq
                t = max(0.0, min(1.0, t))

                closest = {
                    "x": old_pos["x"] + seg["x"] * t,
                    "y": old_pos["y"] + seg["y"] * t,
                    "z": old_pos["z"] + seg["z"] * t,
                }
                dist = calculate_distance(closest, asteroid.position)

            if dist <= asteroid.radius:
                return asteroid

        return None

    def get_state(self) -> dict:
        """Serialise field state for telemetry/GUI rendering."""
        return {
            "field_id": self.field_id,
            "center": self.center,
            "radius": self.radius,
            "count": len(self.asteroids),
            "asteroids": [
                {
                    "id": a.id,
                    "position": a.position,
                    "radius": a.radius,
                }
                for a in self.asteroids
            ],
        }
