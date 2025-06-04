# hybrid/systems/bio_monitor_system.py
"""Monitor crew health and g-force limits."""

from hybrid.base_system import BaseSystem
import math
import logging

logger = logging.getLogger(__name__)

class BioMonitorSystem(BaseSystem):
    """Monitors crew health and g-force limitations."""

    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}

        # Basic settings
        self.power_draw = config.get("power_draw", 1.0)
        self.g_limit = config.get("g_limit", 8.0)
        self.fail_timer = config.get("fail_timer", 0.0)
        self.current_g = config.get("current_g", 0.0)
        self.status = config.get("status", "nominal")
        self.crew_health = config.get("crew_health", 1.0)
        self.override = config.get("override", False)

        # Extended configuration
        self.crew_count = int(config.get("crew_count", 1))
        self.health_status = config.get("health_status", "nominal")
        self.max_sustained_g = float(config.get("max_sustained_g", 3.0))
        self.max_peak_g = float(config.get("max_peak_g", 8.0))
        self.safety_override = config.get("safety_override", False)
        self.events = []

    def tick(self, dt, ship, event_bus):
        if not self.enabled:
            return

        power_system = ship.systems.get("power")
        if power_system and not power_system.request_power(self.power_draw * dt, "bio_monitor"):
            event_bus.publish("bio_monitor_offline", None, "bio_monitor")
            return

        a = ship.acceleration
        g_force = math.sqrt(a["x"]**2 + a["y"]**2 + a["z"]**2) / 9.81
        self.current_g = g_force

        if self.override or self.safety_override:
            self.status = "override"
            self.fail_timer = 0
            return

        old_status = self.status

        if g_force > self.max_peak_g or g_force > self.g_limit:
            self.fail_timer += dt
            if self.fail_timer > 3:
                self.status = "fatal"
                self.crew_health = 0.0
                self.health_status = "critical"
                event_bus.publish("crew_fatal", None, "bio_monitor")
            else:
                self.status = "warning"
                self.health_status = "warning"
                event_bus.publish("high_g_warning", {"g_force": g_force, "timer": self.fail_timer}, "bio_monitor")
        elif g_force > self.max_sustained_g:
            self.health_status = "warning"
            self.status = "warning"
            event_bus.publish("bio_warning", {"system": "bio", "g_forces": g_force, "limit": self.max_sustained_g})
        else:
            self.status = "nominal"
            self.health_status = "nominal"
            self.fail_timer = 0

        if old_status != self.status:
            event_bus.publish("bio_status_change", {"status": self.status}, "bio_monitor")

    def command(self, action, params):
        if action in ("override_bio_monitor", "override"):
            return self.set_override(True)
        if action == "reset_override":
            return self.set_override(False)
        if action == "reset_warnings":
            return self.reset_warnings()
        if action == "get_crew_status":
            return self.get_crew_status()
        if action == "status":
            return self.get_state()
        if action == "power_on":
            return self.power_on()
        if action == "power_off":
            return self.power_off()
        return super().command(action, params)

    def set_override(self, enabled=True):
        self.override = enabled
        self.safety_override = enabled
        status = "enabled" if enabled else "disabled"
        return {"status": f"Bio monitor override {status}", "override": enabled}

    def reset_warnings(self):
        if self.current_g <= self.max_sustained_g:
            self.health_status = "nominal"
            self.status = "monitoring"
            self.events = []
            return {"status": "Bio monitor warnings reset"}
        return {"status": "Warnings not reset", "error": "Current g-forces still exceed safe limits"}

    def get_crew_status(self):
        crew_status = []
        for i in range(self.crew_count):
            crew_status.append({
                "id": f"crew_{i+1}",
                "health": self.health_status,
                "g_tolerance": {
                    "current": self.current_g,
                    "max_sustained": self.max_sustained_g,
                    "max_peak": self.max_peak_g,
                },
            })
        return {"status": "Crew status retrieved", "crew_count": self.crew_count, "crew": crew_status, "overall": self.health_status}

    def get_state(self):
        state = super().get_state()
        state.update({
            "g_limit": self.g_limit,
            "fail_timer": round(self.fail_timer, 1),
            "current_g": round(self.current_g, 2),
            "status": self.status,
            "crew_health": self.crew_health,
            "override": self.override,
            "crew_count": self.crew_count,
            "health_status": self.health_status,
            "max_sustained_g": self.max_sustained_g,
            "max_peak_g": self.max_peak_g,
            "safety_override": self.safety_override,
        })
        return state
