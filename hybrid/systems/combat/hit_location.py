# hybrid/systems/combat/hit_location.py
"""Hit location physics — determines WHERE a projectile strikes a ship
and what damage results from the intercept geometry.

Impact location is computed from the projectile's velocity vector relative
to the target ship's position and orientation. The hit point in ship-local
coordinates determines:
  1. Which armor section absorbs the hit (fore/aft/port/starboard/dorsal/ventral)
  2. The angle of incidence vs hull surface normal (oblique = ricochet)
  3. Which subsystem is physically nearest the penetration point
  4. Penetration depth based on velocity, mass, and armor thickness

No hit tables. No random subsystem selection. Physics determines everything.
"""

import math
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Armor section definitions — surface normals in ship-local frame
# Ship frame: +X = forward (fore), +Y = port, +Z = up (dorsal)
SECTION_NORMALS = {
    "fore":      {"x":  1.0, "y":  0.0, "z":  0.0},
    "aft":       {"x": -1.0, "y":  0.0, "z":  0.0},
    "port":      {"x":  0.0, "y":  1.0, "z":  0.0},
    "starboard": {"x":  0.0, "y": -1.0, "z":  0.0},
    "dorsal":    {"x":  0.0, "y":  0.0, "z":  1.0},
    "ventral":   {"x":  0.0, "y":  0.0, "z": -1.0},
}

# Default subsystem locations in ship-local coordinates (fraction of ship length/beam/draft)
# Used when ship class doesn't provide explicit placement data.
# Coordinates are in meters relative to ship center.
DEFAULT_SUBSYSTEM_ZONES = {
    "propulsion":   {"section": "aft",     "x_frac": -0.8, "y_frac":  0.0, "z_frac":  0.0},
    "reactor":      {"section": "aft",     "x_frac": -0.4, "y_frac":  0.0, "z_frac":  0.0},
    "rcs":          {"section": "fore",    "x_frac":  0.6, "y_frac":  0.0, "z_frac":  0.0},
    "sensors":      {"section": "fore",    "x_frac":  0.9, "y_frac":  0.0, "z_frac":  0.1},
    "weapons":      {"section": "fore",    "x_frac":  0.7, "y_frac":  0.0, "z_frac":  0.2},
    "targeting":    {"section": "fore",    "x_frac":  0.5, "y_frac":  0.0, "z_frac":  0.0},
    "life_support": {"section": "midship", "x_frac":  0.0, "y_frac":  0.0, "z_frac":  0.0},
    "radiators":    {"section": "midship", "x_frac":  0.1, "y_frac":  0.0, "z_frac":  0.3},
}

# Armor material properties — resistance factor per cm of thickness
MATERIAL_RESISTANCE = {
    "composite_cermet": 1.0,   # Standard military armor
    "steel":            0.6,   # Basic steel plating
    "titanium":         0.8,   # Lighter but weaker
    "depleted_uranium": 1.4,   # Heavy, very resistant
}

# Ricochet angle threshold (degrees from surface tangent)
# Impacts more oblique than this bounce off
RICOCHET_ANGLE_DEG = 70.0

# Minimum penetration factor after oblique angle reduction
MIN_OBLIQUE_FACTOR = 0.1


@dataclass
class HitLocation:
    """Result of hit-location computation."""
    # Where the hit landed
    armor_section: str           # fore/aft/port/starboard/dorsal/ventral
    impact_point_local: Dict[str, float]  # Ship-local coordinates (meters)

    # Angle of incidence
    angle_of_incidence: float    # Degrees from surface normal (0 = head-on, 90 = glancing)
    is_ricochet: bool            # True if angle exceeds ricochet threshold

    # Armor interaction
    armor_thickness_cm: float    # Thickness at impact section
    armor_material: str          # Material type
    penetration_factor: float    # 0.0 (no pen) to 1.0+ (clean through)

    # Subsystem targeting
    nearest_subsystem: str       # Physically closest subsystem to impact point
    subsystem_distance: float    # Distance from impact to subsystem center (meters)

    # Feedback
    description: str             # Human-readable hit description


