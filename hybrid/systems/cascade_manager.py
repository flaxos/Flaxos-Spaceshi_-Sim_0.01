# hybrid/systems/cascade_manager.py
"""Cascade damage effects: subsystem failures propagate through dependent systems.

When a subsystem is damaged or destroyed, cascading effects ripple through
all systems that depend on it. Each cascade produces causal feedback so the
player understands exactly *what* failed and *why*.

Dependency graph:
    reactor -> [propulsion, rcs, sensors, weapons, targeting, life_support, radiators]
    sensors -> [targeting]
    rcs     -> [targeting]  (cannot aim = solutions degrade)

Cascade effects are *not* additional damage — they are performance penalties
applied on top of the existing combined_factor (damage * heat). A destroyed
reactor doesn't break the sensors; it denies them power so they can't operate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dependency definitions
# ---------------------------------------------------------------------------

@dataclass
class CascadeEffect:
    """A single cascade relationship: source failure degrades a dependent."""
    source: str            # Subsystem whose failure triggers this cascade
    dependent: str         # Subsystem that suffers the cascade effect
    description: str       # Human-readable explanation for the player
    penalty_failed: float  # Factor applied when source is OFFLINE/DESTROYED (0.0 = total denial)
    penalty_damaged: float # Factor applied when source is DAMAGED (partial degradation)


# The canonical dependency table.  Each entry says:
#   "When <source> is damaged/destroyed, <dependent> performance is scaled by penalty."
CASCADE_RULES: List[CascadeEffect] = [
    # Reactor powers everything
    CascadeEffect(
        source="reactor",
        dependent="propulsion",
        description="Reactor failure — main drive has no power",
        penalty_failed=0.0,
        penalty_damaged=0.5,
    ),
    CascadeEffect(
        source="reactor",
        dependent="rcs",
        description="Reactor failure — RCS thrusters have no power",
        penalty_failed=0.0,
        penalty_damaged=0.5,
    ),
    CascadeEffect(
        source="reactor",
        dependent="sensors",
        description="Reactor failure — sensors have no power",
        penalty_failed=0.0,
        penalty_damaged=0.6,
    ),
    CascadeEffect(
        source="reactor",
        dependent="weapons",
        description="Reactor failure — weapons have no power",
        penalty_failed=0.0,
        penalty_damaged=0.5,
    ),
    CascadeEffect(
        source="reactor",
        dependent="targeting",
        description="Reactor failure — targeting computer has no power",
        penalty_failed=0.0,
        penalty_damaged=0.6,
    ),
    CascadeEffect(
        source="reactor",
        dependent="life_support",
        description="Reactor failure — life support has no power",
        penalty_failed=0.0,
        penalty_damaged=0.7,
    ),
    # Sensors feed the targeting pipeline
    CascadeEffect(
        source="sensors",
        dependent="targeting",
        description="Sensors offline — targeting pipeline is blind, no new tracks possible",
        penalty_failed=0.0,
        penalty_damaged=0.4,
    ),
    # RCS required to aim weapons (ship must rotate to point weapons)
    CascadeEffect(
        source="rcs",
        dependent="targeting",
        description="RCS offline — cannot orient ship to aim weapons, firing solutions degrading",
        penalty_failed=0.1,
        penalty_damaged=0.6,
    ),
    # Reactor powers radiator coolant pumps
    CascadeEffect(
        source="reactor",
        dependent="radiators",
        description="Reactor failure — radiator coolant pumps have no power, heat rejection degraded",
        penalty_failed=0.1,
        penalty_damaged=0.7,
    ),
]


# ---------------------------------------------------------------------------
# Cascade Manager
# ---------------------------------------------------------------------------

class CascadeManager:
    """Evaluates cascade effects each tick and publishes causal feedback.

    Sits between the damage model and individual systems. Each tick it:
    1. Reads subsystem statuses from the damage model
    2. Computes a cascade_factor per subsystem (product of all upstream penalties)
    3. Publishes ``cascade_effect`` events when factors change
    4. Exposes ``get_cascade_factor(subsystem)`` for systems to query
    """

    def __init__(self, rules: Optional[List[CascadeEffect]] = None):
        self._rules = rules if rules is not None else CASCADE_RULES
        # subsystem -> current cascade factor (1.0 = no cascade)
        self._factors: Dict[str, float] = {}
        # Active cascade alerts (source -> dependent -> description)
        self._active_cascades: Dict[str, Dict[str, str]] = {}

    def tick(self, damage_model, event_bus=None, ship_id: Optional[str] = None):
        """Recompute cascade factors from current damage model state.

        Args:
            damage_model: DamageModel instance with subsystem health data
            event_bus: Optional EventBus for publishing cascade events
            ship_id: Ship identifier for event context
        """
        new_factors: Dict[str, float] = {}
        new_cascades: Dict[str, Dict[str, str]] = {}

        from hybrid.systems.damage_model import SubsystemStatus

        for rule in self._rules:
            source_sub = damage_model.subsystems.get(rule.source)
            if not source_sub:
                continue
            # Skip if dependent doesn't exist on this ship
            if rule.dependent not in damage_model.subsystems:
                continue

            status = source_sub.get_status()

            # Determine penalty based on source status
            if status in (SubsystemStatus.DESTROYED, SubsystemStatus.OFFLINE):
                penalty = rule.penalty_failed
            elif status == SubsystemStatus.DAMAGED:
                penalty = rule.penalty_damaged
            else:
                penalty = 1.0  # No cascade when source is healthy

            if penalty < 1.0:
                # Accumulate: multiple sources can degrade the same dependent
                current = new_factors.get(rule.dependent, 1.0)
                new_factors[rule.dependent] = current * penalty

                # Track active cascades for reporting
                new_cascades.setdefault(rule.source, {})[rule.dependent] = rule.description

        # Detect changes and publish events
        for dep, factor in new_factors.items():
            old_factor = self._factors.get(dep, 1.0)
            if abs(factor - old_factor) > 0.01 and event_bus:
                # Find the descriptions for this cascade
                descriptions = []
                for src, deps in new_cascades.items():
                    if dep in deps:
                        descriptions.append(deps[dep])

                event_bus.publish("cascade_effect", {
                    "ship_id": ship_id,
                    "subsystem": dep,
                    "cascade_factor": round(factor, 3),
                    "previous_factor": round(old_factor, 3),
                    "descriptions": descriptions,
                })

        # Detect cleared cascades
        for dep, old_factor in self._factors.items():
            if dep not in new_factors and old_factor < 1.0 and event_bus:
                event_bus.publish("cascade_cleared", {
                    "ship_id": ship_id,
                    "subsystem": dep,
                    "previous_factor": round(old_factor, 3),
                })

        self._factors = new_factors
        self._active_cascades = new_cascades

    def get_cascade_factor(self, subsystem: str) -> float:
        """Get the cascade penalty factor for a subsystem.

        Returns:
            float: 0.0 (completely denied by upstream failure) to 1.0 (no cascade).
        """
        return self._factors.get(subsystem, 1.0)

    def get_active_cascades(self) -> List[dict]:
        """Get list of currently active cascade effects for reporting.

        Returns:
            list: Active cascade descriptions with source, dependent, description
        """
        result = []
        for source, deps in self._active_cascades.items():
            for dependent, description in deps.items():
                result.append({
                    "source": source,
                    "dependent": dependent,
                    "description": description,
                    "cascade_factor": round(self._factors.get(dependent, 1.0), 3),
                })
        return result

    def get_report(self) -> dict:
        """Get cascade status report for telemetry.

        Returns:
            dict: Cascade factors and active effects
        """
        return {
            "factors": {k: round(v, 3) for k, v in self._factors.items()},
            "active_cascades": self.get_active_cascades(),
        }
