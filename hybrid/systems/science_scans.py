# hybrid/systems/science_scans.py
"""Science station active scan commands.

Provides range-limited active scans that extract detailed information
from tracked contacts:
- Spectral analysis: drive type, ISP range, max accel from IR spectrum
- Composition scan: armor type, hull class, mass from radar returns

Design:
- Both scans require a tracked contact (confidence > 0.3).
- Quality degrades with range; results are "unknown" beyond max range.
- Results are cached on the contact until the contact is lost.
- Ground truth comes from target ship's actual systems (via _all_ships_ref),
  with noise added based on range and sensor health.
"""

import logging
import math
import random
from typing import Any, Dict, Optional, Tuple

from hybrid.utils.errors import success_dict, error_dict
from hybrid.utils.math_utils import calculate_distance

logger = logging.getLogger(__name__)

# Range limits (metres)
SPECTRAL_MAX_RANGE = 50_000.0   # 50 km
SPECTRAL_FULL_RANGE = 25_000.0  # Full quality within 25 km
COMPOSITION_MAX_RANGE = 20_000.0  # 20 km
COMPOSITION_FULL_RANGE = 5_000.0  # Full quality within 5 km

# Drive type catalogue with ISP ranges (seconds) and typical max accel
DRIVE_CATALOGUE: Dict[str, Dict[str, Any]] = {
    "epstein":   {"isp_range": [800_000, 1_200_000], "typical_accel": 100.0},
    "fusion":    {"isp_range": [10_000, 50_000],     "typical_accel": 30.0},
    "chemical":  {"isp_range": [200, 450],           "typical_accel": 40.0},
    "ion":       {"isp_range": [3_000, 12_000],      "typical_accel": 0.5},
    "cold_gas":  {"isp_range": [50, 100],            "typical_accel": 0.1},
}

# Map from known ISP ranges to drive type labels
_ISP_DRIVE_MAP = [
    (500_000, "epstein"),
    (5_000,   "fusion"),
    (1_000,   "ion"),
    (150,     "chemical"),
    (0,       "cold_gas"),
]


def _range_quality(distance: float, max_range: float,
                   full_range: float) -> float:
    """Compute scan quality factor (0-1) from distance.

    Args:
        distance: Distance to target in metres
        max_range: Maximum effective scan range
        full_range: Range within which quality is 1.0

    Returns:
        Quality factor 0.0-1.0
    """
    if distance <= full_range:
        return 1.0
    if distance >= max_range:
        return 0.0
    # Linear degradation between full_range and max_range
    return 1.0 - (distance - full_range) / (max_range - full_range)


def _infer_drive_type_from_isp(isp: float) -> str:
    """Classify drive type from ISP value.

    Args:
        isp: Specific impulse in seconds

    Returns:
        Drive type string
    """
    for threshold, dtype in _ISP_DRIVE_MAP:
        if isp >= threshold:
            return dtype
    return "unknown"


def _add_noise(value: float, noise_fraction: float) -> float:
    """Add Gaussian noise to a value.

    Args:
        value: True value
        noise_fraction: Standard deviation as fraction of value

    Returns:
        Noisy value (clamped >= 0)
    """
    if value <= 0 or noise_fraction <= 0:
        return value
    return max(0.0, value + random.gauss(0, value * noise_fraction))


def spectral_scan(contact, target_ship, ship,
                  sensor_health: float, sim_time: float) -> dict:
    """Perform spectral analysis to identify propulsion characteristics.

    Reads the target's propulsion system for ground truth, then adds
    range-dependent noise. Returns drive type, ISP range, and estimated
    max acceleration.

    Args:
        contact: ContactData for the target
        target_ship: Resolved target Ship object (may be None)
        ship: Player's own ship (for distance calculation)
        sensor_health: Sensor health factor 0-1
        sim_time: Current simulation time

    Returns:
        dict: Result dict (success_dict or error_dict)
    """
    if not contact:
        return error_dict("NO_CONTACT", "No contact provided")

    # Confidence gate
    confidence = getattr(contact, "confidence", 0.0)
    if confidence < 0.3:
        return error_dict("LOW_CONFIDENCE",
                          f"Contact confidence too low ({confidence:.0%}); "
                          f"needs > 30% for spectral scan")

    # Range check
    distance = calculate_distance(ship.position, contact.position)
    if distance > SPECTRAL_MAX_RANGE:
        return error_dict("OUT_OF_RANGE",
                          f"Target at {distance/1000:.1f} km — spectral scan "
                          f"effective within {SPECTRAL_MAX_RANGE/1000:.0f} km")

    quality = _range_quality(distance, SPECTRAL_MAX_RANGE,
                             SPECTRAL_FULL_RANGE) * sensor_health

    # Derive ground truth from target ship
    drive_type = "unknown"
    isp = 0.0
    max_accel = 0.0

    if target_ship:
        propulsion = target_ship.systems.get("propulsion")
        if propulsion:
            isp = getattr(propulsion, "isp", 3000.0)
            max_thrust = getattr(propulsion, "max_thrust", 0.0)
            mass = getattr(target_ship, "mass", 1.0)
            if mass > 0:
                max_accel = max_thrust / mass
            drive_type = _infer_drive_type_from_isp(isp)

    # Apply noise based on quality
    noise_frac = 0.05 + 0.45 * (1.0 - quality)  # 5% at best, 50% at worst

    # Drive type confidence tracks quality directly
    drive_confidence = round(min(0.95, quality * 0.95 + 0.05), 3)

    # If quality is very low, mask the drive type
    if quality < 0.15:
        drive_type = "unknown"
        drive_confidence = 0.0

    # ISP range: widen the reported range based on noise
    isp_noisy = _add_noise(isp, noise_frac) if isp > 0 else 0.0
    spread = max(100.0, isp * noise_frac * 2.0)
    isp_range = [round(max(0, isp_noisy - spread), 0),
                 round(isp_noisy + spread, 0)]

    # Max accel with noise
    max_accel_est = round(_add_noise(max_accel, noise_frac), 2)

    # Fall back to catalogue estimate if we know the type but have no data
    if max_accel_est <= 0 and drive_type in DRIVE_CATALOGUE:
        cat = DRIVE_CATALOGUE[drive_type]
        max_accel_est = round(_add_noise(cat["typical_accel"], noise_frac), 2)
        isp_range = [round(cat["isp_range"][0] * (1 - noise_frac), 0),
                     round(cat["isp_range"][1] * (1 + noise_frac), 0)]

    result_data = {
        "drive_type": drive_type,
        "drive_type_confidence": drive_confidence,
        "estimated_isp_range": isp_range,
        "estimated_max_accel": max_accel_est,
        "scan_quality": round(quality, 3),
        "range_km": round(distance / 1000, 1),
    }

    return success_dict(
        f"Spectral scan of {contact.id}: drive={drive_type} "
        f"(conf {drive_confidence:.0%})",
        contact_id=contact.id,
        spectral_scan=result_data,
        analysis_quality=round(quality, 3),
    )


