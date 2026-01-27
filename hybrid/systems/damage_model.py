# hybrid/systems/damage_model.py
"""Subsystem damage model for tracking health and degradation effects.

Sprint C: Enhanced with mission kill detection and combat damage tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class SubsystemStatus(Enum):
    """Subsystem operational status."""
    NOMINAL = "nominal"      # Full operation
    DEGRADED = "degraded"    # Reduced capability
    CRITICAL = "critical"    # Severely impaired
    FAILED = "failed"        # Non-functional


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

    def get_status(self) -> SubsystemStatus:
        """Get operational status based on health."""
        pct = self.health_percent()
        if pct <= 0 or self.health <= self.failure_health():
            return SubsystemStatus.FAILED
        elif pct < 25:
            return SubsystemStatus.CRITICAL
        elif pct < 75:
            return SubsystemStatus.DEGRADED
        return SubsystemStatus.NOMINAL

    def is_failed(self) -> bool:
        """Check if subsystem has failed."""
        return self.health <= self.failure_health()


class DamageModel:
    """Tracks per-subsystem health and provides degradation factors.

    Sprint C: Enhanced with mission kill detection for combat scenarios.
    A ship is "mission killed" when it can no longer maneuver or fight.
    """

    # Subsystems that must be functional to avoid mission kill
    MOBILITY_SYSTEMS = ["propulsion", "rcs"]
    COMBAT_SYSTEMS = ["weapons", "targeting"]

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

        # Damage history for combat analysis
        self.damage_history: List[dict] = []
        self._total_damage_taken = 0.0

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

    def apply_damage(self, subsystem: str, amount: float, source: str = None) -> dict:
        """Apply damage to a subsystem.

        Args:
            subsystem: Name of subsystem to damage
            amount: Damage amount
            source: Optional damage source identifier

        Returns:
            dict: Damage result with subsystem status
        """
        if amount <= 0:
            return {"ok": False, "error": "Invalid damage amount"}

        data = self.subsystems.get(subsystem)
        if not data:
            return {"ok": False, "error": f"Unknown subsystem '{subsystem}'"}

        prev_health = data.health
        prev_status = data.get_status()

        data.health = max(0.0, data.health - amount)
        self._total_damage_taken += amount

        new_status = data.get_status()

        # Record damage in history
        self.damage_history.append({
            "subsystem": subsystem,
            "damage": amount,
            "source": source,
            "health_before": prev_health,
            "health_after": data.health,
            "status_change": prev_status != new_status,
            "new_status": new_status.value,
        })

        # Log significant status changes
        if new_status == SubsystemStatus.FAILED and prev_status != SubsystemStatus.FAILED:
            logger.warning(f"Subsystem {subsystem} FAILED")
        elif new_status == SubsystemStatus.CRITICAL and prev_status not in [SubsystemStatus.CRITICAL, SubsystemStatus.FAILED]:
            logger.warning(f"Subsystem {subsystem} CRITICAL")

        result = self.get_subsystem_report(subsystem)
        result["damage_applied"] = amount
        result["status_changed"] = prev_status != new_status
        return result

    def repair_subsystem(self, subsystem: str, amount: float) -> dict:
        """Repair a subsystem.

        Args:
            subsystem: Name of subsystem to repair
            amount: Repair amount

        Returns:
            dict: Repair result with subsystem status
        """
        if amount <= 0:
            return {"ok": False, "error": "Invalid repair amount"}

        data = self.subsystems.get(subsystem)
        if not data:
            return {"ok": False, "error": f"Unknown subsystem '{subsystem}'"}

        prev_health = data.health
        data.health = min(data.max_health, data.health + amount)

        result = self.get_subsystem_report(subsystem)
        result["repair_applied"] = data.health - prev_health
        return result

    def get_degradation_factor(self, subsystem: str) -> float:
        """Get performance degradation factor for a subsystem.

        Args:
            subsystem: Subsystem name

        Returns:
            float: Factor from 0.0 (failed) to 1.0 (full health)
        """
        data = self.subsystems.get(subsystem)
        if not data or data.max_health <= 0:
            return 1.0

        if data.health <= data.failure_health():
            return 0.0

        return max(0.1, data.health / data.max_health)

    def is_subsystem_failed(self, subsystem: str) -> bool:
        """Check if a specific subsystem has failed.

        Args:
            subsystem: Subsystem name

        Returns:
            bool: True if failed
        """
        data = self.subsystems.get(subsystem)
        if not data:
            return False
        return data.is_failed()

    def is_mobility_kill(self) -> bool:
        """Check if ship has suffered a mobility kill.

        A mobility kill means the ship cannot maneuver effectively.
        Both propulsion AND RCS must be functional for mobility.

        Returns:
            bool: True if mobility is compromised
        """
        for system in self.MOBILITY_SYSTEMS:
            if system in self.subsystems and self.subsystems[system].is_failed():
                return True
        return False

    def is_firepower_kill(self) -> bool:
        """Check if ship has suffered a firepower kill.

        A firepower kill means the ship cannot effectively engage targets.

        Returns:
            bool: True if weapons are compromised
        """
        weapons = self.subsystems.get("weapons")
        if weapons and weapons.is_failed():
            return True
        return False

    def is_mission_kill(self) -> bool:
        """Check if ship has suffered a mission kill.

        A mission kill means the ship can no longer perform its combat role.
        This occurs when the ship loses EITHER mobility OR firepower.

        Returns:
            bool: True if ship is mission killed
        """
        return self.is_mobility_kill() or self.is_firepower_kill()

    def get_mission_kill_reason(self) -> Optional[str]:
        """Get the reason for mission kill status.

        Returns:
            str: Reason for mission kill, or None if not mission killed
        """
        if not self.is_mission_kill():
            return None

        reasons = []
        if self.is_mobility_kill():
            failed = [s for s in self.MOBILITY_SYSTEMS
                      if s in self.subsystems and self.subsystems[s].is_failed()]
            reasons.append(f"mobility_kill ({', '.join(failed)})")
        if self.is_firepower_kill():
            reasons.append("firepower_kill (weapons)")

        return "; ".join(reasons)

    def get_failed_subsystems(self) -> List[str]:
        """Get list of failed subsystems.

        Returns:
            list: Names of failed subsystems
        """
        return [name for name, data in self.subsystems.items() if data.is_failed()]

    def get_critical_subsystems(self) -> List[str]:
        """Get list of critical (but not failed) subsystems.

        Returns:
            list: Names of critical subsystems
        """
        return [
            name for name, data in self.subsystems.items()
            if data.get_status() == SubsystemStatus.CRITICAL
        ]

    def get_subsystem_report(self, subsystem: str) -> dict:
        """Get detailed report for a subsystem.

        Args:
            subsystem: Subsystem name

        Returns:
            dict: Subsystem status report
        """
        data = self.subsystems.get(subsystem)
        if not data:
            return {"ok": False, "error": f"Unknown subsystem '{subsystem}'"}

        status = data.get_status()

        return {
            "ok": True,
            "subsystem": subsystem,
            "health": data.health,
            "max_health": data.max_health,
            "health_percent": data.health_percent(),
            "criticality": data.criticality,
            "failure_threshold": data.failure_threshold,
            "status": status.value,
            "degradation_factor": self.get_degradation_factor(subsystem),
        }

    def get_report(self) -> dict:
        """Get full damage model report.

        Returns:
            dict: Complete damage status
        """
        return {
            "subsystems": {
                name: self.get_subsystem_report(name)
                for name in sorted(self.subsystems.keys())
            },
            "total_damage_taken": self._total_damage_taken,
            "mission_kill": self.is_mission_kill(),
            "mission_kill_reason": self.get_mission_kill_reason(),
            "mobility_kill": self.is_mobility_kill(),
            "firepower_kill": self.is_firepower_kill(),
            "failed_subsystems": self.get_failed_subsystems(),
            "critical_subsystems": self.get_critical_subsystems(),
        }

    def get_combat_summary(self) -> dict:
        """Get combat-focused damage summary.

        Returns:
            dict: Summary for combat evaluation
        """
        return {
            "mission_kill": self.is_mission_kill(),
            "mobility_kill": self.is_mobility_kill(),
            "firepower_kill": self.is_firepower_kill(),
            "propulsion_factor": self.get_degradation_factor("propulsion"),
            "rcs_factor": self.get_degradation_factor("rcs"),
            "weapons_factor": self.get_degradation_factor("weapons"),
            "sensors_factor": self.get_degradation_factor("sensors"),
            "total_damage": self._total_damage_taken,
            "damage_events": len(self.damage_history),
        }