def compute_hit_location(
    projectile_velocity: Dict[str, float],
    projectile_mass: float,
    projectile_armor_pen: float,
    ship_position: Dict[str, float],
    ship_quaternion,
    ship_dimensions: Optional[Dict[str, float]],
    ship_armor: Optional[Dict],
    ship_systems: Optional[Dict],
    ship_weapon_mounts: Optional[List[Dict]],
    ship_subsystems: Optional[List[str]] = None,
    closest_point: Optional[Dict[str, float]] = None,
) -> HitLocation:
    """Compute where a projectile hits a ship based on intercept geometry.

    Uses the projectile's velocity vector relative to the ship to determine
    the impact point on the hull. The ship's orientation transforms the
    approach vector into ship-local coordinates.

    Args:
        projectile_velocity: Projectile velocity in world frame {x, y, z}
        projectile_mass: Mass of projectile in kg
        projectile_armor_pen: Base armor penetration rating
        ship_position: Ship center position in world frame
        ship_quaternion: Ship's orientation quaternion
        ship_dimensions: Ship dimensions {length_m, beam_m, draft_m}
        ship_armor: Armor sections dict {section: {thickness_cm, material}}
        ship_systems: Ship systems config (for placement data)
        ship_weapon_mounts: Weapon mount definitions (for placement data)
        ship_subsystems: List of subsystem names on this ship
        closest_point: Closest approach point on projectile path (world frame)

    Returns:
        HitLocation with all computed impact data
    """
    # Get ship dimensions (fall back to reasonable defaults)
    dims = ship_dimensions or {"length_m": 20.0, "beam_m": 6.0, "draft_m": 4.0}
    half_length = dims.get("length_m", 20.0) / 2.0
    half_beam = dims.get("beam_m", 6.0) / 2.0
    half_draft = dims.get("draft_m", 4.0) / 2.0

    # Transform projectile velocity into ship-local frame
    approach_local = _world_to_ship_frame(projectile_velocity, ship_quaternion)

    # Use closest approach point for more accurate impact location
    impact_offset_world = None
    if closest_point:
        impact_offset_world = {
            "x": closest_point["x"] - ship_position["x"],
            "y": closest_point["y"] - ship_position["y"],
            "z": closest_point["z"] - ship_position["z"],
        }

    # Determine impact point on hull surface
    impact_local = _compute_impact_point(
        approach_local, half_length, half_beam, half_draft, impact_offset_world, ship_quaternion
    )

    # Determine which armor section was hit
    section = _determine_armor_section(impact_local, half_length, half_beam, half_draft)

    # Calculate angle of incidence against the section's surface normal
    section_normal = SECTION_NORMALS.get(section, {"x": 1.0, "y": 0.0, "z": 0.0})
    angle_of_incidence = _angle_between_vectors(
        _negate_vec(approach_local), section_normal
    )

    # Check for ricochet
    is_ricochet = angle_of_incidence > RICOCHET_ANGLE_DEG

    # Get armor properties at impact section
    armor_thickness = 2.0  # default cm
    armor_material = "composite_cermet"
    if ship_armor and section in ship_armor:
        section_armor = ship_armor[section]
        if isinstance(section_armor, dict):
            armor_thickness = section_armor.get("thickness_cm", 2.0)
            armor_material = section_armor.get("material", "composite_cermet")

    # Calculate penetration
    penetration_factor = _calculate_penetration(
        projectile_velocity, projectile_mass, projectile_armor_pen,
        armor_thickness, armor_material, angle_of_incidence, is_ricochet
    )

    # Find nearest subsystem to impact point
    subsystem_positions = _build_subsystem_positions(
        dims, ship_systems, ship_weapon_mounts, ship_subsystems
    )
    nearest_sub, sub_distance = _find_nearest_subsystem(
        impact_local, subsystem_positions
    )

    # Generate human-readable description
    description = _generate_hit_description(
        section, angle_of_incidence, is_ricochet,
        penetration_factor, nearest_sub, armor_thickness
    )

    return HitLocation(
        armor_section=section,
        impact_point_local=impact_local,
        angle_of_incidence=angle_of_incidence,
        is_ricochet=is_ricochet,
        armor_thickness_cm=armor_thickness,
        armor_material=armor_material,
        penetration_factor=penetration_factor,
        nearest_subsystem=nearest_sub,
        subsystem_distance=sub_distance,
        description=description,
    )


