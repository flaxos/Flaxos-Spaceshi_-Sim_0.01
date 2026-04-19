# hybrid/systems/combat/projectile_manager.py
"""Projectile manager for simulating in-flight projectiles.

Tracks fired projectiles as they travel through space, checking for
intercepts against ships each tick. Railgun slugs are unguided
Newtonian projectiles — straight-line trajectories where hit/miss
is determined by firing solution accuracy, not RNG.

Intercept detection uses closest-approach-during-tick to avoid
tunnelling at high projectile velocities (20 km/s railgun slugs
can travel 2 km per 0.1s tick).
"""

import math
import logging
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from hybrid.core.event_bus import EventBus
from hybrid.utils.math_utils import (
    magnitude, subtract_vectors, calculate_distance,
    dot_product,
)
from hybrid.systems.combat.hit_location import compute_hit_location, HitLocation

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

    # Projectile physical properties (for hit-location penetration physics)
    mass: float = 5.0  # kg — projectile mass
    armor_penetration: float = 1.0  # weapon armor penetration rating

    # Firing conditions snapshot (for causal feedback on impact)
    confidence: float = 0.0
    confidence_factors: Dict[str, float] = field(default_factory=dict)
    target_vel_at_fire: Dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0, "z": 0})
    target_pos_at_fire: Dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0, "z": 0})
    target_accel_at_fire: float = 0.0  # Target acceleration magnitude at fire time
    intercept_point: Dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0, "z": 0})


