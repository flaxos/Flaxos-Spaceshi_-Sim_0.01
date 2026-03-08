# hybrid/systems/flight_computer/planning.py
"""Burn plan estimation for the flight computer."""

import math
import logging
from typing import List, Optional

from hybrid.systems.flight_computer.models import BurnPlan
from hybrid.utils.math_utils import magnitude, subtract_vectors

logger = logging.getLogger(__name__)


def plan_goto(ship, position: dict, params: dict) -> BurnPlan:
    """Estimate burn plan for a go-to-position command.

    Args:
        ship: Ship object.
        position: Target position {x, y, z}.
        params: Additional parameters.

    Returns:
        BurnPlan with estimates.
    """
    vec = subtract_vectors(position, ship.position)
    distance = magnitude(vec)
    max_accel = _max_accel(ship)

    # Constant-accel brachistochrone: accel half the way, brake the other half
    if max_accel > 0 and distance > 0:
        est_time = 2.0 * math.sqrt(distance / max_accel)
        delta_v = max_accel * est_time  # total dv for both phases
    else:
        est_time = 0.0
        delta_v = 0.0

    fuel_cost = _fuel_for_delta_v(ship, delta_v)
    fuel_avail = _fuel_available(ship)
    warnings: List[str] = []
    confidence = 1.0

    if fuel_cost > fuel_avail:
        warnings.append(f"Insufficient fuel: need {fuel_cost:.1f}, have {fuel_avail:.1f}")
        confidence = max(0.0, fuel_avail / fuel_cost) if fuel_cost > 0 else 0

    return BurnPlan(
        command="navigate_to",
        estimated_time=est_time,
        fuel_cost=fuel_cost,
        delta_v=delta_v,
        confidence=confidence,
        phases=["accelerate", "coast", "brake", "hold"],
        warnings=warnings,
    )


def plan_intercept(ship, target_id: str, params: dict) -> BurnPlan:
    """Estimate burn plan for intercept.

    Args:
        ship: Ship object.
        target_id: Target sensor contact ID.
        params: Additional parameters.

    Returns:
        BurnPlan with estimates.
    """
    from hybrid.navigation.relative_motion import calculate_relative_motion

    target = _resolve_target(ship, target_id)
    warnings: List[str] = []
    if target is None:
        return BurnPlan(
            command="intercept", confidence=0.0,
            warnings=["Target not found in sensor contacts"],
        )

    rel = calculate_relative_motion(ship, target)
    max_accel = _max_accel(ship)
    distance = rel["range"]

    closing = -rel["range_rate"] if rel["closing"] else 0
    if closing > 1:
        est_time = distance / closing
    elif max_accel > 0:
        est_time = 2.0 * math.sqrt(distance / max_accel)
    else:
        est_time = 0
        warnings.append("No propulsion available")

    delta_v = rel["relative_velocity_magnitude"] + (max_accel * est_time * 0.3)
    fuel_cost = _fuel_for_delta_v(ship, delta_v)
    fuel_avail = _fuel_available(ship)
    confidence = 1.0

    if fuel_cost > fuel_avail:
        warnings.append("Insufficient fuel for intercept")
        confidence = max(0.0, fuel_avail / fuel_cost)

    if rel["range"] > 500_000:
        warnings.append("Target beyond effective range (>500km)")

    return BurnPlan(
        command="intercept",
        estimated_time=est_time,
        fuel_cost=fuel_cost,
        delta_v=delta_v,
        confidence=confidence,
        phases=["intercept", "approach", "match"],
        warnings=warnings,
    )