def _world_to_ship_frame(
    world_vec: Dict[str, float], quaternion
) -> Dict[str, float]:
    """Transform a world-frame vector into ship-local frame.

    Args:
        world_vec: Vector in world coordinates {x, y, z}
        quaternion: Ship's orientation quaternion

    Returns:
        Vector in ship-local coordinates {x, y, z}
    """
    if quaternion is None:
        return dict(world_vec)

    try:
        # Inverse rotation: world → ship frame
        conj = quaternion.conjugate()
        result = conj.rotate_vector((world_vec["x"], world_vec["y"], world_vec["z"]))
        return {"x": float(result[0]), "y": float(result[1]), "z": float(result[2])}
    except Exception:
        return dict(world_vec)


def _compute_impact_point(
    approach_local: Dict[str, float],
    half_length: float,
    half_beam: float,
    half_draft: float,
    impact_offset_world: Optional[Dict[str, float]] = None,
    quaternion=None,
) -> Dict[str, float]:
    """Compute where the projectile hits the hull surface.

    Ray-traces from the approach direction to find the hull intersection
    point, treating the ship as an axis-aligned box in ship-local frame.

    Args:
        approach_local: Approach vector in ship frame
        half_length: Half ship length (X axis)
        half_beam: Half ship beam (Y axis)
        half_draft: Half ship draft (Z axis)
        impact_offset_world: Offset from ship center to closest approach (world frame)
        quaternion: Ship orientation for transforming offset

    Returns:
        Impact point in ship-local coordinates
    """
    # If we have a closest-approach offset, transform it to ship frame
    if impact_offset_world and quaternion:
        offset_local = _world_to_ship_frame(impact_offset_world, quaternion)
    elif impact_offset_world:
        offset_local = dict(impact_offset_world)
    else:
        offset_local = {"x": 0.0, "y": 0.0, "z": 0.0}

    # Clamp offset to ship hull boundary (AABB)
    # This gives us the impact point on the hull surface
    impact = {
        "x": max(-half_length, min(half_length, offset_local["x"])),
        "y": max(-half_beam, min(half_beam, offset_local["y"])),
        "z": max(-half_draft, min(half_draft, offset_local["z"])),
    }

    # If offset is inside the ship (close hit), project to hull surface
    # using approach direction
    if (abs(impact["x"]) < half_length and
        abs(impact["y"]) < half_beam and
        abs(impact["z"]) < half_draft):
        impact = _project_to_hull_surface(
            impact, approach_local, half_length, half_beam, half_draft
        )

    return impact


def _project_to_hull_surface(
    point: Dict[str, float],
    direction: Dict[str, float],
    half_length: float,
    half_beam: float,
    half_draft: float,
) -> Dict[str, float]:
    """Project an interior point to the hull surface along approach direction.

    Uses ray-box intersection from outside to find which face the
    projectile would hit first.

    Args:
        point: Interior point in ship frame
        direction: Approach direction in ship frame
        half_length, half_beam, half_draft: Ship half-extents

    Returns:
        Point on hull surface
    """
    # Determine which face the projectile approaches from
    # by checking which axis component of the approach vector is dominant
    dx = abs(direction.get("x", 0))
    dy = abs(direction.get("y", 0))
    dz = abs(direction.get("z", 0))

    max_d = max(dx, dy, dz)
    if max_d < 1e-10:
        # No clear approach direction — use the closest face
        return _snap_to_nearest_face(point, half_length, half_beam, half_draft)

    # Project to the face that the projectile approaches from
    if dx == max_d:
        # Coming from fore or aft
        sign = -1.0 if direction["x"] > 0 else 1.0  # Approach from opposite side
        return {
            "x": sign * half_length,
            "y": max(-half_beam, min(half_beam, point["y"])),
            "z": max(-half_draft, min(half_draft, point["z"])),
        }
    elif dy == max_d:
        # Coming from port or starboard
        sign = -1.0 if direction["y"] > 0 else 1.0
        return {
            "x": max(-half_length, min(half_length, point["x"])),
            "y": sign * half_beam,
            "z": max(-half_draft, min(half_draft, point["z"])),
        }
    else:
        # Coming from dorsal or ventral
        sign = -1.0 if direction["z"] > 0 else 1.0
        return {
            "x": max(-half_length, min(half_length, point["x"])),
            "y": max(-half_beam, min(half_beam, point["y"])),
            "z": sign * half_draft,
        }


