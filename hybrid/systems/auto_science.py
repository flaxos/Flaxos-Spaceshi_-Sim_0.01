# hybrid/systems/auto_science.py
"""Auto-science system: CPU-ASSIST tier automated science analysis.

When enabled, monitors sensor contacts and auto-queues scans on new
unscanned contacts. Proposes threat flags when warships are detected.

Scan behavior:
  - Auto-execute scans immediately (scans are non-destructive)
  - Threat flags wait for approval in manual mode, auto-execute in auto mode
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Dict, Optional, Set

from hybrid.core.base_system import BaseSystem
from hybrid.systems.proposals import ProposalManager, Proposal

logger = logging.getLogger(__name__)

PROPOSAL_TIMEOUT = 10.0
PROPOSAL_COOLDOWN = 15.0
SCAN_CONFIDENCE_MIN = 0.3
THREAT_FLAG_CLASSES = {"corvette", "frigate", "destroyer", "cruiser", "battleship",
                       "carrier", "warship", "gunship"}


class ScienceMode(Enum):
    """Auto-science operating mode."""
    AUTO = "auto"
    MANUAL = "manual"


class AutoScienceSystem(BaseSystem):
    """CPU-ASSIST automated science analysis.

    Monitors sensor contacts, auto-queues scans on new unscanned contacts,
    and proposes threat flags when warship-class contacts are detected.
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        super().__init__(config)
        self.enabled = False
        self.science_mode = ScienceMode.AUTO
        self._proposals = ProposalManager(max_proposals=5, cooldown=PROPOSAL_COOLDOWN)
        self._scanned_contacts: Set[str] = set()
        self._flagged_contacts: Set[str] = set()
        self._last_scan_time = 0.0
        self._scan_queue: list = []

    def tick(self, dt: float, ship=None, event_bus=None):
        """Evaluate science situation and manage proposals."""
        if not self.enabled or ship is None:
            return
        now = time.time()
        self._proposals.expire_old(now, "science_proposal_expired", event_bus, ship)
        if now - self._last_scan_time >= 3.0:
            self._last_scan_time = now
            self._check_new_contacts(ship, event_bus, now)
            self._check_threat_flags(ship, event_bus, now)
        self._process_scan_queue(ship, event_bus, now)
        self._auto_execute(ship, event_bus, now)

    # ------------------------------------------------------------------
    # Contact scanning
    # ------------------------------------------------------------------

    def _check_new_contacts(self, ship, event_bus, now: float):
        """Queue scans for new unscanned contacts."""
        sensors = ship.systems.get("sensors")
        if not sensors or not hasattr(sensors, "contact_tracker"):
            return

        contacts = sensors.contact_tracker.contacts
        for cid, contact in contacts.items():
            confidence = getattr(contact, "confidence", 0.0)
            if confidence < SCAN_CONFIDENCE_MIN:
                continue
            if cid in self._scanned_contacts:
                continue
            # Queue spectral scan
            self._scan_queue.append({
                "contact_id": cid,
                "scan_type": "spectral",
                "queued_at": now,
            })
            self._scanned_contacts.add(cid)

            if event_bus and ship:
                event_bus.publish("science_auto_scan_queued", {
                    "ship_id": ship.id,
                    "contact_id": cid,
                    "scan_type": "spectral",
                })

    def _process_scan_queue(self, ship, event_bus, now: float):
        """Execute queued scans (non-destructive, auto-execute immediately)."""
        science = ship.systems.get("science")
        if not science or not self._scan_queue:
            return

        # Process one scan per tick to avoid flooding
        scan = self._scan_queue.pop(0)
        try:
            params = {
                "_ship": ship, "ship": ship, "event_bus": event_bus,
                "contact_id": scan["contact_id"],
            }
            if scan["scan_type"] == "spectral":
                science.command("science_spectral_scan", params)
            elif scan["scan_type"] == "composition":
                science.command("science_composition_scan", params)

            if event_bus and ship:
                event_bus.publish("science_auto_scan_executed", {
                    "ship_id": ship.id,
                    "contact_id": scan["contact_id"],
                    "scan_type": scan["scan_type"],
                })
        except Exception as e:
            logger.debug(f"Auto-science scan failed for {scan['contact_id']}: {e}")

    # ------------------------------------------------------------------
    # Threat flagging
    # ------------------------------------------------------------------

    def _check_threat_flags(self, ship, event_bus, now: float):
        """Propose threat flags for warship-class contacts."""
        sensors = ship.systems.get("sensors")
        if not sensors or not hasattr(sensors, "contact_tracker"):
            return

        contacts = sensors.contact_tracker.contacts
        for cid, contact in contacts.items():
            if cid in self._flagged_contacts:
                continue
            classification = getattr(contact, "classification", "").lower()
            if not any(cls in classification for cls in THREAT_FLAG_CLASSES):
                continue

            key = f"threat_flag_{cid}"
            if not self._proposals.can_propose(key, now):
                continue

            auto_exec = self.science_mode == ScienceMode.AUTO
            name = getattr(contact, "name", None) or cid
            proposal = self._proposals.create(
                prefix="SCI", action="threat_flag",
                target=cid,
                confidence=getattr(contact, "confidence", 0.5),
                reason=f"{name} classified as {classification}",
                timeout=PROPOSAL_TIMEOUT, auto_execute=auto_exec, now=now,
                params={"contact_id": cid, "classification": classification},
            )
            if event_bus and ship:
                event_bus.publish("science_proposal", {
                    "ship_id": ship.id, **proposal.to_dict(),
                })

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _auto_execute(self, ship, event_bus, now: float):
        """Execute proposals that have timed out in auto mode."""
        for p in self._proposals.get_auto_execute_ready(now):
            self._execute_proposal(p, ship, event_bus)

    def _execute_proposal(self, proposal: Proposal, ship, event_bus):
        """Execute a science proposal (threat flag)."""
        if proposal.action == "threat_flag":
            contact_id = proposal.params.get("contact_id", proposal.target)
            self._flagged_contacts.add(contact_id)
            proposal.status = "executed"
            if event_bus and ship:
                event_bus.publish("science_threat_flagged", {
                    "ship_id": ship.id,
                    "contact_id": contact_id,
                    "classification": proposal.params.get("classification", "unknown"),
                    "proposal_id": proposal.proposal_id,
                })
        else:
            proposal.status = "expired"

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def command(self, action: str, params: dict = None) -> dict:
        """Handle auto-science commands."""
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
        return {"error": f"Unknown auto_science command: {action}"}

    def _cmd_enable(self, params: dict) -> dict:
        """Enable auto-science system."""
        self.enabled = True
        return {"ok": True, "status": "Auto-science ENABLED",
                "mode": self.science_mode.value}

    def _cmd_disable(self, params: dict) -> dict:
        """Disable auto-science system."""
        self.enabled = False
        self._proposals.clear()
        self._scan_queue.clear()
        return {"ok": True, "status": "Auto-science DISABLED"}

    def _cmd_set_mode(self, params: dict) -> dict:
        """Set operating mode (auto or manual)."""
        mode_str = params.get("mode", "")
        try:
            mode = ScienceMode(mode_str)
        except ValueError:
            return {"ok": False, "error": f"Invalid mode '{mode_str}'. "
                    f"Valid: {[m.value for m in ScienceMode]}"}
        self.science_mode = mode
        self._proposals.set_auto_execute(mode == ScienceMode.AUTO)
        return {"ok": True, "status": f"Auto-science mode: {mode.value}",
                "mode": mode.value}

    def _cmd_approve(self, params: dict) -> dict:
        """Approve a pending science proposal."""
        p = self._proposals.find_pending(params.get("proposal_id"))
        if not p:
            return {"ok": False, "error": "No pending proposals to approve"}
        ship = params.get("_ship") or params.get("ship")
        self._execute_proposal(p, ship, params.get("event_bus"))
        return {"ok": True, "status": f"Approved {p.action} on {p.target}",
                "proposal_id": p.proposal_id}

    def _cmd_deny(self, params: dict) -> dict:
        """Deny a pending science proposal."""
        p = self._proposals.find_pending(params.get("proposal_id"))
        if not p:
            return {"ok": False, "error": "No pending proposals to deny"}
        p.status = "denied"
        return {"ok": True, "status": f"Denied {p.action} on {p.target}",
                "proposal_id": p.proposal_id}

    def _cmd_status(self, params: dict) -> dict:
        """Get auto-science status."""
        return {"ok": True, **self.get_state()}

    def get_state(self) -> dict:
        """Return system state for telemetry."""
        return {
            "enabled": self.enabled,
            "status": "active" if self.enabled else "standby",
            "mode": self.science_mode.value,
            "proposals": [p.to_dict() for p in self._proposals.pending],
            "proposal_count": self._proposals.pending_count,
            "scanned_contacts": len(self._scanned_contacts),
            "flagged_contacts": list(self._flagged_contacts),
            "scan_queue_size": len(self._scan_queue),
        }
