# hybrid/systems/auto_fleet.py
"""Auto-fleet system: CPU-ASSIST tier automated fleet management.

When enabled, evaluates the tactical situation and proposes fleet-level
actions for player approval:
  - Formation recommendation based on threat geometry
  - Target distribution across fleet members
  - Retreat recommendation when fleet damage exceeds threshold
  - Regroup recommendation when formation spread is too wide

Modes:
  - auto: proposals auto-execute after timeout
  - manual: proposals wait for player approval indefinitely
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Dict, Optional

from hybrid.core.base_system import BaseSystem
from hybrid.systems.proposals import ProposalManager, Proposal

logger = logging.getLogger(__name__)

PROPOSAL_TIMEOUT = 8.0
PROPOSAL_COOLDOWN = 10.0

# Damage thresholds for retreat/regroup proposals
RETREAT_DAMAGE_THRESHOLD = 0.6   # >60% fleet average damage
REGROUP_SPREAD_THRESHOLD = 15000  # meters -- formation too wide

# How often (seconds) to re-evaluate the tactical picture
SCAN_INTERVAL = 3.0

# Formation recommendations based on threat count
FORMATION_THREAT_MAP = {
    0: "line",       # No threats: travel formation
    1: "wedge",      # Single threat: aggressive wedge
    2: "wall",       # Two threats: broadside wall
    3: "diamond",    # Multiple threats: defensive diamond
}


class FleetMode(Enum):
    """Auto-fleet operating mode."""
    AUTO = "auto"
    MANUAL = "manual"


class AutoFleetSystem(BaseSystem):
    """CPU-ASSIST automated fleet management.

    Monitors fleet state and tactical picture, proposes fleet-level
    actions. Player approves or denies proposals.
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        super().__init__(config)
        self.enabled = False
        self.fleet_mode = FleetMode.AUTO
        self._proposals = ProposalManager(max_proposals=4, cooldown=PROPOSAL_COOLDOWN)
        self._last_scan_time = 0.0

    def tick(self, dt: float, ship=None, event_bus=None):
        """Evaluate fleet situation and manage proposals."""
        if not self.enabled or ship is None:
            return

        now = time.time()
        self._proposals.expire_old(now, "fleet_proposal_expired", event_bus, ship)

        if now - self._last_scan_time < SCAN_INTERVAL:
            return
        self._last_scan_time = now

        fleet_coord = ship.systems.get("fleet_coord")
        if not fleet_coord:
            return

        fleet_state = self._get_fleet_state(fleet_coord, ship)
        if not fleet_state:
            return

        self._propose_formation(fleet_state, ship, event_bus, now)
        self._propose_retreat(fleet_state, ship, event_bus, now)
        self._propose_regroup(fleet_state, ship, event_bus, now)
        self._propose_target_distribution(fleet_state, ship, event_bus, now)
        self._auto_execute(ship, event_bus, now)

    # ------------------------------------------------------------------
    # Tactical evaluation helpers
    # ------------------------------------------------------------------

    def _get_fleet_state(self, fleet_coord, ship) -> Optional[dict]:
        """Pull fleet state from the fleet_coord system.

        Returns a dict with keys: ships, threats, formation, spread, avg_damage.
        Returns None if no fleet data is available.
        """
        try:
            status = fleet_coord.command("fleet_status", {
                "ship": ship, "_ship": ship,
                "event_bus": getattr(ship, "event_bus", None),
            })
        except Exception:
            return None

        fleet = status.get("fleet") or status.get("fleets", [{}])[0] if isinstance(status, dict) else None
        if not fleet:
            return None

        ships = fleet.get("ships", [])
        if not ships:
            return None

        # Compute average damage across fleet members
        damage_values = []
        for s in ships:
            health = s.get("health", 1.0)
            damage_values.append(1.0 - health)
        avg_damage = sum(damage_values) / len(damage_values) if damage_values else 0.0

        # Compute formation spread (max distance from center of mass)
        spread = 0.0
        if len(ships) > 1:
            positions = []
            for s in ships:
                pos = s.get("position", {})
                positions.append((pos.get("x", 0), pos.get("y", 0), pos.get("z", 0)))
            cx = sum(p[0] for p in positions) / len(positions)
            cy = sum(p[1] for p in positions) / len(positions)
            cz = sum(p[2] for p in positions) / len(positions)
            for px, py, pz in positions:
                d = ((px - cx)**2 + (py - cy)**2 + (pz - cz)**2) ** 0.5
                if d > spread:
                    spread = d

        # Count threats from sensor contacts
        threat_count = 0
        sensors = ship.systems.get("sensors")
        if sensors and hasattr(sensors, "contact_tracker"):
            for cid, c in sensors.contact_tracker.contacts.items():
                if hasattr(c, "classification") and c.classification in ("hostile", "unknown"):
                    if hasattr(c, "confidence") and c.confidence > 0.3:
                        threat_count += 1

        return {
            "ships": ships,
            "formation": fleet.get("formation"),
            "spread": spread,
            "avg_damage": avg_damage,
            "threat_count": threat_count,
            "fleet_id": fleet.get("fleet_id") or fleet.get("id"),
        }

    def _propose_formation(self, state: dict, ship, event_bus, now: float):
        """Propose formation change based on threat geometry."""
        action_key = "recommend_formation"
        if not self._proposals.can_propose(action_key, now):
            return

        threat_count = state["threat_count"]
        key = min(threat_count, max(FORMATION_THREAT_MAP.keys()))
        recommended = FORMATION_THREAT_MAP.get(key, "line")

        current = state.get("formation")
        if current == recommended:
            return

        confidence = 0.7 + min(threat_count * 0.05, 0.25)
        auto_exec = self.fleet_mode == FleetMode.AUTO

        proposal = self._proposals.create(
            prefix="FL", action=action_key,
            target=recommended,
            confidence=confidence,
            reason=f"{threat_count} threat(s) detected -- recommend {recommended.upper()} formation",
            timeout=PROPOSAL_TIMEOUT,
            auto_execute=auto_exec, now=now,
            params={"formation": recommended, "fleet_id": state.get("fleet_id")},
        )

        if event_bus and ship:
            event_bus.publish("fleet_proposal", {
                "ship_id": ship.id, **proposal.to_dict(),
            })

    def _propose_retreat(self, state: dict, ship, event_bus, now: float):
        """Propose retreat when fleet damage is critical."""
        action_key = "recommend_retreat"
        if not self._proposals.can_propose(action_key, now):
            return

        if state["avg_damage"] < RETREAT_DAMAGE_THRESHOLD:
            return

        confidence = min(0.5 + state["avg_damage"], 1.0)
        auto_exec = self.fleet_mode == FleetMode.AUTO

        proposal = self._proposals.create(
            prefix="FL", action=action_key,
            target="retreat",
            confidence=confidence,
            reason=f"Fleet damage {state['avg_damage']:.0%} -- recommend RETREAT",
            timeout=PROPOSAL_TIMEOUT,
            auto_execute=auto_exec, now=now,
            params={"maneuver": "evasive", "fleet_id": state.get("fleet_id")},
        )

        if event_bus and ship:
            event_bus.publish("fleet_proposal", {
                "ship_id": ship.id, **proposal.to_dict(),
            })

    def _propose_regroup(self, state: dict, ship, event_bus, now: float):
        """Propose regroup when formation spread exceeds threshold."""
        action_key = "recommend_regroup"
        if not self._proposals.can_propose(action_key, now):
            return

        if state["spread"] < REGROUP_SPREAD_THRESHOLD:
            return

        confidence = min(0.6 + (state["spread"] - REGROUP_SPREAD_THRESHOLD) / 50000, 1.0)
        auto_exec = self.fleet_mode == FleetMode.AUTO

        proposal = self._proposals.create(
            prefix="FL", action=action_key,
            target="regroup",
            confidence=confidence,
            reason=f"Formation spread {state['spread']/1000:.1f}km -- recommend REGROUP",
            timeout=PROPOSAL_TIMEOUT,
            auto_execute=auto_exec, now=now,
            params={"maneuver": "hold", "fleet_id": state.get("fleet_id")},
        )

        if event_bus and ship:
            event_bus.publish("fleet_proposal", {
                "ship_id": ship.id, **proposal.to_dict(),
            })

    def _propose_target_distribution(self, state: dict, ship, event_bus, now: float):
        """Propose target assignments when multiple threats and ships."""
        action_key = "recommend_target_dist"
        if not self._proposals.can_propose(action_key, now):
            return

        if state["threat_count"] < 2 or len(state["ships"]) < 2:
            return

        confidence = 0.75
        auto_exec = self.fleet_mode == FleetMode.AUTO

        proposal = self._proposals.create(
            prefix="FL", action=action_key,
            target="distribute_targets",
            confidence=confidence,
            reason=f"{state['threat_count']} threats, {len(state['ships'])} ships -- recommend SPLIT FIRE",
            timeout=PROPOSAL_TIMEOUT,
            auto_execute=auto_exec, now=now,
            params={"fleet_id": state.get("fleet_id")},
        )

        if event_bus and ship:
            event_bus.publish("fleet_proposal", {
                "ship_id": ship.id, **proposal.to_dict(),
            })

    def _auto_execute(self, ship, event_bus, now: float):
        """Execute proposals that have timed out in auto mode."""
        for p in self._proposals.get_auto_execute_ready(now):
            self._execute_proposal(p, ship, event_bus)

    def _execute_proposal(self, proposal: Proposal, ship, event_bus):
        """Execute a fleet proposal through the fleet_coord system."""
        fleet_coord = ship.systems.get("fleet_coord")
        if not fleet_coord:
            proposal.status = "expired"
            return

        try:
            cmd_params = {
                "ship": ship, "_ship": ship,
                "event_bus": event_bus,
                "_from_auto_fleet": True,
            }

            if proposal.action == "recommend_formation":
                formation = proposal.params.get("formation", "line")
                fleet_id = proposal.params.get("fleet_id")
                cmd_params["formation"] = formation
                cmd_params["fleet_id"] = fleet_id
                cmd_params["spacing"] = 2000
                fleet_coord.command("fleet_form", cmd_params)

            elif proposal.action == "recommend_retreat":
                fleet_id = proposal.params.get("fleet_id")
                maneuver = proposal.params.get("maneuver", "evasive")
                cmd_params["fleet_id"] = fleet_id
                cmd_params["maneuver"] = maneuver
                fleet_coord.command("fleet_maneuver", cmd_params)

            elif proposal.action == "recommend_regroup":
                fleet_id = proposal.params.get("fleet_id")
                maneuver = proposal.params.get("maneuver", "hold")
                cmd_params["fleet_id"] = fleet_id
                cmd_params["maneuver"] = maneuver
                fleet_coord.command("fleet_maneuver", cmd_params)

            elif proposal.action == "recommend_target_dist":
                pass

            else:
                proposal.status = "expired"
                return

            proposal.status = "executed"
            if event_bus and ship:
                event_bus.publish("fleet_proposal_executed", {
                    "ship_id": ship.id,
                    "proposal_id": proposal.proposal_id,
                    "action": proposal.action,
                })
        except Exception as e:
            logger.error(f"Auto-fleet execute failed: {e}")
            proposal.status = "expired"

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def command(self, action: str, params: dict = None) -> dict:
        """Handle auto-fleet commands."""
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
        return {"error": f"Unknown auto_fleet command: {action}"}

    def _cmd_enable(self, params: dict) -> dict:
        """Enable auto-fleet system."""
        self.enabled = True
        return {"ok": True, "status": "Auto-fleet ENABLED",
                "mode": self.fleet_mode.value}

    def _cmd_disable(self, params: dict) -> dict:
        """Disable auto-fleet system."""
        self.enabled = False
        self._proposals.clear()
        return {"ok": True, "status": "Auto-fleet DISABLED"}

    def _cmd_set_mode(self, params: dict) -> dict:
        """Set auto-fleet operating mode (auto/manual)."""
        mode_str = params.get("mode", "")
        try:
            mode = FleetMode(mode_str)
        except ValueError:
            return {"ok": False, "error": f"Invalid mode '{mode_str}'. "
                    f"Valid: {[m.value for m in FleetMode]}"}

        self.fleet_mode = mode
        auto_exec = mode == FleetMode.AUTO
        self._proposals.set_auto_execute(auto_exec)
        return {"ok": True, "status": f"Auto-fleet mode: {mode.value}",
                "mode": mode.value}

    def _cmd_approve(self, params: dict) -> dict:
        """Approve a pending fleet proposal."""
        p = self._proposals.find_pending(params.get("proposal_id"))
        if not p:
            return {"ok": False, "error": "No pending fleet proposals to approve"}
        ship = params.get("_ship") or params.get("ship")
        self._execute_proposal(p, ship, params.get("event_bus"))
        return {"ok": True, "status": f"Approved {p.action}",
                "proposal_id": p.proposal_id}

    def _cmd_deny(self, params: dict) -> dict:
        """Deny a pending fleet proposal."""
        p = self._proposals.find_pending(params.get("proposal_id"))
        if not p:
            return {"ok": False, "error": "No pending fleet proposals to deny"}
        p.status = "denied"
        return {"ok": True, "status": f"Denied {p.action}",
                "proposal_id": p.proposal_id}

    def _cmd_status(self, params: dict) -> dict:
        """Get auto-fleet status."""
        return {"ok": True, **self.get_state()}

    def get_state(self) -> dict:
        """Return system state for telemetry."""
        return {
            "enabled": self.enabled,
            "status": "active" if self.enabled else "standby",
            "mode": self.fleet_mode.value,
            "proposals": [p.to_dict() for p in self._proposals.pending],
            "proposal_count": self._proposals.pending_count,
        }
