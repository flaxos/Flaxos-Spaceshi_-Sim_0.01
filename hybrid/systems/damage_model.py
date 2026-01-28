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
    """Subsystem operational status.

    v0.6.0: Health states follow the progression:
        ONLINE → DAMAGED → OFFLINE → DESTROYED

    Legacy compatibility:
        NOMINAL maps to ONLINE
        DEGRADED maps to DAMAGED
        CRITICAL maps to DAMAGED (severe)
        FAILED maps to OFFLINE
    """
    # v0.6.0 state names
    ONLINE = "online"        # Full operation (>75% health)
    DAMAGED = "damaged"      # Reduced capability (25-75% health)
    OFFLINE = "offline"      # Non-functional (≤threshold, but repairable)
    DESTROYED = "destroyed"  # Permanently non-functional (health = 0)

    # Legacy aliases (backward compatibility)
    NOMINAL = "online"       # Alias for ONLINE
    DEGRADED = "damaged"     # Alias for DAMAGED
    CRITICAL = "damaged"     # Maps to DAMAGED (use is_critical() for distinction)
    FAILED = "offline"       # Alias for OFFLINE


@dataclass
class SubsystemHealth:
    """Tracks health and heat state for a single subsystem.

    v0.6.0: Added heat management fields.
    """
    name: str
    max_health: float
    health: float
    criticality: float
    failure_threshold: float
    # v0.6.0: Heat management
    heat: float = 0.0
    max_heat: float = 100.0
    heat_generation: float = 1.0
    heat_dissipation: float = 1.5
    overheat_threshold: float = 0.80
    overheat_penalty: float = 0.5

    def health_percent(self) -> float:
        if self.max_health <= 0:
            return 0.0
        return max(0.0, min(100.0, (self.health / self.max_health) * 100.0))

    def failure_health(self) -> float:
        if self.failure_threshold <= 1.0:
            return max(0.0, self.failure_threshold * self.max_health)
        return self.failure_threshold

    def heat_percent(self) -> float:
        """Get current heat as percentage of max."""
        if self.max_heat <= 0:
            return 0.0
        return max(0.0, min(100.0, (self.heat / self.max_heat) * 100.0))

    def is_overheated(self) -> bool:
        """Check if subsystem is overheated."""
        return self.heat >= (self.max_heat * self.overheat_threshold)

    def get_heat_factor(self) -> float:
        """Get performance factor due to heat (1.0 = normal, lower = degraded).

        Returns:
            float: 1.0 if not overheated, overheat_penalty if overheated
        """
        if self.is_overheated():
            return self.overheat_penalty
        return 1.0

    def add_heat(self, amount: float) -> float:
        """Add heat to the subsystem.

        Args:
            amount: Heat to add

        Returns:
            float: New heat level
        """
        self.heat = min(self.max_heat, self.heat + amount)
        return self.heat

    def dissipate_heat(self, dt: float) -> float:
        """Dissipate heat over time.

        Args:
            dt: Time delta in seconds

        Returns:
            float: New heat level
        """
        self.heat = max(0.0, self.heat - (self.heat_dissipation * dt))
        return self.heat

    def get_status(self) -> SubsystemStatus:
        """Get operational status based on health.

        v0.6.0 state progression: ONLINE → DAMAGED → OFFLINE → DESTROYED

        Returns:
            SubsystemStatus: Current operational status
        """
        pct = self.health_percent()

        # DESTROYED: health = 0, subsystem is permanently non-functional
        if pct <= 0:
            return SubsystemStatus.DESTROYED

        # OFFLINE: health at or below failure threshold, non-functional but repairable
        if self.health <= self.failure_health():
            return SubsystemStatus.OFFLINE

        # DAMAGED: reduced capability (health < 75%)
        if pct < 75:
            return SubsystemStatus.DAMAGED

        # ONLINE: full operation (health >= 75%)
        return SubsystemStatus.ONLINE

    def is_critical(self) -> bool:
        """Check if subsystem is in critical state (< 25% health but not failed).

        Returns:
            bool: True if health < 25% but subsystem is still operational
        """
        pct = self.health_percent()
        return pct < 25 and pct > 0 and self.health > self.failure_health()

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
        """Register a subsystem with health and heat tracking.

        v0.6.0: Added heat settings from schema.
        """
        # Health settings
        max_health = float(overrides.get("max_health", defaults.get("max_health", 100.0)))
        health = float(overrides.get("health", overrides.get("current_health", max_health)))
        criticality = float(overrides.get("criticality", defaults.get("criticality", 1.0)))
        failure_threshold = float(overrides.get("failure_threshold", defaults.get("failure_threshold", 0.2)))

        # v0.6.0: Heat settings
        max_heat = float(overrides.get("max_heat", defaults.get("max_heat", 100.0)))
        heat = float(overrides.get("heat", 0.0))
        heat_generation = float(overrides.get("heat_generation", defaults.get("heat_generation", 1.0)))
        heat_dissipation = float(overrides.get("heat_dissipation", defaults.get("heat_dissipation", 1.5)))
        overheat_threshold = float(overrides.get("overheat_threshold", defaults.get("overheat_threshold", 0.80)))
        overheat_penalty = float(overrides.get("overheat_penalty", defaults.get("overheat_penalty", 0.5)))

        self.subsystems[name] = SubsystemHealth(
            name=name,
            max_health=max_health,
            health=min(max_health, max(0.0, health)),
            criticality=max(0.0, criticality),
            failure_threshold=max(0.0, failure_threshold),
            # v0.6.0: Heat tracking
            heat=max(0.0, heat),
            max_heat=max(1.0, max_heat),
            heat_generation=max(0.0, heat_generation),
            heat_dissipation=max(0.0, heat_dissipation),
            overheat_threshold=max(0.0, min(1.0, overheat_threshold)),
            overheat_penalty=max(0.0, min(1.0, overheat_penalty)),
        )

    def apply_damage(
        self,
        subsystem: str,
        amount: float,
        source: str = None,
        event_bus=None,
        ship_id: str = None
    ) -> dict:
        """Apply damage to a subsystem.

        v0.6.0: Enhanced with state transition events.

        Args:
            subsystem: Name of subsystem to damage
            amount: Damage amount
            source: Optional damage source identifier
            event_bus: Optional EventBus for publishing state change events
            ship_id: Optional ship ID for event context

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
        status_changed = prev_status != new_status

        # Record damage in history
        self.damage_history.append({
            "subsystem": subsystem,
            "damage": amount,
            "source": source,
            "health_before": prev_health,
            "health_after": data.health,
            "status_change": status_changed,
            "prev_status": prev_status.value,
            "new_status": new_status.value,
        })

        # v0.6.0: Publish state transition events
        if status_changed and event_bus:
            event_bus.publish("subsystem_state_changed", {
                "ship_id": ship_id,
                "subsystem": subsystem,
                "prev_status": prev_status.value,
                "new_status": new_status.value,
                "health": data.health,
                "health_percent": data.health_percent(),
                "source": source,
            })

            # Log and publish specific state transitions
            if new_status == SubsystemStatus.DESTROYED:
                logger.warning(f"Subsystem {subsystem} DESTROYED")
                event_bus.publish("subsystem_destroyed", {
                    "ship_id": ship_id,
                    "subsystem": subsystem,
                    "source": source,
                })
            elif new_status == SubsystemStatus.OFFLINE:
                logger.warning(f"Subsystem {subsystem} OFFLINE")
                event_bus.publish("subsystem_offline", {
                    "ship_id": ship_id,
                    "subsystem": subsystem,
                    "source": source,
                })
            elif new_status == SubsystemStatus.DAMAGED and data.is_critical():
                logger.warning(f"Subsystem {subsystem} CRITICAL")
                event_bus.publish("subsystem_critical", {
                    "ship_id": ship_id,
                    "subsystem": subsystem,
                    "health_percent": data.health_percent(),
                    "source": source,
                })
        elif status_changed:
            # Fallback logging when no event_bus provided
            if new_status == SubsystemStatus.OFFLINE:
                logger.warning(f"Subsystem {subsystem} OFFLINE")
            elif new_status == SubsystemStatus.DESTROYED:
                logger.warning(f"Subsystem {subsystem} DESTROYED")
            elif data.is_critical():
                logger.warning(f"Subsystem {subsystem} CRITICAL")

        result = self.get_subsystem_report(subsystem)
        result["damage_applied"] = amount
        result["status_changed"] = status_changed
        result["prev_status"] = prev_status.value
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

    def add_heat(
        self,
        subsystem: str,
        amount: float,
        event_bus=None,
        ship_id: str = None
    ) -> dict:
        """Add heat to a subsystem.

        v0.6.0: Heat management.

        Args:
            subsystem: Name of subsystem
            amount: Heat to add
            event_bus: Optional EventBus for overheat events
            ship_id: Optional ship ID for event context

        Returns:
            dict: Heat result with current status
        """
        data = self.subsystems.get(subsystem)
        if not data:
            return {"ok": False, "error": f"Unknown subsystem '{subsystem}'"}

        was_overheated = data.is_overheated()
        data.add_heat(amount)
        now_overheated = data.is_overheated()

        # Publish overheat event on transition
        if now_overheated and not was_overheated and event_bus:
            event_bus.publish("subsystem_overheat", {
                "ship_id": ship_id,
                "subsystem": subsystem,
                "heat": data.heat,
                "heat_percent": data.heat_percent(),
                "penalty": data.overheat_penalty,
            })
            logger.warning(f"Subsystem {subsystem} OVERHEATED")

        return {
            "ok": True,
            "subsystem": subsystem,
            "heat": data.heat,
            "max_heat": data.max_heat,
            "heat_percent": data.heat_percent(),
            "overheated": data.is_overheated(),
            "heat_factor": data.get_heat_factor(),
        }

    def dissipate_heat(self, dt: float, event_bus=None, ship_id: str = None):
        """Dissipate heat from all subsystems.

        v0.6.0: Called each tick to passively cool subsystems.

        Args:
            dt: Time delta in seconds
            event_bus: Optional EventBus for cooldown events
            ship_id: Optional ship ID for event context
        """
        for name, data in self.subsystems.items():
            was_overheated = data.is_overheated()
            data.dissipate_heat(dt)
            now_overheated = data.is_overheated()

            # Publish cooldown event on transition
            if was_overheated and not now_overheated and event_bus:
                event_bus.publish("subsystem_cooled", {
                    "ship_id": ship_id,
                    "subsystem": name,
                    "heat": data.heat,
                    "heat_percent": data.heat_percent(),
                })

    def get_combined_factor(self, subsystem: str) -> float:
        """Get combined performance factor from damage and heat.

        v0.6.0: Combines degradation_factor and heat_factor.

        Args:
            subsystem: Subsystem name

        Returns:
            float: Combined factor (0.0-1.0)
        """
        data = self.subsystems.get(subsystem)
        if not data:
            return 1.0

        damage_factor = self.get_degradation_factor(subsystem)
        heat_factor = data.get_heat_factor()
        return damage_factor * heat_factor

    def get_subsystem_report(self, subsystem: str) -> dict:
        """Get detailed report for a subsystem.

        v0.6.0: Now includes heat status.

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
            # Health
            "health": data.health,
            "max_health": data.max_health,
            "health_percent": data.health_percent(),
            "criticality": data.criticality,
            "failure_threshold": data.failure_threshold,
            "status": status.value,
            "is_critical": data.is_critical(),
            "degradation_factor": self.get_degradation_factor(subsystem),
            # v0.6.0: Heat
            "heat": data.heat,
            "max_heat": data.max_heat,
            "heat_percent": data.heat_percent(),
            "overheated": data.is_overheated(),
            "heat_factor": data.get_heat_factor(),
            # v0.6.0: Combined factor
            "combined_factor": self.get_combined_factor(subsystem),
        }

    def get_overheated_subsystems(self) -> List[str]:
        """Get list of overheated subsystems.

        v0.6.0: Heat management.

        Returns:
            list: Names of overheated subsystems
        """
        return [name for name, data in self.subsystems.items() if data.is_overheated()]

    def get_report(self) -> dict:
        """Get full damage model report.

        v0.6.0: Now includes heat status.

        Returns:
            dict: Complete damage and heat status
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
            # v0.6.0: Heat status
            "overheated_subsystems": self.get_overheated_subsystems(),
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
