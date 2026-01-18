# hybrid/navigation/relative_motion.py
"""Relative motion calculations for navigation and autopilot."""

import math
from typing import Dict, Optional, Tuple
from hybrid.utils.math_utils import (
    subtract_vectors, magnitude, dot_product, normalize_vector,
    scale_vector, add_vectors
)

def calculate_relative_motion(observer_ship, target_contact) -> Dict:
    """Calculate comprehensive relative motion parameters.

    Args:
        observer_ship: Observer ship object with position, velocity
        target_contact: Target contact or ship with position, velocity

    Returns:
        dict: Relative motion data including:
            - range: Distance to target (m)
            - range_rate: Closing speed (m/s, negative = closing)
            - lateral_velocity: Perpendicular drift speed (m/s)
            - relative_velocity_vector: Full relative velocity vector
            - time_to_closest_approach: Seconds until CPA (None if opening)
            - closest_approach_distance: Minimum distance at CPA (m)
            - bearing: Direction to target {yaw, pitch} (degrees)
            - aspect: Target's orientation relative to line of sight (degrees)
    """
    # Get positions and velocities
    observer_pos = observer_ship.position
    observer_vel = observer_ship.velocity

    # Handle both ship objects and contact data
    if hasattr(target_contact, 'position'):
        target_pos = target_contact.position
        target_vel = getattr(target_contact, 'velocity', {"x": 0, "y": 0, "z": 0})
    else:
        target_pos = target_contact
        target_vel = {"x": 0, "y": 0, "z": 0}

    # Relative position and velocity
    rel_pos = subtract_vectors(target_pos, observer_pos)
    rel_vel = subtract_vectors(target_vel, observer_vel)

    # Range to target
    range_to_target = magnitude(rel_pos)

    # Range rate (closing speed)
    # Positive = opening, negative = closing
    if range_to_target > 0.001:
        range_direction = normalize_vector(rel_pos)
        range_rate = dot_product(rel_vel, range_direction)
    else:
        range_rate = 0.0

    # Lateral velocity (perpendicular component)
    if range_to_target > 0.001:
        radial_component = scale_vector(range_direction, range_rate)
        lateral_vel_vector = subtract_vectors(rel_vel, radial_component)
        lateral_velocity = magnitude(lateral_vel_vector)
    else:
        lateral_velocity = magnitude(rel_vel)

    # Time to closest approach and CPA distance
    time_to_cpa = None
    cpa_distance = None

    if range_rate < -0.001:  # Closing
        # Calculate when range rate becomes zero
        # Using quadratic formula for distance over time
        rel_vel_mag_sq = magnitude(rel_vel) ** 2
        if rel_vel_mag_sq > 0.001:
            time_to_cpa = -dot_product(rel_pos, rel_vel) / rel_vel_mag_sq

            if time_to_cpa > 0:
                # Calculate position at CPA
                future_rel_pos = add_vectors(
                    rel_pos,
                    scale_vector(rel_vel, time_to_cpa)
                )
                cpa_distance = magnitude(future_rel_pos)
            else:
                time_to_cpa = None

    # Bearing to target (in observer's reference frame)
    from hybrid.utils.math_utils import calculate_bearing
    bearing = calculate_bearing(observer_pos, target_pos, observer_ship.orientation)

    # Aspect angle (target's orientation relative to line of sight)
    # Only available if target has orientation
    aspect = None
    if hasattr(target_contact, 'orientation'):
        # Calculate line of sight from target back to observer
        los_to_observer = subtract_vectors(observer_pos, target_pos)
        if magnitude(los_to_observer) > 0.001:
            # Target's heading vs line to observer
            target_heading_rad = math.radians(target_contact.orientation.get('yaw', 0))
            los_angle = math.atan2(los_to_observer['y'], los_to_observer['x'])
            aspect = math.degrees(target_heading_rad - los_angle)

            # Normalize to [-180, 180]
            while aspect > 180:
                aspect -= 360
            while aspect < -180:
                aspect += 360

    return {
        "range": range_to_target,
        "range_rate": range_rate,
        "lateral_velocity": lateral_velocity,
        "relative_velocity_vector": rel_vel,
        "relative_velocity_magnitude": magnitude(rel_vel),
        "time_to_closest_approach": time_to_cpa,
        "closest_approach_distance": cpa_distance,
        "bearing": bearing,
        "aspect": aspect,
        "closing": range_rate < 0
    }

def calculate_intercept_time(observer_ship, target_contact, max_acceleration: float = None) -> Optional[float]:
    """Estimate time to intercept using simplified proportional navigation.

    Args:
        observer_ship: Observer ship
        target_contact: Target to intercept
        max_acceleration: Maximum acceleration available (m/s²)

    Returns:
        float: Estimated intercept time in seconds, or None if impossible
    """
    rel_motion = calculate_relative_motion(observer_ship, target_contact)

    # Simple estimate: range / relative_velocity
    rel_vel_mag = rel_motion["relative_velocity_magnitude"]

    if rel_vel_mag < 0.1:
        # Target stationary relative to us, use constant acceleration estimate
        if max_acceleration and max_acceleration > 0:
            # t = sqrt(2 * d / a)
            return math.sqrt(2 * rel_motion["range"] / max_acceleration)
        return None

    # Basic estimate
    return rel_motion["range"] / rel_vel_mag

