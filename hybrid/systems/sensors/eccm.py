# hybrid/systems/sensors/eccm.py
"""Electronic Counter-Countermeasures (ECCM) system.

ECCM provides counterplay to enemy ECM. Each technique has a physical
basis and a real trade-off -- there is no free lunch in the EM spectrum.

Techniques:
- **Frequency hopping**: Rapidly change radar frequency to decorrelate
  from noise jamming. Reduces jamming effectiveness 60-80% but increases
  sensor power draw (frequency synthesiser is power-hungry).
- **Burn-through mode**: Brute-force increase radar power to overcome
  jamming. Massive heat generation and reveals own position (bigger radar
  emission = easier to detect). Effective at short-to-medium range where
  the 1/r^4 radar equation is in your favour.
- **Multi-spectral correlation**: Cross-reference IR, radar, and lidar
  returns to filter out single-spectrum countermeasures (chaff only
  affects radar, flares only affect IR). Requires all three sensor types
  functional -- if any is damaged, correlation degrades.
- **Home-on-jam**: Use the enemy's jamming emissions as a targeting
  source. Turns their ECM into a beacon. Provides bearing only (not
  range), since you are measuring the jammer's signal direction, not
  round-trip time. Range requires triangulation or closing.

ECCM effectiveness scales with sensor subsystem health. Damaged sensors
can still attempt ECCM but with reduced effectiveness.
"""

from __future__ import annotations

import logging
import math
from enum import Enum
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ECCMMode(Enum):
    """Active ECCM operating modes."""
    OFF = "off"
    FREQUENCY_HOP = "frequency_hop"
    BURN_THROUGH = "burn_through"


# Default ECCM configuration
DEFAULT_ECCM_CONFIG = {
    # Frequency hopping
    "freq_hop_jam_reduction": 0.70,      # 70% reduction in jamming effectiveness
    "freq_hop_power_multiplier": 1.8,    # 80% more sensor power draw
    "freq_hop_min_reduction": 0.60,      # Minimum jam reduction (damaged sensors)
    "freq_hop_max_reduction": 0.80,      # Maximum jam reduction (perfect sensors)

    # Burn-through mode
    "burn_through_power_multiplier": 4.0,  # 4x radar power output
    "burn_through_heat_rate": 50000.0,     # W heat generation (massive)
    "burn_through_power_draw": 120.0,      # kW power draw (4x normal radar)
    "burn_through_emission_multiplier": 6.0,  # Own ship becomes 6x more visible on radar

    # Multi-spectral correlation
    "multispectral_chaff_reduction": 0.85,  # 85% reduction in chaff noise
    "multispectral_flare_reduction": 0.80,  # 80% reduction in flare decoy effect
    # Requires: IR (passive), radar (active), lidar (active) all functional

    # Home-on-jam
    "hoj_min_jammer_power": 5000.0,  # W minimum jammer power to get a bearing
    "hoj_bearing_accuracy": 0.95,    # Bearing quality (very precise -- signal is strong)
    "hoj_range_accuracy": 0.0,       # No range data from passive reception
}


