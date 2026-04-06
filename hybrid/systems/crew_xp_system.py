# hybrid/systems/crew_xp_system.py
"""Crew experience point system.

Awards XP to crew members based on combat actions, piloting events, and
sustained high-g operations.  Subscribes to the event bus and maps each
event to the crew member at the relevant station.

Design notes:
- XP is granular (integer points) so players see steady progress bars.
- High-stress actions (firing with low confidence, high-g piloting) award
  bonus XP -- learning under pressure is faster.
- The system is passive: it never blocks or modifies other systems, only
  reads events and writes to CrewMember.experience.
"""

import math
import logging
from typing import Optional, List, Dict, Any

from hybrid.core.base_system import BaseSystem

logger = logging.getLogger(__name__)

# XP amounts for each event type.
# These are deliberately small -- advancement takes sustained play.
XP_WEAPON_HIT = 5
XP_WEAPON_HIT_LOW_CONFIDENCE_BONUS = 3   # Extra if confidence < 0.5
XP_LOCK_ACHIEVED = 3
XP_AUTOPILOT_COMPLETE = 5
XP_AUTOPILOT_COMPLETE_COMBAT_BONUS = 5   # Extra if completed during combat
XP_REPAIR_COMPLETE = 8
XP_SCAN_COMPLETE = 3
XP_ECM_SUCCESS = 5
XP_BOARDING_PER_TICK = 2
XP_HIGH_G_PER_SECOND = 1                 # All skills +1/s above 3g

# G-load threshold for "learning under pressure" bonus
HIGH_G_THRESHOLD = 3.0


