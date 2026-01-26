# hybrid/systems/damage_model.py
"""Subsystem damage model for tracking health and degradation effects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class SubsystemHealth:
    name: str
    max_health: float
    health: float
    criticality: float
    failure_threshold: float

    def health_percent(self) -> float:
        if self.max_health <= 0:
            return 0.0
        return max(0.0, min(100.0, (self.health / self.max_health) * 100.0))

    def failure_health(self) -> float:
        if self.failure_threshold <= 1.0:
            return max(0.0, self.failure_threshold * self.max_health)
        return self.failure_threshold


class DamageModel:
    """Tracks per-subsystem health and provides degradation factors."""

    def __init__(
        self,
        config: Optional[dict] = None,
        schema: Optional[dict] = None,
        systems_config: Optional[dict] = None,
    ):
        config = config or {}
        schema = schema or {}
        systems_config = systems_config or {}

        subsystem_configs = config.get("subsystems", config)
        self.subsystems: Dict[str, SubsystemHealth] = {}

        for subsystem_name, defaults in schema.items():
            self._register_subsystem(subsystem_name, defaults, subsystem_configs.get(subsystem_name, {}))

        for subsystem_name in systems_config.keys():
            if subsystem_name not in self.subsystems:
                self._register_subsystem(subsystem_name, {}, subsystem_configs.get(subsystem_name, {}))

        for subsystem_name, overrides in subsystem_configs.items():
            if subsystem_name not in self.subsystems:
                self._register_subsystem(subsystem_name, {}, overrides)

    def _register_subsystem(self, name: str, defaults: dict, overrides: dict):
        max_health = float(overrides.get("max_health", defaults.get("max_health", 100.0)))
        health = float(overrides.get("health", overrides.get("current_health", max_health)))
        criticality = float(overrides.get("criticality", defaults.get("criticality", 1.0)))
        failure_threshold = float(overrides.get("failure_threshold", defaults.get("failure_threshold", 0.2)))

        self.subsystems[name] = SubsystemHealth(
            name=name,
            max_health=max_health,
            health=min(max_health, max(0.0, health)),
            criticality=max(0.0, criticality),
            failure_threshold=max(0.0, failure_threshold),
        )

    def apply_damage(self, subsystem: str, amount: float) -> dict:
        if amount <= 0:
            return {"ok": False, "error": "Invalid damage amount"}

        data = self.subsystems.get(subsystem)
        if not data:
            return {"ok": False, "error": f"Unknown subsystem '{subsystem}'"}

        data.health = max(0.0, data.health - amount)
        return self.get_subsystem_report(subsystem)

    def repair_subsystem(self, subsystem: str, amount: float) -> dict:
        if amount <= 0:
            return {"ok": False, "error": "Invalid repair amount"}

        data = self.subsystems.get(subsystem)
        if not data:
            return {"ok": False, "error": f"Unknown subsystem '{subsystem}'"}

        data.health = min(data.max_health, data.health + amount)
        return self.get_subsystem_report(subsystem)

    def get_degradation_factor(self, subsystem: str) -> float:
        data = self.subsystems.get(subsystem)
        if not data or data.max_health <= 0:
            return 1.0

        if data.health <= data.failure_health():
            return 0.0

        return max(0.1, data.health / data.max_health)

    def get_subsystem_report(self, subsystem: str) -> dict:
        data = self.subsystems.get(subsystem)
        if not data:
            return {"ok": False, "error": f"Unknown subsystem '{subsystem}'"}

        health_percent = data.health_percent()
        status = "failed" if data.health <= data.failure_health() else "degraded" if health_percent < 100.0 else "nominal"

        return {
            "ok": True,
            "subsystem": subsystem,
            "health": data.health,
            "max_health": data.max_health,
            "health_percent": health_percent,
            "criticality": data.criticality,
            "failure_threshold": data.failure_threshold,
            "status": status,
            "degradation_factor": self.get_degradation_factor(subsystem),
        }

    def get_report(self) -> dict:
        return {
            "subsystems": {
                name: self.get_subsystem_report(name)
                for name in sorted(self.subsystems.keys())
            }
        }
