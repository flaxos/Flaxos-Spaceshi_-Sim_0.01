# hybrid/systems/crew_fatigue_system.py
"""Crew fatigue and g-load performance system.

Models human physical limits under sustained acceleration:
- G-load impairment: At 5g+ manual tasks take longer, error rates increase
- Blackout risk: Extreme sustained g-loads (7g+ for 30s+) cause crew blackout
- Fatigue accumulation: Combat stress and high-g maneuvers accumulate fatigue
- Rest recovery: Fatigue only recovers during low-g rest periods
- Skill-based performance: Experienced crew resist fatigue effects better

This is NOT an abstract buff system. It models real physics:
- Human tolerance is ~1g sustained, 3g comfortable, 5g+ impaired, 9g blackout
- Fatigue from g-loads follows dose-response (integral of excess g over time)
- Recovery requires actual low-g time, not a cooldown timer
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from hybrid.core.base_system import BaseSystem

logger = logging.getLogger(__name__)

# G-force thresholds (in multiples of Earth gravity)
G_COMFORTABLE = 1.5    # No performance impact
G_MODERATE = 3.0       # Mild fatigue accumulation
G_HIGH = 5.0           # Manual tasks impaired, error rates increase
G_EXTREME = 7.0        # Blackout risk begins
G_FATAL = 12.0         # Lethal within seconds

# Fatigue constants
FATIGUE_RATE_BASE = 0.001       # Base fatigue per second (8h shift = ~29% from time alone)
FATIGUE_RATE_COMBAT = 0.003     # Additional fatigue during combat
FATIGUE_RATE_G_LOAD = 0.02      # Fatigue per second per excess g above G_COMFORTABLE
REST_RECOVERY_RATE = 0.005      # Recovery per second at low-g (full rest in ~200s = 3.3min game time)
REST_G_THRESHOLD = 0.5          # Must be below this g-load to recover

# Blackout model
BLACKOUT_ONSET_TIME = 30.0      # Seconds at extreme g before blackout
BLACKOUT_RECOVERY_TIME = 15.0   # Seconds to recover from blackout at low-g

# Performance impact multipliers
# These multiply the crew skill efficiency
FATIGUE_PERFORMANCE_CURVE = [
    # (fatigue_level, performance_multiplier)
    (0.0, 1.0),    # Fresh: full performance
    (0.3, 0.95),   # Slightly tired: 95%
    (0.5, 0.85),   # Moderate fatigue: 85%
    (0.7, 0.70),   # Heavy fatigue: 70%
    (0.9, 0.50),   # Exhausted: 50%
    (1.0, 0.35),   # Collapsed: 35%
]

G_LOAD_PERFORMANCE_CURVE = [
    # (current_g, performance_multiplier)
    (0.0, 1.0),    # Zero-g: full performance
    (G_COMFORTABLE, 1.0),
    (G_MODERATE, 0.90),
    (G_HIGH, 0.65),
    (G_EXTREME, 0.35),
    (G_FATAL, 0.05),
]


@dataclass
class CrewState:
    """Physical state of the crew complement."""
    fatigue: float = 0.0            # 0.0 (rested) to 1.0 (exhausted)
    g_dose: float = 0.0            # Accumulated g-load stress (resets slowly)
    blackout_timer: float = 0.0    # Time spent at extreme g (resets at low-g)
    is_blacked_out: bool = False   # Currently incapacitated
    blackout_recovery: float = 0.0 # Recovery timer after blackout
    combat_time: float = 0.0       # Continuous combat exposure (seconds)
    rest_time: float = 0.0         # Continuous rest time (seconds)
    current_g: float = 0.0         # Current g-load on crew

    def to_dict(self) -> dict:
        """Serialize for telemetry."""
        return {
            "fatigue": round(self.fatigue, 3),
            "g_dose": round(self.g_dose, 3),
            "blackout_timer": round(self.blackout_timer, 1),
            "is_blacked_out": self.is_blacked_out,
            "blackout_recovery": round(self.blackout_recovery, 1),
            "combat_time": round(self.combat_time, 1),
            "rest_time": round(self.rest_time, 1),
            "current_g": round(self.current_g, 2),
        }


def _interpolate_curve(curve: list, value: float) -> float:
    """Linearly interpolate a performance curve.

    Args:
        curve: List of (input_value, output_multiplier) tuples, sorted ascending.
        value: The input value to look up.

    Returns:
        Interpolated multiplier.
    """
    if value <= curve[0][0]:
        return curve[0][1]
    if value >= curve[-1][0]:
        return curve[-1][1]

    for i in range(len(curve) - 1):
        x0, y0 = curve[i]
        x1, y1 = curve[i + 1]
        if x0 <= value <= x1:
            t = (value - x0) / (x1 - x0) if x1 != x0 else 0.0
            return y0 + t * (y1 - y0)

    return curve[-1][1]


class CrewFatigueSystem(BaseSystem):
    """Models crew physical performance under acceleration and fatigue.

    Integrates with:
    - Ship physics: reads acceleration for g-load calculation
    - Bio monitor: complements (not replaces) the simple g-limit model
    - Targeting: crew fatigue degrades firing solution computation
    - Helm: fatigued crew execute maneuvers less precisely
    - Ops: repair team efficiency affected by crew fatigue
    """

    def __init__(self, config: dict = None):
        super().__init__(config)
        config = config or {}

        self.power_draw = config.get("power_draw", 0.5)

        # G-force thresholds (configurable per ship class)
        self.g_comfortable = float(config.get("g_comfortable", G_COMFORTABLE))
        self.g_high = float(config.get("g_high", G_HIGH))
        self.g_extreme = float(config.get("g_extreme", G_EXTREME))

        # Crew complement affects resilience (more crew = shift rotation)
        self.crew_count = int(config.get("crew_count", 1))

        # Skill modifier: higher = more fatigue-resistant crew
        # 1.0 = average, 0.5 = green crew (fatigue 2x faster), 1.5 = veteran
        self.crew_experience = float(config.get("crew_experience", 1.0))

        # Current crew state
        self.crew = CrewState()

        # Combat detection (driven by events)
        self._in_combat = False
        self._combat_cooldown = 0.0

        # Alert level tracking
        self._last_alert = ""

        # Track whether rest was ordered
        self._rest_ordered = False

    def tick(self, dt: float, ship=None, event_bus=None):
        """Update crew fatigue state each simulation tick.

        Args:
            dt: Time step in seconds
            ship: Ship object (for acceleration data)
            event_bus: Event bus for publishing crew events
        """
        if not self.enabled or ship is None:
            return

        # Calculate current g-load from ship acceleration
        a = ship.acceleration
        accel_mag = math.sqrt(a["x"]**2 + a["y"]**2 + a["z"]**2)
        current_g = accel_mag / 9.81
        self.crew.current_g = current_g

        # Detect combat from recent weapon events
        self._update_combat_state(dt, ship)

        # Update g-load effects
        self._update_g_effects(dt, current_g, event_bus, ship)

        # Update fatigue accumulation / recovery
        self._update_fatigue(dt, current_g, event_bus, ship)

        # Update blackout model
        self._update_blackout(dt, current_g, event_bus, ship)

        # Emit alert events based on crew state
        self._emit_alerts(event_bus, ship)

    def _update_combat_state(self, dt: float, ship):
        """Track whether ship is in active combat."""
        # Check for recent weapon fire or incoming damage
        combat = ship.systems.get("combat")
        if combat and hasattr(combat, "get_state"):
            combat_state = combat.get_state()
            weapons = combat_state.get("truth_weapons", {})
            for w in weapons.values():
                if isinstance(w, dict) and w.get("last_fired_ago", 999) < 30:
                    self._in_combat = True
                    self._combat_cooldown = 30.0
                    break

        if self._combat_cooldown > 0:
            self._combat_cooldown -= dt
            self._in_combat = self._combat_cooldown > 0

        if self._in_combat:
            self.crew.combat_time += dt
            self.crew.rest_time = 0.0
        else:
            self.crew.combat_time = max(0.0, self.crew.combat_time - dt * 0.1)

    def _update_g_effects(self, dt: float, current_g: float, event_bus, ship):
        """Update g-load dose accumulation."""
        excess_g = max(0.0, current_g - self.g_comfortable)
        if excess_g > 0:
            # G-dose accumulates proportional to excess g-force
            # Experienced crew resist better
            resistance = max(0.3, self.crew_experience)
            dose_rate = excess_g * FATIGUE_RATE_G_LOAD / resistance
            self.crew.g_dose = min(1.0, self.crew.g_dose + dose_rate * dt)
            self.crew.rest_time = 0.0
        else:
            # G-dose recovers slowly at comfortable g
            recovery = REST_RECOVERY_RATE * 0.5 * dt
            self.crew.g_dose = max(0.0, self.crew.g_dose - recovery)

    def _update_fatigue(self, dt: float, current_g: float, event_bus, ship):
        """Update overall fatigue level."""
        is_resting = current_g < REST_G_THRESHOLD and not self._in_combat

        if is_resting and self._rest_ordered:
            # Active rest: faster recovery
            self.crew.rest_time += dt
            recovery = REST_RECOVERY_RATE * 2.0 * dt
            self.crew.fatigue = max(0.0, self.crew.fatigue - recovery)
        elif is_resting:
            # Passive recovery at low-g
            self.crew.rest_time += dt
            recovery = REST_RECOVERY_RATE * dt
            self.crew.fatigue = max(0.0, self.crew.fatigue - recovery)
        else:
            self.crew.rest_time = 0.0

            # Fatigue accumulates from multiple sources
            rate = FATIGUE_RATE_BASE

            # High-g fatigue (dominant factor during hard burns)
            excess_g = max(0.0, current_g - self.g_comfortable)
            rate += excess_g * FATIGUE_RATE_G_LOAD

            # Combat stress fatigue
            if self._in_combat:
                rate += FATIGUE_RATE_COMBAT

            # Experienced crew fatigue slower
            rate /= max(0.3, self.crew_experience)

            self.crew.fatigue = min(1.0, self.crew.fatigue + rate * dt)

    def _update_blackout(self, dt: float, current_g: float, event_bus, ship):
        """Update blackout state from extreme g-loads."""
        if current_g >= self.g_extreme:
            # Accumulate blackout timer
            severity = (current_g - self.g_extreme) / (G_FATAL - self.g_extreme)
            rate = 1.0 + severity * 2.0  # Faster onset at higher g
            self.crew.blackout_timer += rate * dt

            if self.crew.blackout_timer >= BLACKOUT_ONSET_TIME and not self.crew.is_blacked_out:
                self.crew.is_blacked_out = True
                self.crew.blackout_recovery = BLACKOUT_RECOVERY_TIME
                if event_bus and ship:
                    event_bus.publish("crew_blackout", {
                        "ship_id": ship.id,
                        "g_force": round(current_g, 1),
                        "description": f"Crew blacked out at {current_g:.1f}g "
                                       f"after {self.crew.blackout_timer:.0f}s sustained",
                    })
        else:
            # Recovery from extreme g
            self.crew.blackout_timer = max(0.0, self.crew.blackout_timer - dt * 2.0)

            if self.crew.is_blacked_out:
                if current_g < self.g_comfortable:
                    self.crew.blackout_recovery -= dt
                    if self.crew.blackout_recovery <= 0:
                        self.crew.is_blacked_out = False
                        self.crew.blackout_recovery = 0.0
                        if event_bus and ship:
                            event_bus.publish("crew_recovered", {
                                "ship_id": ship.id,
                                "description": "Crew regaining consciousness",
                            })

    def _emit_alerts(self, event_bus, ship):
        """Emit crew state alerts when thresholds are crossed."""
        if not event_bus or not ship:
            return

        # Determine alert level
        if self.crew.is_blacked_out:
            alert = "blackout"
        elif self.crew.fatigue > 0.9:
            alert = "exhausted"
        elif self.crew.fatigue > 0.7:
            alert = "heavy_fatigue"
        elif self.crew.current_g >= self.g_high:
            alert = "high_g"
        elif self.crew.fatigue > 0.5:
            alert = "moderate_fatigue"
        else:
            alert = "nominal"

        if alert != self._last_alert:
            self._last_alert = alert
            if alert != "nominal":
                event_bus.publish("crew_fatigue_alert", {
                    "ship_id": ship.id,
                    "alert": alert,
                    "fatigue": round(self.crew.fatigue, 2),
                    "g_force": round(self.crew.current_g, 1),
                    "performance": round(self.get_performance_factor(), 2),
                    "description": self._alert_description(alert),
                })

    def _alert_description(self, alert: str) -> str:
        """Human-readable alert description."""
        descriptions = {
            "blackout": "Crew incapacitated — all manual operations suspended",
            "exhausted": "Crew exhausted — severe performance degradation, risk of errors",
            "heavy_fatigue": "Crew heavily fatigued — manual tasks significantly slower",
            "high_g": f"High g-load ({self.crew.current_g:.1f}g) — crew performance impaired",
            "moderate_fatigue": "Crew showing signs of fatigue — consider rest rotation",
        }
        return descriptions.get(alert, "")

    # ------------------------------------------------------------------
    # Performance queries (called by other systems)
    # ------------------------------------------------------------------

    def get_performance_factor(self) -> float:
        """Get overall crew performance multiplier (0.0 to 1.0).

        Combines fatigue degradation and current g-load impairment.
        Used by targeting, helm, ops systems to scale their effectiveness.

        Returns:
            Performance multiplier (0.0 = incapacitated, 1.0 = peak)
        """
        if self.crew.is_blacked_out:
            return 0.0

        fatigue_factor = _interpolate_curve(
            FATIGUE_PERFORMANCE_CURVE, self.crew.fatigue
        )
        g_factor = _interpolate_curve(
            G_LOAD_PERFORMANCE_CURVE, self.crew.current_g
        )

        # Combine multiplicatively
        return max(0.0, min(1.0, fatigue_factor * g_factor))

    def get_station_performance(self, station: str) -> float:
        """Get performance factor for a specific station role.

        Different stations are affected differently by fatigue:
        - HELM: Heavily impacted by g-loads (physical precision)
        - TACTICAL: Moderately impacted (computation + timing)
        - ENGINEERING: Mildly impacted (physical repair work)
        - SENSORS/SCIENCE: Least impacted (cognitive, sitting work)

        Args:
            station: Station name (helm, tactical, ops, engineering, etc.)

        Returns:
            Performance multiplier (0.0 to 1.0)
        """
        base = self.get_performance_factor()
        if base == 0.0:
            return 0.0

        # Station-specific g-load sensitivity
        g_sensitivity = {
            "helm": 1.2,        # Helmsman needs precise physical control
            "tactical": 1.0,    # Standard sensitivity
            "ops": 0.9,         # Slightly less physical
            "engineering": 1.1, # Physical repair work affected
            "comms": 0.7,       # Mostly cognitive
            "science": 0.7,     # Mostly cognitive
        }

        sensitivity = g_sensitivity.get(station.lower(), 1.0)

        # Apply extra g-load penalty for physically demanding stations
        if sensitivity != 1.0 and self.crew.current_g > self.g_comfortable:
            excess = self.crew.current_g - self.g_comfortable
            g_penalty = excess * 0.05 * (sensitivity - 0.7)
            base = max(0.05, base - g_penalty)

        return round(max(0.0, min(1.0, base)), 3)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def command(self, action: str, params: dict) -> dict:
        """Handle crew fatigue commands."""
        if action == "crew_rest":
            return self._cmd_crew_rest(params)
        elif action == "crew_status":
            return self._cmd_crew_status(params)
        elif action == "cancel_rest":
            return self._cmd_cancel_rest(params)
        return super().command(action, params)

    def _cmd_crew_rest(self, params: dict) -> dict:
        """Order crew to rest stations (must be at low-g)."""
        if self.crew.current_g > REST_G_THRESHOLD + 0.5:
            return {
                "ok": False,
                "error": "CANNOT_REST_UNDER_G",
                "message": f"Cannot rest crew at {self.crew.current_g:.1f}g. "
                           f"Reduce acceleration below {REST_G_THRESHOLD}g first.",
            }
        self._rest_ordered = True
        return {
            "ok": True,
            "status": "Crew rest ordered",
            "fatigue": round(self.crew.fatigue, 2),
            "recovery_rate": "accelerated",
        }

    def _cmd_cancel_rest(self, params: dict) -> dict:
        """Cancel crew rest order."""
        self._rest_ordered = False
        return {
            "ok": True,
            "status": "Crew rest cancelled — returning to duty stations",
            "fatigue": round(self.crew.fatigue, 2),
        }

    def _cmd_crew_status(self, params: dict) -> dict:
        """Get detailed crew fatigue status."""
        perf = self.get_performance_factor()
        stations = {}
        for s in ["helm", "tactical", "ops", "engineering", "comms", "science"]:
            stations[s] = self.get_station_performance(s)

        status_label = "nominal"
        if self.crew.is_blacked_out:
            status_label = "BLACKOUT"
        elif self.crew.fatigue > 0.9:
            status_label = "EXHAUSTED"
        elif self.crew.fatigue > 0.7:
            status_label = "HEAVY_FATIGUE"
        elif self.crew.fatigue > 0.5:
            status_label = "FATIGUED"
        elif self.crew.current_g > self.g_high:
            status_label = "G_IMPAIRED"

        return {
            "ok": True,
            "status": status_label,
            "crew_state": self.crew.to_dict(),
            "performance": round(perf, 3),
            "station_performance": stations,
            "rest_ordered": self._rest_ordered,
            "in_combat": self._in_combat,
            "crew_experience": self.crew_experience,
            "thresholds": {
                "g_comfortable": self.g_comfortable,
                "g_high": self.g_high,
                "g_extreme": self.g_extreme,
            },
        }

    # ------------------------------------------------------------------
    # State for telemetry
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Return system state for telemetry."""
        state = super().get_state()
        perf = self.get_performance_factor()

        status = "nominal"
        if self.crew.is_blacked_out:
            status = "blackout"
        elif self.crew.fatigue > 0.9:
            status = "exhausted"
        elif self.crew.fatigue > 0.7:
            status = "heavy_fatigue"
        elif self.crew.fatigue > 0.5:
            status = "fatigued"
        elif self.crew.current_g > self.g_high:
            status = "g_impaired"

        state.update({
            "status": status,
            "fatigue": round(self.crew.fatigue, 3),
            "g_load": round(self.crew.current_g, 2),
            "g_dose": round(self.crew.g_dose, 3),
            "performance": round(perf, 3),
            "is_blacked_out": self.crew.is_blacked_out,
            "blackout_timer": round(self.crew.blackout_timer, 1),
            "rest_ordered": self._rest_ordered,
            "in_combat": self._in_combat,
            "crew_experience": self.crew_experience,
        })
        return state
