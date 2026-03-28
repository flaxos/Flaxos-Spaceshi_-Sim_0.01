# hybrid/systems/sensors/emission_model.py
"""Physics-based emission model for sensor detection.

Ships emit detectable signatures across multiple spectra:
- **IR (infrared)**: Drive plumes, radiator heat, reactor waste heat.
  A ship burning hard at 5g is visible across the system; a cold drifter
  is nearly invisible on IR.
- **Radar cross-section (RCS)**: Physical size and reflectivity. Passive
  attribute of the target — active radar from the observer bounces off it
  with inverse-square falloff both ways (1/r^4 round-trip).
- **Lidar return**: Precise but narrow-beam active scan. Higher resolution
  than radar at close range but must be pointed at a known bearing.

Detection range depends on target signature vs sensor noise floor, not
arbitrary range caps. Resolution degrades with distance — at long range
you get a bearing and maybe a range estimate, not a detailed track.
"""

import math
from typing import Dict, Any, Optional

# Physical constants
STEFAN_BOLTZMANN = 5.67e-8  # W/m^2/K^4
SPACE_BACKGROUND_TEMP = 2.7  # K (CMB)

# Scaling constants for game balance
# These translate real physics into gameplay-meaningful detection ranges
IR_SENSITIVITY = 1.0e-6     # Sensor noise floor (W/m^2) — lower = more sensitive
RADAR_POWER_DEFAULT = 1.0e6  # Default radar transmit power (W)
RADAR_SENSITIVITY = 1.0e-12  # Radar receiver noise floor (W)
LIDAR_SENSITIVITY = 1.0e-10  # Lidar receiver noise floor (W)

# Drive plume thermal decay constants
# After cutting engines, residual plume/nozzle heat decays exponentially
# tau ~ 15s: nozzle glow fades over ~30-45s (2-3 time constants)
PLUME_DECAY_TAU = 15.0  # Seconds — thermal decay time constant
PLUME_RESIDUAL_FRACTION = 0.05  # 5% of peak plume IR lingers as nozzle glow