class ECCMState:
    """Tracks ECCM state for a single ship's sensor system.

    ECCM is not a separate ship system -- it is a capability of the
    sensor system that modifies how incoming sensor data is processed.
    The sensor system owns an ECCMState and queries it during detection.
    """

    def __init__(self, config: Optional[dict] = None):
        """Initialize ECCM state.

        Args:
            config: Optional configuration overrides.
        """
        cfg = dict(DEFAULT_ECCM_CONFIG)
        if config:
            cfg.update(config)

        # Active ECCM mode
        self.mode: ECCMMode = ECCMMode.OFF

        # Frequency hopping parameters
        self.freq_hop_jam_reduction = float(cfg["freq_hop_jam_reduction"])
        self.freq_hop_power_multiplier = float(cfg["freq_hop_power_multiplier"])
        self.freq_hop_min_reduction = float(cfg["freq_hop_min_reduction"])
        self.freq_hop_max_reduction = float(cfg["freq_hop_max_reduction"])

        # Burn-through parameters
        self.burn_through_power_multiplier = float(cfg["burn_through_power_multiplier"])
        self.burn_through_heat_rate = float(cfg["burn_through_heat_rate"])
        self.burn_through_power_draw = float(cfg["burn_through_power_draw"])
        self.burn_through_emission_multiplier = float(cfg["burn_through_emission_multiplier"])

        # Multi-spectral correlation parameters
        self.multispectral_chaff_reduction = float(cfg["multispectral_chaff_reduction"])
        self.multispectral_flare_reduction = float(cfg["multispectral_flare_reduction"])
        self.multispectral_active = False  # Toggled by command

        # Home-on-jam
        self.hoj_min_jammer_power = float(cfg["hoj_min_jammer_power"])
        self.hoj_bearing_accuracy = float(cfg["hoj_bearing_accuracy"])
        self.hoj_range_accuracy = float(cfg["hoj_range_accuracy"])
        self.hoj_active = False  # Toggled by command

        # Sensor health factor (1.0 = perfect, 0.0 = destroyed)
        self._sensor_health: float = 1.0

    def set_sensor_health(self, factor: float) -> None:
        """Update sensor health factor for ECCM effectiveness scaling.

        Args:
            factor: Sensor degradation factor (0.0-1.0).
        """
        self._sensor_health = max(0.0, min(1.0, factor))

    # ------------------------------------------------------------------
    # Mode activation
    # ------------------------------------------------------------------

    def activate_frequency_hop(self) -> dict:
        """Enable frequency hopping ECCM mode.

        Returns:
            dict: Activation result.
        """
        if self.mode == ECCMMode.BURN_THROUGH:
            # Must deactivate burn-through first -- they use incompatible
            # radar waveforms (burn-through needs sustained power on one
            # frequency; hopping spreads power across many)
            return {
                "ok": False,
                "error": "BURN_THROUGH_ACTIVE",
                "message": "Deactivate burn-through before enabling frequency hop",
            }

        self.mode = ECCMMode.FREQUENCY_HOP
        return {
            "ok": True,
            "message": "Frequency hopping ECCM active",
            "mode": self.mode.value,
            "jam_reduction": self._effective_freq_hop_reduction(),
            "power_multiplier": self.freq_hop_power_multiplier,
        }

    def activate_burn_through(self) -> dict:
        """Enable burn-through ECCM mode.

        Returns:
            dict: Activation result.
        """
        if self.mode == ECCMMode.FREQUENCY_HOP:
            return {
                "ok": False,
                "error": "FREQ_HOP_ACTIVE",
                "message": "Deactivate frequency hop before enabling burn-through",
            }

        self.mode = ECCMMode.BURN_THROUGH
        return {
            "ok": True,
            "message": "Burn-through mode active -- high heat and emission signature",
            "mode": self.mode.value,
            "power_multiplier": self.burn_through_power_multiplier,
            "heat_rate": self.burn_through_heat_rate,
            "emission_multiplier": self.burn_through_emission_multiplier,
        }

    def deactivate_eccm_mode(self) -> dict:
        """Deactivate current ECCM mode (frequency hop or burn-through).

        Returns:
            dict: Deactivation result.
        """
        prev = self.mode.value
        self.mode = ECCMMode.OFF
        return {
            "ok": True,
            "message": f"ECCM mode deactivated (was: {prev})",
            "mode": self.mode.value,
        }

    def set_multispectral(self, enabled: bool) -> dict:
        """Enable or disable multi-spectral correlation.

        Args:
            enabled: Whether to enable correlation.

        Returns:
            dict: Result.
        """
        self.multispectral_active = bool(enabled)
        state = "active" if self.multispectral_active else "inactive"
        return {
            "ok": True,
            "message": f"Multi-spectral correlation {state}",
            "multispectral_active": self.multispectral_active,
        }

    def set_home_on_jam(self, enabled: bool) -> dict:
        """Enable or disable home-on-jam mode.

        Args:
            enabled: Whether to enable HoJ.

        Returns:
            dict: Result.
        """
        self.hoj_active = bool(enabled)
        state = "active" if self.hoj_active else "inactive"
        return {
            "ok": True,
            "message": f"Home-on-jam {state}",
            "hoj_active": self.hoj_active,
        }

    # ------------------------------------------------------------------
    # ECCM effect calculations (called by sensor pipeline)
    # ------------------------------------------------------------------

    def _effective_freq_hop_reduction(self) -> float:
        """Calculate effective jamming reduction from frequency hopping.

        Scales linearly with sensor health between min and max reduction.

        Returns:
            float: Fraction of jamming that is negated (0.6-0.8).
        """
        health = self._sensor_health
        # Lerp between min and max reduction based on sensor health
        return self.freq_hop_min_reduction + (
            self.freq_hop_max_reduction - self.freq_hop_min_reduction
        ) * health

    def get_jam_factor_modifier(self, raw_jam_factor: float) -> float:
        """Modify an incoming jamming degradation factor using active ECCM.

        The raw_jam_factor comes from ECMSystem.get_jammer_effect_at_range()
        where 0 = fully jammed, 1 = no effect.  ECCM pushes it back toward 1.

        Frequency hop: directly reduces the jamming penalty.
        Burn-through: increases effective radar power (handled elsewhere),
            but also slightly reduces jam sensitivity here because the
            stronger return signal improves SNR.

        Args:
            raw_jam_factor: Jamming factor from enemy ECM (0-1).

        Returns:
            float: Modified jamming factor after ECCM (closer to 1.0).
        """
        if self.mode == ECCMMode.OFF:
            return raw_jam_factor

        # How much degradation the jammer is applying (0 = none, 1 = total)
        jam_penalty = 1.0 - raw_jam_factor

        if self.mode == ECCMMode.FREQUENCY_HOP:
            reduction = self._effective_freq_hop_reduction()
            # Remove 60-80% of the jamming penalty
            jam_penalty *= (1.0 - reduction)

        elif self.mode == ECCMMode.BURN_THROUGH:
            # Burn-through improves SNR which implicitly reduces jam effect.
            # Model as ~40% jam reduction (less than freq hop, but stacks
            # with the radar power boost applied in the active sensor).
            health_scaled = 0.30 + 0.10 * self._sensor_health
            jam_penalty *= (1.0 - health_scaled)

        return max(0.05, min(1.0, 1.0 - jam_penalty))

    def get_burn_through_radar_multiplier(self) -> float:
        """Get radar power multiplier from burn-through mode.

        Applied to active sensor radar power during detection calculations.
        Even with damaged sensors, burn-through provides some boost because
        it is a raw power increase, not a signal processing technique.

        Returns:
            float: Radar power multiplier (1.0 if burn-through not active).
        """
        if self.mode != ECCMMode.BURN_THROUGH:
            return 1.0

        # Full multiplier even at reduced sensor health (it is brute force)
        # but cap at 50% if sensors are badly damaged (hardware limits)
        min_mult = 1.0 + (self.burn_through_power_multiplier - 1.0) * 0.5
        return min_mult + (self.burn_through_power_multiplier - min_mult) * self._sensor_health

    def get_chaff_reduction(self, has_ir: bool, has_radar: bool,
                            has_lidar: bool) -> float:
        """Get chaff noise reduction from multi-spectral correlation.

        Chaff only affects radar returns. If we can cross-reference with
        IR and lidar, we can identify which returns are chaff (no IR
        signature, no lidar return from thin foil) and filter them.

        Args:
            has_ir: Whether IR (passive) sensor is functional.
            has_radar: Whether radar (active) sensor is functional.
            has_lidar: Whether lidar sensor is functional.

        Returns:
            float: Fraction of chaff noise to remove (0.0-0.85).
        """
        if not self.multispectral_active:
            return 0.0

        # Need all three sensor types for full correlation
        sensor_count = sum([has_ir, has_radar, has_lidar])
        if sensor_count < 2:
            # Cannot correlate with only one sensor type
            return 0.0

        # Two sensors give partial correlation, three give full
        if sensor_count == 2:
            base_reduction = self.multispectral_chaff_reduction * 0.5
        else:
            base_reduction = self.multispectral_chaff_reduction

        return base_reduction * self._sensor_health

    def get_flare_reduction(self, has_ir: bool, has_radar: bool,
                            has_lidar: bool) -> float:
        """Get flare decoy reduction from multi-spectral correlation.

        Flares only affect IR. If we can cross-reference with radar
        (flare has tiny RCS) and lidar (small physical size), we can
        distinguish the decoy from the real ship.

        Args:
            has_ir: Whether IR (passive) sensor is functional.
            has_radar: Whether radar (active) sensor is functional.
            has_lidar: Whether lidar sensor is functional.

        Returns:
            float: Fraction of flare effect to remove (0.0-0.80).
        """
        if not self.multispectral_active:
            return 0.0

        sensor_count = sum([has_ir, has_radar, has_lidar])
        if sensor_count < 2:
            return 0.0

        if sensor_count == 2:
            base_reduction = self.multispectral_flare_reduction * 0.5
        else:
            base_reduction = self.multispectral_flare_reduction

        return base_reduction * self._sensor_health

    def get_sensor_power_multiplier(self) -> float:
        """Get total sensor power draw multiplier from active ECCM modes.

        Returns:
            float: Power multiplier (>=1.0).
        """
        multiplier = 1.0

        if self.mode == ECCMMode.FREQUENCY_HOP:
            multiplier *= self.freq_hop_power_multiplier
        elif self.mode == ECCMMode.BURN_THROUGH:
            # Burn-through power draw is separate (handled via heat),
            # but the radar subsystem also draws more
            multiplier *= (self.burn_through_power_draw / 30.0)  # Relative to normal 30kW

        return multiplier

    def get_burn_through_emission_multiplier(self) -> float:
        """Get own-ship emission multiplier from burn-through.

        Burn-through makes your radar emissions much stronger, which
        means enemy passive sensors can detect you more easily.

        Returns:
            float: Emission multiplier (1.0 if not in burn-through).
        """
        if self.mode != ECCMMode.BURN_THROUGH:
            return 1.0
        return self.burn_through_emission_multiplier

    # ------------------------------------------------------------------
    # Home-on-jam
    # ------------------------------------------------------------------

    def check_home_on_jam(self, target_ship, observer_position: dict,
                          distance: float) -> Optional[dict]:
        """Check if an enemy jammer can be used as a targeting source.

        Home-on-jam detects the enemy's jamming emissions and derives a
        bearing to the jammer. This is passive reception -- no range data
        unless combined with other sensors or triangulation.

        Args:
            target_ship: Ship to check for jamming emissions.
            observer_position: Observer's position dict {x, y, z}.
            distance: Distance to target in metres.

        Returns:
            dict with bearing-only contact data, or None if target is
            not jamming or signal is too weak.
        """
        if not self.hoj_active:
            return None

        # Check if target has an active jammer
        target_ecm = target_ship.systems.get("ecm") if hasattr(target_ship, "systems") else None
        if not target_ecm or not getattr(target_ecm, "jammer_enabled", False):
            return None

        # Calculate received jammer power at our position (inverse square)
        jammer_power = getattr(target_ecm, "jammer_power", 0.0)
        ecm_factor = getattr(target_ecm, "_ecm_factor", 1.0)
        effective_power = jammer_power * ecm_factor

        if distance <= 0:
            return None

        received_flux = effective_power / (4.0 * math.pi * distance * distance)

        # Need minimum signal strength for bearing determination.
        # Jammer signals are broadband and powerful -- even at long range
        # the directional antenna can resolve a bearing. The threshold
        # is set very low because we are detecting a deliberate broadcast,
        # not a faint radar return.
        # Reference: 5kW jammer at 500km should be detectable.
        min_flux = self.hoj_min_jammer_power / (4.0 * math.pi * (500_000.0 ** 2))
        if received_flux < min_flux:
            return None

        # Bearing accuracy: very good (jammer signal is strong and
        # intentionally broadcast), scaled by sensor health
        bearing_quality = self.hoj_bearing_accuracy * self._sensor_health

        from hybrid.utils.math_utils import calculate_bearing
        bearing = calculate_bearing(observer_position, target_ship.position)

        return {
            "detection_method": "home_on_jam",
            "bearing": bearing,
            "bearing_quality": bearing_quality,
            # No range data -- HoJ is bearing-only
            "has_range": False,
            "jammer_power": effective_power,
            "signal_strength": received_flux,
        }

    # ------------------------------------------------------------------
    # Jamming analysis
    # ------------------------------------------------------------------

    def analyze_jamming(self, target_ship, distance: float) -> dict:
        """Analyze enemy ECM emissions to identify type and recommend counter.

        This is the analyze-jamming command implementation. It examines
        the target's active ECM modes and suggests the best ECCM response.

        Args:
            target_ship: Ship whose ECM to analyze.
            distance: Distance to target in metres.

        Returns:
            dict: Analysis results with ECM type identification and
                  recommended countermeasure.
        """
        target_ecm = target_ship.systems.get("ecm") if hasattr(target_ship, "systems") else None
        if not target_ecm:
            return {
                "ok": True,
                "ecm_detected": False,
                "message": "No ECM emissions detected from target",
                "threats": [],
                "recommendation": "none",
            }

        threats = []
        recommendations = []

        # Check radar jamming
        if getattr(target_ecm, "jammer_enabled", False):
            jam_factor = target_ecm.get_jammer_effect_at_range(distance)
            severity = "severe" if jam_factor < 0.3 else "moderate" if jam_factor < 0.7 else "minor"
            threats.append({
                "type": "noise_jamming",
                "severity": severity,
                "jam_factor": round(jam_factor, 3),
                "jammer_power": getattr(target_ecm, "jammer_power", 0),
            })
            if severity == "severe":
                recommendations.append("burn_through")
                recommendations.append("home_on_jam")
            else:
                recommendations.append("frequency_hop")

        # Check chaff
        if target_ecm.is_chaff_active():
            threats.append({
                "type": "chaff",
                "rcs_multiplier": round(target_ecm.get_chaff_rcs_multiplier(), 2),
                "noise_radius": round(target_ecm.get_chaff_noise_radius(), 1),
            })
            recommendations.append("multispectral")

        # Check flares
        if target_ecm.is_flare_active():
            threats.append({
                "type": "flare",
                "ir_power": target_ecm.get_flare_ir_power(),
            })
            recommendations.append("multispectral")

        # Check EMCON (not really a threat, just reduced signature)
        if getattr(target_ecm, "emcon_active", False):
            threats.append({
                "type": "emcon",
                "ir_reduction": getattr(target_ecm, "emcon_ir_reduction", 1.0),
            })
            # No direct counter to EMCON -- target is just quieter
            recommendations.append("close_range")

        # Deduplicate recommendations
        seen = set()
        unique_recs = []
        for r in recommendations:
            if r not in seen:
                seen.add(r)
                unique_recs.append(r)

        primary_rec = unique_recs[0] if unique_recs else "none"

        return {
            "ok": True,
            "ecm_detected": len(threats) > 0,
            "threats": threats,
            "threat_count": len(threats),
            "recommendation": primary_rec,
            "all_recommendations": unique_recs,
            "message": (
                f"Detected {len(threats)} ECM threat(s) -- recommend {primary_rec}"
                if threats else "No ECM emissions detected from target"
            ),
        }

    # ------------------------------------------------------------------
    # Tick / heat
    # ------------------------------------------------------------------

    def tick(self, dt: float, ship: Any = None, event_bus: Any = None) -> None:
        """Update ECCM state each tick.

        Handles burn-through heat generation and power draw.

        Args:
            dt: Time step in seconds.
            ship: Ship object.
            event_bus: EventBus for events.
        """
        if ship is None or dt <= 0:
            return

        # Update sensor health from ship damage model
        if hasattr(ship, "get_effective_factor"):
            self._sensor_health = ship.get_effective_factor("sensors")
        elif hasattr(ship, "damage_model"):
            self._sensor_health = ship.damage_model.get_degradation_factor("sensors")

        # Burn-through heat generation
        if self.mode == ECCMMode.BURN_THROUGH:
            if hasattr(ship, "damage_model"):
                sensors_sub = ship.damage_model.subsystems.get("sensors")
                if sensors_sub and event_bus:
                    heat_per_tick = self.burn_through_heat_rate * dt / 1000.0
                    ship.damage_model.add_heat("sensors", heat_per_tick, event_bus, ship.id)

    # ------------------------------------------------------------------
    # State / telemetry
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Get ECCM state for telemetry.

        Returns:
            dict: Complete ECCM status.
        """
        return {
            "mode": self.mode.value,
            "multispectral_active": self.multispectral_active,
            "hoj_active": self.hoj_active,
            "sensor_health": round(self._sensor_health, 2),
            "freq_hop_jam_reduction": (
                round(self._effective_freq_hop_reduction(), 2)
                if self.mode == ECCMMode.FREQUENCY_HOP else None
            ),
            "burn_through_radar_mult": (
                round(self.get_burn_through_radar_multiplier(), 2)
                if self.mode == ECCMMode.BURN_THROUGH else None
            ),
            "burn_through_emission_mult": (
                round(self.get_burn_through_emission_multiplier(), 2)
                if self.mode == ECCMMode.BURN_THROUGH else None
            ),
            "power_multiplier": round(self.get_sensor_power_multiplier(), 2),
            "status": self._get_status_string(),
        }

    def _get_status_string(self) -> str:
        """Get human-readable ECCM status string."""
        parts = []
        if self.mode != ECCMMode.OFF:
            parts.append(self.mode.value.upper().replace("_", "-"))
        if self.multispectral_active:
            parts.append("MULTI-SPEC")
        if self.hoj_active:
            parts.append("HOJ")
        if parts:
            return " | ".join(parts)
        return "standby"
