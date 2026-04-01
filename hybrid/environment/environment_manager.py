# hybrid/environment/environment_manager.py
"""Central manager for all environmental hazards in a scenario.

Ticked once per simulation step by the Simulator.  Provides query
methods used by the projectile manager, torpedo manager, and sensor
system to check how the environment affects their domain.

Kept lightweight: the manager is a container and query facade,
not a physics engine.  Individual AsteroidField and HazardZone
objects own their own physics.
"""

import logging
from typing import Dict, List, Optional, Tuple

from hybrid.environment.asteroid_field import AsteroidField, Asteroid
from hybrid.environment.hazard_zone import HazardZone, HazardType
from hybrid.utils.math_utils import calculate_distance

logger = logging.getLogger(__name__)


class EnvironmentManager:
    """Holds all environmental hazards and provides query methods.

    Integration points:
    - Simulator.tick() calls env_manager.tick() and check_ship_collisions()
    - ProjectileManager.tick() calls env_manager.check_projectile_obstruction()
    - TorpedoManager.tick() calls env_manager.check_torpedo_degradation()
    - PassiveSensor.update() calls env_manager.get_sensor_modifier()
    """

    def __init__(self):
        self.asteroid_fields: List[AsteroidField] = []
        self.hazard_zones: List[HazardZone] = []

    def tick(self, dt: float) -> None:
        """Advance all environmental objects (asteroid drift)."""
        for af in self.asteroid_fields:
            af.tick(dt)

    def load_from_scenario(self, env_data: dict) -> None:
        """Parse the `environment:` section of a scenario YAML.

        Expected schema:
            environment:
              asteroid_fields:
                - id: "belt_alpha"
                  center: {x: 50000, y: 0, z: 0}
                  radius: 20000
                  count: 80
                  seed: 42
              hazard_zones:
                - id: "rad_zone_1"
                  center: {x: -30000, y: 0, z: 10000}
                  radius: 15000
                  type: "radiation"
                  intensity: 0.8

        Args:
            env_data: Dict from scenario YAML `environment:` key
        """
        if not env_data:
            return

        for af_data in env_data.get("asteroid_fields", []):
            try:
                af = AsteroidField(
                    field_id=af_data.get("id", "field"),
                    center=af_data.get("center", {"x": 0, "y": 0, "z": 0}),
                    radius=af_data.get("radius", 10000),
                    count=af_data.get("count", 50),
                    seed=af_data.get("seed"),
                )
                self.asteroid_fields.append(af)
                logger.info(
                    "Loaded asteroid field '%s': %d asteroids in %.0f m radius",
                    af.field_id, len(af.asteroids), af.radius,
                )
            except Exception as e:
                logger.error("Failed to load asteroid field: %s", e)

        for hz_data in env_data.get("hazard_zones", []):
            try:
                hz = HazardZone(
                    zone_id=hz_data.get("id", "zone"),
                    center=hz_data.get("center", {"x": 0, "y": 0, "z": 0}),
                    radius=hz_data.get("radius", 10000),
                    hazard_type=hz_data.get("type", "debris"),
                    intensity=hz_data.get("intensity", 1.0),
                )
                self.hazard_zones.append(hz)
                logger.info(
                    "Loaded hazard zone '%s': %s, %.0f m radius, intensity %.1f",
                    hz.zone_id, hz.hazard_type.value, hz.radius, hz.intensity,
                )
            except Exception as e:
                logger.error("Failed to load hazard zone: %s", e)

    # ---- Ship collision queries ----

    def check_ship_collisions(
        self, ships: list, dt: float, event_bus=None,
    ) -> List[dict]:
        """Check all ships against all asteroid fields for collisions.

        Damage scales with relative impact speed:
        - < 10 m/s: negligible scrape
        - 10-100 m/s: minor hull damage (5-50)
        - 100-1000 m/s: major hull damage (50-500)
        - > 1000 m/s: catastrophic (500+)

        Args:
            ships: List of Ship objects
            dt: Tick timestep (unused but reserved for swept checks)
            event_bus: Optional EventBus for publishing collision events

        Returns:
            List of collision event dicts
        """
        events = []

        for ship in ships:
            ship_radius = self._get_ship_radius(ship)

            for af in self.asteroid_fields:
                result = af.check_ship_collision(
                    ship.position, ship.velocity, ship_radius
                )
                if result is None:
                    continue

                asteroid, rel_speed = result

                # Damage scales linearly with relative speed (simplified model).
                # At 100 m/s, ~50 hull damage; at 1 km/s, ~500 hull damage.
                hull_damage = rel_speed * 0.5

                if hull_damage < 1.0:
                    continue  # Negligible brush

                # Apply damage to ship
                if hasattr(ship, "take_damage"):
                    ship.take_damage(
                        hull_damage,
                        source=f"asteroid:{asteroid.id}",
                    )

                event = {
                    "type": "asteroid_collision",
                    "ship_id": ship.id,
                    "asteroid_id": asteroid.id,
                    "relative_speed": rel_speed,
                    "hull_damage": hull_damage,
                    "asteroid_radius": asteroid.radius,
                }
                events.append(event)

                if event_bus:
                    event_bus.publish("asteroid_collision", event)

                logger.info(
                    "Ship %s collided with asteroid %s at %.0f m/s, %.0f damage",
                    ship.id, asteroid.id, rel_speed, hull_damage,
                )

        return events

    # ---- Projectile obstruction queries ----

    def check_projectile_obstruction(
        self, old_pos: Dict[str, float], new_pos: Dict[str, float],
    ) -> Optional[Asteroid]:
        """Check if a projectile path is blocked by any asteroid.

        Called by ProjectileManager for each projectile each tick.

        Args:
            old_pos: Projectile start position this tick
            new_pos: Projectile end position this tick

        Returns:
            The obstructing Asteroid, or None
        """
        for af in self.asteroid_fields:
            hit = af.check_projectile_obstruction(old_pos, new_pos)
            if hit is not None:
                return hit
        return None

    # ---- Torpedo/missile degradation queries ----

    def check_torpedo_degradation(
        self, position: Dict[str, float], dt: float,
    ) -> Tuple[float, bool]:
        """Check environmental effects on a torpedo/missile at a position.

        Returns accumulated damage and whether datalink is severed.

        Args:
            position: Munition position {x, y, z}
            dt: Tick timestep for damage-per-second calculation

        Returns:
            (damage_this_tick, datalink_blocked)
        """
        total_damage = 0.0
        datalink_blocked = False

        for hz in self.hazard_zones:
            if not hz.contains(position):
                continue

            # Debris zones deal structural damage
            dps = hz.get_munition_dps()
            if dps > 0:
                total_damage += dps * dt

            # Nebulae sever datalink
            if hz.blocks_datalink():
                datalink_blocked = True

        return (total_damage, datalink_blocked)

    # ---- Sensor modifier queries ----

    def get_sensor_modifier(self, position: Dict[str, float]) -> float:
        """Get the combined sensor range multiplier at a position.

        If the observer is inside multiple zones, the most severe
        modifier wins (minimum). This prevents stacking radiation
        zones to get below-zero detection.

        Args:
            position: Observer position {x, y, z}

        Returns:
            float: Multiplier for passive sensor range (0.0-1.0)
        """
        worst_modifier = 1.0

        for hz in self.hazard_zones:
            if hz.contains(position):
                mod = hz.get_sensor_modifier()
                worst_modifier = min(worst_modifier, mod)

        return worst_modifier

    def check_los_blocked(
        self,
        pos_a: Dict[str, float],
        pos_b: Dict[str, float],
    ) -> bool:
        """Check if line-of-sight between two positions is blocked by a nebula.

        Uses sphere-segment intersection: if the LOS line passes within
        the nebula's radius of its center, LOS is blocked.

        Args:
            pos_a: First position {x, y, z}
            pos_b: Second position {x, y, z}

        Returns:
            True if any nebula blocks the LOS
        """
        for hz in self.hazard_zones:
            if not hz.blocks_los():
                continue

            # Closest point on segment A->B to zone center
            seg = {
                "x": pos_b["x"] - pos_a["x"],
                "y": pos_b["y"] - pos_a["y"],
                "z": pos_b["z"] - pos_a["z"],
            }
            seg_len_sq = seg["x"] ** 2 + seg["y"] ** 2 + seg["z"] ** 2

            if seg_len_sq < 1e-10:
                # A and B are coincident -- just check if inside
                if hz.contains(pos_a):
                    return True
                continue

            to_center = {
                "x": hz.center["x"] - pos_a["x"],
                "y": hz.center["y"] - pos_a["y"],
                "z": hz.center["z"] - pos_a["z"],
            }
            t = (
                to_center["x"] * seg["x"]
                + to_center["y"] * seg["y"]
                + to_center["z"] * seg["z"]
            ) / seg_len_sq
            t = max(0.0, min(1.0, t))

            closest = {
                "x": pos_a["x"] + seg["x"] * t,
                "y": pos_a["y"] + seg["y"] * t,
                "z": pos_a["z"] + seg["z"] * t,
            }
            dist = calculate_distance(closest, hz.center)

            if dist <= hz.radius:
                return True

        return False

    # ---- Telemetry ----

    def get_state(self) -> dict:
        """Serialise full environment state for GUI rendering."""
        return {
            "asteroid_fields": [af.get_state() for af in self.asteroid_fields],
            "hazard_zones": [hz.get_state() for hz in self.hazard_zones],
        }

    def clear(self) -> None:
        """Remove all environmental objects."""
        self.asteroid_fields.clear()
        self.hazard_zones.clear()

    @staticmethod
    def _get_ship_radius(ship) -> float:
        """Estimate ship bounding sphere from dimensions, with 25m floor."""
        dims = getattr(ship, "dimensions", None)
        if dims and isinstance(dims, dict):
            length = dims.get("length_m", 0)
            beam = dims.get("beam_m", 0)
            draft = dims.get("draft_m", 0)
            max_dim = max(length, beam, draft)
            if max_dim > 0:
                return max(max_dim / 2.0, 15.0)
        return 25.0