def calculate_ir_signature(ship) -> float:
    """Calculate a ship's infrared emission power in watts.

    IR signature comes from three sources:
    1. Drive plume: dominant when thrusting. Exhaust temperature scales
       with thrust magnitude (hotter exhaust = more IR). After cutting
       engines, residual nozzle glow decays exponentially.
    2. Radiator heat: ships must radiate waste heat from reactor and
       systems. Always present but modest compared to a drive plume.
    3. Base hull emission: warm hull in cold space. Minimal but non-zero.

    Args:
        ship: Ship object with systems and physical state.

    Returns:
        float: Total IR emission power in watts.
    """
    ir_watts = 0.0

    # --- 1. Drive plume (dominant source) ---
    # Thrust produces enormous IR from superheated exhaust
    thrust_magnitude = _get_thrust_magnitude(ship)
    propulsion = ship.systems.get("propulsion")
    max_thrust = getattr(propulsion, "max_thrust", 50000.0) if propulsion else 50000.0
    throttle_fraction = min(1.0, thrust_magnitude / max(max_thrust, 1.0))

    # Track plume thermal history for post-burn decay
    ir_history = _get_ir_history(ship)
    current_time = getattr(ship, "sim_time", 0.0)

    if thrust_magnitude > 0:
        # Drive plume IR scales with thrust^1.5 (non-linear: hotter + bigger plume)
        # A ship at full burn radiates ~10MW of IR
        plume_power = 1.0e7 * (throttle_fraction ** 1.5)
        ir_watts += plume_power

        # Record peak plume power and time for decay calculation
        ir_history["peak_plume_power"] = plume_power
        ir_history["last_burn_time"] = current_time
        ir_history["is_burning"] = True
    else:
        # Post-burn nozzle glow: exponential decay from last plume power
        # Physical basis: nozzle and exhaust bell retain heat after cutoff
        peak = ir_history.get("peak_plume_power", 0.0)
        last_burn = ir_history.get("last_burn_time", 0.0)
        was_burning = ir_history.get("is_burning", False)
        ir_history["is_burning"] = False

        if peak > 0 and current_time > last_burn:
            dt_since_burn = current_time - last_burn
            # Exponential decay: P(t) = P_peak * exp(-t/tau)
            decay = math.exp(-dt_since_burn / PLUME_DECAY_TAU)
            residual_power = peak * max(decay, PLUME_RESIDUAL_FRACTION)

            # Below 5% of peak, nozzle has cooled enough to ignore
            if residual_power > peak * PLUME_RESIDUAL_FRACTION * 1.01:
                ir_watts += residual_power
            else:
                # Fully cooled — clear the history
                ir_history["peak_plume_power"] = 0.0

    # Store decay metadata for telemetry
    ir_history["current_plume_ir"] = ir_watts

    # --- 2. Radiator / reactor waste heat ---
    # If thermal system exists, use its physics-based radiator IR emission.
    # This makes heat management directly visible to enemy sensors:
    # hotter ship = brighter IR = easier to detect.
    thermal = ship.systems.get("thermal")
    if thermal and hasattr(thermal, "get_radiator_ir_emission"):
        radiator_power = thermal.get_radiator_ir_emission()
        ir_watts += radiator_power
    else:
        # Legacy fallback: estimate from reactor heat
        reactor_heat_fraction = _get_reactor_heat_fraction(ship)
        radiator_power = 5.0e4 + reactor_heat_fraction * 4.5e5
        ir_watts += radiator_power

    # --- 3. Infrastructure heat ---
    # With thermal system: infrastructure heat is already captured in hull
    # temperature. Without: use mass-based estimate.
    if not thermal:
        mass = getattr(ship, "mass", 1000.0)
        infrastructure_watts = mass * 20.0  # 20 W/kg baseline
        ir_watts += infrastructure_watts

    # --- 4. Base hull thermal emission ---
    # Use dynamic hull temperature from thermal system if available.
    hull_area = _estimate_hull_area(ship)
    hull_temp = 300.0  # K default
    if thermal and hasattr(thermal, "hull_temperature"):
        hull_temp = thermal.hull_temperature
    hull_ir = STEFAN_BOLTZMANN * hull_area * (hull_temp**4 - SPACE_BACKGROUND_TEMP**4)
    ir_watts += hull_ir

    # Apply ship-specific IR modifier (stealth coating, etc.)
    ir_modifier = _get_ship_signature_modifier(ship, "ir_modifier")
    ir_watts *= ir_modifier

    # ECM: EMCON mode reduces IR emissions (shutting down non-essential
    # systems, minimising thermal output). This is the physical basis
    # for signature reduction — you actually emit less, not a magic cloak.
    ecm = ship.systems.get("ecm")
    if ecm and hasattr(ecm, "get_emcon_ir_modifier"):
        ir_watts *= ecm.get_emcon_ir_modifier()

    return ir_watts


def calculate_radar_cross_section(ship) -> float:
    """Calculate a ship's radar cross-section in square metres.

    RCS depends on physical size and shape. Larger ships reflect more
    radar energy. Ships can have reduced RCS through stealth shaping.

    Args:
        ship: Ship object.

    Returns:
        float: Radar cross-section in m^2.
    """
    # Base RCS from mass (rough correlation: RCS ~ mass^(2/3))
    # A 1000kg ship ~ 100m^2 RCS, a 100,000kg station ~ 2150m^2
    # Space structures have flat panels, radiators, and solar arrays
    # that reflect radar strongly compared to aircraft.
    mass = getattr(ship, "mass", 1000.0)
    base_rcs = mass ** (2.0 / 3.0) * 0.1

    # Apply ship-specific RCS modifier (stealth shaping)
    rcs_modifier = _get_ship_signature_modifier(ship, "rcs_modifier")
    base_rcs *= rcs_modifier

    # ECM: EMCON mode slightly reduces RCS (power down active emitters,
    # retract movable surfaces). Effect is modest — you can't change hull shape.
    ecm = ship.systems.get("ecm")
    if ecm and hasattr(ecm, "get_emcon_rcs_modifier"):
        base_rcs *= ecm.get_emcon_rcs_modifier()

    # ECCM: Burn-through mode massively increases own radar emissions,
    # making the ship much easier to detect on enemy passive sensors.
    # This is the trade-off for the increased detection capability.
    sensors = ship.systems.get("sensors")
    if sensors and hasattr(sensors, "eccm"):
        base_rcs *= sensors.eccm.get_burn_through_emission_multiplier()

    return base_rcs