class ProjectileManager:
    """Manages in-flight projectiles and checks for intercepts.

    Each tick:
    1. Advance all projectile positions by velocity * dt
    2. Check each projectile against all ships using closest-approach
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
        mass: float = 5.0,
        armor_penetration: float = 1.0,
        confidence: float = 0.0,
        confidence_factors: Optional[Dict[str, float]] = None,
        target_vel_at_fire: Optional[Dict[str, float]] = None,
        target_pos_at_fire: Optional[Dict[str, float]] = None,
        target_accel_at_fire: float = 0.0,
        intercept_point: Optional[Dict[str, float]] = None,
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
            hit_probability: Pre-computed probability from firing solution
            sim_time: Current simulation time
            target_id: Intended target (for events)
            target_subsystem: Intended subsystem target
            hit_radius: Intercept distance threshold
            confidence: Firing solution confidence at launch (0-1)
            confidence_factors: Breakdown of confidence factors at launch
            target_vel_at_fire: Target velocity at fire time
            target_pos_at_fire: Target position at fire time
            target_accel_at_fire: Target accel magnitude at fire time (m/s²)
            intercept_point: Predicted intercept point at fire time

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
            mass=mass,
            armor_penetration=armor_penetration,
            confidence=confidence,
            confidence_factors=confidence_factors or {},
            target_vel_at_fire=target_vel_at_fire or {"x": 0, "y": 0, "z": 0},
            target_pos_at_fire=target_pos_at_fire or {"x": 0, "y": 0, "z": 0},
            target_accel_at_fire=target_accel_at_fire,
            intercept_point=intercept_point or {"x": 0, "y": 0, "z": 0},
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

    def tick(
        self, dt: float, sim_time: float, ships: dict,
        environment_manager=None,
    ) -> List[dict]:
        """Advance all projectiles and check for intercepts.

        Uses closest-approach-during-tick to detect hits even when
        projectile speed * dt >> hit_radius (e.g. 20km/s * 0.1s = 2km).

        Args:
            dt: Time step in seconds
            sim_time: Current simulation time
            ships: Dict of ship_id -> Ship objects
            environment_manager: Optional EnvironmentManager for asteroid
                obstruction checks.  A railgun slug that hits an asteroid
                is absorbed -- the rock is opaque to kinetic impactors.

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
                self._event_bus.publish("projectile_expired", {
                    "projectile_id": proj.id,
                    "weapon": proj.weapon_name,
                    "shooter": proj.shooter_id,
                    "target": proj.target_id,
                    "flight_time": age,
                    "confidence_at_fire": proj.confidence,
                    "feedback": (
                        f"Miss — slug expired after {age:.1f}s flight, "
                        f"solution confidence was {proj.confidence:.0%}"
                    ),
                })
                continue

            # Save pre-advance position for closest-approach check
            old_pos = dict(proj.position)

            # Advance position (Newtonian: straight line, no guidance)
            proj.position["x"] += proj.velocity["x"] * dt
            proj.position["y"] += proj.velocity["y"] * dt
            proj.position["z"] += proj.velocity["z"] * dt

            # Check asteroid obstruction before ship intercepts.
            # A slug that hits a rock never reaches the target.
            if environment_manager is not None:
                hit_asteroid = environment_manager.check_projectile_obstruction(
                    old_pos, proj.position,
                )
                if hit_asteroid is not None:
                    proj.alive = False
                    self._event_bus.publish("projectile_asteroid_impact", {
                        "projectile_id": proj.id,
                        "weapon": proj.weapon_name,
                        "shooter": proj.shooter_id,
                        "target": proj.target_id,
                        "asteroid_id": hit_asteroid.id,
                        "flight_time": age,
                        "feedback": (
                            f"Slug absorbed by asteroid {hit_asteroid.id} "
                            f"after {age:.1f}s flight"
                        ),
                    })
                    continue

            # Check for intercepts against all ships (except shooter)
            hit_ship, closest_point = self._check_intercepts(proj, old_pos, dt, ships)

            if hit_ship:
                event = self._apply_hit(proj, hit_ship, sim_time, closest_point)
                events.append(event)
                proj.alive = False
            else:
                surviving.append(proj)

        self._projectiles = surviving
        return events

    def _check_intercepts(
        self, proj: Projectile, old_pos: dict, dt: float, ships: dict
    ):
        """Check if projectile passed within hit radius of any ship this tick.

        Uses closest-approach-during-segment math: given the projectile's
        line segment from old_pos to new pos, find the point on that segment
        closest to each ship and check distance.

        This prevents tunnelling where a 20 km/s slug passes through a
        50m hit sphere in a single 0.1s tick (2 km travel).

        Args:
            proj: Projectile to check
            old_pos: Position at start of tick
            dt: Time step
            ships: Dict of ship_id -> Ship

        Returns:
            Tuple of (Ship, closest_point) if intercepted, (None, None) otherwise.
            closest_point is the point on the projectile path nearest the ship.
        """
        # Segment vector: old_pos -> new_pos
        seg = {
            "x": proj.position["x"] - old_pos["x"],
            "y": proj.position["y"] - old_pos["y"],
            "z": proj.position["z"] - old_pos["z"],
        }
        seg_len_sq = seg["x"]**2 + seg["y"]**2 + seg["z"]**2

        best_ship = None
        best_dist = float('inf')
        best_closest = None

        for ship_id, ship in ships.items():
            # Don't hit shooter
            if ship_id == proj.shooter_id:
                continue

            # Vector from segment start to ship
            to_ship = {
                "x": ship.position["x"] - old_pos["x"],
                "y": ship.position["y"] - old_pos["y"],
                "z": ship.position["z"] - old_pos["z"],
            }

            if seg_len_sq < 1e-10:
                # Projectile barely moved — just check endpoint distance
                dist = calculate_distance(proj.position, ship.position)
                closest = dict(proj.position)
            else:
                # Project ship position onto segment, clamped to [0, 1]
                t = (
                    to_ship["x"] * seg["x"] +
                    to_ship["y"] * seg["y"] +
                    to_ship["z"] * seg["z"]
                ) / seg_len_sq
                t = max(0.0, min(1.0, t))

                # Closest point on segment
                closest = {
                    "x": old_pos["x"] + seg["x"] * t,
                    "y": old_pos["y"] + seg["y"] * t,
                    "z": old_pos["z"] + seg["z"] * t,
                }
                dist = calculate_distance(closest, ship.position)

            ship_radius = self._get_ship_hit_radius(ship)
            effective_radius = max(proj.hit_radius, ship_radius)
            if dist <= effective_radius and dist < best_dist:
                best_dist = dist
                best_ship = ship
                best_closest = closest

        return best_ship, best_closest

    def _get_ship_hit_radius(self, ship) -> float:
        """Calculate hit radius from ship dimensions.

        Bigger ships are easier to hit. Uses the largest dimension / 2
        as the hit sphere radius, with a floor of 15m for tiny objects.
        Falls back to DEFAULT_HIT_RADIUS when no dimensions exist.
        """
        dims = getattr(ship, 'dimensions', None)
        if dims and isinstance(dims, dict):
            length = dims.get('length_m', 0)
            beam = dims.get('beam_m', 0)
            draft = dims.get('draft_m', 0)
            max_dim = max(length, beam, draft)
            if max_dim > 0:
                return max(max_dim / 2.0, 15.0)
        return DEFAULT_HIT_RADIUS

    def _apply_hit(
        self, proj: Projectile, target_ship, sim_time: float,
        closest_point: Optional[Dict[str, float]] = None,
    ) -> dict:
        """Apply projectile hit to target ship using hit-location physics.

        Hit probability was pre-computed from the firing solution at
        launch time. On hit, the impact location is determined by the
        actual intercept geometry — slug trajectory vs ship position and
        orientation. The hit location determines which subsystem is
        affected based on physical proximity.

        Args:
            proj: Projectile that hit
            target_ship: Ship that was hit
            sim_time: Current simulation time
            closest_point: Point on projectile path nearest to ship center

        Returns:
            Hit event dict
        """
        # Use pre-computed hit probability from firing solution
        hit_roll = random.random()
        actual_hit = hit_roll < proj.hit_probability

        damage_result = None
        subsystem_hit = None
        hit_location = None

        armor_result = None
        if actual_hit and hasattr(target_ship, "take_damage"):
            # Compute hit location from intercept geometry
            hit_location = self._compute_hit_location(proj, target_ship, closest_point)

            # The hit location determines the subsystem, not random selection
            subsystem_hit = hit_location.nearest_subsystem

            # Resolve penetration through the mutable armor model when available.
            # The armor model tracks ablation so repeated PDC hits on the same
            # section eventually strip the armor and allow full penetration.
            # Falls back to static hit_location penetration for ships without
            # an armor model (backward compatibility).
            armor_model = getattr(target_ship, "armor_model", None)
            if armor_model is not None:
                armor_result = armor_model.resolve_hit(
                    section=hit_location.armor_section,
                    projectile_velocity=proj.velocity,
                    projectile_mass=proj.mass,
                    armor_penetration_rating=proj.armor_penetration,
                    angle_of_incidence=hit_location.angle_of_incidence,
                )
                pen_factor = armor_result.penetration_factor
                is_ricochet = armor_result.is_ricochet
            else:
                pen_factor = hit_location.penetration_factor
                is_ricochet = hit_location.is_ricochet

            # Ricochet: minimal damage, no subsystem damage
            if is_ricochet:
                hull_damage = proj.damage * 0.1  # Glancing blow
                sub_damage = 0.0
            else:
                hull_damage = proj.damage * pen_factor
                sub_damage = proj.subsystem_damage * pen_factor

            # Apply hull damage (without random subsystem propagation —
            # we already know exactly which subsystem is hit)
            damage_result = target_ship.take_damage(
                hull_damage,
                source=f"{proj.shooter_id}:{proj.weapon_name}",
                target_subsystem=subsystem_hit if sub_damage > 0 else None,
            )

            # Apply direct subsystem damage based on physical proximity
            if sub_damage > 0 and hasattr(target_ship, "damage_model"):
                target_ship.damage_model.apply_damage(
                    subsystem_hit, sub_damage
                )
                if damage_result:
                    damage_result["subsystem_hit"] = subsystem_hit
                    damage_result["subsystem_damage"] = sub_damage

        flight_time = sim_time - proj.spawn_time

        # Generate causal feedback — the player always knows WHY
        if hit_location and actual_hit:
            feedback = self._generate_hit_location_feedback(
                proj, target_ship, hit_location, flight_time
            )
        else:
            feedback = self._generate_causal_feedback(
                proj, target_ship, actual_hit, subsystem_hit, flight_time
            )

        # Pre-calculate true reported damage
        reported_damage = 0.0
        reported_sub_damage = 0.0
        if actual_hit:
            # pen_factor was set during armor resolution
            if locals().get("is_ricochet"):
                reported_damage = proj.damage * 0.1
                reported_sub_damage = 0.0
            else:
                reported_damage = proj.damage * locals().get("pen_factor", 1.0)
                reported_sub_damage = proj.subsystem_damage * locals().get("pen_factor", 1.0)

        event = {
            "type": "projectile_impact",
            "projectile_id": proj.id,
            "weapon": proj.weapon_name,
            "weapon_mount": proj.weapon_mount,
            "shooter": proj.shooter_id,
            "target": target_ship.id,
            "hit": actual_hit,
            "damage": reported_damage,
            "subsystem_hit": subsystem_hit,
            "subsystem_damage": reported_sub_damage,
            "sim_time": sim_time,
            "flight_time": flight_time,
            "damage_result": damage_result,
            "confidence_at_fire": proj.confidence,
            "confidence_factors": proj.confidence_factors,
            "feedback": feedback,
            # Hit location physics data
            "hit_location": {
                "armor_section": hit_location.armor_section,
                "angle_of_incidence": hit_location.angle_of_incidence,
                "is_ricochet": hit_location.is_ricochet,
                "armor_thickness_cm": hit_location.armor_thickness_cm,
                "penetration_factor": hit_location.penetration_factor,
                "nearest_subsystem": hit_location.nearest_subsystem,
                "impact_point": hit_location.impact_point_local,
            } if hit_location else None,
            # Armor ablation data (from mutable armor model)
            "armor_ablation": {
                "ablation_cm": armor_result.ablation_cm,
                "remaining_thickness_cm": armor_result.remaining_thickness_cm,
                "description": armor_result.description,
            } if armor_result else None,
        }

        self._event_bus.publish("projectile_impact", event)
        return event

    def _compute_hit_location(
        self, proj: Projectile, target_ship, closest_point: Optional[Dict[str, float]],
    ) -> HitLocation:
        """Compute hit location using intercept geometry.

        Args:
            proj: Projectile with velocity and mass
            target_ship: Ship being hit
            closest_point: Closest approach point on projectile path

        Returns:
            HitLocation with all impact data
        """
        # Get ship properties
        ship_quat = getattr(target_ship, "quaternion", None)
        ship_dims = getattr(target_ship, "dimensions", None)
        ship_armor = getattr(target_ship, "armor", None)
        ship_weapon_mounts = getattr(target_ship, "weapon_mounts", None)

        # Get raw systems config for subsystem placement data
        # _systems_config has the original JSON with placement positions;
        # target_ship.systems has loaded system objects (not useful for placement)
        ship_systems = getattr(target_ship, "_systems_config", None)

        # Get subsystem names from damage model
        subsystem_names = None
        if hasattr(target_ship, "damage_model") and hasattr(target_ship.damage_model, "subsystems"):
            subsystem_names = list(target_ship.damage_model.subsystems.keys())

        return compute_hit_location(
            projectile_velocity=proj.velocity,
            projectile_mass=proj.mass,
            projectile_armor_pen=proj.armor_penetration,
            ship_position=target_ship.position,
            ship_quaternion=ship_quat,
            ship_dimensions=ship_dims,
            ship_armor=ship_armor,
            ship_systems=ship_systems,
            ship_weapon_mounts=ship_weapon_mounts,
            ship_subsystems=subsystem_names,
            closest_point=closest_point,
        )

    def _generate_hit_location_feedback(
        self, proj: Projectile, target_ship, hit_location: HitLocation,
        flight_time: float,
    ) -> str:
        """Generate feedback incorporating hit-location physics.

        Args:
            proj: Projectile that hit
            target_ship: Ship that was hit
            hit_location: Computed hit location data
            flight_time: Slug flight time

        Returns:
            Human-readable feedback string
        """
        target_name = getattr(target_ship, "name", target_ship.id)
        feedback = f"{hit_location.description} on {target_name}"

        # Add engagement context
        if proj.confidence >= 0.8:
            feedback += f", high-confidence solution ({proj.confidence:.0%})"
        elif proj.confidence >= 0.5:
            feedback += f", moderate solution ({proj.confidence:.0%})"

        feedback += f", {flight_time:.1f}s flight time"
        return feedback

    def _generate_causal_feedback(
        self, proj: Projectile, target_ship, actual_hit: bool,
        subsystem_hit: Optional[str], flight_time: float,
    ) -> str:
        """Generate human-readable causal feedback for a projectile impact.

        Explains WHY the slug hit or missed based on physical conditions.
        The player should always understand the reason behind the outcome.

        Args:
            proj: Projectile with firing conditions snapshot
            target_ship: Ship that was intercepted
            actual_hit: Whether the slug actually connected
            subsystem_hit: Which subsystem was hit (if any)
            flight_time: Time the slug was in flight

        Returns:
            Human-readable feedback string
        """
        target_name = getattr(target_ship, "name", target_ship.id)

        if actual_hit:
            # Determine what subsystem was hit and build a descriptive message
            if subsystem_hit:
                subsystem_label = {
                    "propulsion": "drive system",
                    "power": "reactor",
                    "sensors": "sensor array",
                    "weapons": "weapons mount",
                    "rcs": "RCS thruster cluster",
                    "radiators": "radiator panel",
                    "life_support": "life support",
                    "targeting": "targeting computer",
                }.get(subsystem_hit, subsystem_hit)
                feedback = f"Hit — {subsystem_label} on {target_name}"
            else:
                feedback = f"Hit — hull strike on {target_name}"

            # Add context about the engagement quality
            if proj.confidence >= 0.8:
                feedback += f", high-confidence solution ({proj.confidence:.0%})"
            elif proj.confidence >= 0.5:
                feedback += f", moderate solution ({proj.confidence:.0%})"

            feedback += f", {flight_time:.1f}s flight time"
            return feedback

        # Miss — explain why based on firing conditions
        reasons = []

        # Check if target was maneuvering during flight
        target_accel_g = proj.target_accel_at_fire / 9.81
        if target_accel_g > 0.5:
            reasons.append(
                f"target was maneuvering at {target_accel_g:.1f}g "
                f"during {flight_time:.1f}s slug flight"
            )

        # Check confidence factors for the weakest link
        factors = proj.confidence_factors
        if factors:
            # Find the worst factor
            if factors.get("track_quality", 1.0) < 0.5:
                reasons.append("degraded sensor track quality")
            if factors.get("range_factor", 1.0) < 0.5:
                reasons.append("extreme engagement range")
            if factors.get("own_rotation", 1.0) < 0.7:
                reasons.append("ship rotation degraded aim stability")
            if factors.get("weapon_health", 1.0) < 0.7:
                reasons.append("weapon system damage reduced accuracy")

        # Check if target position diverged from prediction
        if hasattr(target_ship, "position") and proj.intercept_point:
            actual_pos = target_ship.position
            pred = proj.intercept_point
            miss_dist = math.sqrt(
                (actual_pos["x"] - pred["x"])**2 +
                (actual_pos["y"] - pred["y"])**2 +
                (actual_pos["z"] - pred["z"])**2
            )
            if miss_dist > 100:
                reasons.append(
                    f"target displaced {miss_dist:.0f}m from predicted intercept"
                )

        if not reasons:
            reasons.append(
                f"solution confidence was {proj.confidence:.0%}, "
                f"probabilistic miss over {flight_time:.1f}s flight"
            )

        feedback = f"Miss — {', '.join(reasons)}"
        return feedback

    def get_state(self) -> List[dict]:
        """Get state of all active projectiles for telemetry.

        Returns:
            List of projectile state dicts
        """
        return [
            {
                "id": p.id,
                "weapon": p.weapon_name,
                "mount": p.weapon_mount,
                "shooter": p.shooter_id,
                "target": p.target_id,
                "position": p.position,
                "velocity": p.velocity,
                "alive": p.alive,
                "age": 0.0,  # Filled by caller if needed
            }
            for p in self._projectiles
            if p.alive
        ]

    def clear(self):
        """Remove all projectiles."""
        self._projectiles.clear()
