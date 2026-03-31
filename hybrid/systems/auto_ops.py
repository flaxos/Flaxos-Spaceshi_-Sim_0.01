# hybrid/systems/auto_ops.py
"""Auto-ops system: CPU-ASSIST tier automated operations management.

When enabled, monitors subsystem health and combat state, then proposes:
  - Repair dispatch to the most damaged critical subsystem
  - Power profile changes based on tactical situation

The player approves or denies proposals. In auto mode, proposals
auto-execute after a 10-second timeout. In manual mode, they wait
for explicit approval.

Proposals are published to telemetry so the GUI can render approval UI.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any

from hybrid.core.base_system import BaseSystem

logger = logging.getLogger(__name__)

# Proposal timeout in seconds
PROPOSAL_TIMEOUT = 10.0
# Minimum health threshold to trigger repair proposal (percentage)
REPAIR_THRESHOLD = 0.6
# Critical health threshold (percentage)
CRITICAL_THRESHOLD = 0.35
# Cooldown between proposals for same subsystem (seconds)
PROPOSAL_COOLDOWN = 15.0
# Maximum number of active proposals
MAX_PROPOSALS = 3

# Subsystem priority for auto-repair (higher = repaired first)
REPAIR_PRIORITIES: Dict[str, int] = {
    "reactor": 10,
    "sensors": 8,
    "propulsion": 7,
    "rcs": 6,
    "weapons": 5,
    "targeting": 5,
    "radiators": 4,
    "life_support": 9,
}


class OpsMode(Enum):
    """Auto-ops operating mode."""
    AUTO = "auto"      # Auto-execute after timeout
    MANUAL = "manual"  # Wait for player approval


@dataclass
class OpsProposal:
    """A proposed ops action awaiting player approval."""
    proposal_id: str
    action: str             # "dispatch_repair" or "set_power_profile"
    target: str             # Subsystem name or power profile name
    reason: str             # Human-readable explanation
    params: Dict[str, Any]  # Parameters for the command
    created_at: float       # Time when created
    timeout: float          # Seconds until auto-execute or expiry
    auto_execute: bool      # Whether to auto-execute on timeout
    status: str = "pending"

    def to_dict(self) -> dict:
        """Serialize for telemetry."""
        return {
            "proposal_id": self.proposal_id,
            "action": self.action,
            "target": self.target,
            "reason": self.reason,
            "created_at": self.created_at,
            "timeout": self.timeout,
            "auto_execute": self.auto_execute,
            "status": self.status,
            "time_remaining": max(0.0, self.timeout - (time.time() - self.created_at)),
        }


class AutoOpsSystem(BaseSystem):
    """CPU-ASSIST tier automated operations management.

    Monitors subsystem health and proposes repair dispatch and
    power profile changes. Player approves or denies.
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        super().__init__(config)

        # Disabled by default -- player enables via command
        self.enabled = False

        self.ops_mode = OpsMode.AUTO
        self._proposals: List[OpsProposal] = []
        self._proposal_counter = 0
        self._last_proposal_time: Dict[str, float] = {}
        self._last_scan_time = 0.0

    def tick(self, dt: float, ship=None, event_bus=None):
        """Evaluate ops situation and manage proposals.

        Args:
            dt: Time step in seconds
            ship: Ship object
            event_bus: Event bus for publishing events
        """
        if not self.enabled or ship is None:
            return

        now = time.time()

        # 1. Expire old proposals
        self._expire_proposals(now, event_bus, ship)

        # 2. Scan for repair needs (every 3 seconds)
        if now - self._last_scan_time >= 3.0:
            self._last_scan_time = now
            self._scan_repair_needs(ship, event_bus, now)

        # 3. Auto-execute timed-out proposals in auto mode
        self._auto_execute_proposals(ship, event_bus, now)

    def _expire_proposals(self, now: float, event_bus, ship):
        """Remove expired proposals."""
        still_active = []
        for p in self._proposals:
            if p.status != "pending":
                continue
            elapsed = now - p.created_at
            if elapsed > p.timeout and not p.auto_execute:
                p.status = "expired"
                if event_bus and ship:
                    event_bus.publish("ops_proposal_expired", {
                        "ship_id": ship.id,
                        "proposal_id": p.proposal_id,
                    })
            else:
                still_active.append(p)
        self._proposals = still_active

    def _scan_repair_needs(self, ship, event_bus, now: float):
        """Check subsystem health and propose repairs."""
        if len(self._proposals) >= MAX_PROPOSALS:
            return

        if not hasattr(ship, "damage_model"):
            return

        ops = ship.systems.get("ops")
        if not ops:
            return

        # Find subsystems that need repair, sorted by priority
        needs_repair = []
        for name, sub in ship.damage_model.subsystems.items():
            health_pct = sub.health / sub.max_health if sub.max_health > 0 else 1.0
            if health_pct < REPAIR_THRESHOLD:
                priority = REPAIR_PRIORITIES.get(name, 1)
                # Boost priority for critical systems
                if health_pct < CRITICAL_THRESHOLD:
                    priority += 5
                needs_repair.append((name, health_pct, priority))

        if not needs_repair:
            return

        # Sort by priority (highest first)
        needs_repair.sort(key=lambda x: x[2], reverse=True)

        # Check if any idle repair teams exist
        has_idle_team = False
        if hasattr(ops, "repair_teams"):
            for team in ops.repair_teams:
                if team.status.value == "idle":
                    has_idle_team = True
                    break

        if not has_idle_team:
            return

        # Propose repair for the highest priority damaged subsystem
        target_name, health_pct, _ = needs_repair[0]

        # Check cooldown
        last_time = self._last_proposal_time.get(f"repair_{target_name}", 0.0)
        if now - last_time < PROPOSAL_COOLDOWN:
            return

        # Check if already have a pending proposal for this subsystem
        for p in self._proposals:
            if p.target == target_name and p.status == "pending":
                return

        self._proposal_counter += 1
        auto_exec = self.ops_mode == OpsMode.AUTO
        proposal = OpsProposal(
            proposal_id=f"OP-{self._proposal_counter:04d}",
            action="dispatch_repair",
            target=target_name,
            reason=f"{target_name} at {health_pct:.0%}",
            params={"subsystem": target_name},
            created_at=now,
            timeout=PROPOSAL_TIMEOUT,
            auto_execute=auto_exec,
            status="pending",
        )
        self._proposals.append(proposal)
        self._last_proposal_time[f"repair_{target_name}"] = now

        if event_bus and ship:
            event_bus.publish("ops_proposal", {
                "ship_id": ship.id,
                **proposal.to_dict(),
            })

        logger.info(
            f"Auto-ops proposes repair {target_name} "
            f"(health={health_pct:.0%}, auto_execute={auto_exec})"
        )

    def _auto_execute_proposals(self, ship, event_bus, now: float):
        """Execute proposals that have timed out in auto mode."""
        for p in self._proposals:
            if p.status != "pending" or not p.auto_execute:
                continue
            elapsed = now - p.created_at
            if elapsed < p.timeout:
                continue
            self._execute_proposal(p, ship, event_bus)

    def _execute_proposal(self, proposal: OpsProposal, ship, event_bus):
        """Execute an ops proposal through the ops system.

        Args:
            proposal: The proposal to execute
            ship: Ship object
            event_bus: Event bus for events
        """
        ops = ship.systems.get("ops") if ship else None
        if not ops:
            proposal.status = "expired"
            return

        try:
            params = {
                "_ship": ship,
                "ship": ship,
                "event_bus": event_bus,
                **proposal.params,
            }

            if proposal.action == "dispatch_repair":
                result = ops.command("dispatch_repair", params)
            else:
                proposal.status = "expired"
                return

            proposal.status = "executed"
            if event_bus and ship:
                event_bus.publish("ops_proposal_executed", {
                    "ship_id": ship.id,
                    "proposal_id": proposal.proposal_id,
                    "action": proposal.action,
                    "target": proposal.target,
                    "result": result if isinstance(result, dict) else str(result),
                })

            logger.info(f"Auto-ops executed {proposal.action} on {proposal.target}")

        except Exception as e:
            logger.error(f"Auto-ops execute failed: {e}")
            proposal.status = "expired"

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def command(self, action: str, params: dict = None) -> dict:
        """Handle auto-ops commands."""
        params = params or {}

        if action == "enable":
            return self._cmd_enable(params)
        elif action == "disable":
            return self._cmd_disable(params)
        elif action == "set_mode":
            return self._cmd_set_mode(params)
        elif action == "approve":
            return self._cmd_approve(params)
        elif action == "deny":
            return self._cmd_deny(params)
        elif action == "status":
            return self._cmd_status(params)

        return {"error": f"Unknown auto_ops command: {action}"}

    def _cmd_enable(self, params: dict) -> dict:
        """Enable auto-ops system."""
        self.enabled = True
        return {
            "ok": True,
            "status": "Auto-ops ENABLED",
            "mode": self.ops_mode.value,
        }

    def _cmd_disable(self, params: dict) -> dict:
        """Disable auto-ops system."""
        self.enabled = False
        for p in self._proposals:
            if p.status == "pending":
                p.status = "expired"
        self._proposals = []
        return {"ok": True, "status": "Auto-ops DISABLED"}

    def _cmd_set_mode(self, params: dict) -> dict:
        """Set operating mode (auto or manual).

        Args:
            params: Must include 'mode' key
        """
        mode_str = params.get("mode", "")
        try:
            mode = OpsMode(mode_str)
        except ValueError:
            valid = [m.value for m in OpsMode]
            return {
                "ok": False,
                "error": f"Invalid mode '{mode_str}'. Valid: {valid}",
            }

        self.ops_mode = mode

        # Update auto-execute flag on pending proposals
        auto_exec = mode == OpsMode.AUTO
        for p in self._proposals:
            if p.status == "pending":
                p.auto_execute = auto_exec

        return {
            "ok": True,
            "status": f"Auto-ops mode set to {mode.value}",
            "mode": mode.value,
        }

    def _cmd_approve(self, params: dict) -> dict:
        """Approve a pending ops proposal."""
        pid = params.get("proposal_id")
        if not pid:
            for p in self._proposals:
                if p.status == "pending":
                    pid = p.proposal_id
                    break

        if not pid:
            return {"ok": False, "error": "No pending proposals to approve"}

        for p in self._proposals:
            if p.proposal_id == pid and p.status == "pending":
                ship = params.get("_ship") or params.get("ship")
                event_bus = params.get("event_bus")
                self._execute_proposal(p, ship, event_bus)
                return {
                    "ok": True,
                    "status": f"Approved and executed {p.action} on {p.target}",
                    "proposal_id": pid,
                }

        return {"ok": False, "error": f"Proposal '{pid}' not found or not pending"}

    def _cmd_deny(self, params: dict) -> dict:
        """Deny a pending ops proposal."""
        pid = params.get("proposal_id")
        if not pid:
            for p in self._proposals:
                if p.status == "pending":
                    pid = p.proposal_id
                    break

        if not pid:
            return {"ok": False, "error": "No pending proposals to deny"}

        for p in self._proposals:
            if p.proposal_id == pid and p.status == "pending":
                p.status = "denied"
                return {
                    "ok": True,
                    "status": f"Denied {p.action} on {p.target}",
                    "proposal_id": pid,
                }

        return {"ok": False, "error": f"Proposal '{pid}' not found or not pending"}

    def _cmd_status(self, params: dict) -> dict:
        """Get auto-ops status."""
        return {"ok": True, **self.get_state()}

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Return system state for telemetry."""
        return {
            "enabled": self.enabled,
            "status": "active" if self.enabled else "standby",
            "mode": self.ops_mode.value,
            "proposals": [p.to_dict() for p in self._proposals if p.status == "pending"],
            "proposal_count": len([p for p in self._proposals if p.status == "pending"]),
        }