def composition_scan(contact, target_ship, ship,
                     sensor_health: float, sim_time: float,
                     has_active_ping: bool = True) -> dict:
    """Perform composition scan to estimate hull and armor properties.

    Reads the target's armor model and ship class for ground truth,
    then adds range-dependent noise. Requires recent active radar data.

    Args:
        contact: ContactData for the target
        target_ship: Resolved target Ship object (may be None)
        ship: Player's own ship (for distance calculation)
        sensor_health: Sensor health factor 0-1
        sim_time: Current simulation time
        has_active_ping: Whether player has recent active radar data

    Returns:
        dict: Result dict (success_dict or error_dict)
    """
    if not contact:
        return error_dict("NO_CONTACT", "No contact provided")

    # Confidence gate
    confidence = getattr(contact, "confidence", 0.0)
    if confidence < 0.3:
        return error_dict("LOW_CONFIDENCE",
                          f"Contact confidence too low ({confidence:.0%}); "
                          f"needs > 30% for composition scan")

    # Active radar requirement
    if not has_active_ping:
        return error_dict("NO_ACTIVE_DATA",
                          "Composition scan requires active radar data — "
                          "ping sensors first")

    # Range check
    distance = calculate_distance(ship.position, contact.position)
    if distance > COMPOSITION_MAX_RANGE:
        return error_dict("OUT_OF_RANGE",
                          f"Target at {distance/1000:.1f} km — composition scan "
                          f"effective within {COMPOSITION_MAX_RANGE/1000:.0f} km")

    quality = _range_quality(distance, COMPOSITION_MAX_RANGE,
                             COMPOSITION_FULL_RANGE) * sensor_health

    # Ground truth from target ship
    armor_type = "unknown"
    armor_thickness = 0.0
    ship_class = "unknown"
    estimated_mass = 0.0

    if target_ship:
        # Armor data
        armor_model = getattr(target_ship, "armor_model", None)
        if armor_model and hasattr(armor_model, "sections"):
            # Get the dominant material and average thickness
            materials: Dict[str, int] = {}
            total_thickness = 0.0
            count = 0
            for section in armor_model.sections.values():
                mat = getattr(section, "material", "steel")
                materials[mat] = materials.get(mat, 0) + 1
                total_thickness += getattr(section, "thickness_cm", 0.0)
                count += 1
            if count > 0:
                armor_thickness = (total_thickness / count) * 10.0  # cm -> mm
                # Most common material
                armor_type = max(materials, key=materials.get)

        # Ship class
        ship_class = getattr(target_ship, "class_type", "unknown")

        # Mass
        estimated_mass = getattr(target_ship, "mass", 0.0)

    # Apply noise
    noise_frac = 0.05 + 0.55 * (1.0 - quality)  # 5% at best, 60% at worst

    armor_thickness_est = round(_add_noise(armor_thickness, noise_frac), 1)
    mass_est = round(_add_noise(estimated_mass, noise_frac), 0)

    # Class confidence
    class_confidence = round(min(0.95, quality * 0.9 + 0.05), 3)
    if quality < 0.2:
        ship_class = "unknown"
        armor_type = "unknown"
        class_confidence = 0.0

    result_data = {
        "armor_type": armor_type,
        "armor_thickness_estimate": armor_thickness_est,
        "estimated_ship_class": ship_class,
        "class_confidence": class_confidence,
        "estimated_mass": mass_est,
        "scan_quality": round(quality, 3),
        "range_km": round(distance / 1000, 1),
    }

    return success_dict(
        f"Composition scan of {contact.id}: {ship_class} "
        f"({armor_type} armor, {armor_thickness_est:.0f}mm)",
        contact_id=contact.id,
        composition_scan=result_data,
        analysis_quality=round(quality, 3),
    )
