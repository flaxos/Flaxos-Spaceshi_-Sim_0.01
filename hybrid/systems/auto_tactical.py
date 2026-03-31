# hybrid/systems/auto_tactical.py
"""Auto-tactical system: CPU-ASSIST tier automated targeting and fire proposals.

When enabled, the system evaluates sensor contacts each tick, auto-designates
the highest-threat target, and proposes fire actions when firing solutions
reach sufficient confidence. The player approves or denies proposals.

Engagement rules:
  - weapons_free: auto-execute after timeout (5s)
  - weapons_hold: wait for player approval indefinitely
  - defensive_only: auto-fire PDCs only, hold railgun/torpedo

Proposals are published to telemetry so the GUI can render approval UI.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any

from hybrid.core.base_system import BaseSystem
from hybrid.fleet.threat_assessment import AIThreatAssessment

logger = logging.getLogger(__name__)

# Proposal timeout in seconds
PROPOSAL_TIMEOUT = 5.0
# Minimum firing solution confidence to propose fire
MIN_FIRE_CONFIDENCE = 0.7
# Maximum number of active proposals (prevent queue buildup)
MAX_PROPOSALS = 3
# Cooldown between proposals for same action (seconds)
PROPOSAL_COOLDOWN = 3.0


class EngagementMode(Enum):
    """Rules of engagement for auto-tactical."""
    WEAPONS_FREE = "weapons_free"
    WEAPONS_HOLD = "weapons_hold"
    DEFENSIVE_ONLY = "defensive_only"


@dataclass
class TacticalProposal:
    """A proposed tactical action awaiting player approval."""
    proposal_id: str
    action: str              # e.g. "fire_railgun", "fire_pdc", "launch_torpedo"
    target_id: str           # Contact ID
    confidence: float        # Firing solution confidence
    reason: str              # Human-readable reason
    created_at: float        # Simulation time when created
    timeout: float           # Seconds until auto-execute or expiry
    auto_execute: bool       # Whether to auto-execute on timeout
    status: str = "pending"  # pending, approved, denied, expired, executed

    def to_dict(self) -> dict:
        """Serialize for telemetry."""
        return {
            "proposal_id": self.proposal_id,
            "action": self.action,
            "target_id": self.target_id,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "created_at": self.created_at,
            "timeout": self.timeout,
            "auto_execute": self.auto_execute,
            "status": self.status,
            "time_remaining": max(0.0, self.timeout - (time.time() - self.created_at)),
        }


class AutoTacticalSystem(BaseSystem):
    """CPU-ASSIST tier automated targeting and fire control.

    Ticks when enabled. Evaluates contacts, proposes fire actions,
    and executes approved proposals through the combat system.
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        super().__init__(config)

        # Disabled by default -- player enables via command
        self.enabled = False

        self.engagement_mode = EngagementMode.WEAPONS_FREE
        self._proposals: List[TacticalProposal] = []
        self._proposal_counter = 0
        self._last_proposal_time: Dict[str, float] = {}
        self._last_auto_designate_time = 0.0

    def tick(self, dt: float, ship=None, event_bus=None):
        """Evaluate tactical situation and manage proposals.

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

        # 2. Auto-designate target if none locked
        self._auto_designate(ship, event_bus, now)

        # 3. Propose fire if solution is good
        self._propose_fire(ship, event_bus, now)

        # 4. Auto-execute timed-out proposals in weapons_free mode
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
                    event_bus.publish("tactical_proposal_expired", {
                        "ship_id": ship.id,
                        "proposal_id": p.proposal_id,
                        "action": p.action,
                    })
            else:
                still_active.append(p)
        self._proposals = still_active

    def _auto_designate(self, ship, event_bus, now: float):
        """Auto-designate highest-threat contact if no target locked."""
        # Rate limit: check every 2 seconds
        if now - self._last_auto_designate_time < 2.0:
            return

        self._last_auto_designate_time = now

        targeting = ship.systems.get("targeting")
        if not targeting:
            return

        # Already have a locked target
        locked = getattr(targeting, "locked_target", None)
        if locked:
            return

        # Get sensor contacts
        sensors = ship.systems.get("sensors")
        if not sensors or not hasattr(sensors, "contact_tracker"):
            return

        tracker = sensors.contact_tracker
        contacts = []
        for cid, contact in tracker.contacts.items():
            # Only target contacts with sufficient confidence
            if hasattr(contact, "confidence") and contact.confidence > 0.3:
                contacts.append((cid, contact))

        if not contacts:
            return

        # Prioritize by threat
        prioritized = AIThreatAssessment.prioritize_targets(contacts, ship)
        if not prioritized:
            return

        best_id, best_contact = prioritized[0]

        # Auto-designate
        try:
            targeting.lock_target(
                contact_id=best_id,
                sim_time=getattr(ship, "sim_time", None),
            )
            if event_bus:
                event_bus.publish("auto_tactical_designate", {
                    "ship_id": ship.id,
                    "contact_id": best_id,
                    "classification": getattr(best_contact, "classification", "unknown"),
                })
            logger.info(f"Auto-tactical designated target {best_id}")
        except Exception as e:
            logger.debug(f"Auto-designate failed: {e}")

    def _propose_fire(self, ship, event_bus, now: float):
        """Propose fire action if firing solution confidence is high enough."""
        if len(self._proposals) >= MAX_PROPOSALS:
            return

        targeting = ship.systems.get("targeting")
        combat = ship.systems.get("combat")
        if not targeting or not combat:
            return

        locked = getattr(targeting, "locked_target", None)
        if not locked:
            return

        # Get firing solution
        solution = None
        if hasattr(targeting, "get_state"):
            tgt_state = targeting.get_state()
            solution = tgt_state.get("firing_solution")

        if not solution:
            return

        confidence = solution.get("confidence", 0.0)
        if confidence < MIN_FIRE_CONFIDENCE:
            return

        # Determine best weapon to propose
        weapon_action = self._select_weapon(ship, confidence)
        if not weapon_action:
            return

        # Check cooldown for this action
        last_time = self._last_proposal_time.get(weapon_action, 0.0)
        if now - last_time < PROPOSAL_COOLDOWN:
            return

        # Check if already have a pending proposal for this action
        for p in self._proposals:
            if p.action == weapon_action and p.status == "pending":
                return

        # Defensive-only mode: only propose PDC fire
        if (self.engagement_mode == EngagementMode.DEFENSIVE_ONLY
                and weapon_action not in ("fire_pdc",)):
            return

        # Create proposal
        self._proposal_counter += 1
        auto_exec = self.engagement_mode == EngagementMode.WEAPONS_FREE
        proposal = TacticalProposal(
            proposal_id=f"TP-{self._proposal_counter:04d}",
            action=weapon_action,
            target_id=locked,
            confidence=confidence,
            reason=f"Solution confidence {confidence:.0%} on {locked}",
            created_at=now,
            timeout=PROPOSAL_TIMEOUT,
            auto_execute=auto_exec,
            status="pending",
        )
        self._proposals.append(proposal)
        self._last_proposal_time[weapon_action] = now

        if event_bus and ship:
            event_bus.publish("tactical_proposal", {
                "ship_id": ship.id,
                **proposal.to_dict(),
            })

        logger.info(
            f"Auto-tactical proposes {weapon_action} on {locked} "
            f"(confidence={confidence:.2f}, auto_execute={auto_exec})"
        )

    def _select_weapon(self, ship, confidence: float) -> Optional[str]:
        """Select the best weapon to fire based on available weapons and ammo.

        Args:
            ship: Ship object
            confidence: Firing solution confidence

        Returns:
            Command name (e.g. "fire_railgun") or None
        """
        combat = ship.systems.get("combat")
        if not combat or not hasattr(combat, "get_state"):
            return None

        combat_state = combat.get_state()
        weapons = combat_state.get("truth_weapons", {})

        # Prefer railgun for high-confidence shots
        for wname, wstate in weapons.items():
            if not isinstance(wstate, dict):
                continue
            wtype = wstate.get("type", "")
            ammo = wstate.get("ammo", 0)
            ready = wstate.get("ready", False)

            if "railgun" in wtype.lower() and ammo > 0 and ready:
                return "fire_railgun"

        # Fall back to torpedo if available
        for wname, wstate in weapons.items():
            if not isinstance(wstate, dict):
                continue
            wtype = wstate.get("type", "")
            ammo = wstate.get("ammo", 0)
            ready = wstate.get("ready", False)

            if "torpedo" in wtype.lower() and ammo > 0 and ready:
                return "launch_torpedo"

        return None

    def _auto_execute_proposals(self, ship, event_bus, now: float):
        """Execute proposals that have timed out in weapons_free mode."""
        for p in self._proposals:
            if p.status != "pending" or not p.auto_execute:
                continue

            elapsed = now - p.created_at
            if elapsed < p.timeout:
                continue

            # Execute the fire command
            self._execute_proposal(p, ship, event_bus)

    def _execute_proposal(self, proposal: TacticalProposal, ship, event_bus):
        """Execute a tactical proposal through the combat system.

        Args:
            proposal: The proposal to execute
            ship: Ship object
            event_bus: Event bus for events
        """
        combat = ship.systems.get("combat")
        if not combat:
            proposal.status = "expired"
            return

        try:
            params = {
                "_ship": ship,
                "ship": ship,
                "event_bus": event_bus,
                "_from_auto_tactical": True,
            }

            # Use ship._all_ships_ref for target resolution
            if hasattr(ship, "_all_ships_ref"):
                params["all_ships"] = {s.id: s for s in ship._all_ships_ref}

            if proposal.action == "fire_railgun":
                result = combat.command("fire", params)
            elif proposal.action == "launch_torpedo":
                params["profile"] = "direct"
                result = combat.command("launch_torpedo", params)
            elif proposal.action == "fire_pdc":
                result = combat.command("fire", params)
            else:
                proposal.status = "expired"
                return

            proposal.status = "executed"
            if event_bus and ship:
                event_bus.publish("tactical_proposal_executed", {
                    "ship_id": ship.id,
                    "proposal_id": proposal.proposal_id,
                    "action": proposal.action,
                    "result": result if isinstance(result, dict) else str(result),
                })

            logger.info(f"Auto-tactical executed {proposal.action} on {proposal.target_id}")

        except Exception as e:
            logger.error(f"Auto-tactical execute failed: {e}")
            proposal.status = "expired"

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def command(self, action: str, params: dict = None) -> dict:
        """Handle auto-tactical commands."""
        params = params or {}

        if action == "enable":
            return self._cmd_enable(params)
        elif action == "disable":
            return self._cmd_disable(params)
        elif action == "set_engagement_rules":
            return self._cmd_set_engagement_rules(params)
        elif action == "approve":
            return self._cmd_approve(params)
        elif action == "deny":
            return self._cmd_deny(params)
        elif action == "status":
            return self._cmd_status(params)

        return {"error": f"Unknown auto_tactical command: {action}"}

    def _cmd_enable(self, params: dict) -> dict:
        """Enable auto-tactical system."""
        self.enabled = True
        return {
            "ok": True,
            "status": "Auto-tactical ENABLED",
            "engagement_mode": self.engagement_mode.value,
        }

    def _cmd_disable(self, params: dict) -> dict:
        """Disable auto-tactical system."""
        self.enabled = False
        # Clear pending proposals
        for p in self._proposals:
            if p.status == "pending":
                p.status = "expired"
        self._proposals = []
        return {"ok": True, "status": "Auto-tactical DISABLED"}

    def _cmd_set_engagement_rules(self, params: dict) -> dict:
        """Set engagement rules mode.

        Args:
            params: Must include 'mode' key
        """
        mode_str = params.get("mode", "")
        try:
            mode = EngagementMode(mode_str)
        except ValueError:
            valid = [m.value for m in EngagementMode]
            return {
                "ok": False,
                "error": f"Invalid mode '{mode_str}'. Valid: {valid}",
            }

        self.engagement_mode = mode

        # Update auto-execute flag on pending proposals
        auto_exec = mode == EngagementMode.WEAPONS_FREE
        for p in self._proposals:
            if p.status == "pending":
                if mode == EngagementMode.DEFENSIVE_ONLY and p.action != "fire_pdc":
                    p.status = "expired"
                else:
                    p.auto_execute = auto_exec

        return {
            "ok": True,
            "status": f"Engagement rules set to {mode.value}",
            "mode": mode.value,
        }

    def _cmd_approve(self, params: dict) -> dict:
        """Approve a pending tactical proposal.

        Args:
            params: Must include 'proposal_id' key
        """
        pid = params.get("proposal_id")
        if not pid:
            # Approve the first pending proposal
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
                    "status": f"Approved and executed {p.action}",
                    "proposal_id": pid,
                }

        return {"ok": False, "error": f"Proposal '{pid}' not found or not pending"}

    def _cmd_deny(self, params: dict) -> dict:
        """Deny a pending tactical proposal.

        Args:
            params: Must include 'proposal_id' key
        """
        pid = params.get("proposal_id")
        if not pid:
            # Deny the first pending proposal
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
                    "status": f"Denied {p.action} on {p.target_id}",
                    "proposal_id": pid,
                }

        return {"ok": False, "error": f"Proposal '{pid}' not found or not pending"}

    def _cmd_status(self, params: dict) -> dict:
        """Get auto-tactical status."""
        return {
            "ok": True,
            **self.get_state(),
        }

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Return system state for telemetry."""
        return {
            "enabled": self.enabled,
            "status": "active" if self.enabled else "standby",
            "engagement_mode": self.engagement_mode.value,
            "proposals": [p.to_dict() for p in self._proposals if p.status == "pending"],
            "proposal_count": len([p for p in self._proposals if p.status == "pending"]),
        }
