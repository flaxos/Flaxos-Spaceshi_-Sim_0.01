# hybrid/systems/crew_binding_system.py
"""
Crew-station binding system wrapper.

Thin adapter that lets the CrewStationBinder participate in the
standard ship.systems[] command routing. Unlike heavy systems
(propulsion, sensors), this has no tick logic -- it's purely
command-driven.
"""

import logging
from typing import Optional, Dict, Any

from hybrid.core.base_system import BaseSystem
from server.stations.crew_system import CrewManager, CrewSkills, StationSkill
from server.stations.crew_binding import CrewStationBinder
from server.stations.station_types import StationType

logger = logging.getLogger(__name__)


class CrewBindingSystem(BaseSystem):
    """Ship system that manages crew-to-station assignments.

    Wraps CrewStationBinder so it can sit in ship.systems["crew_binding"]
    and receive routed commands from the command handler.

    The actual binder instance is shared across all ships via the
    CrewManager, but each ship gets its own system instance that
    delegates to the shared binder.
    """

    # Class-level shared state -- set once at server startup
    _shared_crew_manager: Optional[CrewManager] = None
    _shared_binder: Optional[CrewStationBinder] = None

    def __init__(self, config: Optional[dict] = None):
        config = config if config is not None else {}
        super().__init__(config)
        self.power_draw = 0.0  # No power cost for crew management

    @classmethod
    def set_shared_state(
        cls,
        crew_manager: CrewManager,
        binder: CrewStationBinder,
    ) -> None:
        """Set the shared CrewManager and binder at server init time."""
        cls._shared_crew_manager = crew_manager
        cls._shared_binder = binder

    @classmethod
    def get_multiplier(cls, ship_id: str, station: StationType, ship=None) -> float:
        """Get crew performance multiplier for a station on a ship.

        Combines two independent crew factors:
        1. Skill-based: crew member competence at this station (from CrewStationBinder)
        2. Fatigue-based: g-load, combat stress, blackout (from CrewFatigueSystem)

        Returns 1.0 (no effect) when crew binding is not initialized,
        so gameplay systems degrade gracefully without crew assignments.

        Args:
            ship_id: Ship identifier for crew slot lookup.
            station: Which station's multiplier to retrieve.
            ship: Optional ship object. When provided, fatigue effects
                  from crew_fatigue system are folded into the result.
        """
        binder = cls._shared_binder
        if binder is None:
            base = 1.0
        elif ship_id not in binder._slots:
            base = 1.0
        else:
            base = binder.get_station_multiplier(ship_id, station)

        # Apply ship-level crew fatigue (g-load, combat stress, blackout).
        # Without a ship reference we return skill-only -- backward compatible
        # with callers that don't have a ship handy.
        # Guard: ship.systems must be a real dict, not a MagicMock that
        # auto-creates attributes (test mocks hit this path).
        if ship is not None and isinstance(getattr(ship, 'systems', None), dict):
            fatigue_sys = ship.systems.get("crew_fatigue")
            if fatigue_sys is not None and hasattr(fatigue_sys, 'get_station_performance'):
                base *= fatigue_sys.get_station_performance(station.value)

        return base

    def tick(self, dt: float, ship: Any = None, event_bus: Any = None) -> None:
        """No per-tick work needed for crew assignments."""
        pass

    def command(self, action: str, params: dict) -> dict:
        """Route commands to the shared CrewStationBinder.

        The command dispatcher calls system.command(action, params).
        We delegate to the binder, which is the real implementation.
        """
        binder = self._shared_binder
        if binder is None:
            return {"ok": False, "error": "Crew binding system not initialized"}

        # The params dict has 'ship' injected by execute_command
        ship = params.get("ship") or params.get("_ship")
        if ship is None:
            return {"ok": False, "error": "No ship context"}

        # Route to the appropriate handler
        handlers = {
            "assign_crew": self._cmd_assign,
            "transfer_crew": self._cmd_transfer,
            "unassign_crew": self._cmd_unassign,
            "crew_station_status": self._cmd_status,
        }

        handler = handlers.get(action)
        if handler is None:
            return {"ok": False, "error": f"Unknown crew_binding action: {action}"}

        return handler(binder, ship, params)

    def _cmd_assign(
        self, binder: CrewStationBinder, ship: Any, params: dict,
    ) -> dict:
        """Handle assign_crew command."""
        crew_id = params.get("crew_id")
        station_str = params.get("station")
        if not crew_id or not station_str:
            return {"ok": False, "error": "crew_id and station are required"}

        try:
            station = StationType(station_str)
        except ValueError:
            return {"ok": False, "error": f"Invalid station: {station_str}"}

        ok, msg = binder.assign_crew(ship.id, crew_id, station)
        return {"ok": ok, "status" if ok else "error": msg}

    def _cmd_transfer(
        self, binder: CrewStationBinder, ship: Any, params: dict,
    ) -> dict:
        """Handle transfer_crew command."""
        crew_id = params.get("crew_id")
        station_str = params.get("to_station")
        if not crew_id or not station_str:
            return {"ok": False, "error": "crew_id and to_station are required"}

        try:
            station = StationType(station_str)
        except ValueError:
            return {"ok": False, "error": f"Invalid station: {station_str}"}

        ok, msg = binder.transfer_crew(ship.id, crew_id, station)
        return {"ok": ok, "status" if ok else "error": msg}

    def _cmd_unassign(
        self, binder: CrewStationBinder, ship: Any, params: dict,
    ) -> dict:
        """Handle unassign_crew command."""
        station_str = params.get("station")
        if not station_str:
            return {"ok": False, "error": "station is required"}

        try:
            station = StationType(station_str)
        except ValueError:
            return {"ok": False, "error": f"Invalid station: {station_str}"}

        ok, msg = binder.unassign_crew(ship.id, station)
        return {"ok": ok, "status" if ok else "error": msg}

    def _cmd_status(
        self, binder: CrewStationBinder, ship: Any, params: dict,
    ) -> dict:
        """Handle crew_station_status command."""
        status = binder.get_ship_crew_status(ship.id)
        return {"ok": True, "status": "Crew station report", "stations": status}

    def get_state(self) -> dict:
        """Return current state for telemetry."""
        base = super().get_state()
        base["type"] = "crew_binding"
        return base
