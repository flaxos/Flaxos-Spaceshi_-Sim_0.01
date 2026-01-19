# hybrid/utils/math_utils.py
"""Mathematical utilities with NaN/Inf guards and vector operations."""

import math
import logging

logger = logging.getLogger(__name__)

# Maximum allowed values to prevent overflow
MAX_POSITION = 1e12  # 1 trillion meters (~6700 AU)
MAX_VELOCITY = 1e6   # 1 million m/s (~0.33% speed of light)
MAX_ACCELERATION = 1e4  # 10,000 m/s²

def is_valid_number(value):
    """Check if a number is finite and not NaN.

    Args:
        value: Number to check

    Returns:
        bool: True if value is a valid finite number
    """
    return not (math.isnan(value) or math.isinf(value))

def is_valid_vector(vector, keys=None):
    """Check if all components of a vector are valid numbers.

    Args:
        vector (dict): Vector dictionary with x, y, z or pitch, yaw, roll
        keys (list, optional): Specific keys to check. Defaults to ['x', 'y', 'z']

    Returns:
        bool: True if all components are valid
    """
    if keys is None:
        keys = ['x', 'y', 'z']

    return all(is_valid_number(vector.get(key, 0)) for key in keys)

def clamp(value, min_value, max_value):
    """Clamp a value between min and max.

    Args:
        value: Value to clamp
        min_value: Minimum allowed value
        max_value: Maximum allowed value

    Returns:
        Clamped value
    """
    return max(min_value, min(max_value, value))

def safe_divide(numerator, denominator, default=0.0):
    """Safely divide two numbers, returning default if denominator is zero or result is invalid.

    Args:
        numerator: Numerator value
        denominator: Denominator value
        default: Value to return if division fails

    Returns:
        Result of division or default value
    """
    if abs(denominator) < 1e-10:
        return default

    result = numerator / denominator

    if not is_valid_number(result):
        logger.warning(f"Division produced invalid result: {numerator}/{denominator}")
        return default

    return result

def magnitude(vector, keys=None):
    """Calculate magnitude of a vector.

    Args:
        vector (dict): Vector dictionary
        keys (list, optional): Keys to use for calculation. Defaults to ['x', 'y', 'z']

    Returns:
        float: Magnitude of the vector
    """
    if keys is None:
        keys = ['x', 'y', 'z']

    sum_of_squares = sum(vector.get(key, 0)**2 for key in keys)
    return math.sqrt(sum_of_squares)

def normalize_vector(vector, keys=None):
    """Normalize a vector to unit length.

    Args:
        vector (dict): Vector to normalize
        keys (list, optional): Keys to normalize. Defaults to ['x', 'y', 'z']

    Returns:
        dict: Normalized vector, or zero vector if magnitude is too small
    """
    if keys is None:
        keys = ['x', 'y', 'z']

    mag = magnitude(vector, keys)

    if mag < 1e-10:
        return {key: 0.0 for key in keys}

    return {key: vector.get(key, 0) / mag for key in keys}

def add_vectors(v1, v2, keys=None):
    """Add two vectors.

    Args:
        v1 (dict): First vector
        v2 (dict): Second vector
        keys (list, optional): Keys to add. Defaults to ['x', 'y', 'z']

    Returns:
        dict: Sum of vectors
    """
    if keys is None:
        keys = ['x', 'y', 'z']

    return {key: v1.get(key, 0) + v2.get(key, 0) for key in keys}

def subtract_vectors(v1, v2, keys=None):
    """Subtract v2 from v1.

    Args:
        v1 (dict): First vector
        v2 (dict): Second vector
        keys (list, optional): Keys to subtract. Defaults to ['x', 'y', 'z']

    Returns:
        dict: Difference of vectors (v1 - v2)
    """
    if keys is None:
        keys = ['x', 'y', 'z']

    return {key: v1.get(key, 0) - v2.get(key, 0) for key in keys}

def scale_vector(vector, scalar, keys=None):
    """Scale a vector by a scalar.

    Args:
        vector (dict): Vector to scale
        scalar: Scaling factor
        keys (list, optional): Keys to scale. Defaults to ['x', 'y', 'z']

    Returns:
        dict: Scaled vector
    """
    if keys is None:
        keys = ['x', 'y', 'z']

    return {key: vector.get(key, 0) * scalar for key in keys}

def dot_product(v1, v2, keys=None):
    """Calculate dot product of two vectors.

    Args:
        v1 (dict): First vector
        v2 (dict): Second vector
        keys (list, optional): Keys to use. Defaults to ['x', 'y', 'z']

    Returns:
        float: Dot product
    """
    if keys is None:
        keys = ['x', 'y', 'z']

    return sum(v1.get(key, 0) * v2.get(key, 0) for key in keys)