def _snap_to_nearest_face(
    point: Dict[str, float],
    half_length: float, half_beam: float, half_draft: float,
) -> Dict[str, float]:
    """Snap a point to the nearest face of the ship AABB."""
    # Find which face is closest
    distances = {
        "x+": half_length - point["x"],
        "x-": point["x"] + half_length,
        "y+": half_beam - point["y"],
        "y-": point["y"] + half_beam,
        "z+": half_draft - point["z"],
        "z-": point["z"] + half_draft,
    }
    nearest = min(distances, key=lambda k: abs(distances[k]))
    result = dict(point)
    if nearest == "x+":
        result["x"] = half_length
    elif nearest == "x-":
        result["x"] = -half_length
    elif nearest == "y+":
        result["y"] = half_beam
    elif nearest == "y-":
        result["y"] = -half_beam
    elif nearest == "z+":
        result["z"] = half_draft
    elif nearest == "z-":
        result["z"] = -half_draft
    return result


def _determine_armor_section(
    impact_local: Dict[str, float],
    half_length: float, half_beam: float, half_draft: float,
) -> str:
    """Determine which armor section a ship-local impact point falls on.

    Maps the impact point to one of six sections based on which face
    of the ship's bounding box it's on or closest to.

    Args:
        impact_local: Impact point in ship-local coords
        half_length, half_beam, half_draft: Ship half-extents

    Returns:
        Armor section name (fore/aft/port/starboard/dorsal/ventral)
    """
    # Normalize coordinates to [-1, 1] range relative to ship extents
    nx = impact_local["x"] / max(half_length, 0.1)
    ny = impact_local["y"] / max(half_beam, 0.1)
    nz = impact_local["z"] / max(half_draft, 0.1)

    # The dominant axis determines the section
    ax, ay, az = abs(nx), abs(ny), abs(nz)
    max_axis = max(ax, ay, az)

    if max_axis < 1e-10:
        return "fore"  # Dead center — default to fore

    if ax == max_axis:
        return "fore" if nx > 0 else "aft"
    elif ay == max_axis:
        return "port" if ny > 0 else "starboard"
    else:
        return "dorsal" if nz > 0 else "ventral"


def _angle_between_vectors(v1: Dict[str, float], v2: Dict[str, float]) -> float:
    """Compute angle in degrees between two vectors.

    Args:
        v1, v2: Vectors as {x, y, z} dicts

    Returns:
        Angle in degrees [0, 180]
    """
    dot = (v1["x"] * v2["x"] + v1["y"] * v2["y"] + v1["z"] * v2["z"])

    mag1 = math.sqrt(v1["x"]**2 + v1["y"]**2 + v1["z"]**2)
    mag2 = math.sqrt(v2["x"]**2 + v2["y"]**2 + v2["z"]**2)

    if mag1 < 1e-10 or mag2 < 1e-10:
        return 0.0

    cos_angle = max(-1.0, min(1.0, dot / (mag1 * mag2)))
    return math.degrees(math.acos(cos_angle))


def _negate_vec(v: Dict[str, float]) -> Dict[str, float]:
    """Negate a vector (reverse direction)."""
    return {"x": -v["x"], "y": -v["y"], "z": -v["z"]}