def calculate_intercept_point(observer_ship, target_contact, intercept_time: float = None) -> Dict[str, float]:
    """Calculate predicted intercept point.

    Args:
        observer_ship: Observer ship
        target_contact: Target to intercept
        intercept_time: Time to intercept (calculated if not provided)

    Returns:
        dict: Predicted intercept position {x, y, z}
    """
    if intercept_time is None:
        intercept_time = calculate_intercept_time(observer_ship, target_contact)
        if intercept_time is None:
            # Can't calculate intercept, return current target position
            return target_contact.position if hasattr(target_contact, 'position') else target_contact

    # Predict target position at intercept time
    target_pos = target_contact.position if hasattr(target_contact, 'position') else target_contact
    target_vel = getattr(target_contact, 'velocity', {"x": 0, "y": 0, "z": 0})

    return add_vectors(target_pos, scale_vector(target_vel, intercept_time))

def calculate_required_burn(observer_ship, target_velocity: Dict[str, float]) -> Dict:
    """Calculate required burn to match a target velocity.

    Args:
        observer_ship: Observer ship
        target_velocity: Desired velocity vector

    Returns:
        dict: Burn information including:
            - delta_v: Required delta-v magnitude (m/s)
            - delta_v_vector: Required delta-v vector
            - burn_direction: Unit vector of burn direction
            - duration: Estimated burn duration (s) if max_accel available
    """
    current_vel = observer_ship.velocity
    delta_v_vector = subtract_vectors(target_velocity, current_vel)
    delta_v_magnitude = magnitude(delta_v_vector)

    burn_direction = normalize_vector(delta_v_vector) if delta_v_magnitude > 0.001 else {"x": 0, "y": 0, "z": 0}

    # Estimate burn duration if we have propulsion data
    duration = None
    propulsion = observer_ship.systems.get("propulsion")
    if propulsion and hasattr(propulsion, "max_thrust") and observer_ship.mass > 0:
        max_accel = propulsion.max_thrust / observer_ship.mass
        if max_accel > 0:
            duration = delta_v_magnitude / max_accel

    return {
        "delta_v": delta_v_magnitude,
        "delta_v_vector": delta_v_vector,
        "burn_direction": burn_direction,
        "duration": duration
    }

def calculate_approach_vector(observer_ship, target_contact, desired_range: float = 1000.0) -> Dict[str, float]:
    """Calculate vector to approach target to desired range.

    Args:
        observer_ship: Observer ship
        target_contact: Target to approach
        desired_range: Desired final range (m)

    Returns:
        dict: Approach vector {x, y, z}
    """
    rel_pos = subtract_vectors(
        target_contact.position if hasattr(target_contact, 'position') else target_contact,
        observer_ship.position
    )

    current_range = magnitude(rel_pos)

    if current_range < desired_range * 1.1:  # Already close enough
        return {"x": 0, "y": 0, "z": 0}

    # Direction to target
    direction = normalize_vector(rel_pos)

    # Scale to bring us to desired range
    approach_distance = current_range - desired_range
    return scale_vector(direction, approach_distance)

def calculate_closing_speed(observer_ship, target_contact) -> float:
    """Calculate closing speed (negative of range rate).

    Args:
        observer_ship: Observer ship
        target_contact: Target contact

    Returns:
        float: Closing speed in m/s (positive = closing, negative = opening)
    """
    rel_motion = calculate_relative_motion(observer_ship, target_contact)
    return -rel_motion["range_rate"]

def predict_position(ship_or_contact, delta_time: float) -> Dict[str, float]:
    """Predict future position of a ship or contact.

    Args:
        ship_or_contact: Ship or contact object
        delta_time: Time in future (seconds)

    Returns:
        dict: Predicted position {x, y, z}
    """
    pos = ship_or_contact.position if hasattr(ship_or_contact, 'position') else ship_or_contact
    vel = getattr(ship_or_contact, 'velocity', {"x": 0, "y": 0, "z": 0})

    return add_vectors(pos, scale_vector(vel, delta_time))

def is_collision_course(observer_ship, target_contact, cpa_threshold: float = 100.0) -> bool:
    """Check if on collision course with target.

    Args:
        observer_ship: Observer ship
        target_contact: Target contact
        cpa_threshold: Distance threshold for collision warning (m)

    Returns:
        bool: True if collision predicted within threshold
    """
    rel_motion = calculate_relative_motion(observer_ship, target_contact)

    if not rel_motion["closing"]:
        return False

    cpa_dist = rel_motion["closest_approach_distance"]
    return cpa_dist is not None and cpa_dist < cpa_threshold

def vector_to_heading(vector: Dict[str, float]) -> Dict[str, float]:
    """Convert a 3D vector to heading angles.

    Args:
        vector: Vector {x, y, z}

    Returns:
        dict: Heading {pitch, yaw, roll} in degrees
    """
    # Yaw (horizontal angle)
    yaw = math.degrees(math.atan2(vector['y'], vector['x']))

    # Pitch (vertical angle)
    horizontal_dist = math.sqrt(vector['x']**2 + vector['y']**2)
    pitch = math.degrees(math.atan2(vector['z'], horizontal_dist)) if horizontal_dist > 0 else 0

    # Roll not determined from direction vector
    roll = 0.0

    return {"pitch": pitch, "yaw": yaw, "roll": roll}

def heading_to_vector(heading: Dict[str, float], magnitude: float = 1.0) -> Dict[str, float]:
    """Convert heading angles to a 3D direction vector.

    Args:
        heading: Heading {pitch, yaw, roll} in degrees
        magnitude: Vector magnitude (default 1.0 for unit vector)

    Returns:
        dict: Direction vector {x, y, z}
    """
    pitch_rad = math.radians(heading.get('pitch', 0))
    yaw_rad = math.radians(heading.get('yaw', 0))

    # Convert spherical to Cartesian
    x = magnitude * math.cos(pitch_rad) * math.cos(yaw_rad)
    y = magnitude * math.cos(pitch_rad) * math.sin(yaw_rad)
    z = magnitude * math.sin(pitch_rad)

    return {"x": x, "y": y, "z": z}
