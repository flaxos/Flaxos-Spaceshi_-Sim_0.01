# hybrid/systems/auto_comms.py
"""Auto-comms system: CPU-ASSIST tier automated communications management.

When enabled, manages:
  - Auto-respond to hails based on diplomatic state
  - Communication policy enforcement (open, radio_silence, diplomatic)
  - Periodic fleet status broadcast to allied ships

Policies:
  - open_comms: auto-respond to all hails based on diplomatic state
  - radio_silence: auto-deny all incoming hails, no broadcasts
  - diplomatic_mode: propose responses, wait for player approval
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

from hybrid.core.base_system import BaseSystem
from hybrid.systems.crew_binding_system import CrewBindingSystem
from hybrid.systems.proposals import ProposalManager, Proposal
from server.stations.crew_system import StationSkill

logger = logging.getLogger(__name__)

PROPOSAL_TIMEOUT = 10.0
PROPOSAL_COOLDOWN = 15.0
BROADCAST_INTERVAL = 60.0


class CommsPolicy(Enum):
    """Communication policy modes."""
    OPEN_COMMS = "open_comms"
    RADIO_SILENCE = "radio_silence"
    DIPLOMATIC_MODE = "diplomatic_mode"


class AutoCommsSystem(BaseSystem):
    """CPU-ASSIST automated communications management.

    Monitors incoming hails and manages responses based on diplomatic
    state and communication policy. Broadcasts fleet status to allies
    at regular intervals.
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        super().__init__(config)
        self.enabled = False
        self.comms_policy = CommsPolicy.OPEN_COMMS
        self._proposals = ProposalManager(max_proposals=5, cooldown=PROPOSAL_COOLDOWN)
        self._last_broadcast_time = 0.0
        self._last_hail_check_time = 0.0
        self._responded_hails: set = set()

    def tick(self, dt: float, ship=None, event_bus=None):
        """Evaluate comms situation and manage proposals."""
        if not self.enabled or ship is None:
            return
        now = time.time()
        self._proposals.expire_old(now, "comms_proposal_expired", event_bus, ship)
        if now - self._last_hail_check_time >= 2.0:
            self._last_hail_check_time = now
            self._check_pending_hails(ship, event_bus, now)
        if self.comms_policy != CommsPolicy.RADIO_SILENCE:
            self._check_broadcast(ship, event_bus, now)
        self._auto_execute(ship, event_bus, now)

    # ------------------------------------------------------------------
    # Hail response
    # ------------------------------------------------------------------

    def _get_crew_efficiency(self, ship) -> float:
        """Look up best crew communications efficiency for this ship.

        Returns 0.5 default if no crew data is available, so proposals
        still work without the crew system -- just at reduced confidence.
        """
        crew_eff = 0.5
        crew_mgr = CrewBindingSystem._shared_crew_manager
        if crew_mgr and hasattr(crew_mgr, 'get_ship_crew'):
            crew_list = crew_mgr.get_ship_crew(ship.id)
            if crew_list:
                crew_eff = max(
                    c.get_current_efficiency(StationSkill.COMMUNICATIONS)
                    for c in crew_list
                )
        return crew_eff

    def _check_pending_hails(self, ship, event_bus, now: float):
        """Check for pending incoming hails and respond or propose."""
        comms = ship.systems.get("comms")
        if not comms:
            return

        comms_state = comms.get_state() if hasattr(comms, "get_state") else {}
        message_log = comms_state.get("message_log", [])

        for msg in message_log:
            msg_id = msg.get("id", id(msg))
            if msg_id in self._responded_hails:
                continue
            if msg.get("direction") != "incoming" or msg.get("type") != "hail":
                continue

            self._responded_hails.add(msg_id)
            sender_faction = msg.get("faction", "")
            diplo = self._get_diplomatic_state(ship, sender_faction)

            if self.comms_policy == CommsPolicy.RADIO_SILENCE:
                continue

            response = self._generate_response(diplo, ship)
            if response is None:
                continue

            if self.comms_policy == CommsPolicy.OPEN_COMMS:
                # Auto-execute immediately
                self._send_response(ship, msg, response, event_bus)
            else:
                # Diplomatic mode: propose and wait for approval
                key = f"hail_response_{msg_id}"
                if not self._proposals.can_propose(key, now):
                    continue
                crew_eff = self._get_crew_efficiency(ship)
                adjusted_confidence = 0.8 * (0.5 + 0.5 * crew_eff)
                proposal = self._proposals.create(
                    prefix="COM", action="hail_response",
                    target=msg.get("sender", "unknown"),
                    confidence=adjusted_confidence,
                    reason=f"Hail from {msg.get('sender', 'unknown')} ({diplo})",
                    timeout=PROPOSAL_TIMEOUT, auto_execute=False, now=now,
                    params={"msg": msg, "response": response},
                    crew_efficiency=crew_eff,
                )
                if event_bus and ship:
                    event_bus.publish("comms_proposal", {
                        "ship_id": ship.id, **proposal.to_dict(),
                    })

    def _generate_response(self, diplo_state: str, ship) -> Optional[str]:
        """Generate a response based on diplomatic state.

        Args:
            diplo_state: Diplomatic state string (allied/neutral/hostile/unknown)
            ship: Ship object

        Returns:
            Response message string, or None for no response
        """
        ship_name = getattr(ship, "name", "Unknown")
        faction = getattr(ship, "faction", "Unknown")

        if diplo_state == "allied":
            return f"This is {ship_name}, {faction}. Identifying. Status nominal."
        elif diplo_state == "neutral":
            return f"This is {ship_name}, {faction}. Identifying."
        elif diplo_state == "hostile":
            return None
        return f"This is {ship_name}. Identifying."

    def _send_response(self, ship, original_msg: dict, response: str,
                       event_bus):
        """Send a response through the comms system.

        Args:
            ship: Ship object
            original_msg: The original hail message
            response: Response text
            event_bus: Event bus for publishing events
        """
        comms = ship.systems.get("comms")
        if not comms:
            return
        try:
            params = {
                "_ship": ship, "ship": ship, "event_bus": event_bus,
                "target": original_msg.get("sender", ""),
                "message": response,
            }
            comms.command("hail_contact", params)
            if event_bus and ship:
                event_bus.publish("comms_auto_response", {
                    "ship_id": ship.id,
                    "target": original_msg.get("sender", ""),
                    "response": response,
                })
        except Exception as e:
            logger.debug(f"Auto-comms response failed: {e}")

    # ------------------------------------------------------------------
    # Fleet broadcast
    # ------------------------------------------------------------------

    def _check_broadcast(self, ship, event_bus, now: float):
        """Broadcast fleet status to allied ships at regular intervals."""
        if now - self._last_broadcast_time < BROADCAST_INTERVAL:
            return
        self._last_broadcast_time = now

        comms = ship.systems.get("comms")
        if not comms:
            return

        ship_name = getattr(ship, "name", "Unknown")
        status = f"{ship_name} status: operational"

        try:
            params = {
                "_ship": ship, "ship": ship, "event_bus": event_bus,
                "message": status,
            }
            comms.command("broadcast_message", params)
        except Exception as e:
            logger.debug(f"Auto-comms broadcast failed: {e}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_diplomatic_state(self, ship, contact_faction: str) -> str:
        """Get diplomatic state between ship faction and contact faction."""
        our_faction = getattr(ship, "faction", "")
        if not contact_faction:
            return "unknown"
        try:
            from hybrid.fleet.faction_rules import get_diplomatic_state
            return get_diplomatic_state(our_faction, contact_faction).value
        except Exception:
            return "unknown"

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _auto_execute(self, ship, event_bus, now: float):
        """Execute proposals that have timed out."""
        for p in self._proposals.get_auto_execute_ready(now):
            self._execute_proposal(p, ship, event_bus)

    def _execute_proposal(self, proposal: Proposal, ship, event_bus):
        """Execute a comms proposal."""
        if proposal.action == "hail_response":
            msg = proposal.params.get("msg", {})
            response = proposal.params.get("response", "")
            self._send_response(ship, msg, response, event_bus)
            proposal.status = "executed"
        else:
            proposal.status = "expired"

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def command(self, action: str, params: dict = None) -> dict:
        """Handle auto-comms commands."""
        params = params or {}
        handlers = {
            "enable": self._cmd_enable,
            "disable": self._cmd_disable,
            "set_policy": self._cmd_set_policy,
            "approve": self._cmd_approve,
            "deny": self._cmd_deny,
            "status": self._cmd_status,
        }
        handler = handlers.get(action)
        if handler:
            return handler(params)
        return {"error": f"Unknown auto_comms command: {action}"}

    def _cmd_enable(self, params: dict) -> dict:
        """Enable auto-comms system."""
        self.enabled = True
        return {"ok": True, "status": "Auto-comms ENABLED",
                "policy": self.comms_policy.value}

    def _cmd_disable(self, params: dict) -> dict:
        """Disable auto-comms system."""
        self.enabled = False
        self._proposals.clear()
        return {"ok": True, "status": "Auto-comms DISABLED"}

    def _cmd_set_policy(self, params: dict) -> dict:
        """Set communication policy."""
        policy_str = params.get("policy", "")
        try:
            policy = CommsPolicy(policy_str)
        except ValueError:
            return {"ok": False, "error": f"Invalid policy '{policy_str}'. "
                    f"Valid: {[p.value for p in CommsPolicy]}"}
        self.comms_policy = policy
        auto_exec = policy == CommsPolicy.OPEN_COMMS
        self._proposals.set_auto_execute(auto_exec)
        return {"ok": True, "status": f"Comms policy: {policy.value}",
                "policy": policy.value}

    def _cmd_approve(self, params: dict) -> dict:
        """Approve a pending comms proposal."""
        p = self._proposals.find_pending(params.get("proposal_id"))
        if not p:
            return {"ok": False, "error": "No pending proposals to approve"}
        ship = params.get("_ship") or params.get("ship")
        self._execute_proposal(p, ship, params.get("event_bus"))
        return {"ok": True, "status": f"Approved {p.action} to {p.target}",
                "proposal_id": p.proposal_id}

    def _cmd_deny(self, params: dict) -> dict:
        """Deny a pending comms proposal."""
        p = self._proposals.find_pending(params.get("proposal_id"))
        if not p:
            return {"ok": False, "error": "No pending proposals to deny"}
        p.status = "denied"
        return {"ok": True, "status": f"Denied {p.action} to {p.target}",
                "proposal_id": p.proposal_id}

    def _cmd_status(self, params: dict) -> dict:
        """Get auto-comms status."""
        return {"ok": True, **self.get_state()}

    def get_state(self) -> dict:
        """Return system state for telemetry."""
        return {
            "enabled": self.enabled,
            "status": "active" if self.enabled else "standby",
            "policy": self.comms_policy.value,
            "proposals": [p.to_dict() for p in self._proposals.pending],
            "proposal_count": self._proposals.pending_count,
            "responded_hails": len(self._responded_hails),
        }
