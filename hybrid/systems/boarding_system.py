# hybrid/systems/boarding_system.py
"""Boarding system for capturing mission-killed ships.

When a target ship is mission-killed (propulsion destroyed, hull intact),
an attacker that has docked can initiate a boarding action to change the
target's faction. This is the "capture instead of destroy" endgame.

Design rules:
- Preconditions: attacker must be docked with target, target must be
  mission-killed, target hull must be > 0 (no boarding a wreck).
- Progress rate: attacker COMMAND skill * BASE_RATE per second.
- Defender resistance: DAMAGE_CONTROL skill reduces rate; each active
  weapon system on the defender applies a -20% penalty; a functioning
  reactor applies -10%.  These model the real difficulty of boarding a
  ship that still has some fight left.
- Capture: when progress >= 1.0, target faction changes to attacker faction.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from hybrid.core.base_system import BaseSystem

logger = logging.getLogger(__name__)


# Base boarding rate per second, scaled by attacker COMMAND skill (1-6).
# At skill 3 (COMPETENT): 3 * 0.01 = 0.03/s => ~33s to board unresisted.
# At skill 6 (MASTER):    6 * 0.01 = 0.06/s => ~17s to board unresisted.
BASE_RATE = 0.01


class BoardingState(Enum):
    """Boarding action state machine."""
    IDLE = "idle"
    DOCKING = "docking"          # Waiting for dock confirmation
    BOARDING = "boarding"        # Crew crossing, progress advancing
    CAPTURED = "captured"        # Target faction changed
    FAILED = "failed"            # Preconditions lost mid-boarding


class BoardingSystem(BaseSystem):
    """Manages boarding actions against mission-killed ships.

    Attached to the *attacker* ship.  Reads docking status from the
    ship's docking system and damage state from the target ship's
    damage model.
    """

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.state: BoardingState = BoardingState.IDLE
        self.target_ship_id: Optional[str] = None
        self.progress: float = 0.0
        self.failure_reason: Optional[str] = None
        # Snapshot of resistance factors for telemetry display
        self._resistance_info: dict = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def begin_boarding(
        self,
        target_ship_id: str,
        ship,
        all_ships: dict,
    ) -> dict:
        """Initiate a boarding action against a target ship.

        Preconditions checked here, not deferred to tick, so the player
        gets immediate feedback on why boarding cannot start.

        Args:
            target_ship_id: ID of the ship to board
            ship: The attacker ship object
            all_ships: Dict of ship_id -> ship for target lookup

        Returns:
            dict with ok/error status
        """
        if self.state == BoardingState.BOARDING:
            return {"ok": False, "error": "Boarding already in progress"}
        if self.state == BoardingState.CAPTURED:
            return {"ok": False, "error": "Target already captured"}

        # --- Check docked ---
        docked_to = getattr(ship, "docked_to", None)
        if docked_to != target_ship_id:
            return {
                "ok": False,
                "error": f"Not docked with {target_ship_id}. "
                         f"Currently docked to: {docked_to or 'nothing'}",
            }

        # --- Resolve target ---
        target = all_ships.get(target_ship_id)
        if target is None:
            return {"ok": False, "error": f"Target {target_ship_id} not found"}

        # --- Target must be mission-killed ---
        damage_model = getattr(target, "damage_model", None)
        if damage_model is None or not damage_model.is_mission_kill():
            return {
                "ok": False,
                "error": "Target is not mission-killed. "
                         "Disable propulsion/weapons first.",
            }

        # --- Target hull must be intact (no boarding a wreck) ---
        hull = getattr(target, "hull_integrity", 1.0)
        if hull <= 0:
            return {"ok": False, "error": "Target hull destroyed; nothing to board"}

        # All checks passed
        self.target_ship_id = target_ship_id
        self.state = BoardingState.BOARDING
        self.progress = 0.0
        self.failure_reason = None
        self._resistance_info = {}

        logger.info(
            "Ship %s begins boarding %s", ship.id, target_ship_id,
        )
        return {"ok": True, "status": "boarding_started", "target": target_ship_id}

    def cancel_boarding(self) -> dict:
        """Abort an in-progress boarding action.

        Returns:
            dict with ok/error status
        """
        if self.state not in (BoardingState.BOARDING, BoardingState.DOCKING):
            return {"ok": False, "error": f"Cannot cancel in state {self.state.value}"}

        prev_target = self.target_ship_id
        self._reset()
        logger.info("Boarding of %s cancelled", prev_target)
        return {"ok": True, "status": "boarding_cancelled"}

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def tick(self, dt: float, ship=None, event_bus=None) -> None:
        """Advance boarding progress each simulation tick.

        Args:
            dt: Time step in seconds
            ship: The attacker ship object
            event_bus: Optional event bus for publishing boarding events
        """
        if not self.enabled or ship is None:
            return
        if self.state != BoardingState.BOARDING:
            return

        # Resolve target from ship's live all_ships reference
        all_ships_ref = getattr(ship, "_all_ships_ref", None)
        if all_ships_ref is None:
            return
        all_ships = {s.id: s for s in all_ships_ref}
        target = all_ships.get(self.target_ship_id)

        # --- Validate preconditions each tick ---
        if target is None:
            self._fail("Target lost", event_bus, ship)
            return

        docked_to = getattr(ship, "docked_to", None)
        if docked_to != self.target_ship_id:
            self._fail("No longer docked with target", event_bus, ship)
            return

        hull = getattr(target, "hull_integrity", 1.0)
        if hull <= 0:
            self._fail("Target hull destroyed during boarding", event_bus, ship)
            return

        # --- Calculate boarding rate ---
        attacker_skill = self._get_crew_skill(ship, "command")
        base_progress = attacker_skill * BASE_RATE * dt

        # --- Defender resistance ---
        resistance, info = self._calculate_resistance(target)
        effective_progress = base_progress * resistance
        self._resistance_info = info

        self.progress = min(1.0, self.progress + effective_progress)

        # --- Check capture ---
        if self.progress >= 1.0:
            self._capture(ship, target, event_bus)

    # ------------------------------------------------------------------
    # Command interface (for system_commands routing)
    # ------------------------------------------------------------------

    def command(self, action: str, params: dict) -> dict:
        """Handle boarding commands routed through the hybrid command handler.

        Args:
            action: Command action name
            params: Command parameters (includes _ship, all_ships, event_bus)

        Returns:
            dict with command result
        """
        if action == "begin_boarding":
            ship = params.get("_ship") or params.get("ship")
            target_id = params.get("target_ship_id") or params.get("target")
            if not target_id:
                return {"ok": False, "error": "Missing target_ship_id"}

            # Prefer _all_ships_ref on the ship (always available per CLAUDE.md)
            all_ships_ref = getattr(ship, "_all_ships_ref", None)
            if all_ships_ref:
                all_ships = {s.id: s for s in all_ships_ref}
            else:
                raw = params.get("all_ships", {})
                all_ships = raw if isinstance(raw, dict) else {
                    s.id: s for s in raw
                }

            return self.begin_boarding(target_id, ship, all_ships)

        if action == "cancel_boarding":
            return self.cancel_boarding()

        if action == "status":
            return self.get_state()

        if action == "power_on":
            return self.power_on()
        if action == "power_off":
            return self.power_off()

        return super().command(action, params)

    # ------------------------------------------------------------------
    # State / telemetry
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Return boarding system telemetry for the GUI.

        Returns:
            dict with current boarding state, progress, target, and resistance
        """
        return {
            **super().get_state(),
            "state": self.state.value,
            "target": self.target_ship_id,
            "progress": round(self.progress, 4),
            "failure_reason": self.failure_reason,
            "resistance": self._resistance_info,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_crew_skill(self, ship, skill_name: str) -> int:
        """Read a crew skill level from the ship, defaulting to 3 (COMPETENT).

        The crew system stores skills as integers 1-6.  We look up the
        first crew member on the ship (or fall back to 3).

        Args:
            ship: Ship object
            skill_name: Skill attribute name on CrewSkills (e.g. "command")

        Returns:
            int: Skill level 1-6
        """
        crew_system = getattr(ship, "crew_system", None)
        if crew_system and hasattr(crew_system, "get_ship_crew"):
            members = crew_system.get_ship_crew(ship.id)
            if members:
                skills = getattr(members[0], "skills", None)
                if skills:
                    return getattr(skills, skill_name, 3)
        return 3  # Default COMPETENT

    def _calculate_resistance(self, target) -> tuple[float, dict]:
        """Calculate defender resistance factor that slows boarding.

        Resistance is a multiplier on the boarding rate (lower = harder).
        - Defender DAMAGE_CONTROL skill: each level above 1 reduces rate
          by 5% (skill 6 = -25%).
        - Each non-failed weapon system: -20%.
        - Functioning reactor: -10%.

        Args:
            target: The target ship being boarded

        Returns:
            tuple of (resistance_multiplier, info_dict_for_telemetry)
        """
        factor = 1.0
        info: dict = {}

        # Defender crew resistance (DAMAGE_CONTROL skill)
        defender_dc_skill = self._get_crew_skill(target, "damage_control")
        dc_penalty = (defender_dc_skill - 1) * 0.05  # 0% at skill 1, 25% at skill 6
        factor -= dc_penalty
        info["damage_control_skill"] = defender_dc_skill
        info["damage_control_penalty"] = round(dc_penalty, 2)

        # Active weapon systems on defender
        damage_model = getattr(target, "damage_model", None)
        active_weapons = 0
        if damage_model:
            # Check both 'weapons' and 'targeting' since both are combat-relevant
            for sys_name in ("weapons", "targeting"):
                sub = damage_model.subsystems.get(sys_name)
                if sub and not sub.is_failed():
                    active_weapons += 1
        weapon_penalty = active_weapons * 0.20
        factor -= weapon_penalty
        info["active_weapons"] = active_weapons
        info["weapon_penalty"] = round(weapon_penalty, 2)

        # Functioning reactor
        reactor_penalty = 0.0
        if damage_model:
            reactor = damage_model.subsystems.get("reactor")
            if reactor and not reactor.is_failed():
                reactor_penalty = 0.10
                factor -= reactor_penalty
        info["reactor_penalty"] = round(reactor_penalty, 2)

        # Clamp: even maximal resistance shouldn't make capture impossible,
        # just very slow.  Floor at 10% rate.
        factor = max(0.10, factor)
        info["total_factor"] = round(factor, 2)

        return factor, info

    def _capture(self, attacker_ship, target, event_bus) -> None:
        """Finalise capture: change target faction, transition to CAPTURED.

        Args:
            attacker_ship: The ship performing the boarding
            target: The target ship being captured
            event_bus: Optional event bus for publishing capture event
        """
        old_faction = getattr(target, "faction", "unknown")
        target.faction = attacker_ship.faction
        self.state = BoardingState.CAPTURED
        self.progress = 1.0

        logger.info(
            "Ship %s captured %s (faction %s -> %s)",
            attacker_ship.id,
            self.target_ship_id,
            old_faction,
            target.faction,
        )

        if event_bus:
            event_bus.publish("ship_captured", {
                "attacker": attacker_ship.id,
                "target": self.target_ship_id,
                "old_faction": old_faction,
                "new_faction": target.faction,
            })

    def _fail(self, reason: str, event_bus, ship) -> None:
        """Transition to FAILED state with a reason.

        Args:
            reason: Human-readable failure description
            event_bus: Optional event bus for publishing failure event
            ship: Attacker ship (for event context)
        """
        self.state = BoardingState.FAILED
        self.failure_reason = reason
        logger.warning(
            "Boarding of %s failed: %s", self.target_ship_id, reason,
        )
        if event_bus:
            event_bus.publish("boarding_failed", {
                "attacker": ship.id if ship else None,
                "target": self.target_ship_id,
                "reason": reason,
            })

    def _reset(self) -> None:
        """Reset boarding state to idle."""
        self.state = BoardingState.IDLE
        self.target_ship_id = None
        self.progress = 0.0
        self.failure_reason = None
        self._resistance_info = {}
