# hybrid/systems/science_system.py
"""Science station analysis system.

Provides deep sensor analysis, contact classification, spectral analysis,
mass estimation, and threat assessment.  Science gives other stations the
intelligence they need to make tactical decisions.

Design principles:
- Analysis quality depends on sensor health, contact range, and track age.
- Closer range + better sensors = more accurate results.
- Analysis takes time conceptually — results are instantaneous commands but
  confidence reflects how much data the sensors have gathered.
- No magic: all estimates derive from physics (emissions, RCS, F=ma).
"""

import logging
import math
from typing import Dict, Any, Optional
from hybrid.core.base_system import BaseSystem
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_SCIENCE_CONFIG = {
    "power_draw": 1.0,  # kW
}

# Ship class profiles for classification matching
# Maps mass ranges and RCS ranges to probable ship classes
SHIP_CLASS_PROFILES = {
    "corvette":  {"mass_min": 1000, "mass_max": 5000,   "length_min": 30,  "length_max": 60},
    "frigate":   {"mass_min": 5000, "mass_max": 20000,  "length_min": 60,  "length_max": 120},
    "destroyer": {"mass_min": 15000, "mass_max": 50000, "length_min": 100, "length_max": 180},
    "cruiser":   {"mass_min": 40000, "mass_max": 150000, "length_min": 150, "length_max": 300},
    "freighter": {"mass_min": 20000, "mass_max": 200000, "length_min": 100, "length_max": 400},
}

# IR signature thresholds for drive type inference
DRIVE_TYPE_THRESHOLDS = {
    "epstein":  1.0e6,   # >1MW plume = high-performance drive
    "nuclear":  1.0e5,   # 100kW-1MW = nuclear thermal
    "ion":      1.0e3,   # 1-100kW = efficient ion drive
}


