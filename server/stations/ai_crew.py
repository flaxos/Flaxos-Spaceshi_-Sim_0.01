"""
AI Crew System for unclaimed stations.

When a station is unclaimed, an AI crew member runs basic automated
behaviors at a configurable competence level.  This ensures the ship
can function even with a skeleton human crew.

AI crew behaviors are intentionally simple -- they keep the ship alive
but make suboptimal decisions that a human would improve on.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Set, Any, List

from .station_types import StationType

logger = logging.getLogger(__name__)


@dataclass
class AICrewMember:
    """Represents an AI-controlled station operator."""
    station: StationType
    ship_id: str
    competence: float = 0.7  # 0.0 (useless) to 1.0 (expert)
    active: bool = True
    last_action_time: float = 0.0
    action_interval: float = 5.0  # seconds between AI decisions


class AICrewManager:
    """
    Manages AI crew for unclaimed stations on each ship.

    The AI crew runs periodic tick-based behaviors.  When a human player
    claims a station, the AI for that station is deactivated.  When the
    human releases the station, the AI takes over again.

    Competence affects decision quality:
      - 1.0: Optimal decisions (expert NPC)
      - 0.7: Good but not perfect (default)
      - 0.3: Slow reactions, occasional mistakes
      - 0.0: No actions taken (placeholder only)
    """

    def __init__(self, default_competence: float = 0.7):
        self.default_competence = max(0.0, min(1.0, default_competence))
        # ship_id -> station -> AICrewMember
        self._ai_crew: Dict[str, Dict[StationType, AICrewMember]] = {}
        # Stations that should have AI crew (excludes CAPTAIN and FLEET_COMMANDER)
        self._automatable_stations: Set[StationType] = {
            StationType.HELM,
            StationType.TACTICAL,
            StationType.OPS,
            StationType.ENGINEERING,
            StationType.COMMS,
            StationType.SCIENCE,
        }

    def register_ship(self, ship_id: str, competence: Optional[float] = None):
        """Initialize AI crew for all automatable stations on a ship."""
        comp = competence if competence is not None else self.default_competence
        ship_crew: Dict[StationType, AICrewMember] = {}
        for station in self._automatable_stations:
            ship_crew[station] = AICrewMember(
                station=station,
                ship_id=ship_id,
                competence=comp,
            )
        self._ai_crew[ship_id] = ship_crew
        logger.info(
            f"AI crew registered for ship {ship_id} "
            f"({len(ship_crew)} stations, competence={comp:.1f})"
        )

    def deactivate_station(self, ship_id: str, station: StationType):
        """Deactivate AI for a station (human claimed it)."""
        crew = self._ai_crew.get(ship_id, {})
        if station in crew:
            crew[station].active = False
            logger.debug(f"AI crew deactivated: {station.value} on {ship_id}")

    def activate_station(self, ship_id: str, station: StationType):
        """Reactivate AI for a station (human released it)."""
        crew = self._ai_crew.get(ship_id, {})
        if station in crew:
            crew[station].active = True
            logger.debug(f"AI crew activated: {station.value} on {ship_id}")

    def set_competence(self, ship_id: str, station: StationType, competence: float):
        """Set competence level for an AI crew member."""
        crew = self._ai_crew.get(ship_id, {})
        if station in crew:
            crew[station].competence = max(0.0, min(1.0, competence))

    def tick(self, ships: Dict[str, Any], dt: float):
        """
        Run AI crew behaviors for all ships.

        Called once per simulation tick. Each AI crew member checks
        whether it's time to act based on its action_interval.
        """
        now = time.time()

        for ship_id, crew in self._ai_crew.items():
            ship = ships.get(ship_id)
            if not ship:
                continue

            # Skip fully AI-controlled ships -- they have their own
            # AIController and don't need per-station AI crew.
            if getattr(ship, "ai_enabled", False):
                continue

            for station, ai in crew.items():
                if not ai.active or ai.competence <= 0.0:
                    continue

                # Check if enough time has passed for next action
                elapsed = now - ai.last_action_time
                # Lower competence = slower reaction time
                interval = ai.action_interval / max(ai.competence, 0.1)
                if elapsed < interval:
                    continue

                ai.last_action_time = now
                self._run_station_ai(ship, ai)

    def _run_station_ai(self, ship: Any, ai: AICrewMember):
        """Run AI behavior for a specific station."""
        try:
            if ai.station == StationType.OPS:
                self._ai_ops(ship, ai)
            elif ai.station == StationType.ENGINEERING:
                self._ai_engineering(ship, ai)
            elif ai.station == StationType.TACTICAL:
                self._ai_tactical(ship, ai)
            # Other stations (HELM, COMMS, SCIENCE) are passive by default --
            # AI doesn't take actions unless there's an immediate need
        except Exception as e:
            logger.debug(f"AI crew error ({ai.station.value} on {ai.ship_id}): {e}")

    def _ai_ops(self, ship: Any, ai: AICrewMember):
        """
        AI Ops behavior: dispatch repair teams to damaged systems.

        The AI checks for damaged subsystems and dispatches idle repair
        teams to the most damaged one.
        """
        ops = ship.systems.get("ops")
        if not ops:
            return

        # Check for damaged subsystems that need repair
        damage_model = getattr(ship, "damage_model", None)
        if not damage_model:
            return

        # Find most damaged subsystem
        worst_subsystem = None
        worst_factor = 1.0
        for subsystem in ["propulsion", "rcs", "sensors", "weapons", "reactor",
                          "targeting", "life_support", "radiators"]:
            factor = damage_model.get_combined_factor(subsystem)
            if factor < worst_factor:
                worst_factor = factor
                worst_subsystem = subsystem

        # Only dispatch repairs if something is significantly damaged
        if worst_subsystem and worst_factor < 0.8:
            try:
                ops.command("dispatch_repair", {
                    "ship": ship,
                    "subsystem": worst_subsystem,
                })
            except Exception:
                pass

    def _ai_engineering(self, ship: Any, ai: AICrewMember):
        """
        AI Engineering behavior: manage heat sinks when overheating.
        """
        thermal = ship.systems.get("thermal")
        if not thermal:
            return

        state = thermal.get_state()
        hull_temp = state.get("hull_temperature", 300)
        warning_temp = state.get("warning_temperature", 400)
        sinks_remaining = state.get("heat_sink_remaining", 0)

        # Activate heat sink if overheating and sinks available
        if hull_temp > warning_temp * 0.95 and sinks_remaining > 0:
            if not state.get("heat_sink_active", False):
                try:
                    thermal.command("activate_heat_sink", {"ship": ship})
                except Exception:
                    pass

    def _ai_tactical(self, ship: Any, ai: AICrewMember):
        """
        AI Tactical behavior: set PDCs to auto mode for point defense.

        The AI ensures PDCs are in auto mode for torpedo/projectile defense.
        It does NOT fire weapons proactively -- that's the captain's call.
        """
        combat = ship.systems.get("combat")
        if not combat:
            return

        # Ensure PDC auto mode is on (defensive posture)
        for weapon in combat.weapons.values():
            if hasattr(weapon, "weapon_type") and "PDC" in str(weapon.weapon_type):
                if hasattr(weapon, "auto_mode") and not weapon.auto_mode:
                    try:
                        combat.command("set_pdc_mode", {
                            "ship": ship,
                            "mode": "auto",
                        })
                    except Exception:
                        pass
                    break  # Only need to set once

    def get_status(self, ship_id: str) -> List[Dict[str, Any]]:
        """Get AI crew status for a ship."""
        crew = self._ai_crew.get(ship_id, {})
        return [
            {
                "station": ai.station.value,
                "active": ai.active,
                "competence": ai.competence,
            }
            for ai in crew.values()
        ]

    def get_all_status(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get AI crew status for all ships."""
        return {
            ship_id: self.get_status(ship_id)
            for ship_id in self._ai_crew
        }
