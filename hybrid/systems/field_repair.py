# hybrid/systems/field_repair.py
"""Mid-mission field repair system for damage control during combat.

Design rationale:
- Field repairs are limited to 50% health (IMPAIRED). Only dock repairs
  can restore to NOMINAL. This creates a meaningful tactical choice:
  keep fighting with degraded systems or break off to a dock.
- Spare parts are finite. Each repair consumes parts proportional to
  the health restored. Running out of parts means no more field repairs.
- High g-loads slow or halt repairs. Damage control crews cannot work
  effectively when the ship is maneuvering hard. This forces the captain
  to choose between evasive action and getting systems back online.
- Repairs are interruptible: further damage to the subsystem being
  repaired resets progress, and high-g maneuvers pause the repair.

Integration:
- Sits alongside OpsSystem. OpsSystem owns the repair teams; this module
  manages repair constraints (parts, g-load, health cap).
- Ticked by OpsSystem during its repair team update.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Field repair can only restore health up to this fraction of max_health.
# Dock repairs are needed to go beyond this threshold.
FIELD_REPAIR_HEALTH_CAP = 0.50

# Spare parts consumed per health point restored.
# A subsystem with max_health=100 at 0% needs 50 parts to reach 50%.
PARTS_PER_HEALTH_POINT = 1.0

# G-load thresholds for repair speed modifiers.
# Below LOW_G: full repair speed (crew works normally).
# Between LOW_G and HIGH_G: linearly degraded repair speed.
# Above HIGH_G: repair impossible (crew cannot hold tools steady).
G_LOAD_LOW = 0.5    # Below 0.5g, repair at full speed
G_LOAD_HIGH = 3.0   # Above 3g, repair halted entirely

# Default spare parts capacity. Ships carry a limited supply of
# replacement components, wiring, sealant, etc.
DEFAULT_SPARE_PARTS = 200.0
DEFAULT_MAX_SPARE_PARTS = 200.0


class RepairPriority(Enum):
    """Priority levels for repair queue ordering."""
    CRITICAL = 3    # Repair immediately (propulsion, reactor)
    HIGH = 2        # Repair soon (weapons, sensors)
    NORMAL = 1      # Standard priority
    LOW = 0         # Repair when nothing else needs attention


@dataclass
class RepairJob:
    """Tracks a single field repair task.

    Each job represents a repair team working on a specific subsystem.
    Progress accumulates over time, consuming spare parts as health is restored.
    """
    subsystem: str
    priority: RepairPriority = RepairPriority.NORMAL
    health_restored: float = 0.0      # Total health points restored so far
    parts_consumed: float = 0.0       # Total spare parts used
    paused: bool = False              # True when g-load too high
    pause_reason: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize for telemetry."""
        return {
            "subsystem": self.subsystem,
            "priority": self.priority.name.lower(),
            "health_restored": round(self.health_restored, 1),
            "parts_consumed": round(self.parts_consumed, 1),
            "paused": self.paused,
            "pause_reason": self.pause_reason,
        }