def calculate_ir_detection_range(ir_watts: float, sensor_sensitivity: float = None) -> float:
    """Calculate maximum detection range for an IR source.

    Detection occurs when received flux > sensor noise floor.
    IR radiates isotropically, so flux = P / (4*pi*r^2).
    Range = sqrt(P / (4*pi*sensitivity)).

    Args:
        ir_watts: IR emission power in watts.
        sensor_sensitivity: Sensor noise floor in W/m^2.

    Returns:
        float: Detection range in metres.
    """
    if ir_watts <= 0:
        return 0.0

    sensitivity = sensor_sensitivity or IR_SENSITIVITY
    # r = sqrt(P / (4 * pi * noise_floor))
    detection_range = math.sqrt(ir_watts / (4.0 * math.pi * sensitivity))
    return detection_range


def calculate_radar_detection_range(rcs: float, transmit_power: float = None,
                                     receiver_sensitivity: float = None) -> float:
    """Calculate maximum radar detection range.

    Radar equation (simplified): received power = Pt * G^2 * lambda^2 * RCS / ((4*pi)^3 * r^4)
    For gameplay we simplify to: r^4 = Pt * RCS / (noise_floor * k)
    where k absorbs antenna gain, wavelength, and (4*pi)^3.

    The key physics: radar signal falls off as 1/r^4 (out and back),
    so doubling range requires 16x the power or RCS.

    Args:
        rcs: Target radar cross-section in m^2.
        transmit_power: Radar transmit power in watts.
        receiver_sensitivity: Receiver noise floor in watts.

    Returns:
        float: Detection range in metres.
    """
    if rcs <= 0:
        return 0.0

    tx_power = transmit_power or RADAR_POWER_DEFAULT
    sensitivity = receiver_sensitivity or RADAR_SENSITIVITY

    # r^4 = Pt * RCS / sensitivity  (simplified radar equation)
    r4 = tx_power * rcs / sensitivity
    detection_range = r4 ** 0.25
    return detection_range


def calculate_lidar_detection_range(rcs: float, transmit_power: float = None,
                                     receiver_sensitivity: float = None) -> float:
    """Calculate maximum lidar detection range.

    Lidar uses focused laser beam — better angular resolution than radar
    but same inverse-square-squared physics for the return signal.
    Lidar transmitters are typically lower power but more focused.

    Args:
        rcs: Target cross-section in m^2.
        transmit_power: Lidar transmit power in watts.
        receiver_sensitivity: Receiver noise floor in watts.

    Returns:
        float: Detection range in metres.
    """
    if rcs <= 0:
        return 0.0

    # Lidar is lower power but more sensitive receiver (focused beam)
    tx_power = transmit_power or (RADAR_POWER_DEFAULT * 0.01)  # 1% of radar power
    sensitivity = receiver_sensitivity or LIDAR_SENSITIVITY

    r4 = tx_power * rcs / sensitivity
    detection_range = r4 ** 0.25
    return detection_range


def calculate_detection_quality(distance: float, detection_range: float) -> float:
    """Calculate detection quality/resolution based on distance.

    At close range: full track (position, velocity, classification).
    At long range: just a bearing and rough range estimate.

    Uses smoothstep falloff so quality stays high within ~50% of
    detection range, then degrades toward the edge.

    Args:
        distance: Distance to target in metres.
        detection_range: Maximum detection range in metres.

    Returns:
        float: Quality factor 0.0 (nothing) to 1.0 (perfect track).
    """
    if detection_range <= 0 or distance > detection_range:
        return 0.0

    ratio = distance / detection_range

    # Smoothstep: stays near 1.0 within 40% of range, drops off from 40-100%
    t = max(0.0, min(1.0, (ratio - 0.4) / 0.6))
    smoothstep = 3.0 * t * t - 2.0 * t * t * t
    quality = 1.0 - smoothstep

    return max(0.05, min(1.0, quality))


def get_ship_emissions(ship) -> Dict[str, Any]:
    """Calculate all emission signatures for a ship.

    This is the main entry point used by the sensor system each tick.

    Args:
        ship: Ship object.

    Returns:
        dict: Emission data with ir_watts, rcs_m2, ir_range, radar_range,
              lidar_range, and component breakdowns.
    """
    ir_watts = calculate_ir_signature(ship)
    rcs = calculate_radar_cross_section(ship)

    thrust_magnitude = _get_thrust_magnitude(ship)
    is_thrusting = thrust_magnitude > 1.0

    # IR profile data for tactical awareness
    ir_history = _get_ir_history(ship)
    cold_drift = getattr(ship, "_cold_drift_active", False)

    # Compute IR level category for status display
    ir_level = _categorize_ir_level(ir_watts, is_thrusting, cold_drift)

    return {
        "ir_watts": ir_watts,
        "rcs_m2": rcs,
        "ir_detection_range": calculate_ir_detection_range(ir_watts),
        "is_thrusting": is_thrusting,
        "thrust_magnitude": thrust_magnitude,
        # IR signature profile
        "ir_level": ir_level,  # "minimal" | "low" | "moderate" | "high" | "extreme"
        "plume_cooling": ir_history.get("peak_plume_power", 0) > 0 and not is_thrusting,
        "cold_drift_active": cold_drift,
    }


