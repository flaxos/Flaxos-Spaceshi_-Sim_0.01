# hybrid/commands/validators.py
"""Input validation utilities for commands."""

import math
from typing import Any, Tuple, Optional
from hybrid.utils.errors import ValidationError, invalid_range_error
from hybrid.utils.math_utils import is_valid_number

class ArgSpec:
    """Specification for a command argument."""

    def __init__(self, name, arg_type, required=True, min_val=None, max_val=None,
                 choices=None, default=None, description=""):
        """Initialize argument specification.

        Args:
            name (str): Argument name
            arg_type (str): Type specification (float, int, str, bool, angle, vector3)
            required (bool): Whether argument is required
            min_val: Minimum allowed value (for numeric types)
            max_val: Maximum allowed value (for numeric types)
            choices (list): Valid choices (for string types)
            default: Default value if not provided
            description (str): Help text
        """
        self.name = name
        self.arg_type = arg_type
        self.required = required
        self.min_val = min_val
        self.max_val = max_val
        self.choices = choices
        self.default = default
        self.description = description

    def validate(self, value):
        """Validate a value against this argument specification.

        Args:
            value: Value to validate

        Returns:
            Tuple[bool, Any, Optional[str]]: (is_valid, converted_value, error_message)
        """
        # Handle missing value
        if value is None:
            if self.required:
                return False, None, f"Missing required argument: {self.name}"
            return True, self.default, None

        # Type conversion and validation
        try:
            if self.arg_type == "float":
                converted = float(value)
                if not is_valid_number(converted):
                    return False, None, f"{self.name}: Invalid number (NaN or Inf)"

                if self.min_val is not None and converted < self.min_val:
                    return False, None, invalid_range_error(self.name, self.min_val, self.max_val, converted)

                if self.max_val is not None and converted > self.max_val:
                    return False, None, invalid_range_error(self.name, self.min_val, self.max_val, converted)

                return True, converted, None

            elif self.arg_type == "int":
                converted = int(value)

                if self.min_val is not None and converted < self.min_val:
                    return False, None, invalid_range_error(self.name, self.min_val, self.max_val, converted)

                if self.max_val is not None and converted > self.max_val:
                    return False, None, invalid_range_error(self.name, self.min_val, self.max_val, converted)

                return True, converted, None

            elif self.arg_type == "str":
                converted = str(value)

                if self.choices and converted not in self.choices:
                    return False, None, f"{self.name}: Must be one of {self.choices}, got '{converted}'"

                return True, converted, None

            elif self.arg_type == "bool":
                if isinstance(value, bool):
                    return True, value, None

                # Parse string boolean
                if isinstance(value, str):
                    lower_val = value.lower()
                    if lower_val in ["true", "1", "yes", "on"]:
                        return True, True, None
                    elif lower_val in ["false", "0", "no", "off"]:
                        return True, False, None

                return False, None, f"{self.name}: Invalid boolean value '{value}'"

            elif self.arg_type == "angle":
                # Angle in degrees, normalize to [-180, 180)
                converted = float(value)
                if not is_valid_number(converted):
                    return False, None, f"{self.name}: Invalid angle (NaN or Inf)"

                # Normalize angle
                while converted >= 180:
                    converted -= 360
                while converted < -180:
                    converted += 360

                return True, converted, None

            elif self.arg_type == "vector3":
                # Expect dict with x, y, z or list [x, y, z]
                if isinstance(value, dict):
                    if not all(key in value for key in ['x', 'y', 'z']):
                        return False, None, f"{self.name}: Vector must have x, y, z components"

                    x, y, z = float(value['x']), float(value['y']), float(value['z'])

                    if not all(is_valid_number(v) for v in [x, y, z]):
                        return False, None, f"{self.name}: Invalid vector values (NaN or Inf)"

                    return True, {"x": x, "y": y, "z": z}, None

                elif isinstance(value, (list, tuple)):
                    if len(value) != 3:
                        return False, None, f"{self.name}: Vector must have 3 components"

                    x, y, z = float(value[0]), float(value[1]), float(value[2])

                    if not all(is_valid_number(v) for v in [x, y, z]):
                        return False, None, f"{self.name}: Invalid vector values (NaN or Inf)"

                    return True, {"x": x, "y": y, "z": z}, None

                return False, None, f"{self.name}: Vector must be dict or list"

            else:
                # Unknown type, just return as-is
                return True, value, None

        except (ValueError, TypeError) as e:
            return False, None, f"{self.name}: Type conversion error - {e}"

