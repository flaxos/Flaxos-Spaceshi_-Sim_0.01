# hybrid/systems/auto_engineering.py
"""Auto-engineering system: CPU-ASSIST tier automated engineering management.

When enabled, monitors thermal state, reactor output, radiator deployment,
and crew fatigue to propose engineering actions. Player approves or denies.

Modes:
  - auto: proposals auto-execute after 8s timeout
  - manual: wait for player approval indefinitely
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

from hybrid.core.base_system import BaseSystem
from hybrid.systems.proposals import ProposalManager, Proposal

logger = logging.getLogger(__name__)

PROPOSAL_TIMEOUT = 8.0
PROPOSAL_COOLDOWN = 12.0

# Thresholds
HIGH_TEMP_PCT = 0.60
RETRACT_UNDER_FIRE_COOLDOWN = 10.0
FATIGUE_THRESHOLD = 0.70
COMFORTABLE_G = 1.5


class EngineeringMode(Enum):
    """Auto-engineering operating mode."""
    AUTO = "auto"
    MANUAL = "manual"


class AutoEngineeringSystem(BaseSystem):
    """CPU-ASSIST automated engineering management.

    Monitors thermal state, reactor output, radiator deployment, and crew
    fatigue. Proposes corrective actions and executes approved proposals
    through the engineering system.
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        super().__init__(config)
        self.enabled = False
        self.eng_mode = EngineeringMode.AUTO
        self._proposals = ProposalManager(max_proposals=3, cooldown=PROPOSAL_COOLDOWN)
        self._last_scan_time = 0.0
        self._last_under_fire_time = 0.0

    def tick(self, dt: float, ship=None, event_bus=None):
        """Evaluate engineering situation and manage proposals."""
        if not self.enabled or ship is None:
            return
        now = time.time()
        self._proposals.expire_old(now, "engineering_proposal_expired", event_bus, ship)
        if now - self._last_scan_time >= 3.0:
            self._last_scan_time = now
            self._check_thermal(ship, event_bus, now)
            self._check_radiators(ship, event_bus, now)
            self._check_fatigue(ship, event_bus, now)
        self._auto_execute(ship, event_bus, now)

    # ------------------------------------------------------------------
    # Proposal generators
    # ------------------------------------------------------------------

    def _check_thermal(self, ship, event_bus, now: float):
        """Propose reactor output changes based on thermal state."""
        thermal = ship.systems.get("thermal")
        engineering = ship.systems.get("engineering")
        if not thermal or not engineering:
            return

        thermal_state = thermal.get_state() if hasattr(thermal, "get_state") else {}
        hull_temp_pct = thermal_state.get("hull_temp_pct", 0.0)

        if hull_temp_pct > HIGH_TEMP_PCT:
            key = "reduce_reactor"
            if not self._proposals.can_propose(key, now):
                return
            auto_exec = self.eng_mode == EngineeringMode.AUTO
            proposal = self._proposals.create(
                prefix="ENG", action="reduce_reactor",
                target="reactor",
                confidence=min(hull_temp_pct, 1.0),
                reason=f"Hull temp at {hull_temp_pct:.0%}",
                timeout=PROPOSAL_TIMEOUT, auto_execute=auto_exec, now=now,
                params={"output": 50},
            )
            if event_bus and ship:
                event_bus.publish("engineering_proposal", {
                    "ship_id": ship.id, **proposal.to_dict(),
                })

    def _check_radiators(self, ship, event_bus, now: float):
        """Propose radiator deploy/retract based on situation."""
        thermal = ship.systems.get("thermal")
        engineering = ship.systems.get("engineering")
        if not thermal or not engineering:
            return

        thermal_state = thermal.get_state() if hasattr(thermal, "get_state") else {}
        hull_temp_pct = thermal_state.get("hull_temp_pct", 0.0)

        eng_state = engineering.get_state() if hasattr(engineering, "get_state") else {}
        rads_deployed = eng_state.get("radiators_deployed", True)

        # Check if under fire (recent damage events)
        under_fire = self._is_under_fire(ship, now)

        if under_fire and rads_deployed:
            key = "retract_radiators"
            if not self._proposals.can_propose(key, now):
                return
            auto_exec = self.eng_mode == EngineeringMode.AUTO
            proposal = self._proposals.create(
                prefix="ENG", action="retract_radiators",
                target="radiators",
                confidence=0.9,
                reason="Under fire -- radiators vulnerable",
                timeout=PROPOSAL_TIMEOUT, auto_execute=auto_exec, now=now,
                params={"deployed": False},
            )
            if event_bus and ship:
                event_bus.publish("engineering_proposal", {
                    "ship_id": ship.id, **proposal.to_dict(),
                })

        elif hull_temp_pct > HIGH_TEMP_PCT and not rads_deployed and not under_fire:
            key = "deploy_radiators"
            if not self._proposals.can_propose(key, now):
                return
            auto_exec = self.eng_mode == EngineeringMode.AUTO
            proposal = self._proposals.create(
                prefix="ENG", action="deploy_radiators",
                target="radiators",
                confidence=hull_temp_pct,
                reason=f"Hull temp at {hull_temp_pct:.0%}",
                timeout=PROPOSAL_TIMEOUT, auto_execute=auto_exec, now=now,
                params={"deployed": True},
            )
            if event_bus and ship:
                event_bus.publish("engineering_proposal", {
                    "ship_id": ship.id, **proposal.to_dict(),
                })

    def _check_fatigue(self, ship, event_bus, now: float):
        """Propose reducing max G when crew fatigue performance is low."""
        crew_fatigue = ship.systems.get("crew_fatigue")
        if not crew_fatigue:
            return

        fatigue_state = (crew_fatigue.get_state()
                         if hasattr(crew_fatigue, "get_state") else {})
        performance = fatigue_state.get("performance_multiplier", 1.0)

        if performance >= FATIGUE_THRESHOLD:
            return

        key = "throttle_governor"
        if not self._proposals.can_propose(key, now):
            return

        auto_exec = self.eng_mode == EngineeringMode.AUTO
        proposal = self._proposals.create(
            prefix="ENG", action="throttle_governor",
            target="drive",
            confidence=1.0 - performance,
            reason=f"Crew performance at {performance:.0%}",
            timeout=PROPOSAL_TIMEOUT, auto_execute=auto_exec, now=now,
            params={"limit": int(COMFORTABLE_G / 3.0 * 100)},
        )
        if event_bus and ship:
            event_bus.publish("engineering_proposal", {
                "ship_id": ship.id, **proposal.to_dict(),
            })

    def _is_under_fire(self, ship, now: float) -> bool:
        """Check if the ship has taken recent damage."""
        if hasattr(ship, "damage_model"):
            last_hit = getattr(ship.damage_model, "last_hit_time", 0.0)
            if now - last_hit < RETRACT_UNDER_FIRE_COOLDOWN:
                self._last_under_fire_time = now
                return True
        return now - self._last_under_fire_time < RETRACT_UNDER_FIRE_COOLDOWN

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _auto_execute(self, ship, event_bus, now: float):
        """Execute proposals that have timed out in auto mode."""
        for p in self._proposals.get_auto_execute_ready(now):
            self._execute_proposal(p, ship, event_bus)

    def _execute_proposal(self, proposal: Proposal, ship, event_bus):
        """Execute an engineering proposal through the engineering system."""
        engineering = ship.systems.get("engineering") if ship else None
        if not engineering:
            proposal.status = "expired"
            return
        try:
            params = {"_ship": ship, "ship": ship, "event_bus": event_bus,
                      **proposal.params}
            if proposal.action == "reduce_reactor":
                engineering.command("set_reactor_output", params)
            elif proposal.action in ("deploy_radiators", "retract_radiators"):
                engineering.command("manage_radiators", params)
            elif proposal.action == "throttle_governor":
                engineering.command("throttle_drive", params)
            else:
                proposal.status = "expired"
                return
            proposal.status = "executed"
            if event_bus and ship:
                event_bus.publish("engineering_proposal_executed", {
                    "ship_id": ship.id, "proposal_id": proposal.proposal_id,
                    "action": proposal.action, "target": proposal.target,
                })
        except Exception as e:
            logger.error(f"Auto-engineering execute failed: {e}")
            proposal.status = "expired"

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def command(self, action: str, params: dict = None) -> dict:
        """Handle auto-engineering commands."""
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
        return {"error": f"Unknown auto_engineering command: {action}"}

    def _cmd_enable(self, params: dict) -> dict:
        """Enable auto-engineering system."""
        self.enabled = True
        return {"ok": True, "status": "Auto-engineering ENABLED",
                "mode": self.eng_mode.value}

    def _cmd_disable(self, params: dict) -> dict:
        """Disable auto-engineering system."""
        self.enabled = False
        self._proposals.clear()
        return {"ok": True, "status": "Auto-engineering DISABLED"}

    def _cmd_set_mode(self, params: dict) -> dict:
        """Set operating mode (auto or manual)."""
        mode_str = params.get("mode", "")
        try:
            mode = EngineeringMode(mode_str)
        except ValueError:
            return {"ok": False, "error": f"Invalid mode '{mode_str}'. "
                    f"Valid: {[m.value for m in EngineeringMode]}"}
        self.eng_mode = mode
        self._proposals.set_auto_execute(mode == EngineeringMode.AUTO)
        return {"ok": True, "status": f"Auto-engineering mode: {mode.value}",
                "mode": mode.value}

    def _cmd_approve(self, params: dict) -> dict:
        """Approve a pending engineering proposal."""
        p = self._proposals.find_pending(params.get("proposal_id"))
        if not p:
            return {"ok": False, "error": "No pending proposals to approve"}
        ship = params.get("_ship") or params.get("ship")
        self._execute_proposal(p, ship, params.get("event_bus"))
        return {"ok": True, "status": f"Approved {p.action} on {p.target}",
                "proposal_id": p.proposal_id}

    def _cmd_deny(self, params: dict) -> dict:
        """Deny a pending engineering proposal."""
        p = self._proposals.find_pending(params.get("proposal_id"))
        if not p:
            return {"ok": False, "error": "No pending proposals to deny"}
        p.status = "denied"
        return {"ok": True, "status": f"Denied {p.action} on {p.target}",
                "proposal_id": p.proposal_id}

    def _cmd_status(self, params: dict) -> dict:
        """Get auto-engineering status."""
        return {"ok": True, **self.get_state()}

    def get_state(self) -> dict:
        """Return system state for telemetry."""
        return {
            "enabled": self.enabled,
            "status": "active" if self.enabled else "standby",
            "mode": self.eng_mode.value,
            "proposals": [p.to_dict() for p in self._proposals.pending],
            "proposal_count": self._proposals.pending_count,
        }