def plan_match(ship, target_id: str) -> BurnPlan:
    """Estimate burn plan for velocity matching.

    Args:
        ship: Ship object.
        target_id: Target sensor contact ID.

    Returns:
        BurnPlan with estimates.
    """
    from hybrid.navigation.relative_motion import calculate_relative_motion

    target = _resolve_target(ship, target_id)
    if target is None:
        return BurnPlan(
            command="match_velocity", confidence=0.0,
            warnings=["Target not found"],
        )

    rel = calculate_relative_motion(ship, target)
    delta_v = rel["relative_velocity_magnitude"]
    max_accel = _max_accel(ship)
    est_time = delta_v / max_accel if max_accel > 0 else 0
    fuel_cost = _fuel_for_delta_v(ship, delta_v)
    fuel_avail = _fuel_available(ship)
    confidence = 1.0
    warnings: List[str] = []

    if fuel_cost > fuel_avail:
        warnings.append("Insufficient fuel for velocity match")
        confidence = max(0.0, fuel_avail / fuel_cost)

    return BurnPlan(
        command="match_velocity",
        estimated_time=est_time,
        fuel_cost=fuel_cost,
        delta_v=delta_v,
        confidence=confidence,
        phases=["matching"],
        warnings=warnings,
    )


def plan_orbit(ship, center: dict, radius: float, params: dict) -> BurnPlan:
    """Estimate burn plan for orbit insertion.

    Args:
        ship: Ship object.
        center: Orbit center {x, y, z}.
        radius: Orbit radius in metres.
        params: Additional parameters.

    Returns:
        BurnPlan with estimates.
    """
    dist = magnitude(subtract_vectors(center, ship.position))
    approach_dist = abs(dist - radius)
    max_accel = _max_accel(ship)

    if max_accel > 0 and approach_dist > 0:
        approach_time = 2.0 * math.sqrt(approach_dist / max_accel)
    else:
        approach_time = 0

    speed_param = params.get("speed")
    if speed_param:
        orbital_speed = float(speed_param)
    else:
        orbital_speed = math.sqrt(0.5 * max_accel * radius) if max_accel > 0 else 0

    circ_dv = orbital_speed
    circ_time = circ_dv / max_accel if max_accel > 0 else 0

    delta_v = (max_accel * approach_time) + circ_dv
    fuel_cost = _fuel_for_delta_v(ship, delta_v)
    fuel_avail = _fuel_available(ship)
    warnings: List[str] = []
    confidence = 1.0

    if fuel_cost > fuel_avail:
        warnings.append("Insufficient fuel for orbit insertion")
        confidence = max(0.0, fuel_avail / fuel_cost)

    return BurnPlan(
        command="orbit",
        estimated_time=approach_time + circ_time,
        fuel_cost=fuel_cost,
        delta_v=delta_v,
        confidence=confidence,
        phases=["approach", "circularize", "orbit"],
        warnings=warnings,
    )


# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------

def _max_accel(ship) -> float:
    """Return ship's max linear acceleration in m/s^2."""
    prop = ship.systems.get("propulsion")
    if prop and hasattr(prop, "max_thrust") and ship.mass > 0:
        return prop.max_thrust / ship.mass
    return 0.0


def _fuel_available(ship) -> float:
    """Return remaining propellant in kg."""
    prop = ship.systems.get("propulsion")
    if prop and hasattr(prop, "fuel_level"):
        return prop.fuel_level
    return 0.0


def _fuel_for_delta_v(ship, delta_v: float) -> float:
    """Rough estimate of fuel required for a given delta-v.

    Uses simplified Tsiolkovsky: dm = m * (1 - exp(-dv / ve))
    with ve approximated from fuel_consumption rate.
    """
    prop = ship.systems.get("propulsion")
    if not prop or not hasattr(prop, "fuel_consumption"):
        return 0.0

    if prop.fuel_consumption > 0 and prop.max_thrust > 0:
        ve = prop.max_thrust / prop.fuel_consumption
    else:
        return 0.0

    if ve <= 0:
        return 0.0

    mass = ship.mass if ship.mass > 0 else 1000.0
    try:
        fuel = mass * (1.0 - math.exp(-delta_v / ve))
    except OverflowError:
        fuel = mass
    return fuel


def _resolve_target(ship, target_id: str):
    """Resolve a target ID to a contact object."""
    sensors = ship.systems.get("sensors")
    if sensors and hasattr(sensors, "get_contact"):
        return sensors.get_contact(target_id)
    return None