def clamp_vector(vector, max_magnitude, keys=None):
    """Clamp a vector to a maximum magnitude.

    Args:
        vector (dict): Vector to clamp
        max_magnitude: Maximum allowed magnitude
        keys (list, optional): Keys to clamp. Defaults to ['x', 'y', 'z']

    Returns:
        dict: Clamped vector
    """
    if keys is None:
        keys = ['x', 'y', 'z']

    mag = magnitude(vector, keys)

    if mag <= max_magnitude:
        return dict(vector)

    scale = max_magnitude / mag
    return scale_vector(vector, scale, keys)

def sanitize_physics_state(position, velocity, acceleration, ship_id="unknown"):
    """Sanitize physics state vectors, recovering from NaN/Inf.

    Args:
        position (dict): Position vector
        velocity (dict): Velocity vector
        acceleration (dict): Acceleration vector
        ship_id: Ship identifier for logging

    Returns:
        tuple: (sanitized_position, sanitized_velocity, sanitized_acceleration, recovered)
    """
    recovered = False

    # Check position
    if not is_valid_vector(position):
        logger.error(f"Ship {ship_id}: Invalid position detected, resetting to origin")
        position = {"x": 0.0, "y": 0.0, "z": 0.0}
        recovered = True
    else:
        # Clamp position to reasonable bounds
        for key in ['x', 'y', 'z']:
            if abs(position[key]) > MAX_POSITION:
                logger.warning(f"Ship {ship_id}: Position {key}={position[key]} exceeds bounds, clamping")
                position[key] = clamp(position[key], -MAX_POSITION, MAX_POSITION)
                recovered = True

    # Check velocity
    if not is_valid_vector(velocity):
        logger.error(f"Ship {ship_id}: Invalid velocity detected, resetting to zero")
        velocity = {"x": 0.0, "y": 0.0, "z": 0.0}
        recovered = True
    else:
        # Clamp velocity to reasonable bounds
        vel_mag = magnitude(velocity)
        if vel_mag > MAX_VELOCITY:
            logger.warning(f"Ship {ship_id}: Velocity magnitude {vel_mag} exceeds bounds, clamping")
            velocity = clamp_vector(velocity, MAX_VELOCITY)
            recovered = True

    # Check acceleration
    if not is_valid_vector(acceleration):
        logger.error(f"Ship {ship_id}: Invalid acceleration detected, resetting to zero")
        acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
        recovered = True
    else:
        # Clamp acceleration to reasonable bounds
        accel_mag = magnitude(acceleration)
        if accel_mag > MAX_ACCELERATION:
            logger.warning(f"Ship {ship_id}: Acceleration magnitude {accel_mag} exceeds bounds, clamping")
            acceleration = clamp_vector(acceleration, MAX_ACCELERATION)
            recovered = True

    return position, velocity, acceleration, recovered

def normalize_angle(angle):
    """Normalize an angle to [-180, 180) range.

    Args:
        angle: Angle in degrees

    Returns:
        float: Normalized angle
    """
    while angle >= 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle

def calculate_distance(pos1, pos2):
    """Calculate distance between two positions.

    Args:
        pos1 (dict): First position {x, y, z}
        pos2 (dict): Second position {x, y, z}

    Returns:
        float: Distance between positions
    """
    diff = subtract_vectors(pos1, pos2)
    return magnitude(diff)

def calculate_bearing(from_pos, to_pos, from_orientation=None):
    """Calculate bearing from one position to another.

    Args:
        from_pos (dict): Observer position {x, y, z}
        to_pos (dict): Target position {x, y, z}
        from_orientation (dict, optional): Observer orientation {pitch, yaw, roll}

    Returns:
        dict: Bearing with {yaw, pitch} in degrees

    Note:
        LIMITATION (Pre-S3): When from_orientation is provided, this function performs
        a simple angular subtraction which doesn't account for roll or proper 3D rotation.
        This causes inaccurate bearings during high-rotation maneuvers or non-zero roll.
        S3 will replace this with quaternion-based bearing calculations for proper aim fidelity.
    """
    diff = subtract_vectors(to_pos, from_pos)

    # Calculate yaw (horizontal angle)
    yaw = math.degrees(math.atan2(diff.get('y', 0), diff.get('x', 0)))

    # Calculate pitch (vertical angle)
    horizontal_distance = math.sqrt(diff.get('x', 0)**2 + diff.get('y', 0)**2)
    pitch = math.degrees(math.atan2(diff.get('z', 0), horizontal_distance))

    # If observer orientation is provided, make bearing relative to it
    # WARNING: This is a simplified approximation that ignores roll and 3D rotation matrix
    if from_orientation:
        yaw = normalize_angle(yaw - from_orientation.get('yaw', 0))
        pitch = normalize_angle(pitch - from_orientation.get('pitch', 0))

    return {"yaw": yaw, "pitch": pitch}