def _calculate_penetration(
    projectile_velocity: Dict[str, float],
    projectile_mass: float,
    armor_penetration: float,
    armor_thickness_cm: float,
    armor_material: str,
    angle_of_incidence: float,
    is_ricochet: bool,
) -> float:
    """Calculate penetration factor based on physics.

    Penetration depends on:
    - Kinetic energy of the projectile (½mv²)
    - Armor penetration rating of the weapon
    - Armor thickness and material resistance
    - Angle of incidence (oblique hits reduce effective penetration)

    Args:
        projectile_velocity: Velocity vector {x, y, z}
        projectile_mass: Mass in kg
        armor_penetration: Weapon's armor penetration rating
        armor_thickness_cm: Armor thickness at impact section
        armor_material: Armor material type
        angle_of_incidence: Angle from normal in degrees
        is_ricochet: Whether the hit is a ricochet

    Returns:
        Penetration factor: 0.0 = no penetration, 1.0 = clean through
    """
    if is_ricochet:
        # Ricochets still transfer some energy — glancing blow
        return MIN_OBLIQUE_FACTOR

    # Projectile speed
    speed = math.sqrt(
        projectile_velocity["x"]**2 +
        projectile_velocity["y"]**2 +
        projectile_velocity["z"]**2
    )

    # Kinetic energy factor — normalized to railgun baseline
    # Railgun: 5kg at 20km/s = 1e9 J (baseline = 1.0)
    ke = 0.5 * projectile_mass * speed * speed
    ke_factor = min(2.0, ke / 1e9)  # Cap at 2x baseline

    # Armor resistance
    material_factor = MATERIAL_RESISTANCE.get(armor_material, 1.0)
    armor_resistance = armor_thickness_cm * material_factor * 0.1

    # Oblique angle reduces effective penetration
    # At 0°: full penetration. At 60°: cos(60°)=0.5. At 70°+: ricochet
    angle_rad = math.radians(angle_of_incidence)
    oblique_factor = max(MIN_OBLIQUE_FACTOR, math.cos(angle_rad))

    # Effective penetration = weapon_pen * KE_factor * oblique / armor_resistance
    effective_pen = armor_penetration * ke_factor * oblique_factor
    if armor_resistance > 0:
        penetration = effective_pen / (effective_pen + armor_resistance)
    else:
        penetration = 1.0

    return max(0.0, min(1.5, penetration))


def _build_subsystem_positions(
    dimensions: Dict[str, float],
    systems: Optional[Dict],
    weapon_mounts: Optional[List[Dict]],
    subsystem_names: Optional[List[str]] = None,
) -> Dict[str, Dict[str, float]]:
    """Build a map of subsystem names to ship-local positions.

    Uses explicit placement data from ship class definitions when available,
    falls back to default zone positions scaled to ship dimensions.

    Args:
        dimensions: Ship dimensions {length_m, beam_m, draft_m}
        systems: Ship systems config with optional placement data
        weapon_mounts: Weapon mount definitions with placement
        subsystem_names: List of subsystem names to include

    Returns:
        Dict mapping subsystem name → position {x, y, z} in ship-local coords
    """
    half_length = dimensions.get("length_m", 20.0) / 2.0
    half_beam = dimensions.get("beam_m", 6.0) / 2.0
    half_draft = dimensions.get("draft_m", 4.0) / 2.0

    positions = {}

    # Try to get positions from systems config (explicit placement)
    if systems:
        for sys_name, sys_config in systems.items():
            if not isinstance(sys_config, dict):
                continue
            placement = sys_config.get("placement")
            if placement:
                # Handle single placement or list
                if isinstance(placement, list):
                    # Average of multiple placements (e.g. RCS thrusters)
                    avg = {"x": 0.0, "y": 0.0, "z": 0.0}
                    for p in placement:
                        pos = p.get("position", {})
                        avg["x"] += pos.get("x", 0.0)
                        avg["y"] += pos.get("y", 0.0)
                        avg["z"] += pos.get("z", 0.0)
                    n = len(placement)
                    if n > 0:
                        positions[sys_name] = {
                            "x": avg["x"] / n,
                            "y": avg["y"] / n,
                            "z": avg["z"] / n,
                        }
                elif isinstance(placement, dict):
                    pos = placement.get("position", {})
                    positions[sys_name] = {
                        "x": pos.get("x", 0.0),
                        "y": pos.get("y", 0.0),
                        "z": pos.get("z", 0.0),
                    }

    # Map system names to damage_model subsystem names
    # (e.g. "propulsion" system → "propulsion" subsystem)
    # "power" in damage model is the reactor
    if "reactor" not in positions and "propulsion" in positions:
        # Reactor is typically near but forward of propulsion
        prop_pos = positions["propulsion"]
        positions["reactor"] = {
            "x": prop_pos["x"] + half_length * 0.3,
            "y": prop_pos["y"],
            "z": prop_pos["z"],
        }

    # Add weapon mount positions as "weapons" subsystem
    if weapon_mounts and "weapons" not in positions:
        avg = {"x": 0.0, "y": 0.0, "z": 0.0}
        count = 0
        for mount in weapon_mounts:
            placement = mount.get("placement", {})
            pos = placement.get("position", {})
            avg["x"] += pos.get("x", 0.0)
            avg["y"] += pos.get("y", 0.0)
            avg["z"] += pos.get("z", 0.0)
            count += 1
        if count > 0:
            positions["weapons"] = {
                "x": avg["x"] / count,
                "y": avg["y"] / count,
                "z": avg["z"] / count,
            }

    # Fill in missing subsystems with defaults
    all_subsystems = subsystem_names or list(DEFAULT_SUBSYSTEM_ZONES.keys())
    for sub_name in all_subsystems:
        if sub_name not in positions:
            zone = DEFAULT_SUBSYSTEM_ZONES.get(sub_name)
            if zone:
                positions[sub_name] = {
                    "x": zone["x_frac"] * half_length,
                    "y": zone["y_frac"] * half_beam,
                    "z": zone["z_frac"] * half_draft,
                }
            else:
                # Unknown subsystem — place at center
                positions[sub_name] = {"x": 0.0, "y": 0.0, "z": 0.0}

    return positions