def validate_thrust(value):
    """Validate a thrust value (0-1).

    Args:
        value: Thrust value to validate

    Returns:
        Tuple[bool, float, Optional[str]]: (is_valid, clamped_value, error_message)
    """
    try:
        thrust = float(value)

        if not is_valid_number(thrust):
            return False, 0.0, "Thrust must be a valid number (not NaN or Inf)"

        if thrust < 0.0 or thrust > 1.0:
            clamped = max(0.0, min(1.0, thrust))
            return True, clamped, f"Thrust clamped from {thrust} to {clamped} (valid range: 0-1)"

        return True, thrust, None

    except (ValueError, TypeError):
        return False, 0.0, "Thrust must be a number between 0 and 1"

def validate_heading(pitch, yaw, roll=None):
    """Validate heading values.

    Args:
        pitch: Pitch angle in degrees
        yaw: Yaw angle in degrees
        roll: Roll angle in degrees (optional)

    Returns:
        Tuple[bool, dict, Optional[str]]: (is_valid, normalized_values, error_message)
    """
    try:
        p = float(pitch)
        y = float(yaw)

        if not all(is_valid_number(v) for v in [p, y]):
            return False, None, "Heading values must be valid numbers (not NaN or Inf)"

        # Normalize angles to [-180, 180)
        p = normalize_angle_degrees(p)
        y = normalize_angle_degrees(y)

        result = {"pitch": p, "yaw": y}

        if roll is not None:
            r = float(roll)
            if not is_valid_number(r):
                return False, None, "Roll must be a valid number (not NaN or Inf)"
            result["roll"] = normalize_angle_degrees(r)

        return True, result, None

    except (ValueError, TypeError):
        return False, None, "Heading values must be numbers"

def normalize_angle_degrees(angle):
    """Normalize angle to [-180, 180) range.

    Args:
        angle (float): Angle in degrees

    Returns:
        float: Normalized angle
    """
    while angle >= 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle

def validate_power_amount(amount, max_amount=None):
    """Validate a power request amount.

    Args:
        amount: Power amount to validate
        max_amount: Maximum allowed amount (optional)

    Returns:
        Tuple[bool, float, Optional[str]]: (is_valid, clamped_value, error_message)
    """
    try:
        power = float(amount)

        if not is_valid_number(power):
            return False, 0.0, "Power amount must be a valid number (not NaN or Inf)"

        if power < 0:
            return False, 0.0, "Power amount cannot be negative"

        if max_amount is not None and power > max_amount:
            return False, max_amount, f"Power amount {power} exceeds maximum {max_amount}"

        return True, power, None

    except (ValueError, TypeError):
        return False, 0.0, "Power amount must be a number"

def validate_contact_id(contact_id, available_contacts=None):
    """Validate a contact ID.

    Args:
        contact_id: Contact ID to validate
        available_contacts (list, optional): List of valid contact IDs

    Returns:
        Tuple[bool, str, Optional[str]]: (is_valid, contact_id, error_message)
    """
    if not contact_id:
        return False, None, "Contact ID is required"

    contact_str = str(contact_id)

    if available_contacts is not None and contact_str not in available_contacts:
        return False, None, f"Unknown contact: {contact_str}. Available: {', '.join(available_contacts)}"

    return True, contact_str, None

def validate_weapon_type(weapon_type, available_weapons=None):
    """Validate a weapon type.

    Args:
        weapon_type (str): Weapon type to validate
        available_weapons (list, optional): List of valid weapon types

    Returns:
        Tuple[bool, str, Optional[str]]: (is_valid, weapon_type, error_message)
    """
    if not weapon_type:
        return False, None, "Weapon type is required"

    weapon_str = str(weapon_type).lower()

    if available_weapons is not None:
        available_lower = [w.lower() for w in available_weapons]
        if weapon_str not in available_lower:
            return False, None, f"Unknown weapon: {weapon_str}. Available: {', '.join(available_weapons)}"

    return True, weapon_str, None

def validate_autopilot_program(program):
    """Validate an autopilot program name.

    Args:
        program (str): Autopilot program name

    Returns:
        Tuple[bool, str, Optional[str]]: (is_valid, program, error_message)
    """
    valid_programs = ["match", "intercept", "approach", "hold", "off"]

    program_str = str(program).lower()

    if program_str not in valid_programs:
        return False, None, f"Unknown autopilot program: {program}. Valid: {', '.join(valid_programs)}"

    return True, program_str, None
