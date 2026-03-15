# hybrid/systems/ecm_system.py
"""Electronic Countermeasures (ECM) system.

ECM degrades enemy targeting through physical means:
- **Radar jamming**: Noise injection on enemy radar frequencies. Reduces
  incoming radar track quality at range. Effectiveness follows inverse-square
  (jammer power / distance^2). Countered by frequency hopping.
- **Chaff deployment**: Radar-reflective particles that create false radar
  returns, inflating the target's apparent RCS and adding position noise.
  Finite expendable, cloud dissipates over time.
- **Flare deployment**: IR decoys that create false thermal signatures,
  diverting passive IR lock. Finite expendable, burn out quickly.
- **EMCON (Emissions Control)**: Go passive — shut down active sensors,
  reduce own radar/IR signature at the cost of sensor capability. Not a
  magic cloak: it reduces YOUR emissions, not THEIR sensors.

ECM is NOT a magic cloak. It makes the enemy's targeting pipeline noisier,
not impossible. Effectiveness degrades with range (inverse square) and can
be countered by multi-spectral sensors and frequency hopping.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, Any, Optional

from hybrid.core.base_system import BaseSystem
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)

# Physical constants
SPEED_OF_LIGHT = 3.0e8  # m/s

# Default ECM configuration
DEFAULT_ECM_CONFIG = {
    # Radar jammer
    "jammer_power": 50000.0,      # W — effective radiated jammer power
    "jammer_enabled": False,       # Whether jammer is actively broadcasting
    "jammer_heat": 15000.0,        # W — heat generated while jamming
    "jammer_power_draw": 30.0,     # kW power draw while active

    # Chaff
    "chaff_count": 10,             # Number of chaff bundles available
    "chaff_rcs_multiplier": 5.0,   # RCS multiplier when chaff cloud is active
    "chaff_duration": 30.0,        # Seconds before chaff cloud dissipates
    "chaff_noise_radius": 2000.0,  # Metres — position noise added by chaff

    # Flares
    "flare_count": 10,             # Number of IR flares available
    "flare_ir_power": 5.0e6,       # W — IR emission of a flare (mimics drive plume)
    "flare_duration": 8.0,         # Seconds before flare burns out

    # EMCON
    "emcon_ir_reduction": 0.3,     # IR signature multiplier when in EMCON (0.3 = 70% reduction)
    "emcon_rcs_reduction": 0.7,    # RCS multiplier in EMCON (minor — can't change hull shape)
}


class ECMSystem(BaseSystem):
    """Electronic countermeasures system for degrading enemy sensors and targeting.

    The ECM system provides four capabilities:
    1. Radar jamming (continuous, power-hungry, generates heat)
    2. Chaff deployment (expendable, creates radar clutter)
    3. Flare deployment (expendable, creates IR decoys)
    4. EMCON mode (passive signature reduction)

    Other systems query ECM state to modify detection/targeting:
    - Emission model checks EMCON for own-ship signature reduction
    - Enemy passive sensors check for active flares
    - Enemy active sensors check for chaff clouds and jamming
    - Enemy targeting system checks for combined ECM degradation
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        super().__init__(config)

        # Merge defaults
        for key, default in DEFAULT_ECM_CONFIG.items():
            if key not in config:
                config[key] = default

        # --- Radar Jammer ---
        self.jammer_power = float(config.get("jammer_power", DEFAULT_ECM_CONFIG["jammer_power"]))
        self.jammer_enabled = bool(config.get("jammer_enabled", DEFAULT_ECM_CONFIG["jammer_enabled"]))
        self.jammer_heat = float(config.get("jammer_heat", DEFAULT_ECM_CONFIG["jammer_heat"]))
        self.jammer_power_draw = float(config.get("jammer_power_draw", DEFAULT_ECM_CONFIG["jammer_power_draw"]))

        # --- Chaff ---
        self.chaff_count = int(config.get("chaff_count", DEFAULT_ECM_CONFIG["chaff_count"]))
        self.chaff_max = self.chaff_count
        self.chaff_rcs_multiplier = float(config.get("chaff_rcs_multiplier", DEFAULT_ECM_CONFIG["chaff_rcs_multiplier"]))
        self.chaff_duration = float(config.get("chaff_duration", DEFAULT_ECM_CONFIG["chaff_duration"]))
        self.chaff_noise_radius = float(config.get("chaff_noise_radius", DEFAULT_ECM_CONFIG["chaff_noise_radius"]))
        self._active_chaff_remaining = 0.0  # Seconds remaining on current chaff cloud

        # --- Flares ---
        self.flare_count = int(config.get("flare_count", DEFAULT_ECM_CONFIG["flare_count"]))
        self.flare_max = self.flare_count
        self.flare_ir_power = float(config.get("flare_ir_power", DEFAULT_ECM_CONFIG["flare_ir_power"]))
        self.flare_duration = float(config.get("flare_duration", DEFAULT_ECM_CONFIG["flare_duration"]))
        self._active_flare_remaining = 0.0  # Seconds remaining on current flare

        # --- EMCON ---
        self.emcon_active = bool(config.get("emcon_active", False))
        self.emcon_ir_reduction = float(config.get("emcon_ir_reduction", DEFAULT_ECM_CONFIG["emcon_ir_reduction"]))
        self.emcon_rcs_reduction = float(config.get("emcon_rcs_reduction", DEFAULT_ECM_CONFIG["emcon_rcs_reduction"]))

        # Track own-ship damage factor
        self._ecm_factor = 1.0

    def tick(self, dt: float, ship=None, event_bus=None):
        """Update ECM system state each tick.

        Args:
            dt: Time step in seconds
            ship: Ship object
            event_bus: EventBus for events
        """
        if not self.enabled or ship is None or dt <= 0:
            return

        # ECM effectiveness degrades with damage
        if hasattr(ship, "get_effective_factor"):
            self._ecm_factor = ship.get_effective_factor("sensors")
        elif hasattr(ship, "damage_model"):
            self._ecm_factor = ship.damage_model.get_degradation_factor("sensors")
        else:
            self._ecm_factor = 1.0

        # --- Decay active chaff ---
        if self._active_chaff_remaining > 0:
            self._active_chaff_remaining = max(0.0, self._active_chaff_remaining - dt)
            if self._active_chaff_remaining <= 0 and event_bus:
                event_bus.publish("ecm_chaff_expired", {"ship_id": ship.id})

        # --- Decay active flare ---
        if self._active_flare_remaining > 0:
            self._active_flare_remaining = max(0.0, self._active_flare_remaining - dt)
            if self._active_flare_remaining <= 0 and event_bus:
                event_bus.publish("ecm_flare_expired", {"ship_id": ship.id})

        # --- Jammer heat generation ---
        if self.jammer_enabled and event_bus:
            # Report heat to thermal system via damage model
            if hasattr(ship, "damage_model"):
                sensors_sub = ship.damage_model.subsystems.get("sensors")
                if sensors_sub:
                    heat_per_tick = self.jammer_heat * dt / 1000.0  # Scale for subsystem heat units
                    ship.damage_model.add_heat("sensors", heat_per_tick, event_bus, ship.id)

        # --- EMCON enforcement ---
        if self.emcon_active:
            # EMCON disables active sensors and jammer
            if self.jammer_enabled:
                self.jammer_enabled = False
            # Disable active sensor pinging
            sensors = ship.systems.get("sensors")
            if sensors and hasattr(sensors, "active"):
                sensors.active.last_ping_time = getattr(ship, "sim_time", 0.0)

    # ------------------------------------------------------------------
    # ECM effect queries (called by sensor/targeting systems on OTHER ships)
    # ------------------------------------------------------------------

    def get_jammer_effect_at_range(self, distance: float) -> float:
        """Calculate radar jamming degradation at a given range.

        Returns a factor (0-1) where 0 = fully jammed, 1 = no effect.
        Jamming follows inverse-square: closer = more effective.

        Args:
            distance: Distance from jammer to observer in metres

        Returns:
            float: Degradation factor (multiply into radar detection quality)
        """
        if not self.jammer_enabled or distance <= 0:
            return 1.0

        # Jamming signal power at observer: P / (4*pi*r^2)
        # Noise injection ratio compared to baseline sensor noise
        # Higher ratio = more degradation
        effective_power = self.jammer_power * self._ecm_factor
        jammer_flux = effective_power / (4.0 * math.pi * distance * distance)

        # Compare to radar sensitivity baseline (1e-12 W)
        # jam_ratio = how many times above noise floor the jammer is
        noise_floor = 1.0e-12
        jam_ratio = jammer_flux / noise_floor

        # Convert to degradation: at jam_ratio=1 (just at noise floor), minimal effect
        # at jam_ratio=1000, severe degradation
        # factor = 1 / (1 + log10(jam_ratio)) clamped
        if jam_ratio <= 1.0:
            return 1.0

        degradation = 1.0 / (1.0 + math.log10(jam_ratio))
        return max(0.05, min(1.0, degradation))

    def is_chaff_active(self) -> bool:
        """Check if a chaff cloud is currently deployed."""
        return self._active_chaff_remaining > 0

    def get_chaff_rcs_multiplier(self) -> float:
        """Get RCS multiplier from active chaff cloud.

        Returns:
            float: RCS multiplier (>1 when chaff active, 1.0 otherwise)
        """
        if not self.is_chaff_active():
            return 1.0

        # Chaff effectiveness fades linearly over duration
        fade = self._active_chaff_remaining / self.chaff_duration
        return 1.0 + (self.chaff_rcs_multiplier - 1.0) * fade

    def get_chaff_noise_radius(self) -> float:
        """Get position noise radius from active chaff.

        Returns:
            float: Noise radius in metres (0 if no chaff)
        """
        if not self.is_chaff_active():
            return 0.0

        fade = self._active_chaff_remaining / self.chaff_duration
        return self.chaff_noise_radius * fade

    def is_flare_active(self) -> bool:
        """Check if an IR flare is currently burning."""
        return self._active_flare_remaining > 0

    def get_flare_ir_power(self) -> float:
        """Get IR emission from active flare decoy.

        Returns:
            float: Flare IR power in watts (0 if no flare)
        """
        if not self.is_flare_active():
            return 0.0

        # Flare brightness fades over time
        fade = self._active_flare_remaining / self.flare_duration
        return self.flare_ir_power * fade

    def get_emcon_ir_modifier(self) -> float:
        """Get IR signature modifier from EMCON mode.

        Returns:
            float: IR multiplier (< 1.0 when EMCON active, 1.0 otherwise)
        """
        if not self.emcon_active:
            return 1.0
        return self.emcon_ir_reduction

    def get_emcon_rcs_modifier(self) -> float:
        """Get RCS modifier from EMCON mode.

        Returns:
            float: RCS multiplier (< 1.0 when EMCON active, 1.0 otherwise)
        """
        if not self.emcon_active:
            return 1.0
        return self.emcon_rcs_reduction

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def command(self, action: str, params: dict = None) -> dict:
        """Handle ECM commands.

        Commands:
            activate_jammer: Enable radar jamming
            deactivate_jammer: Disable radar jamming
            deploy_chaff: Launch chaff bundle
            deploy_flare: Launch IR flare
            set_emcon: Enable/disable EMCON mode
            ecm_status: Get full ECM status
        """
        params = params or {}

        if action == "activate_jammer":
            return self._cmd_activate_jammer(params)
        elif action == "deactivate_jammer":
            return self._cmd_deactivate_jammer(params)
        elif action == "deploy_chaff":
            return self._cmd_deploy_chaff(params)
        elif action == "deploy_flare":
            return self._cmd_deploy_flare(params)
        elif action == "set_emcon":
            return self._cmd_set_emcon(params)
        elif action == "ecm_status":
            return self.get_state()

        return error_dict("UNKNOWN_COMMAND", f"Unknown ECM command: {action}")

    def _cmd_activate_jammer(self, params: dict) -> dict:
        """Enable radar jammer."""
        if self.emcon_active:
            return error_dict("EMCON_ACTIVE", "Cannot activate jammer while in EMCON mode")
        self.jammer_enabled = True
        event_bus = params.get("event_bus")
        ship = params.get("ship") or params.get("_ship")
        if event_bus and ship:
            event_bus.publish("ecm_jammer_activated", {
                "ship_id": ship.id,
                "jammer_power": self.jammer_power,
            })
        return success_dict("Radar jammer activated", jammer_enabled=True,
                          jammer_power=self.jammer_power)

    def _cmd_deactivate_jammer(self, params: dict) -> dict:
        """Disable radar jammer."""
        self.jammer_enabled = False
        event_bus = params.get("event_bus")
        ship = params.get("ship") or params.get("_ship")
        if event_bus and ship:
            event_bus.publish("ecm_jammer_deactivated", {"ship_id": ship.id})
        return success_dict("Radar jammer deactivated", jammer_enabled=False)

    def _cmd_deploy_chaff(self, params: dict) -> dict:
        """Deploy chaff bundle."""
        if self.chaff_count <= 0:
            return error_dict("NO_CHAFF", "Chaff depleted")

        self.chaff_count -= 1
        self._active_chaff_remaining = self.chaff_duration

        event_bus = params.get("event_bus")
        ship = params.get("ship") or params.get("_ship")
        if event_bus and ship:
            event_bus.publish("ecm_chaff_deployed", {
                "ship_id": ship.id,
                "remaining": self.chaff_count,
                "duration": self.chaff_duration,
            })

        return success_dict(
            f"Chaff deployed — {self.chaff_count} remaining",
            chaff_remaining=self.chaff_count,
            chaff_active=True,
            duration=self.chaff_duration,
        )

    def _cmd_deploy_flare(self, params: dict) -> dict:
        """Deploy IR flare decoy."""
        if self.flare_count <= 0:
            return error_dict("NO_FLARES", "Flares depleted")

        self.flare_count -= 1
        self._active_flare_remaining = self.flare_duration

        event_bus = params.get("event_bus")
        ship = params.get("ship") or params.get("_ship")
        if event_bus and ship:
            event_bus.publish("ecm_flare_deployed", {
                "ship_id": ship.id,
                "remaining": self.flare_count,
                "ir_power": self.flare_ir_power,
                "duration": self.flare_duration,
            })

        return success_dict(
            f"IR flare deployed — {self.flare_count} remaining",
            flare_remaining=self.flare_count,
            flare_active=True,
            duration=self.flare_duration,
        )

    def _cmd_set_emcon(self, params: dict) -> dict:
        """Enable or disable EMCON mode."""
        enable = params.get("enabled", params.get("enable", not self.emcon_active))
        if isinstance(enable, str):
            enable = enable.lower() in ("true", "1", "on", "yes")

        self.emcon_active = bool(enable)

        # EMCON disables active countermeasures
        if self.emcon_active and self.jammer_enabled:
            self.jammer_enabled = False

        event_bus = params.get("event_bus")
        ship = params.get("ship") or params.get("_ship")
        if event_bus and ship:
            event_bus.publish("ecm_emcon_changed", {
                "ship_id": ship.id,
                "emcon_active": self.emcon_active,
            })

        status = "EMCON engaged — emissions minimised" if self.emcon_active else "EMCON disengaged"
        return success_dict(status, emcon_active=self.emcon_active)

    # ------------------------------------------------------------------
    # State / telemetry
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Get ECM system state for telemetry."""
        return {
            "enabled": self.enabled,
            "power_draw": self.power_draw,
            # Jammer
            "jammer_enabled": self.jammer_enabled,
            "jammer_power": self.jammer_power,
            "jammer_heat": self.jammer_heat,
            # Chaff
            "chaff_count": self.chaff_count,
            "chaff_max": self.chaff_max,
            "chaff_active": self.is_chaff_active(),
            "chaff_remaining_time": round(self._active_chaff_remaining, 1),
            # Flares
            "flare_count": self.flare_count,
            "flare_max": self.flare_max,
            "flare_active": self.is_flare_active(),
            "flare_remaining_time": round(self._active_flare_remaining, 1),
            # EMCON
            "emcon_active": self.emcon_active,
            "emcon_ir_reduction": self.emcon_ir_reduction,
            "emcon_rcs_reduction": self.emcon_rcs_reduction,
            # Status
            "ecm_factor": round(self._ecm_factor, 2),
            "status": self._get_status_string(),
        }

    def _get_status_string(self) -> str:
        """Get human-readable ECM status."""
        if self.emcon_active:
            return "EMCON"
        active_modes = []
        if self.jammer_enabled:
            active_modes.append("JAM")
        if self.is_chaff_active():
            active_modes.append("CHAFF")
        if self.is_flare_active():
            active_modes.append("FLARE")
        if active_modes:
            return " | ".join(active_modes)
        return "standby"
