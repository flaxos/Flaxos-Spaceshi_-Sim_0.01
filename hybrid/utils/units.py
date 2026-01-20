# hybrid/utils/units.py
"""Unit conversion and standardization utilities.

Internal units:
- Distance: metres
- Velocity: m/s
- Acceleration: m/s²
- Angles: radians (for internal calculations)
- Time: seconds
- Mass: kg
- Force: Newtons

Display units:
- Distance: metres or km (auto-scaled)
- Velocity: m/s
- Angles: degrees
- Time: seconds, minutes, hours (auto-scaled)
"""

import math

# Distance conversions
def metres_to_km(metres):
    """Convert metres to kilometres."""
    return metres / 1000.0

def km_to_metres(km):
    """Convert kilometres to metres."""
    return km * 1000.0

def to_display_distance(metres):
    """Convert metres to appropriate display unit.

    Args:
        metres (float): Distance in metres

    Returns:
        tuple: (value, unit_string)
    """
    if abs(metres) >= 1000:
        return metres / 1000.0, "km"
    return metres, "m"

def format_distance(metres, precision=1):
    """Format distance for display with appropriate unit.

    Args:
        metres (float): Distance in metres
        precision (int): Decimal places to show

    Returns:
        str: Formatted distance string (e.g., "12.4 km")
    """
    value, unit = to_display_distance(metres)
    return f"{value:.{precision}f} {unit}"

# Angle conversions
def radians_to_degrees(radians):
    """Convert radians to degrees."""
    return math.degrees(radians)

def degrees_to_radians(degrees):
    """Convert degrees to radians."""
    return math.radians(degrees)

def to_display_angle(radians):
    """Convert radians to degrees for display.

    Args:
        radians (float): Angle in radians

    Returns:
        float: Angle in degrees
    """
    return math.degrees(radians)

def from_input_angle(degrees):
    """Convert input angle in degrees to internal radians.

    Args:
        degrees (float): Angle in degrees

    Returns:
        float: Angle in radians
    """
    return math.radians(degrees)

def format_angle(degrees, precision=1):
    """Format angle for display.

    Args:
        degrees (float): Angle in degrees
        precision (int): Decimal places to show

    Returns:
        str: Formatted angle string (e.g., "45.0°")
    """
    return f"{degrees:.{precision}f}°"

# Velocity conversions
def format_velocity(m_per_s, precision=1):
    """Format velocity for display.

    Args:
        m_per_s (float): Velocity in m/s
        precision (int): Decimal places to show

    Returns:
        str: Formatted velocity string (e.g., "340.5 m/s")
    """
    return f"{m_per_s:.{precision}f} m/s"

# Time conversions
def to_display_time(seconds):
    """Convert seconds to appropriate display unit.

    Args:
        seconds (float): Time in seconds

    Returns:
        tuple: (value, unit_string)
    """
    if seconds >= 3600:
        return seconds / 3600.0, "h"
    elif seconds >= 60:
        return seconds / 60.0, "min"
    return seconds, "s"

def format_time(seconds, precision=1):
    """Format time for display with appropriate unit.

    Args:
        seconds (float): Time in seconds
        precision (int): Decimal places to show

    Returns:
        str: Formatted time string (e.g., "12.4 s", "3.5 min")
    """
    value, unit = to_display_time(seconds)
    return f"{value:.{precision}f} {unit}"

# Vector formatting
def format_vector(vector, precision=1, keys=None):
    """Format a vector for display.

    Args:
        vector (dict): Vector dictionary
        precision (int): Decimal places to show
        keys (list, optional): Keys to format. Defaults to ['x', 'y', 'z']

    Returns:
        str: Formatted vector string (e.g., "[12.3, 45.6, 78.9]")
    """
    if keys is None:
        keys = ['x', 'y', 'z']

    values = [f"{vector.get(key, 0):.{precision}f}" for key in keys]
    return f"[{', '.join(values)}]"

def format_heading(orientation, precision=1):
    """Format orientation/heading for display.

    Args:
        orientation (dict): Orientation dictionary with pitch, yaw, roll
        precision (int): Decimal places to show

    Returns:
        str: Formatted heading string (e.g., "P:12.3° Y:45.6° R:0.0°")
    """
    pitch = orientation.get('pitch', 0)
    yaw = orientation.get('yaw', 0)
    roll = orientation.get('roll', 0)

    return f"P:{pitch:.{precision}f}° Y:{yaw:.{precision}f}° R:{roll:.{precision}f}°"

# Mass conversions
def kg_to_tonnes(kg):
    """Convert kilograms to tonnes."""
    return kg / 1000.0

def tonnes_to_kg(tonnes):
    """Convert tonnes to kilograms."""
    return tonnes * 1000.0

def format_mass(kg, precision=1):
    """Format mass for display with appropriate unit.

    Args:
        kg (float): Mass in kilograms
        precision (int): Decimal places to show

    Returns:
        str: Formatted mass string (e.g., "12.4 t")
    """
    if kg >= 1000:
        return f"{kg/1000:.{precision}f} t"
    return f"{kg:.{precision}f} kg"

# Delta-v and specific impulse
def calculate_delta_v(dry_mass_kg, fuel_mass_kg, isp_seconds):
    """Calculate delta-v using Tsiolkovsky rocket equation.

    Args:
        dry_mass_kg (float): Dry mass in kg
        fuel_mass_kg (float): Fuel mass in kg
        isp_seconds (float): Specific impulse in seconds

    Returns:
        float: Delta-v in m/s
    """
    if fuel_mass_kg <= 0:
        return 0.0

    if dry_mass_kg <= 0:
        return 0.0

    total_mass = dry_mass_kg + fuel_mass_kg
    mass_ratio = total_mass / dry_mass_kg

    if mass_ratio <= 0:
        return 0.0

    # Tsiolkovsky: Δv = Isp * g₀ * ln(m₀/m_f)
    g0 = 9.81  # Standard gravity
    return isp_seconds * g0 * math.log(mass_ratio)

def format_delta_v(delta_v_m_s, precision=0):
    """Format delta-v for display.

    Args:
        delta_v_m_s (float): Delta-v in m/s
        precision (int): Decimal places to show

    Returns:
        str: Formatted delta-v string (e.g., "1234 m/s Δv")
    """
    return f"{delta_v_m_s:.{precision}f} m/s Δv"
