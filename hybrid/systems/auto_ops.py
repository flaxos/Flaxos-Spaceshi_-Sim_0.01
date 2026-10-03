# hybrid/systems/auto_ops.py
"""Auto-ops system: CPU-ASSIST tier automated operations management.

When enabled, monitors subsystem health and proposes:
  - Repair dispatch to the most damaged critical subsystem

In auto mode, proposals auto-execute after 10s. In manual mode,
they wait for player approval.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Dict, Optional

from hybrid.core.base_system import BaseSystem
from hybrid.systems.crew_binding_system import CrewBindingSystem
from hybrid.systems.proposals import ProposalManager, Proposal
from server.stations.crew_system import StationSkill

logger = logging.getLogger(__name__)

PROPOSAL_TIMEOUT = 10.0
REPAIR_THRESHOLD = 0.6
CRITICAL_THRESHOLD = 0.35
PROPOSAL_COOLDOWN = 15.0

REPAIR_PRIORITIES: Dict[str, int] = {
    "reactor": 10, "life_support": 9, "sensors": 8,
    "propulsion": 7, "rcs": 6, "weapons": 5,
    "targeting": 5, "radiators": 4,
}


class OpsMode(Enum):
    """Auto-ops operating mode."""
    AUTO = "auto"
    MANUAL = "manual"


class AutoOpsSystem(BaseSystem):
    """CPU-ASSIST automated ops management.

    Monitors subsystem health and proposes repair dispatch.
    Player approves or denies.
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        super().__init__(config)
        self.enabled = False
        self.ops_mode = OpsMode.AUTO
        self._proposals = ProposalManager(max_proposals=3, cooldown=PROPOSAL_COOLDOWN)
        self._last_scan_time = 0.0

    def tick(self, dt: float, ship=None, event_bus=None):
        """Evaluate ops situation and manage proposals."""
        if not self.enabled or ship is None:
            return
        now = time.time()
        self._proposals.expire_old(now, "ops_proposal_expired", event_bus, ship)
        if now - self._last_scan_time >= 3.0:
            self._last_scan_time = now
            self._scan_repair_needs(ship, event_bus, now)
        self._auto_execute(ship, event_bus, now)

    def _get_crew_efficiency(self, ship) -> float:
        """Look up best crew sensor efficiency for this ship.

        Returns 0.5 default if no crew data is available, so proposals
        still work without the crew system -- just at reduced confidence.
        """
        crew_eff = 0.5
        crew_mgr = CrewBindingSystem._shared_crew_manager
        if crew_mgr and hasattr(crew_mgr, 'get_ship_crew'):
            crew_list = crew_mgr.get_ship_crew(ship.id)
            if crew_list:
                crew_eff = max(
                    c.get_current_efficiency(StationSkill.SENSORS)
                    for c in crew_list
                )
        return crew_eff

    def _scan_repair_needs(self, ship, event_bus, now: float):
        """Check subsystem health and propose repairs."""
        if not hasattr(ship, "damage_model"):
            return
        ops = ship.systems.get("ops")
        if not ops or not hasattr(ops, "repair_teams"):
            return

        # Find damaged subsystems sorted by priority
        needs_repair = []
        for name, sub in ship.damage_model.subsystems.items():
            health_pct = sub.health / sub.max_health if sub.max_health > 0 else 1.0
            if health_pct < REPAIR_THRESHOLD:
                priority = REPAIR_PRIORITIES.get(name, 1)
                if health_pct < CRITICAL_THRESHOLD:
                    priority += 5
                needs_repair.append((name, health_pct, priority))

        if not needs_repair:
            return
        needs_repair.sort(key=lambda x: x[2], reverse=True)

        # Check for idle repair teams
        has_idle = any(t.status.value == "idle" for t in ops.repair_teams)
        if not has_idle:
            return

        target_name, health_pct, _ = needs_repair[0]
        key = f"repair_{target_name}"
        if not self._proposals.can_propose(key, now):
            return

        auto_exec = self.ops_mode == OpsMode.AUTO
        crew_eff = self._get_crew_efficiency(ship)
        base_confidence = 1.0 - health_pct
        adjusted_confidence = base_confidence * (0.5 + 0.5 * crew_eff)
        proposal = self._proposals.create(
            prefix="OP", action="dispatch_repair", target=target_name,
            confidence=adjusted_confidence,
            reason=f"{target_name} at {health_pct:.0%}",
            timeout=PROPOSAL_TIMEOUT, auto_execute=auto_exec, now=now,
            params={"subsystem": target_name},
            crew_efficiency=crew_eff,
        )

        if event_bus and ship:
            event_bus.publish("ops_proposal", {
                "ship_id": ship.id, **proposal.to_dict(),
            })

    def _auto_execute(self, ship, event_bus, now: float):
        """Execute proposals that have timed out in auto mode."""
        for p in self._proposals.get_auto_execute_ready(now):
            self._execute_proposal(p, ship, event_bus)

    def _execute_proposal(self, proposal: Proposal, ship, event_bus):
        """Execute an ops proposal through the ops system."""
        ops = ship.systems.get("ops") if ship else None
        if not ops:
            proposal.status = "expired"
            return
        try:
            params = {"_ship": ship, "ship": ship, "event_bus": event_bus,
                      **proposal.params}
            if proposal.action == "dispatch_repair":
                ops.command("dispatch_repair", params)
            else:
                proposal.status = "expired"
                return
            proposal.status = "executed"
            if event_bus and ship:
                event_bus.publish("ops_proposal_executed", {
                    "ship_id": ship.id, "proposal_id": proposal.proposal_id,
                    "action": proposal.action, "target": proposal.target,
                })
        except Exception as e:
            logger.error(f"Auto-ops execute failed: {e}")
            proposal.status = "expired"

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def command(self, action: str, params: dict = None) -> dict:
        """Handle auto-ops commands."""
        params = params or {}
        handlers = {
            "enable": self._cmd_enable,
            "disable": self._cmd_disable,
            "set_mode": self._cmd_set_mode,
            "approve": self._cmd_approve,
            "deny": self._cmd_deny,
            "status": self._cmd_status,
        }
        handler = handlers.get(action)
        if handler:
            return handler(params)
        return {"error": f"Unknown auto_ops command: {action}"}

    def _cmd_enable(self, params: dict) -> dict:
        """Enable auto-ops system."""
        self.enabled = True
        return {"ok": True, "status": "Auto-ops ENABLED",
                "mode": self.ops_mode.value}

    def _cmd_disable(self, params: dict) -> dict:
        """Disable auto-ops system."""
        self.enabled = False
        self._proposals.clear()
        return {"ok": True, "status": "Auto-ops DISABLED"}

    def _cmd_set_mode(self, params: dict) -> dict:
        """Set operating mode (auto or manual)."""
        mode_str = params.get("mode", "")
        try:
            mode = OpsMode(mode_str)
        except ValueError:
            return {"ok": False, "error": f"Invalid mode '{mode_str}'. "
                    f"Valid: {[m.value for m in OpsMode]}"}
        self.ops_mode = mode
        self._proposals.set_auto_execute(mode == OpsMode.AUTO)
        return {"ok": True, "status": f"Auto-ops mode: {mode.value}",
                "mode": mode.value}

    def _cmd_approve(self, params: dict) -> dict:
        """Approve a pending ops proposal."""
        p = self._proposals.find_pending(params.get("proposal_id"))
        if not p:
            return {"ok": False, "error": "No pending proposals to approve"}
        ship = params.get("_ship") or params.get("ship")
        self._execute_proposal(p, ship, params.get("event_bus"))
        return {"ok": True, "status": f"Approved {p.action} on {p.target}",
                "proposal_id": p.proposal_id}

    def _cmd_deny(self, params: dict) -> dict:
        """Deny a pending ops proposal."""
        p = self._proposals.find_pending(params.get("proposal_id"))
        if not p:
            return {"ok": False, "error": "No pending proposals to deny"}
        p.status = "denied"
        return {"ok": True, "status": f"Denied {p.action} on {p.target}",
                "proposal_id": p.proposal_id}

    def _cmd_status(self, params: dict) -> dict:
        """Get auto-ops status."""
        return {"ok": True, **self.get_state()}

    def get_state(self) -> dict:
        """Return system state for telemetry."""
        return {
            "enabled": self.enabled,
            "status": "active" if self.enabled else "standby",
            "mode": self.ops_mode.value,
            "proposals": [p.to_dict() for p in self._proposals.pending],
            "proposal_count": self._proposals.pending_count,
        }