class CrewXPSystem(BaseSystem):
    """Awards XP to crew based on combat and operational actions.

    Subscribes to event bus events each tick and awards XP to the crew
    member assigned to the relevant station.  Requires access to the
    shared CrewStationBinder to resolve station->crew mappings.
    """

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config or {})
        self.power_draw = 0.0  # No power cost

        # Track whether we have subscribed to events yet
        self._subscribed = False

        # Accumulate high-g time fraction between ticks
        self._high_g_accum: float = 0.0

        # Buffer for XP awards from events (processed each tick)
        self._pending_awards: List[Dict[str, Any]] = []

    def _ensure_subscribed(self, event_bus) -> None:
        """Subscribe to relevant events once the event bus is available."""
        if self._subscribed or event_bus is None:
            return

        event_bus.subscribe("weapon_fired", self._on_weapon_fired)
        event_bus.subscribe("target_locked", self._on_lock_achieved)
        event_bus.subscribe("autopilot_complete", self._on_autopilot_complete)
        event_bus.subscribe("repair_complete", self._on_repair_complete)
        event_bus.subscribe("science_auto_scan_executed", self._on_scan_complete)
        # ECM degradation of enemy tracks
        event_bus.subscribe("ecm_jam_success", self._on_ecm_success)

        self._subscribed = True
        logger.debug("CrewXPSystem subscribed to event bus")

    # ------------------------------------------------------------------
    # Event handlers -- queue awards for processing in tick()
    # ------------------------------------------------------------------

    def _on_weapon_fired(self, payload: dict) -> None:
        """Weapon fired event. Award gunnery XP on hits."""
        hit = payload.get("hit")
        if hit is None:
            # Railgun slug in flight -- XP awarded on impact, not launch
            return
        if not hit:
            return
        ship_id = payload.get("ship_id")
        confidence = payload.get("confidence", 1.0)
        xp = XP_WEAPON_HIT
        if confidence < 0.5:
            xp += XP_WEAPON_HIT_LOW_CONFIDENCE_BONUS
        self._pending_awards.append({
            "ship_id": ship_id,
            "skill": "gunnery",
            "xp": xp,
            "reason": "weapon_hit",
        })

    def _on_lock_achieved(self, payload: dict) -> None:
        """Target lock acquired. Award targeting XP."""
        ship_id = payload.get("ship_id")
        self._pending_awards.append({
            "ship_id": ship_id,
            "skill": "targeting",
            "xp": XP_LOCK_ACHIEVED,
            "reason": "lock_achieved",
        })

    def _on_autopilot_complete(self, payload: dict) -> None:
        """Autopilot program finished. Award piloting XP."""
        ship_id = payload.get("ship_id")
        # Check if we were in combat (combat_time tracked by fatigue system)
        in_combat = payload.get("in_combat", False)
        xp = XP_AUTOPILOT_COMPLETE
        if in_combat:
            xp += XP_AUTOPILOT_COMPLETE_COMBAT_BONUS
        self._pending_awards.append({
            "ship_id": ship_id,
            "skill": "piloting",
            "xp": xp,
            "reason": "autopilot_complete",
        })

    def _on_repair_complete(self, payload: dict) -> None:
        """Field repair completed. Award damage_control XP."""
        ship_id = payload.get("ship_id")
        self._pending_awards.append({
            "ship_id": ship_id,
            "skill": "damage_control",
            "xp": XP_REPAIR_COMPLETE,
            "reason": "repair_complete",
        })

    def _on_scan_complete(self, payload: dict) -> None:
        """Sensor scan completed. Award sensors XP."""
        ship_id = payload.get("ship_id")
        self._pending_awards.append({
            "ship_id": ship_id,
            "skill": "sensors",
            "xp": XP_SCAN_COMPLETE,
            "reason": "scan_complete",
        })

    def _on_ecm_success(self, payload: dict) -> None:
        """ECM successfully jammed enemy track. Award EW XP."""
        ship_id = payload.get("ship_id")
        self._pending_awards.append({
            "ship_id": ship_id,
            "skill": "electronic_warfare",
            "xp": XP_ECM_SUCCESS,
            "reason": "ecm_success",
        })

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def tick(self, dt: float, ship=None, event_bus=None) -> None:
        """Process pending XP awards and high-g bonus.

        Args:
            dt: Time step in seconds
            ship: Ship object (for g-load and crew access)
            event_bus: Event bus for subscribing to events
        """
        if not self.enabled or ship is None:
            return

        self._ensure_subscribed(event_bus)

        # Resolve the crew binding system -- we need it to map
        # station -> crew_id for targeted XP awards
        from hybrid.systems.crew_binding_system import CrewBindingSystem
        binder = CrewBindingSystem._shared_binder
        crew_manager = CrewBindingSystem._shared_crew_manager
        if binder is None or crew_manager is None:
            # Crew system not initialized yet -- silently skip
            self._pending_awards.clear()
            return

        # Process queued event-based awards
        for award in self._pending_awards:
            if award["ship_id"] != ship.id:
                continue
            self._apply_skill_xp(
                crew_manager, binder, ship.id,
                award["skill"], award["xp"], event_bus,
            )

        self._pending_awards.clear()

        # High-g bonus: all skills get +1 XP/s when above 3g
        # This models accelerated learning under physical pressure
        a = ship.acceleration
        accel_mag = math.sqrt(a["x"]**2 + a["y"]**2 + a["z"]**2)
        current_g = accel_mag / 9.81

        if current_g >= HIGH_G_THRESHOLD:
            self._high_g_accum += dt
            # Award 1 XP per full second of high-g operations
            while self._high_g_accum >= 1.0:
                self._high_g_accum -= 1.0
                self._award_all_skills_xp(
                    crew_manager, binder, ship.id,
                    XP_HIGH_G_PER_SECOND, event_bus,
                )
        else:
            # Decay accumulator when not under high-g
            self._high_g_accum = max(0.0, self._high_g_accum - dt * 0.5)

    # ------------------------------------------------------------------
    # XP application helpers
    # ------------------------------------------------------------------

    def _apply_skill_xp(
        self,
        crew_manager,
        binder,
        ship_id: str,
        skill_name: str,
        xp: int,
        event_bus=None,
    ) -> None:
        """Award XP to the crew member at the station responsible for a skill.

        Maps skill -> station via STATION_SKILL_MAP (reversed), then looks
        up who is assigned there.
        """
        from server.stations.crew_binding import STATION_SKILL_MAP
        from server.stations.crew_system import StationSkill

        try:
            skill_enum = StationSkill(skill_name)
        except ValueError:
            return

        # Find which station owns this skill
        target_station = None
        for station, skills in STATION_SKILL_MAP.items():
            if skill_enum in skills:
                target_station = station
                break

        if target_station is None:
            return

        # Find the crew member at that station
        slots = binder._slots.get(ship_id)
        if slots is None:
            return
        slot = slots.get(target_station)
        if slot is None or slot.crew_id is None:
            return

        crew = crew_manager.get_crew_member(ship_id, slot.crew_id)
        if crew is None:
            return

        advanced = crew.award_xp(skill_name, xp)
        if advanced and event_bus:
            event_bus.publish("crew_skill_advanced", {
                "ship_id": ship_id,
                "crew_id": crew.crew_id,
                "crew_name": crew.name,
                "skill": skill_name,
                "new_level": crew.skills.get_skill(skill_enum),
            })

    def _award_all_skills_xp(
        self,
        crew_manager,
        binder,
        ship_id: str,
        xp: int,
        event_bus=None,
    ) -> None:
        """Award XP to ALL assigned crew members for ALL their station skills.

        Used for the high-g learning bonus -- everyone learns under pressure.
        """
        from server.stations.crew_binding import STATION_SKILL_MAP

        slots = binder._slots.get(ship_id)
        if slots is None:
            return

        for station, slot in slots.items():
            if slot.crew_id is None:
                continue
            crew = crew_manager.get_crew_member(ship_id, slot.crew_id)
            if crew is None:
                continue

            for skill in STATION_SKILL_MAP.get(station, []):
                advanced = crew.award_xp(skill.value, xp)
                if advanced and event_bus:
                    event_bus.publish("crew_skill_advanced", {
                        "ship_id": ship_id,
                        "crew_id": crew.crew_id,
                        "crew_name": crew.name,
                        "skill": skill.value,
                        "new_level": crew.skills.get_skill(skill),
                    })

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Return system state for telemetry."""
        state = super().get_state()
        state["type"] = "crew_xp"
        state["high_g_accum"] = round(self._high_g_accum, 2)
        state["pending_awards"] = len(self._pending_awards)
        return state