class FieldRepairManager:
    """Manages field repair constraints: spare parts, g-load, and health cap.

    This manager does NOT own repair teams -- OpsSystem does. Instead, it
    provides constraint checks and resource tracking that OpsSystem consults
    during its repair tick.
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        self.spare_parts: float = float(
            config.get("spare_parts", DEFAULT_SPARE_PARTS)
        )
        self.max_spare_parts: float = float(
            config.get("max_spare_parts", DEFAULT_MAX_SPARE_PARTS)
        )
        # Active repair jobs keyed by subsystem name
        self.repair_jobs: Dict[str, RepairJob] = {}
        # Subsystem priority overrides
        self.priorities: Dict[str, RepairPriority] = {}
        # Completed repairs log
        self.completed_repairs: List[dict] = []
        self._total_parts_consumed: float = 0.0

    # ------------------------------------------------------------------
    # G-load repair speed modifier
    # ------------------------------------------------------------------

    def get_g_load_factor(self, current_g: float) -> float:
        """Calculate repair speed multiplier based on current g-load.

        Below G_LOAD_LOW: full speed (1.0).
        Between LOW and HIGH: linear interpolation down to 0.0.
        Above G_LOAD_HIGH: halted (0.0).

        Physical reasoning: damage control crews need to move through
        the ship, hold tools steady, and manipulate components. High
        acceleration pins them against bulkheads and makes fine motor
        work impossible.

        Args:
            current_g: Current g-load on the ship

        Returns:
            float: Repair speed factor 0.0 to 1.0
        """
        if current_g <= G_LOAD_LOW:
            return 1.0
        if current_g >= G_LOAD_HIGH:
            return 0.0
        # Linear interpolation between thresholds
        return 1.0 - (current_g - G_LOAD_LOW) / (G_LOAD_HIGH - G_LOAD_LOW)

    # ------------------------------------------------------------------
    # Health cap enforcement
    # ------------------------------------------------------------------

    def get_field_repair_cap(self, max_health: float) -> float:
        """Get the maximum health achievable through field repair.

        Field crews lack the precision equipment and clean-room conditions
        needed for full restoration. They can patch, splice, and jury-rig
        a subsystem back to partial function but not nominal.

        Args:
            max_health: Subsystem's maximum health

        Returns:
            float: Maximum health field repair can achieve
        """
        return max_health * FIELD_REPAIR_HEALTH_CAP

    # ------------------------------------------------------------------
    # Spare parts management
    # ------------------------------------------------------------------

    def consume_parts(self, health_amount: float) -> float:
        """Consume spare parts for a repair. Returns actual health repaired.

        If insufficient parts remain, repairs are reduced proportionally.

        Args:
            health_amount: Desired health points to restore

        Returns:
            float: Actual health points that can be restored given parts supply
        """
        parts_needed = health_amount * PARTS_PER_HEALTH_POINT
        if parts_needed <= self.spare_parts:
            self.spare_parts -= parts_needed
            self._total_parts_consumed += parts_needed
            return health_amount
        else:
            # Partial repair with remaining parts
            actual_health = self.spare_parts / PARTS_PER_HEALTH_POINT
            self._total_parts_consumed += self.spare_parts
            self.spare_parts = 0.0
            return actual_health

    def resupply_parts(self, amount: float) -> float:
        """Resupply spare parts (e.g., from docking at a station).

        Args:
            amount: Parts to add

        Returns:
            float: New spare parts level
        """
        self.spare_parts = min(self.max_spare_parts, self.spare_parts + amount)
        return self.spare_parts

    # ------------------------------------------------------------------
    # Repair job management
    # ------------------------------------------------------------------

    def start_repair(self, subsystem: str, priority: Optional[RepairPriority] = None) -> RepairJob:
        """Start or update a repair job for a subsystem.

        Args:
            subsystem: Subsystem name to repair
            priority: Optional priority override

        Returns:
            RepairJob: The active repair job
        """
        if subsystem in self.repair_jobs:
            job = self.repair_jobs[subsystem]
            if priority is not None:
                job.priority = priority
            return job

        job_priority = priority or self.priorities.get(subsystem, RepairPriority.NORMAL)
        job = RepairJob(subsystem=subsystem, priority=job_priority)
        self.repair_jobs[subsystem] = job
        return job

    def cancel_repair(self, subsystem: str) -> Optional[RepairJob]:
        """Cancel an active repair job.

        Args:
            subsystem: Subsystem name

        Returns:
            RepairJob if cancelled, None if not found
        """
        return self.repair_jobs.pop(subsystem, None)

    def complete_repair(self, subsystem: str) -> None:
        """Mark a repair job as complete and log it.

        Args:
            subsystem: Subsystem name
        """
        job = self.repair_jobs.pop(subsystem, None)
        if job:
            self.completed_repairs.append({
                "subsystem": subsystem,
                "health_restored": round(job.health_restored, 1),
                "parts_consumed": round(job.parts_consumed, 1),
            })

    def set_priority(self, subsystem: str, priority: RepairPriority) -> None:
        """Set repair priority for a subsystem.

        Args:
            subsystem: Subsystem name
            priority: Priority level
        """
        self.priorities[subsystem] = priority
        # Update active job if one exists
        if subsystem in self.repair_jobs:
            self.repair_jobs[subsystem].priority = priority

    def get_repair_queue(self) -> List[RepairJob]:
        """Get active repair jobs sorted by priority (highest first).

        Returns:
            list: Sorted repair jobs
        """
        return sorted(
            self.repair_jobs.values(),
            key=lambda j: j.priority.value,
            reverse=True,
        )

    # ------------------------------------------------------------------
    # Tick integration (called by OpsSystem)
    # ------------------------------------------------------------------

    def apply_repair_constraints(
        self,
        subsystem: str,
        raw_repair_amount: float,
        current_health: float,
        max_health: float,
        current_g: float,
    ) -> tuple[float, Optional[str]]:
        """Apply all field repair constraints to a raw repair amount.

        This is the main integration point. OpsSystem calls this before
        applying any repair to get the constrained amount.

        Constraints applied (in order):
        1. G-load speed factor
        2. Health cap (50% max)
        3. Spare parts availability

        Args:
            subsystem: Subsystem being repaired
            raw_repair_amount: Base repair amount from team repair_rate * dt
            current_health: Current subsystem health
            max_health: Maximum subsystem health
            current_g: Current ship g-load

        Returns:
            tuple: (actual_repair_amount, pause_reason or None)
        """
        # 1. G-load factor
        g_factor = self.get_g_load_factor(current_g)
        if g_factor <= 0.0:
            # Update job pause state
            job = self.repair_jobs.get(subsystem)
            if job:
                job.paused = True
                job.pause_reason = f"High g-load ({current_g:.1f}g) — repair halted"
            return 0.0, f"High g-load ({current_g:.1f}g) — repair halted"

        adjusted_amount = raw_repair_amount * g_factor

        # 2. Health cap — field repair cannot exceed 50% of max_health
        cap = self.get_field_repair_cap(max_health)
        if current_health >= cap:
            job = self.repair_jobs.get(subsystem)
            if job:
                job.paused = True
                job.pause_reason = "Field repair limit reached (50%) — dock repair needed"
            return 0.0, "Field repair limit reached (50%) — dock repair needed"

        # Don't overshoot the cap
        headroom = cap - current_health
        adjusted_amount = min(adjusted_amount, headroom)

        # 3. Spare parts
        actual_amount = self.consume_parts(adjusted_amount)
        if actual_amount <= 0.0:
            job = self.repair_jobs.get(subsystem)
            if job:
                job.paused = True
                job.pause_reason = "No spare parts remaining"
            return 0.0, "No spare parts remaining"

        # Update job tracking
        job = self.repair_jobs.get(subsystem)
        if job:
            job.health_restored += actual_amount
            job.parts_consumed += actual_amount * PARTS_PER_HEALTH_POINT
            job.paused = False
            job.pause_reason = None

        return actual_amount, None

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Get field repair state for telemetry."""
        return {
            "spare_parts": round(self.spare_parts, 1),
            "max_spare_parts": round(self.max_spare_parts, 1),
            "spare_parts_percent": round(
                (self.spare_parts / self.max_spare_parts * 100)
                if self.max_spare_parts > 0 else 0.0, 1
            ),
            "active_repairs": {
                name: job.to_dict()
                for name, job in self.repair_jobs.items()
            },
            "repair_queue": [j.to_dict() for j in self.get_repair_queue()],
            "completed_repairs": self.completed_repairs[-10:],  # Last 10
            "total_parts_consumed": round(self._total_parts_consumed, 1),
        }
