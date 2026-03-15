"""
Server-side command parameter validation.

Enforces server-authoritative constraints on all command parameters.
Prevents clients from sending invalid, out-of-range, or malicious values.
"""

import math
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Maximum coordinate value (1 AU in meters)
MAX_COORDINATE = 1.5e11

# Validation rules: command -> {param: (type, min, max, default)}
PARAM_RULES: Dict[str, Dict[str, Tuple]] = {
    "set_thrust": {
        "thrust": (float, 0.0, 1.0, 0.0),
        "throttle": (float, 0.0, 1.0, 0.0),
        "g": (float, 0.0, 20.0, None),  # Max 20G
    },
    "set_thrust_vector": {
        "x": (float, -1e6, 1e6, 0.0),
        "y": (float, -1e6, 1e6, 0.0),
        "z": (float, -1e6, 1e6, 0.0),
    },
    "set_course": {
        "x": (float, -MAX_COORDINATE, MAX_COORDINATE, None),
        "y": (float, -MAX_COORDINATE, MAX_COORDINATE, None),
        "z": (float, -MAX_COORDINATE, MAX_COORDINATE, None),
    },
    "set_orientation": {
        "pitch": (float, -360.0, 360.0, None),
        "yaw": (float, -360.0, 360.0, None),
        "roll": (float, -360.0, 360.0, None),
    },
    "set_angular_velocity": {
        "pitch": (float, -360.0, 360.0, 0.0),
        "yaw": (float, -360.0, 360.0, 0.0),
        "roll": (float, -360.0, 360.0, 0.0),
    },
    "point_at": {
        "x": (float, -MAX_COORDINATE, MAX_COORDINATE, None),
        "y": (float, -MAX_COORDINATE, MAX_COORDINATE, None),
        "z": (float, -MAX_COORDINATE, MAX_COORDINATE, None),
    },
    "fire_railgun": {
        "weapon_id": (str, None, None, None),
    },
    "fire_pdc": {
        "weapon_id": (str, None, None, None),
    },
    "fire_combat": {
        "weapon_id": (str, None, None, None),
    },
    "execute_burn": {
        "duration": (float, 0.1, 3600.0, 10.0),
        "throttle": (float, 0.0, 1.0, None),
        "g": (float, 0.0, 20.0, None),
        "pitch": (float, -90.0, 90.0, None),
        "yaw": (float, -360.0, 360.0, None),
    },
    "emergency_burn": {
        "pitch": (float, -90.0, 90.0, None),
        "yaw": (float, -360.0, 360.0, None),
        "duration": (float, 0.1, 300.0, None),
    },
    "set_power_allocation": {
        "level": (float, 0.0, 1.0, None),
    },
}


def _is_valid_number(value: Any) -> bool:
    """Check if a value is a valid finite number."""
    try:
        f = float(value)
        return math.isfinite(f)
    except (ValueError, TypeError):
        return False


def validate_command_params(cmd: str, params: dict) -> Tuple[bool, Optional[str], dict]:
    """Validate command parameters against defined rules.

    Args:
        cmd: Command name
        params: Raw parameters from client

    Returns:
        Tuple of (is_valid, error_message, sanitized_params)
        If is_valid is False, error_message describes the issue.
        sanitized_params contains cleaned/clamped values.
    """
    rules = PARAM_RULES.get(cmd)
    if not rules:
        # No specific rules - pass through (command handler will validate)
        return True, None, params

    sanitized = dict(params)

    for param_name, (param_type, min_val, max_val, default) in rules.items():
        if param_name not in params:
            continue  # Optional param not provided

        raw_value = params[param_name]

        if param_type == float:
            if not _is_valid_number(raw_value):
                return False, f"Invalid value for '{param_name}': must be a finite number", params
            value = float(raw_value)
            if min_val is not None and value < min_val:
                value = min_val
            if max_val is not None and value > max_val:
                value = max_val
            sanitized[param_name] = value

        elif param_type == str:
            if not isinstance(raw_value, str) or len(raw_value) > 256:
                return False, f"Invalid value for '{param_name}': must be a string (max 256 chars)", params
            sanitized[param_name] = raw_value

    return True, None, sanitized


def validate_ship_ownership(client_id: str, ship_id: str, session) -> Tuple[bool, Optional[str]]:
    """Validate that a client is authorized to control a ship.

    In station mode, checks session assignment.
    Returns (is_valid, error_message).
    """
    if session is None:
        # No session tracking (minimal mode) - allow but log
        logger.debug(f"No session for {client_id}, allowing ship {ship_id}")
        return True, None

    if not session.ship_id:
        return False, "Not assigned to any ship"

    if session.ship_id != ship_id:
        return False, f"Not authorized to control ship {ship_id}"

    return True, None