class ScienceSystem(BaseSystem):
    """Science station sensor analysis system.

    Provides:
    - analyze_contact: Deep sensor analysis of a tracked contact
    - spectral_analysis: Emission signature breakdown (IR, RCS)
    - estimate_mass: Mass estimation from RCS and observed acceleration
    - assess_threat: Tactical threat evaluation
    - science_status: System status readout
    """

    def __init__(self, config: Optional[dict] = None):
        config = config if config is not None else {}
        for key, default in DEFAULT_SCIENCE_CONFIG.items():
            if key not in config:
                config[key] = default
        super().__init__(config)
        self._sim_time: float = 0.0

    def tick(self, dt: float, ship=None, event_bus=None):
        """Update science system each tick."""
        if not self.enabled or ship is None or dt <= 0:
            return
        self._sim_time += dt

    def command(self, action: str, params: dict = None) -> dict:
        """Dispatch science commands."""
        params = params or {}
        if action == "analyze_contact":
            return self._cmd_analyze_contact(params)
        elif action == "spectral_analysis":
            return self._cmd_spectral_analysis(params)
        elif action == "estimate_mass":
            return self._cmd_estimate_mass(params)
        elif action == "assess_threat":
            return self._cmd_assess_threat(params)
        elif action == "science_status":
            return self._cmd_science_status(params)
        return error_dict("UNKNOWN_COMMAND", f"Unknown science command: {action}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_sensor_health(self, ship) -> float:
        """Get sensor health factor from ship damage model."""
        if ship and hasattr(ship, "get_effective_factor"):
            return ship.get_effective_factor("sensors")
        return 1.0

    def _get_contact_and_target(self, params: dict):
        """Resolve a contact_id to ContactData and the real target ship.

        Returns:
            (contact, target_ship, error_dict_or_None)
        """
        ship = params.get("ship") or params.get("_ship")
        contact_id = params.get("contact_id")

        if not contact_id:
            return None, None, error_dict("MISSING_PARAM", "Must specify 'contact_id'")
        if not ship:
            return None, None, error_dict("NO_SHIP", "No ship context")

        sensors = ship.systems.get("sensors")
        if not sensors or not hasattr(sensors, "contact_tracker"):
            return None, None, error_dict("NO_SENSORS", "Sensor system not available")

        contact = sensors.contact_tracker.get_contact(contact_id)
        if not contact:
            return None, None, error_dict("CONTACT_NOT_FOUND",
                                          f"No contact with ID '{contact_id}'")

        # Resolve target ship from all_ships reference
        target_ship = None
        all_ships = params.get("all_ships")
        if not all_ships:
            all_ships = getattr(ship, "_all_ships_ref", None)

        if all_ships:
            # Find the real ship ID from the contact tracker mapping
            tracker = sensors.contact_tracker
            real_id = None
            for rid, sid in tracker.id_mapping.items():
                if sid == contact.id:
                    real_id = rid
                    break
            if real_id and isinstance(all_ships, dict):
                target_ship = all_ships.get(real_id)
            elif real_id:
                for s in all_ships:
                    if getattr(s, "id", None) == real_id:
                        target_ship = s
                        break

        return contact, target_ship, None

    def _compute_analysis_quality(self, contact, ship) -> float:
        """Compute overall analysis quality (0-1) from sensor health, range, age."""
        sensor_factor = self._get_sensor_health(ship)
        confidence = getattr(contact, "confidence", 0.5)
        age = contact.get_age(self._sim_time) if hasattr(contact, "get_age") else 0.0
        age_factor = max(0.1, 1.0 - (age / 120.0))  # Degrades over 2 minutes
        return min(1.0, sensor_factor * confidence * age_factor)

    def _classify_from_mass(self, mass_kg: float) -> str:
        """Classify ship type from estimated mass."""
        for cls_name, profile in SHIP_CLASS_PROFILES.items():
            if profile["mass_min"] <= mass_kg <= profile["mass_max"]:
                return cls_name
        if mass_kg < 1000:
            return "small_craft"
        return "capital_ship"

    def _infer_drive_type(self, ir_watts: float, is_thrusting: bool) -> dict:
        """Infer drive type from IR signature."""
        if not is_thrusting or ir_watts < 100:
            return {"drive_type": "unknown", "burn_state": "cold",
                    "estimated_thrust_kn": 0.0}

        drive_type = "unknown"
        if ir_watts > DRIVE_TYPE_THRESHOLDS["epstein"]:
            drive_type = "epstein"
        elif ir_watts > DRIVE_TYPE_THRESHOLDS["nuclear"]:
            drive_type = "nuclear_thermal"
        elif ir_watts > DRIVE_TYPE_THRESHOLDS["ion"]:
            drive_type = "ion"

        # Rough thrust estimate from plume power:
        # plume_power ~ 1e7 * (throttle^1.5) where throttle = thrust/max_thrust
        # Invert: throttle ~ (plume_power / 1e7)^(2/3)
        throttle_est = min(1.0, (ir_watts / 1.0e7) ** (2.0 / 3.0))
        # Assume ~50kN max thrust for generic estimate
        thrust_kn = throttle_est * 50.0

        burn_state = "full" if throttle_est > 0.8 else "partial"

        return {
            "drive_type": drive_type,
            "burn_state": burn_state,
            "estimated_thrust_kn": round(thrust_kn, 1),
        }

    # ------------------------------------------------------------------
    # Command: analyze_contact
    # ------------------------------------------------------------------

    def _cmd_analyze_contact(self, params: dict) -> dict:
        """Perform deep sensor analysis on a contact.

        Returns comprehensive contact data: position, velocity, distance,
        emissions profile, and preliminary classification.
        """
        ship = params.get("ship") or params.get("_ship")
        contact, target_ship, err = self._get_contact_and_target(params)
        if err:
            return err

        quality = self._compute_analysis_quality(contact, ship)

        # Build contact data from sensor track
        from hybrid.utils.math_utils import calculate_distance
        distance = calculate_distance(ship.position, contact.position)
        age = contact.get_age(self._sim_time) if hasattr(contact, "get_age") else 0.0

        contact_data = {
            "position": dict(contact.position),
            "velocity": dict(contact.velocity),
            "distance": round(distance, 1),
            "confidence": round(quality, 3),
            "detection_method": contact.detection_method,
            "age": round(age, 1),
        }

        # Emissions analysis (if target ship is available for detailed data)
        emissions = self._get_emissions_data(target_ship, quality)

        # Ship classification attempt
        classification = contact.classification or "Unknown"
        if target_ship and quality > 0.4:
            classification = self._attempt_classification(target_ship, quality)

        return success_dict(
            f"Analysis of {contact.id}: {classification} at {distance/1000:.1f}km",
            contact_id=contact.id,
            contact_data=contact_data,
            emissions=emissions,
            classification=classification,
            analysis_quality=round(quality, 3),
        )

    # ------------------------------------------------------------------
    # Command: spectral_analysis
    # ------------------------------------------------------------------

    def _cmd_spectral_analysis(self, params: dict) -> dict:
        """Analyze emission signature to identify drive type and thermal state."""
        ship = params.get("ship") or params.get("_ship")
        contact, target_ship, err = self._get_contact_and_target(params)
        if err:
            return err

        quality = self._compute_analysis_quality(contact, ship)

        if quality < 0.15:
            return error_dict("INSUFFICIENT_DATA",
                              f"Track quality too low for spectral analysis "
                              f"(quality: {quality:.0%})")

        spectral_data = {}

        # IR signature breakdown
        ir_data = self._get_ir_breakdown(target_ship, quality)
        spectral_data["ir_signature"] = ir_data

        # RCS data
        rcs_data = self._get_rcs_data(target_ship, quality)
        spectral_data["rcs_data"] = rcs_data

        # Drive type inference from IR
        from hybrid.systems.sensors.emission_model import calculate_ir_signature
        ir_watts = calculate_ir_signature(target_ship) if target_ship else 0.0
        thrust_mag = self._get_thrust_magnitude(target_ship)
        is_thrusting = thrust_mag > 1.0

        drive_info = self._infer_drive_type(ir_watts, is_thrusting)
        spectral_data["drive_inference"] = drive_info

        return success_dict(
            f"Spectral analysis of {contact.id}: "
            f"drive={drive_info['drive_type']}, burn={drive_info['burn_state']}",
            contact_id=contact.id,
            spectral_data=spectral_data,
            analysis_quality=round(quality, 3),
        )

    # ------------------------------------------------------------------
    # Command: estimate_mass
    # ------------------------------------------------------------------

    def _cmd_estimate_mass(self, params: dict) -> dict:
        """Estimate target mass from RCS and observed acceleration (F=ma)."""
        ship = params.get("ship") or params.get("_ship")
        contact, target_ship, err = self._get_contact_and_target(params)
        if err:
            return err

        quality = self._compute_analysis_quality(contact, ship)

        if quality < 0.2:
            return error_dict("INSUFFICIENT_DATA",
                              f"Track quality too low for mass estimation "
                              f"(quality: {quality:.0%})")

        # Method 1: RCS-based mass inference
        # RCS = mass^(2/3) * 0.1 → mass = (RCS / 0.1)^(3/2)
        from hybrid.systems.sensors.emission_model import calculate_radar_cross_section
        rcs = calculate_radar_cross_section(target_ship) if target_ship else 0.0
        rcs_mass_estimate = (rcs / 0.1) ** 1.5 if rcs > 0 else 0.0

        # Method 2: F=ma from observed acceleration and estimated thrust
        fma_mass_estimate = None
        method = "rcs_inference"
        if target_ship:
            from hybrid.utils.math_utils import magnitude
            accel_mag = magnitude(getattr(target_ship, "acceleration", {"x": 0, "y": 0, "z": 0}))
            thrust_mag = self._get_thrust_magnitude(target_ship)

            if accel_mag > 0.01 and thrust_mag > 1.0:
                fma_mass_estimate = thrust_mag / accel_mag
                method = "fma_observation"

        # Best estimate: prefer F=ma when available (more accurate)
        if fma_mass_estimate and fma_mass_estimate > 0:
            estimated_mass = fma_mass_estimate
        else:
            estimated_mass = rcs_mass_estimate

        # Confidence bounds based on quality
        uncertainty = 0.5 - (quality * 0.35)  # 50% uncertain at low Q, 15% at high Q
        range_low = estimated_mass * (1.0 - uncertainty)
        range_high = estimated_mass * (1.0 + uncertainty)

        confidence = "high" if quality > 0.7 else ("moderate" if quality > 0.4 else "low")

        # Dimension inference from mass
        ship_class = self._classify_from_mass(estimated_mass)
        profile = SHIP_CLASS_PROFILES.get(ship_class, {})
        est_length = (profile.get("length_min", 0) + profile.get("length_max", 0)) / 2.0

        return success_dict(
            f"Mass estimate for {contact.id}: {estimated_mass:.0f}kg "
            f"({confidence} confidence, {method})",
            contact_id=contact.id,
            mass_estimate={
                "estimated_mass": round(estimated_mass, 1),
                "confidence": confidence,
                "method": method,
                "range_low": round(range_low, 1),
                "range_high": round(range_high, 1),
            },
            dimension_inference={
                "estimated_length": round(est_length, 1),
                "ship_class": ship_class,
            },
            analysis_quality=round(quality, 3),
        )

    # ------------------------------------------------------------------
    # Command: assess_threat
    # ------------------------------------------------------------------

    def _cmd_assess_threat(self, params: dict) -> dict:
        """Evaluate target as tactical threat based on available data."""
        ship = params.get("ship") or params.get("_ship")
        contact, target_ship, err = self._get_contact_and_target(params)
        if err:
            return err

        quality = self._compute_analysis_quality(contact, ship)

        # Start threat scoring (0-100)
        threat_score = 0.0
        notes = []

        # 1. Weapons threat (from ship class / observed weapons)
        weapons_threat = "unknown"
        if target_ship and quality > 0.5:
            combat = target_ship.systems.get("combat")
            if combat and hasattr(combat, "get_state"):
                combat_state = combat.get_state()
                weapon_count = len(combat_state.get("truth_weapons", {}))
                if weapon_count > 0:
                    threat_score += min(30, weapon_count * 10)
                    weapons_threat = f"{weapon_count} weapon(s) detected"
                    notes.append(f"Armed: {weapon_count} weapon system(s)")
                else:
                    weapons_threat = "no weapons detected"
            else:
                weapons_threat = "unknown"
                threat_score += 10  # Unknown = assume some danger
        elif quality <= 0.5:
            weapons_threat = "insufficient data"
            threat_score += 15  # Unknown = moderate threat

        # 2. Mobility threat (acceleration capability)
        mobility_threat = "unknown"
        if target_ship:
            from hybrid.utils.math_utils import magnitude
            accel = magnitude(getattr(target_ship, "acceleration",
                                      {"x": 0, "y": 0, "z": 0}))
            mass = getattr(target_ship, "mass", 1000.0)

            if accel > 10:
                threat_score += 20
                mobility_threat = "high acceleration"
                notes.append(f"High-g maneuver capability ({accel:.1f} m/s²)")
            elif accel > 2:
                threat_score += 10
                mobility_threat = "moderate acceleration"
            else:
                mobility_threat = "low/stationary"

        # 3. Range/geometry factor
        from hybrid.utils.math_utils import calculate_distance
        distance = calculate_distance(ship.position, contact.position)
        if distance < 50_000:  # <50km
            threat_score += 20
            notes.append("Close range — within weapon envelope")
        elif distance < 500_000:  # <500km
            threat_score += 10
            notes.append("Medium range — within railgun envelope")

        # 4. ECM / countermeasures detection
        countermeasures = {
            "ecm_detected": False,
            "emcon_active": False,
            "defensive_systems": [],
        }
        if target_ship and quality > 0.4:
            ecm = target_ship.systems.get("ecm")
            if ecm and hasattr(ecm, "get_state"):
                ecm_state = ecm.get_state()
                if ecm_state.get("jammer_active"):
                    countermeasures["ecm_detected"] = True
                    countermeasures["defensive_systems"].append("active_jammer")
                    threat_score += 10
                    notes.append("Active jammer detected")
                if ecm_state.get("emcon_active"):
                    countermeasures["emcon_active"] = True
                    threat_score += 5
                    notes.append("EMCON mode — attempting signature reduction")

        # 5. Armor assessment (if we know the class)
        armor_threat = "unknown"
        if target_ship and hasattr(target_ship, "armor") and target_ship.armor:
            armor = target_ship.armor
            avg_thickness = 0.0
            count = 0
            for section in armor.values():
                if isinstance(section, dict) and "thickness_cm" in section:
                    avg_thickness += section["thickness_cm"]
                    count += 1
            if count > 0:
                avg_thickness /= count
                if avg_thickness > 5.0:
                    armor_threat = "heavy"
                    threat_score += 10
                elif avg_thickness > 2.0:
                    armor_threat = "moderate"
                    threat_score += 5
                else:
                    armor_threat = "light"

        # Clamp score
        threat_score = min(100, max(0, threat_score))

        # Categorize
        if threat_score >= 80:
            overall = "critical"
        elif threat_score >= 60:
            overall = "high"
        elif threat_score >= 35:
            overall = "moderate"
        elif threat_score >= 15:
            overall = "low"
        else:
            overall = "minimal"

        # Tactical notes
        tactical_notes = "; ".join(notes) if notes else "Insufficient data for detailed assessment"

        # Recommendations
        recommendations = self._generate_recommendations(
            overall, distance, weapons_threat, countermeasures)

        return success_dict(
            f"Threat assessment for {contact.id}: {overall.upper()} "
            f"(score {threat_score:.0f}/100)",
            contact_id=contact.id,
            threat_assessment={
                "overall_threat": overall,
                "threat_score": round(threat_score, 1),
                "weapons_threat": weapons_threat,
                "armor_threat": armor_threat,
                "mobility_threat": mobility_threat,
                "countermeasures": countermeasures,
                "tactical_notes": tactical_notes,
            },
            recommendations=recommendations,
            analysis_quality=round(quality, 3),
        )

    # ------------------------------------------------------------------
    # Command: science_status
    # ------------------------------------------------------------------

    def _cmd_science_status(self, params: dict) -> dict:
        """Return science system status."""
        ship = params.get("ship") or params.get("_ship")

        sensor_health = self._get_sensor_health(ship) if ship else 1.0

        # Count contacts
        contact_count = 0
        if ship:
            sensors = ship.systems.get("sensors")
            if sensors and hasattr(sensors, "contact_tracker"):
                contacts = sensors.contact_tracker.get_all_contacts(self._sim_time)
                contact_count = len(contacts)

        state = self.get_state()
        state["ok"] = True
        state["sensor_health"] = round(sensor_health, 3)
        state["tracked_contacts"] = contact_count
        state["analysis_capabilities"] = {
            "spectral_analysis": sensor_health > 0.15,
            "mass_estimation": sensor_health > 0.2,
            "threat_assessment": True,
            "class_identification": sensor_health > 0.4,
        }
        return state

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        """Return serializable science telemetry."""
        return {
            "enabled": self.enabled,
            "power_draw": self.power_draw,
        }

    # ------------------------------------------------------------------
    # Internal analysis helpers
    # ------------------------------------------------------------------

    def _get_emissions_data(self, target_ship, quality: float) -> dict:
        """Get emission data for a target ship."""
        if not target_ship or quality < 0.2:
            return {
                "ir_watts": None,
                "rcs_m2": None,
                "signature_strength": "unknown",
            }

        from hybrid.systems.sensors.emission_model import (
            calculate_ir_signature, calculate_radar_cross_section,
            calculate_ir_detection_range, _categorize_ir_level,
        )
        ir_watts = calculate_ir_signature(target_ship)
        rcs = calculate_radar_cross_section(target_ship)
        ir_range = calculate_ir_detection_range(ir_watts)
        thrust_mag = self._get_thrust_magnitude(target_ship)

        return {
            "ir_watts": round(ir_watts, 1),
            "rcs_m2": round(rcs, 2),
            "ir_detection_range": round(ir_range, 1),
            "signature_strength": _categorize_ir_level(
                ir_watts, thrust_mag > 1.0,
                getattr(target_ship, "_cold_drift_active", False)),
        }

    def _get_ir_breakdown(self, target_ship, quality: float) -> dict:
        """Get detailed IR signature breakdown."""
        if not target_ship or quality < 0.2:
            return {"total_ir": None, "components": "insufficient data"}

        from hybrid.systems.sensors.emission_model import (
            calculate_ir_signature, _get_ir_history,
        )
        ir_watts = calculate_ir_signature(target_ship)
        ir_history = _get_ir_history(target_ship)

        plume_ir = ir_history.get("current_plume_ir", 0.0)
        is_burning = ir_history.get("is_burning", False)
        peak_plume = ir_history.get("peak_plume_power", 0.0)

        # Estimate radiator + hull contribution
        non_plume_ir = max(0.0, ir_watts - plume_ir)

        return {
            "total_ir": round(ir_watts, 1),
            "plume_ir": round(plume_ir, 1),
            "radiator_hull_ir": round(non_plume_ir, 1),
            "is_burning": is_burning,
            "post_burn_decay": peak_plume > 0 and not is_burning,
        }

    def _get_rcs_data(self, target_ship, quality: float) -> dict:
        """Get RCS data for a target ship."""
        if not target_ship or quality < 0.2:
            return {"effective_rcs": None, "data_available": False}

        from hybrid.systems.sensors.emission_model import calculate_radar_cross_section
        rcs = calculate_radar_cross_section(target_ship)

        emcon_active = False
        ecm = target_ship.systems.get("ecm") if hasattr(target_ship, "systems") else None
        if ecm and hasattr(ecm, "emcon_active"):
            emcon_active = ecm.emcon_active

        return {
            "effective_rcs": round(rcs, 2),
            "emcon_detected": emcon_active,
            "data_available": True,
        }

    def _attempt_classification(self, target_ship, quality: float) -> str:
        """Attempt to classify a ship from its properties."""
        # IFF transponder (highest confidence)
        comms = target_ship.systems.get("comms") if hasattr(target_ship, "systems") else None
        if comms and hasattr(comms, "get_transponder_broadcast"):
            broadcast = comms.get_transponder_broadcast()
            if broadcast:
                name = getattr(target_ship, "name", None)
                cls = getattr(target_ship, "class_type", "unknown")
                if name:
                    return f"{cls} ({name})"
                return cls

        # Mass-based classification
        mass = getattr(target_ship, "mass", 0)
        if mass > 0 and quality > 0.5:
            return self._classify_from_mass(mass)

        return "Unknown"

    @staticmethod
    def _get_thrust_magnitude(ship) -> float:
        """Get current thrust magnitude for a ship."""
        if not ship:
            return 0.0
        from hybrid.utils.math_utils import magnitude as vec_magnitude
        thrust = getattr(ship, "thrust", None)
        if thrust and isinstance(thrust, dict):
            mag = vec_magnitude(thrust)
            if mag > 0.01:
                return mag
        propulsion = ship.systems.get("propulsion") if hasattr(ship, "systems") else None
        if propulsion:
            if hasattr(propulsion, "throttle") and hasattr(propulsion, "max_thrust"):
                return propulsion.throttle * propulsion.max_thrust
        return 0.0

    @staticmethod
    def _generate_recommendations(threat_level: str, distance: float,
                                   weapons_threat: str,
                                   countermeasures: dict) -> list:
        """Generate tactical recommendations based on threat assessment."""
        recs = []
        if threat_level in ("critical", "high"):
            recs.append("Recommend battle stations — high threat contact")
            if distance < 50_000:
                recs.append("Contact within close weapons range — consider evasive action")
            if countermeasures.get("ecm_detected"):
                recs.append("Active jamming detected — switch to passive tracking")
        elif threat_level == "moderate":
            recs.append("Maintain sensor watch — moderate threat")
            if "unknown" in weapons_threat:
                recs.append("Weapons status unknown — recommend caution")
        elif threat_level == "low":
            recs.append("Low threat — continue monitoring")
        else:
            recs.append("Minimal threat — routine tracking")

        if countermeasures.get("emcon_active"):
            recs.append("Target in EMCON — may be attempting to reduce detection")

        return recs
