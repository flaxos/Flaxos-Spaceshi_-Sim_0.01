# hybrid/systems/proposals.py
"""Shared proposal model for CPU-ASSIST tier auto-systems.

Provides TacticalProposal, OpsProposal, and ProposalManager
used by auto_tactical and auto_ops systems.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class Proposal:
    """A proposed action awaiting player approval."""
    proposal_id: str
    action: str
    target: str
    confidence: float
    reason: str
    created_at: float
    timeout: float
    auto_execute: bool
    status: str = "pending"
    params: Dict[str, Any] = field(default_factory=dict)
    crew_efficiency: float = 1.0

    def to_dict(self) -> dict:
        """Serialize for telemetry."""
        return {
            "proposal_id": self.proposal_id,
            "action": self.action,
            "target_id": self.target,
            "target": self.target,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "created_at": self.created_at,
            "timeout": self.timeout,
            "auto_execute": self.auto_execute,
            "status": self.status,
            "time_remaining": max(0.0, self.timeout - (time.time() - self.created_at)),
            "crew_efficiency": round(self.crew_efficiency, 3),
        }


class ProposalManager:
    """Manages a queue of proposals with expiry and auto-execution.

    Args:
        max_proposals: Maximum concurrent pending proposals
        cooldown: Minimum seconds between proposals for same action key
    """

    def __init__(self, max_proposals: int = 3, cooldown: float = 3.0):
        self._proposals: List[Proposal] = []
        self._counter = 0
        self._last_proposal_time: Dict[str, float] = {}
        self._max = max_proposals
        self._cooldown = cooldown

    @property
    def pending(self) -> List[Proposal]:
        """Get all pending proposals."""
        return [p for p in self._proposals if p.status == "pending"]

    @property
    def pending_count(self) -> int:
        """Count pending proposals."""
        return len(self.pending)

    def clear(self):
        """Expire all pending proposals and clear the list."""
        for p in self._proposals:
            if p.status == "pending":
                p.status = "expired"
        self._proposals = []

    def expire_old(self, now: float, event_name: str, event_bus, ship) -> None:
        """Remove expired proposals that are NOT auto-execute.

        Args:
            now: Current time
            event_name: Event to publish on expiry
            event_bus: Event bus
            ship: Ship object
        """
        still_active = []
        for p in self._proposals:
            if p.status != "pending":
                continue
            elapsed = now - p.created_at
            if elapsed > p.timeout and not p.auto_execute:
                p.status = "expired"
                if event_bus and ship:
                    event_bus.publish(event_name, {
                        "ship_id": ship.id,
                        "proposal_id": p.proposal_id,
                        "action": p.action,
                    })
            else:
                still_active.append(p)
        self._proposals = still_active

    def can_propose(self, key: str, now: float) -> bool:
        """Check if a new proposal is allowed for this key.

        Args:
            key: Unique key for cooldown tracking
            now: Current time

        Returns:
            True if proposal is allowed
        """
        if self.pending_count >= self._max:
            return False
        last = self._last_proposal_time.get(key, 0.0)
        if now - last < self._cooldown:
            return False
        # Already have a pending proposal for this key?
        for p in self._proposals:
            if p.action == key and p.status == "pending":
                return False
        return True

    def create(self, prefix: str, action: str, target: str,
               confidence: float, reason: str, timeout: float,
               auto_execute: bool, now: float,
               params: Optional[Dict[str, Any]] = None,
               crew_efficiency: float = 1.0) -> Proposal:
        """Create and store a new proposal.

        Args:
            prefix: ID prefix (e.g. "TP" for tactical, "OP" for ops)
            action: Action name
            target: Target identifier
            confidence: Solution confidence (0-1)
            reason: Human-readable reason
            timeout: Seconds until expiry/auto-execute
            auto_execute: Whether to auto-execute on timeout
            now: Current time
            params: Extra parameters for execution
            crew_efficiency: Crew skill efficiency that influenced confidence

        Returns:
            The new Proposal
        """
        self._counter += 1
        proposal = Proposal(
            proposal_id=f"{prefix}-{self._counter:04d}",
            action=action,
            target=target,
            confidence=confidence,
            reason=reason,
            created_at=now,
            timeout=timeout,
            auto_execute=auto_execute,
            params=params or {},
            crew_efficiency=crew_efficiency,
        )
        self._proposals.append(proposal)
        self._last_proposal_time[action] = now
        return proposal

    def find_pending(self, proposal_id: Optional[str] = None) -> Optional[Proposal]:
        """Find a pending proposal by ID, or the first pending one.

        Args:
            proposal_id: Specific ID to find, or None for first pending

        Returns:
            Proposal or None
        """
        if proposal_id:
            for p in self._proposals:
                if p.proposal_id == proposal_id and p.status == "pending":
                    return p
            return None
        for p in self._proposals:
            if p.status == "pending":
                return p
        return None

    def get_auto_execute_ready(self, now: float) -> List[Proposal]:
        """Get proposals that have timed out and should auto-execute.

        Args:
            now: Current time

        Returns:
            List of proposals ready to auto-execute
        """
        ready = []
        for p in self._proposals:
            if p.status != "pending" or not p.auto_execute:
                continue
            if now - p.created_at >= p.timeout:
                ready.append(p)
        return ready

    def set_auto_execute(self, auto_execute: bool) -> None:
        """Update auto-execute flag on all pending proposals.

        Args:
            auto_execute: New auto-execute setting
        """
        for p in self._proposals:
            if p.status == "pending":
                p.auto_execute = auto_execute
