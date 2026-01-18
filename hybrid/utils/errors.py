# hybrid/utils/errors.py
"""Error handling and formatting utilities."""

class UserError(Exception):
    """Errors shown to user - must be clear and actionable."""
    pass

class ValidationError(UserError):
    """Input validation errors."""
    pass

class CommandError(UserError):
    """Command execution errors."""
    pass

class SystemError(UserError):
    """Ship system errors."""
    pass

def format_error(error_type, message, suggestion=None):
    """Format an error message for display.

    Args:
        error_type (str): Type of error (e.g., "INVALID_RANGE", "NO_TARGET")
        message (str): Error message
        suggestion (str, optional): Helpful suggestion for the user

    Returns:
        str: Formatted error message
    """
    output = f"⚠ {error_type}: {message}"
    if suggestion:
        output += f"\n  → {suggestion}"
    return output

def format_success(message, details=None):
    """Format a success message for display.

    Args:
        message (str): Success message
        details (dict, optional): Additional details to display

    Returns:
        str: Formatted success message
    """
    output = f"✓ {message}"
    if details:
        for key, value in details.items():
            output += f"\n  {key}: {value}"
    return output

def format_warning(message):
    """Format a warning message for display.

    Args:
        message (str): Warning message

    Returns:
        str: Formatted warning message
    """
    return f"⚠ WARNING: {message}"

def format_info(message):
    """Format an info message for display.

    Args:
        message (str): Info message

    Returns:
        str: Formatted info message
    """
    return f"ℹ {message}"

# Common error formatters
def invalid_range_error(param_name, min_val, max_val, current_val=None):
    """Format an invalid range error.

    Args:
        param_name (str): Parameter name
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        current_val: Current invalid value (optional)

    Returns:
        str: Formatted error message
    """
    message = f"{param_name} must be between {min_val} and {max_val}"
    if current_val is not None:
        message += f" (got {current_val})"

    suggestion = f"Try: {param_name} {(min_val + max_val) / 2}"
    return format_error("INVALID_RANGE", message, suggestion)

def no_target_error():
    """Format a no target locked error.

    Returns:
        str: Formatted error message
    """
    return format_error(
        "NO_TARGET",
        "No target locked",
        "Use 'target <contact_id>' first"
    )

def out_of_fuel_error(current_dv=None):
    """Format an out of fuel error.

    Args:
        current_dv (float, optional): Current delta-v remaining

    Returns:
        str: Formatted error message
    """
    message = "Insufficient fuel for maneuver"
    if current_dv is not None:
        message += f" (Current Δv: {current_dv:.0f} m/s)"

    return format_error("OUT_OF_FUEL", message)

def system_offline_error(system_name):
    """Format a system offline error.

    Args:
        system_name (str): Name of the offline system

    Returns:
        str: Formatted error message
    """
    return format_error(
        "SYSTEM_OFFLINE",
        f"{system_name} system is offline",
        f"Use 'power_on {system_name}' to enable it"
    )

def unknown_command_error(command_name, available_commands=None):
    """Format an unknown command error.

    Args:
        command_name (str): Unknown command name
        available_commands (list, optional): List of available commands

    Returns:
        str: Formatted error message
    """
    message = f"Unknown command: '{command_name}'"
    suggestion = None

    if available_commands:
        # Find similar commands (simple string matching)
        similar = [cmd for cmd in available_commands if command_name.lower() in cmd.lower()]
        if similar:
            suggestion = f"Did you mean: {', '.join(similar[:3])}?"
        else:
            suggestion = "Type 'help' to see available commands"

    return format_error("UNKNOWN_COMMAND", message, suggestion)

def validation_error_dict(param_name, expected_type, received_value):
    """Create a validation error dictionary for API responses.

    Args:
        param_name (str): Parameter name
        expected_type (str): Expected type
        received_value: Received value

    Returns:
        dict: Error dictionary
    """
    return {
        "ok": False,
        "error": f"Invalid {param_name}",
        "details": {
            "parameter": param_name,
            "expected": expected_type,
            "received": str(type(received_value).__name__),
            "value": str(received_value)
        }
    }

def success_dict(message, **kwargs):
    """Create a success response dictionary.

    Args:
        message (str): Success message
        **kwargs: Additional fields to include in response

    Returns:
        dict: Success dictionary
    """
    result = {
        "ok": True,
        "status": message
    }
    result.update(kwargs)
    return result

def error_dict(error_type, message, **kwargs):
    """Create an error response dictionary.

    Args:
        error_type (str): Error type
        message (str): Error message
        **kwargs: Additional fields to include in response

    Returns:
        dict: Error dictionary
    """
    result = {
        "ok": False,
        "error": error_type,
        "message": message
    }
    result.update(kwargs)
    return result