# --- Internal helpers ---

def _get_thrust_magnitude(ship) -> float:
    """Get current thrust magnitude from ship state."""
    from hybrid.utils.math_utils import magnitude as vec_magnitude

    # Try thrust vector first
    thrust = getattr(ship, "thrust", None)
    if thrust and isinstance(thrust, dict):
        mag = vec_magnitude(thrust)
        if mag > 0.01:
            return mag

    # Fall back to propulsion system state
    propulsion = ship.systems.get("propulsion")
    if propulsion:
        if hasattr(propulsion, "throttle") and hasattr(propulsion, "max_thrust"):
            return propulsion.throttle * propulsion.max_thrust
        if hasattr(propulsion, "_last_thrust_magnitude"):
            return propulsion._last_thrust_magnitude

    return 0.0


def _get_reactor_heat_fraction(ship) -> float:
    """Get reactor heat as fraction of capacity (0.0-1.0)."""
    if hasattr(ship, "damage_model"):
        reactor_sub = ship.damage_model.subsystems.get("reactor")
        if reactor_sub and hasattr(reactor_sub, "heat") and hasattr(reactor_sub, "max_heat"):
            if reactor_sub.max_heat > 0:
                return min(1.0, reactor_sub.heat / reactor_sub.max_heat)

    # Default: idle reactor
    return 0.1


def _estimate_hull_area(ship) -> float:
    """Estimate hull surface area from mass.

    Rough approximation: area ~ mass^(2/3) for uniform density.
    A 1000kg ship ~ 100m^2 surface area.
    """
    mass = getattr(ship, "mass", 1000.0)
    return mass ** (2.0 / 3.0)


def _get_ship_signature_modifier(ship, modifier_name: str) -> float:
    """Get a signature modifier from ship's sensor config.

    Ships can define modifiers in their JSON config under systems.sensors:
        "ir_modifier": 0.5    (stealth coating halves IR)
        "rcs_modifier": 0.3   (stealth shaping reduces RCS by 70%)

    Args:
        ship: Ship object.
        modifier_name: Name of the modifier field.

    Returns:
        float: Modifier value (default 1.0 = no modification).
    """
    sensors_config = {}
    sensors = ship.systems.get("sensors")
    if sensors:
        if hasattr(sensors, "config"):
            sensors_config = sensors.config
        elif isinstance(sensors, dict):
            sensors_config = sensors

    return float(sensors_config.get(modifier_name, 1.0))


def _get_ir_history(ship) -> dict:
    """Get or initialize the IR thermal history for a ship.

    Tracks plume power over time for post-burn decay calculations.
    Stored on the ship object to persist across ticks.
    """
    if not hasattr(ship, "_ir_history"):
        ship._ir_history = {
            "peak_plume_power": 0.0,
            "last_burn_time": 0.0,
            "is_burning": False,
            "current_plume_ir": 0.0,
        }
    return ship._ir_history


def _categorize_ir_level(ir_watts: float, is_thrusting: bool,
                         cold_drift: bool) -> str:
    """Categorize IR signature into human-readable levels.

    Used by the GUI to display signature status at a glance.

    Args:
        ir_watts: Total IR emission in watts.
        is_thrusting: Whether engines are active.
        cold_drift: Whether emergency cold-drift mode is active.

    Returns:
        str: IR level category.
    """
    if cold_drift:
        return "minimal"
    if ir_watts < 1.0e4:
        return "minimal"  # <10kW — nearly invisible
    if ir_watts < 1.0e5:
        return "low"      # 10-100kW — radiator/hull heat only
    if ir_watts < 1.0e6:
        return "moderate"  # 100kW-1MW — partial thrust or post-burn glow
    if ir_watts < 5.0e6:
        return "high"     # 1-5MW — significant thrust
    return "extreme"      # >5MW — full burn, visible system-wide
