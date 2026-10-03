# hybrid/systems/auto_tactical.py
"""Auto-tactical system: CPU-ASSIST tier automated targeting and fire proposals.

When enabled, evaluates sensor contacts, auto-designates highest-threat
target, and proposes fire actions when firing solution confidence is high.
Player approves or denies proposals.

Engagement rules:
  - weapons_free: auto-execute after 5s timeout
  - weapons_hold: wait for player approval indefinitely
  - defensive_only: auto-fire PDCs only, hold railgun/torpedo
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

from hybrid.core.base_system import BaseSystem
from hybrid.fleet.threat_assessment import AIThreatAssessment
from hybrid.systems.crew_binding_system import CrewBindingSystem
from hybrid.systems.proposals import ProposalManager, Proposal
from server.stations.crew_system import StationSkill

logger = logging.getLogger(__name__)

PROPOSAL_TIMEOUT = 5.0
MIN_FIRE_CONFIDENCE = 0.7


class EngagementMode(Enum):
    """Rules of engagement for auto-tactical."""
    WEAPONS_FREE = "weapons_free"
    WEAPONS_HOLD = "weapons_hold"
    DEFENSIVE_ONLY = "defensive_only"


class AutoTacticalSystem(BaseSystem):
    """CPU-ASSIST automated targeting and fire control.

    Ticks when enabled. Evaluates contacts, proposes fire actions,
    and executes approved proposals through the combat system.
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        super().__init__(config)
        self.enabled = False
        self.engagement_mode = EngagementMode.WEAPONS_FREE
        self._proposals = ProposalManager(max_proposals=3, cooldown=3.0)
        self._last_auto_designate_time = 0.0

    def tick(self, dt: float, ship=None, event_bus=None):
        """Evaluate tactical situation and manage proposals."""
        if not self.enabled or ship is None:
            return
        now = time.time()
        self._proposals.expire_old(now, "tactical_proposal_expired", event_bus, ship)
        self._auto_designate(ship, event_bus, now)
        self._propose_fire(ship, event_bus, now)
        self._auto_execute(ship, event_bus, now)

    def _auto_designate(self, ship, event_bus, now: float):
        """Auto-designate highest-threat contact if no target locked."""
        if now - self._last_auto_designate_time < 2.0:
            return
        self._last_auto_designate_time = now

        targeting = ship.systems.get("targeting")
        if not targeting or getattr(targeting, "locked_target", None):
            return

        sensors = ship.systems.get("sensors")
        if not sensors or not hasattr(sensors, "contact_tracker"):
            return

        contacts = [
            (cid, c) for cid, c in sensors.contact_tracker.contacts.items()
            if hasattr(c, "confidence") and c.confidence > 0.3
        ]
        if not contacts:
            return

        prioritized = AIThreatAssessment.prioritize_targets(contacts, ship)
        if not prioritized:
            return

        best_id, best_contact = prioritized[0]
        try:
            targeting.lock_target(contact_id=best_id,
                                  sim_time=getattr(ship, "sim_time", None))
            if event_bus:
                event_bus.publish("auto_tactical_designate", {
                    "ship_id": ship.id, "contact_id": best_id,
                    "classification": getattr(best_contact, "classification", "unknown"),
                })
        except Exception as e:
            logger.debug(f"Auto-designate failed: {e}")

    def _get_crew_efficiency(self, ship) -> float:
        """Look up best crew gunnery efficiency for this ship.

        Returns 0.5 default if no crew data is available, so proposals
        still work without the crew system -- just at reduced confidence.
        """
        crew_eff = 0.5
        crew_mgr = CrewBindingSystem._shared_crew_manager
        if crew_mgr and hasattr(crew_mgr, 'get_ship_crew'):
            crew_list = crew_mgr.get_ship_crew(ship.id)
            if crew_list:
                crew_eff = max(
                    c.get_current_efficiency(StationSkill.GUNNERY)
                    for c in crew_list
                )
        return crew_eff

    def _propose_fire(self, ship, event_bus, now: float):
        """Propose fire action if firing solution confidence is sufficient."""
        targeting = ship.systems.get("targeting")
        combat = ship.systems.get("combat")
        if not targeting or not combat:
            return

        locked = getattr(targeting, "locked_target", None)
        if not locked:
            return

        solution = None
        if hasattr(targeting, "get_state"):
            solution = targeting.get_state().get("firing_solution")
        if not solution or solution.get("confidence", 0.0) < MIN_FIRE_CONFIDENCE:
            return

        base_confidence = solution["confidence"]
        weapon_action = self._select_weapon(ship)
        if not weapon_action or not self._proposals.can_propose(weapon_action, now):
            return

        if (self.engagement_mode == EngagementMode.DEFENSIVE_ONLY
                and weapon_action != "fire_pdc"):
            return

        # Crew skill scales confidence: 50% baseline + 50% from crew efficiency
        crew_eff = self._get_crew_efficiency(ship)
        adjusted_confidence = base_confidence * (0.5 + 0.5 * crew_eff)

        auto_exec = self.engagement_mode == EngagementMode.WEAPONS_FREE
        proposal = self._proposals.create(
            prefix="TP", action=weapon_action, target=locked,
            confidence=adjusted_confidence,
            reason=f"Solution confidence {adjusted_confidence:.0%} on {locked}",
            timeout=PROPOSAL_TIMEOUT, auto_execute=auto_exec, now=now,
            crew_efficiency=crew_eff,
        )

        if event_bus and ship:
            event_bus.publish("tactical_proposal", {
                "ship_id": ship.id, **proposal.to_dict(),
            })

    def _select_weapon(self, ship) -> Optional[str]:
        """Select best available weapon to fire."""
        combat = ship.systems.get("combat")
        if not combat or not hasattr(combat, "get_state"):
            return None

        weapons = combat.get_state().get("truth_weapons", {})
        for wstate in weapons.values():
            if not isinstance(wstate, dict):
                continue
            wtype = wstate.get("type", "").lower()
            if "railgun" in wtype and wstate.get("ammo", 0) > 0 and wstate.get("ready"):
                return "fire_railgun"

        for wstate in weapons.values():
            if not isinstance(wstate, dict):
                continue
            wtype = wstate.get("type", "").lower()
            if "torpedo" in wtype and wstate.get("ammo", 0) > 0 and wstate.get("ready"):
                return "launch_torpedo"

        return None

    def _auto_execute(self, ship, event_bus, now: float):
        """Execute proposals that have timed out in weapons_free mode."""
        for p in self._proposals.get_auto_execute_ready(now):
            self._execute_proposal(p, ship, event_bus)

    def _execute_proposal(self, proposal: Proposal, ship, event_bus):
        """Execute a tactical proposal through the combat system."""
        combat = ship.systems.get("combat")
        if not combat:
            proposal.status = "expired"
            return
        try:
            params = {"_ship": ship, "ship": ship, "event_bus": event_bus,
                      "_from_auto_tactical": True}
            if hasattr(ship, "_all_ships_ref"):
                params["all_ships"] = {s.id: s for s in ship._all_ships_ref}

            if proposal.action == "fire_railgun":
                combat.command("fire", params)
            elif proposal.action == "launch_torpedo":
                params["profile"] = "direct"
                combat.command("launch_torpedo", params)
            else:
                proposal.status = "expired"
                return
            proposal.status = "executed"
            if event_bus and ship:
                event_bus.publish("tactical_proposal_executed", {
                    "ship_id": ship.id, "proposal_id": proposal.proposal_id,
                    "action": proposal.action,
                })
        except Exception as e:
            logger.error(f"Auto-tactical execute failed: {e}")
            proposal.status = "expired"

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def command(self, action: str, params: dict = None) -> dict:
        """Handle auto-tactical commands."""
        params = params or {}
        handlers = {
            "enable": self._cmd_enable,
            "disable": self._cmd_disable,
            "set_engagement_rules": self._cmd_set_engagement_rules,
            "approve": self._cmd_approve,
            "deny": self._cmd_deny,
            "status": self._cmd_status,
        }
        handler = handlers.get(action)
        if handler:
            return handler(params)
        return {"error": f"Unknown auto_tactical command: {action}"}

    def _cmd_enable(self, params: dict) -> dict:
        """Enable auto-tactical system."""
        self.enabled = True
        return {"ok": True, "status": "Auto-tactical ENABLED",
                "engagement_mode": self.engagement_mode.value}

    def _cmd_disable(self, params: dict) -> dict:
        """Disable auto-tactical system."""
        self.enabled = False
        self._proposals.clear()
        return {"ok": True, "status": "Auto-tactical DISABLED"}

    def _cmd_set_engagement_rules(self, params: dict) -> dict:
        """Set engagement rules mode."""
        mode_str = params.get("mode", "")
        try:
            mode = EngagementMode(mode_str)
        except ValueError:
            return {"ok": False, "error": f"Invalid mode '{mode_str}'. "
                    f"Valid: {[m.value for m in EngagementMode]}"}

        self.engagement_mode = mode
        auto_exec = mode == EngagementMode.WEAPONS_FREE
        self._proposals.set_auto_execute(auto_exec)
        if mode == EngagementMode.DEFENSIVE_ONLY:
            for p in self._proposals.pending:
                if p.action != "fire_pdc":
                    p.status = "expired"

        return {"ok": True, "status": f"Engagement rules: {mode.value}",
                "mode": mode.value}

    def _cmd_approve(self, params: dict) -> dict:
        """Approve a pending tactical proposal."""
        p = self._proposals.find_pending(params.get("proposal_id"))
        if not p:
            return {"ok": False, "error": "No pending proposals to approve"}
        ship = params.get("_ship") or params.get("ship")
        self._execute_proposal(p, ship, params.get("event_bus"))
        return {"ok": True, "status": f"Approved {p.action}",
                "proposal_id": p.proposal_id}

    def _cmd_deny(self, params: dict) -> dict:
        """Deny a pending tactical proposal."""
        p = self._proposals.find_pending(params.get("proposal_id"))
        if not p:
            return {"ok": False, "error": "No pending proposals to deny"}
        p.status = "denied"
        return {"ok": True, "status": f"Denied {p.action} on {p.target}",
                "proposal_id": p.proposal_id}

    def _cmd_status(self, params: dict) -> dict:
        """Get auto-tactical status."""
        return {"ok": True, **self.get_state()}

    def get_state(self) -> dict:
        """Return system state for telemetry."""
        return {
            "enabled": self.enabled,
            "status": "active" if self.enabled else "standby",
            "engagement_mode": self.engagement_mode.value,
            "proposals": [p.to_dict() for p in self._proposals.pending],
            "proposal_count": self._proposals.pending_count,
        }