def _find_nearest_subsystem(
    impact_point: Dict[str, float],
    subsystem_positions: Dict[str, Dict[str, float]],
) -> Tuple[str, float]:
    """Find the subsystem physically closest to the impact point.

    Args:
        impact_point: Impact location in ship-local coords
        subsystem_positions: Map of subsystem name → position

    Returns:
        Tuple of (subsystem_name, distance_meters)
    """
    if not subsystem_positions:
        return "weapons", 0.0  # Fallback

    best_name = None
    best_dist = float("inf")

    for name, pos in subsystem_positions.items():
        dx = impact_point["x"] - pos["x"]
        dy = impact_point["y"] - pos["y"]
        dz = impact_point["z"] - pos["z"]
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist < best_dist:
            best_dist = dist
            best_name = name

    return best_name or "weapons", best_dist


def _generate_hit_description(
    section: str,
    angle: float,
    is_ricochet: bool,
    penetration: float,
    subsystem: str,
    armor_cm: float,
) -> str:
    """Generate human-readable hit description.

    Args:
        section: Armor section hit
        angle: Angle of incidence in degrees
        is_ricochet: Whether the hit ricocheted
        penetration: Penetration factor
        subsystem: Nearest subsystem
        armor_cm: Armor thickness at section

    Returns:
        Description string
    """
    section_label = {
        "fore": "forward hull",
        "aft": "aft hull",
        "port": "port side",
        "starboard": "starboard side",
        "dorsal": "dorsal plating",
        "ventral": "ventral plating",
    }.get(section, section)

    subsystem_label = {
        "propulsion": "drive system",
        "reactor": "reactor",
        "power": "reactor",
        "sensors": "sensor array",
        "weapons": "weapons bay",
        "rcs": "RCS cluster",
        "radiators": "radiator panel",
        "life_support": "life support",
        "targeting": "targeting computer",
    }.get(subsystem, subsystem)

    if is_ricochet:
        return (
            f"Glancing blow — slug struck {section_label} at {angle:.0f}° "
            f"and ricocheted off {armor_cm:.1f}cm armor"
        )

    if penetration < 0.3:
        return (
            f"Partial penetration — slug hit {section_label} at {angle:.0f}°, "
            f"{armor_cm:.1f}cm armor absorbed most of the impact"
        )

    if penetration < 0.7:
        return (
            f"Penetration — slug punched through {section_label} "
            f"({armor_cm:.1f}cm armor, {angle:.0f}° incidence), "
            f"fragments near {subsystem_label}"
        )

    return (
        f"Clean penetration — slug pierced {section_label} "
        f"({armor_cm:.1f}cm armor, {angle:.0f}° incidence), "
        f"struck {subsystem_label}"
    )
