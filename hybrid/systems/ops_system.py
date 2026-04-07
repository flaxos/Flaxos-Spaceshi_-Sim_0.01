# hybrid/systems/ops_system.py
"""Ops station system: power budget allocation, damage control teams, and system priorities.

Power is a finite budget from the reactor. The ops officer distributes
reactor output among subsystems based on tactical priority. You cannot
run everything at full simultaneously — hard choices must be made.

Repair teams are physical crew members who take time to move through
the ship and work on damaged systems. Dispatching a team to sensors
means propulsion won't get fixed until the team is reassigned.

Commands:
    allocate_power: Distribute reactor output among subsystems by priority
    dispatch_repair: Send a damage control team to a specific subsystem
    set_system_priority: Triage which systems get power when reactor is impaired
    report_status: Full subsystem integrity readout
    emergency_shutdown: Scram a system to prevent cascade failure
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum

from hybrid.core.base_system import BaseSystem
from hybrid.systems.field_repair import (
    FieldRepairManager, RepairPriority, FIELD_REPAIR_HEALTH_CAP,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Power allocation
# ---------------------------------------------------------------------------

# Default power priorities (higher = gets power first when reactor is impaired)
DEFAULT_PRIORITIES: Dict[str, int] = {
    "life_support": 10,
    "reactor": 9,
    "sensors": 7,
    "rcs": 6,
    "propulsion": 5,
    "targeting": 4,
    "weapons": 3,
    "radiators": 8,
}

# Power allocation percentages (how much of reactor output each system gets)
DEFAULT_POWER_ALLOCATION: Dict[str, float] = {
    "life_support": 0.05,
    "reactor": 0.10,
    "sensors": 0.15,
    "rcs": 0.10,
    "propulsion": 0.25,
    "targeting": 0.10,
    "weapons": 0.15,
    "radiators": 0.10,
}


# ---------------------------------------------------------------------------
# Repair team model
# ---------------------------------------------------------------------------

class RepairTeamStatus(Enum):
    """Status of a damage control team."""
    IDLE = "idle"
    EN_ROUTE = "en_route"
    REPAIRING = "repairing"


@dataclass
class RepairTeam:
    """A physical damage control team on the ship.

    Teams take time to move between subsystems (transit_time) and repair
    at a fixed rate (repair_rate hp/s). They can only work on one system
    at a time.
    """
    team_id: str
    status: RepairTeamStatus = RepairTeamStatus.IDLE
    assigned_subsystem: Optional[str] = None
    transit_remaining: float = 0.0      # seconds until arrival
    repair_rate: float = 2.0            # health points per second
    transit_speed: float = 10.0         # seconds base transit time between compartments

    def to_dict(self) -> dict:
        """Serialize team state for telemetry."""
        return {
            "team_id": self.team_id,
            "status": self.status.value,
            "assigned_subsystem": self.assigned_subsystem,
            "transit_remaining": round(self.transit_remaining, 1),
            "repair_rate": self.repair_rate,
        }


# ---------------------------------------------------------------------------
# Ops System
# ---------------------------------------------------------------------------

class OpsSystem(BaseSystem):
    """Manages power distribution, system priorities, and damage control teams.

    Ticked each frame to:
    1. Apply power allocation factors to subsystem performance
    2. Move repair teams and apply repairs
    3. Track system priority ordering for degraded-reactor scenarios
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        super().__init__(config)

        # Power allocation: subsystem -> fraction of reactor output (0.0-1.0)
        self.power_allocation: Dict[str, float] = dict(DEFAULT_POWER_ALLOCATION)
        if "power_allocation" in config:
            self.power_allocation.update(config["power_allocation"])
        self._normalize_allocation()

        # System priorities: subsystem -> priority level (higher = more important)
        self.system_priorities: Dict[str, int] = dict(DEFAULT_PRIORITIES)
        if "priorities" in config:
            self.system_priorities.update(config["priorities"])

        # Shutdown systems (scrammed to prevent cascade)
        self.shutdown_systems: set = set()

        # Repair teams
        num_teams = int(config.get("repair_teams", 2))
        self.repair_teams: List[RepairTeam] = []
        for i in range(num_teams):
            team_config = {}
            if "repair_team_config" in config:
                team_config = config["repair_team_config"]
            self.repair_teams.append(RepairTeam(
                team_id=f"DC-{i+1}",
                repair_rate=float(team_config.get("repair_rate", 2.0)),
                transit_speed=float(team_config.get("transit_speed", 10.0)),
            ))

        # Track total repairs applied
        self._total_repairs = 0.0

        # Field repair manager: spare parts, g-load constraints, health cap
        field_repair_config = config.get("field_repair", {})
        self.field_repair = FieldRepairManager(field_repair_config)

    def _normalize_allocation(self):
        """Ensure power allocation percentages sum to 1.0."""
        total = sum(self.power_allocation.values())
        if total > 0:
            self.power_allocation = {
                k: v / total for k, v in self.power_allocation.items()
            }

    def tick(self, dt: float, ship=None, event_bus=None):
        """Update ops system each tick.

        Args:
            dt: Time step in seconds
            ship: Ship object
            event_bus: EventBus for publishing events
        """
        if not self.enabled or ship is None or dt <= 0:
            return

        # 1. Apply power allocation effects
        self._apply_power_allocation(ship, event_bus)

        # 2. Enforce emergency shutdowns
        self._enforce_shutdowns(ship, event_bus)

        # 3. Update repair teams
        self._tick_repair_teams(dt, ship, event_bus)

    def _apply_power_allocation(self, ship, event_bus=None):
        """Apply power allocation as a modifier to subsystem performance.

        When the reactor is impaired, systems with lower power allocation
        get penalized more. At full reactor health, allocation just determines
        the relative power distribution.
        """
        if not hasattr(ship, "damage_model"):
            return

        # Get reactor health factor (1.0 = full, 0.0 = dead)
        reactor_factor = ship.get_effective_factor("reactor")

        if reactor_factor >= 0.95:
            # Reactor healthy: no power-based penalties
            return

        # Reactor impaired: systems get power proportional to their allocation
        # multiplied by available reactor output. Lower-priority systems
        # get cut first via the priority ordering.
        sorted_systems = sorted(
            self.power_allocation.keys(),
            key=lambda s: self.system_priorities.get(s, 0),
            reverse=True,
        )

        remaining_power = reactor_factor  # fraction of total output available
        for subsystem in sorted_systems:
            alloc = self.power_allocation.get(subsystem, 0.0)
            if remaining_power >= alloc:
                remaining_power -= alloc
                # System gets full allocation
            else:
                # System gets partial power — reduce its performance
                if alloc > 0 and subsystem in ship.damage_model.subsystems:
                    # Apply power starvation as additional heat to slow the system
                    # (the cascade system handles actual performance via reactor cascade)
                    pass
                remaining_power = 0.0

    def _enforce_shutdowns(self, ship, event_bus=None):
        """Enforce emergency shutdowns on scrammed systems.

        Scrammed systems have their heat pushed to overheat to force
        the cascade system to apply maximum penalties.
        """
        if not hasattr(ship, "damage_model"):
            return

        for subsystem_name in self.shutdown_systems:
            sub = ship.damage_model.subsystems.get(subsystem_name)
            if sub and not sub.is_overheated():
                # Force overheat to shut down
                heat_needed = sub.max_heat * sub.overheat_threshold - sub.heat + 1.0
                if heat_needed > 0:
                    ship.damage_model.add_heat(
                        subsystem_name, heat_needed, event_bus, ship.id
                    )

    def _get_current_g(self, ship) -> float:
        """Get current g-load from ship acceleration.

        Args:
            ship: Ship object

        Returns:
            float: Current g-load (multiples of Earth gravity)
        """
        import math
        a = getattr(ship, "acceleration", {"x": 0, "y": 0, "z": 0})
        accel_mag = math.sqrt(a["x"]**2 + a["y"]**2 + a["z"]**2)
        return accel_mag / 9.81

    def _tick_repair_teams(self, dt: float, ship, event_bus=None):
        """Update repair team positions and apply field repairs.

        Field repairs are constrained by:
        - Spare parts (finite consumable)
        - G-load (high acceleration slows/halts repairs)
        - Health cap (field repair maxes out at 50% — dock for full restore)

        Args:
            dt: Time step in seconds
            ship: Ship object
            event_bus: EventBus for events
        """
        if not hasattr(ship, "damage_model"):
            return

        current_g = self._get_current_g(ship)

        for team in self.repair_teams:
            if team.status == RepairTeamStatus.IDLE:
                continue

            if team.status == RepairTeamStatus.EN_ROUTE:
                # G-load also slows transit (crew moving through corridors)
                g_factor = self.field_repair.get_g_load_factor(current_g)
                transit_dt = dt * max(0.1, g_factor)  # Minimum 10% transit speed
                team.transit_remaining -= transit_dt
                if team.transit_remaining <= 0:
                    team.transit_remaining = 0.0
                    team.status = RepairTeamStatus.REPAIRING
                    # Register repair job with field repair manager
                    self.field_repair.start_repair(team.assigned_subsystem)
                    if event_bus:
                        event_bus.publish("repair_team_arrived", {
                            "ship_id": ship.id,
                            "team_id": team.team_id,
                            "subsystem": team.assigned_subsystem,
                        })
                    logger.info(
                        f"Repair team {team.team_id} arrived at "
                        f"{team.assigned_subsystem}"
                    )

            if team.status == RepairTeamStatus.REPAIRING:
                subsystem = team.assigned_subsystem
                sub = ship.damage_model.subsystems.get(subsystem)

                if not sub:
                    team.status = RepairTeamStatus.IDLE
                    team.assigned_subsystem = None
                    self.field_repair.cancel_repair(subsystem)
                    continue

                # Cannot repair destroyed subsystems
                from hybrid.systems.damage_model import SubsystemStatus
                if sub.get_status() == SubsystemStatus.DESTROYED:
                    team.status = RepairTeamStatus.IDLE
                    team.assigned_subsystem = None
                    self.field_repair.cancel_repair(subsystem)
                    if event_bus:
                        event_bus.publish("repair_failed", {
                            "ship_id": ship.id,
                            "team_id": team.team_id,
                            "subsystem": subsystem,
                            "reason": "destroyed",
                        })
                    continue

                # Check if at field repair cap or full health
                cap = self.field_repair.get_field_repair_cap(sub.max_health)
                if sub.health >= cap:
                    team.status = RepairTeamStatus.IDLE
                    team.assigned_subsystem = None
                    self.field_repair.complete_repair(subsystem)
                    if event_bus:
                        event_bus.publish("repair_complete", {
                            "ship_id": ship.id,
                            "team_id": team.team_id,
                            "subsystem": subsystem,
                            "capped": sub.health < sub.max_health,
                            "field_repair_limit": True,
                        })
                    logger.info(
                        f"Repair team {team.team_id} completed field repairs on "
                        f"{subsystem} (capped at {FIELD_REPAIR_HEALTH_CAP*100:.0f}%)"
                    )
                    continue

                # Apply constrained repair through field repair manager.
                # Crew skill: OPS station crew affects repair speed.
                # Skilled damage control officers direct teams more effectively.
                from hybrid.systems.crew_binding_system import CrewBindingSystem
                from server.stations.station_types import StationType
                crew_repair_mult = CrewBindingSystem.get_multiplier(
                    ship.id, StationType.OPS, ship=ship
                )
                raw_repair = team.repair_rate * dt * crew_repair_mult
                actual_repair, pause_reason = (
                    self.field_repair.apply_repair_constraints(
                        subsystem=subsystem,
                        raw_repair_amount=raw_repair,
                        current_health=sub.health,
                        max_health=sub.max_health,
                        current_g=current_g,
                    )
                )

                if actual_repair > 0:
                    ship.damage_model.repair_subsystem(subsystem, actual_repair)
                    self._total_repairs += actual_repair
                elif pause_reason and event_bus:
                    # Publish pause event (throttled to avoid spam)
                    event_bus.publish("repair_paused", {
                        "ship_id": ship.id,
                        "team_id": team.team_id,
                        "subsystem": subsystem,
                        "reason": pause_reason,
                    })

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def command(self, action: str, params: dict = None) -> dict:
        """Handle ops system commands."""
        params = params or {}

        if action == "allocate_power":
            return self._cmd_allocate_power(params)
        elif action == "dispatch_repair":
            return self._cmd_dispatch_repair(params)
        elif action == "cancel_repair":
            return self._cmd_cancel_repair(params)
        elif action == "repair_status":
            return self._cmd_repair_status(params)
        elif action == "set_repair_priority":
            return self._cmd_set_repair_priority(params)
        elif action == "set_system_priority":
            return self._cmd_set_system_priority(params)
        elif action == "report_status":
            return self._cmd_report_status(params)
        elif action == "emergency_shutdown":
            return self._cmd_emergency_shutdown(params)
        elif action == "restart_system":
            return self._cmd_restart_system(params)

        return {"error": f"Unknown ops command: {action}"}

    def _cmd_allocate_power(self, params: dict) -> dict:
        """Distribute reactor output among subsystems.

        Params:
            allocation (dict): subsystem -> fraction (0.0-1.0)
                e.g. {"propulsion": 0.4, "weapons": 0.3, "sensors": 0.3}
        """
        allocation = params.get("allocation", {})
        if not allocation or not isinstance(allocation, dict):
            return {
                "ok": False,
                "error": "Missing 'allocation' dict. Example: "
                         '{"propulsion": 0.4, "weapons": 0.3, "sensors": 0.3}',
            }

        # Validate all values are numeric and non-negative
        for subsystem, fraction in allocation.items():
            try:
                val = float(fraction)
                if val < 0:
                    return {
                        "ok": False,
                        "error": f"Allocation for '{subsystem}' cannot be negative",
                    }
            except (TypeError, ValueError):
                return {
                    "ok": False,
                    "error": f"Invalid allocation value for '{subsystem}': {fraction}",
                }

        # Apply allocation (merge with existing)
        for subsystem, fraction in allocation.items():
            self.power_allocation[subsystem] = float(fraction)

        self._normalize_allocation()

        return {
            "ok": True,
            "status": "Power allocation updated",
            "allocation": {k: round(v, 3) for k, v in self.power_allocation.items()},
        }

    def _cmd_dispatch_repair(self, params: dict) -> dict:
        """Send a damage control team to a specific subsystem.

        Params:
            subsystem (str): Target subsystem to repair
            team (str, optional): Specific team ID (defaults to first idle team)
        """
        ship = params.get("_ship") or params.get("ship")
        subsystem = params.get("subsystem")

        if not subsystem:
            return {"ok": False, "error": "Missing 'subsystem' parameter"}

        # Validate subsystem exists
        if ship and hasattr(ship, "damage_model"):
            if subsystem not in ship.damage_model.subsystems:
                available = sorted(ship.damage_model.subsystems.keys())
                return {
                    "ok": False,
                    "error": f"Unknown subsystem '{subsystem}'",
                    "available_subsystems": available,
                }

            # Check if subsystem is destroyed (unrepairable)
            sub = ship.damage_model.subsystems[subsystem]
            from hybrid.systems.damage_model import SubsystemStatus
            if sub.get_status() == SubsystemStatus.DESTROYED:
                return {
                    "ok": False,
                    "error": f"Subsystem '{subsystem}' is DESTROYED and cannot be repaired",
                }

            # Check if subsystem is already at full health
            if sub.health >= sub.max_health:
                return {
                    "ok": False,
                    "error": f"Subsystem '{subsystem}' is already at full health",
                }

        # Find a team to dispatch
        team_id = params.get("team")
        team = None

        if team_id:
            # Specific team requested
            team = next(
                (t for t in self.repair_teams if t.team_id == team_id), None
            )
            if not team:
                available_teams = [t.team_id for t in self.repair_teams]
                return {
                    "ok": False,
                    "error": f"Unknown team '{team_id}'",
                    "available_teams": available_teams,
                }
        else:
            # Find first idle team, then first busy team (reassign)
            team = next(
                (t for t in self.repair_teams
                 if t.status == RepairTeamStatus.IDLE), None
            )
            if not team:
                # All teams busy - reassign the one with the most transit remaining
                # (least progress on current task)
                team = max(
                    self.repair_teams,
                    key=lambda t: t.transit_remaining,
                    default=None,
                )

        if not team:
            return {"ok": False, "error": "No repair teams available"}

        # Check if already assigned to this subsystem
        if (team.assigned_subsystem == subsystem
                and team.status in (RepairTeamStatus.EN_ROUTE,
                                    RepairTeamStatus.REPAIRING)):
            return {
                "ok": False,
                "error": f"Team {team.team_id} is already assigned to {subsystem}",
            }

        # Dispatch the team
        old_assignment = team.assigned_subsystem
        team.assigned_subsystem = subsystem
        team.status = RepairTeamStatus.EN_ROUTE
        team.transit_remaining = team.transit_speed  # base transit time

        event_bus = params.get("event_bus")
        if event_bus and ship:
            event_bus.publish("repair_team_dispatched", {
                "ship_id": ship.id,
                "team_id": team.team_id,
                "subsystem": subsystem,
                "previous_assignment": old_assignment,
                "transit_time": team.transit_remaining,
            })

        return {
            "ok": True,
            "status": f"Team {team.team_id} dispatched to {subsystem}",
            "team": team.to_dict(),
            "eta": round(team.transit_remaining, 1),
        }

    def _cmd_cancel_repair(self, params: dict) -> dict:
        """Cancel an active repair job and recall the team.

        Params:
            subsystem (str): Subsystem to cancel repair for
        """
        subsystem = params.get("subsystem")
        if not subsystem:
            return {"ok": False, "error": "Missing 'subsystem' parameter"}

        # Find and recall the team working on this subsystem
        team_found = None
        for team in self.repair_teams:
            if team.assigned_subsystem == subsystem:
                team_found = team
                break

        if not team_found:
            return {
                "ok": False,
                "error": f"No repair team assigned to '{subsystem}'",
            }

        old_status = team_found.status.value
        team_found.status = RepairTeamStatus.IDLE
        team_found.assigned_subsystem = None
        team_found.transit_remaining = 0.0
        self.field_repair.cancel_repair(subsystem)

        event_bus = params.get("event_bus")
        ship = params.get("_ship") or params.get("ship")
        if event_bus and ship:
            event_bus.publish("repair_cancelled", {
                "ship_id": ship.id,
                "team_id": team_found.team_id,
                "subsystem": subsystem,
            })

        return {
            "ok": True,
            "status": f"Repair cancelled: team {team_found.team_id} "
                       f"recalled from {subsystem}",
            "team": team_found.to_dict(),
        }

    def _cmd_repair_status(self, params: dict) -> dict:
        """Get detailed field repair status including spare parts and active jobs.

        Returns spare parts level, active repairs, g-load factor, and queue.
        """
        ship = params.get("_ship") or params.get("ship")

        result: Dict[str, Any] = {
            "ok": True,
            "repair_teams": [t.to_dict() for t in self.repair_teams],
            "field_repair": self.field_repair.get_state(),
        }

        if ship:
            current_g = self._get_current_g(ship)
            g_factor = self.field_repair.get_g_load_factor(current_g)
            result["current_g"] = round(current_g, 2)
            result["g_load_repair_factor"] = round(g_factor, 2)
            result["g_load_status"] = (
                "nominal" if g_factor >= 0.9
                else "degraded" if g_factor > 0
                else "halted"
            )

        return result

    def _cmd_set_repair_priority(self, params: dict) -> dict:
        """Set repair priority for a subsystem.

        Params:
            subsystem (str): Subsystem name
            priority (str): Priority level: critical, high, normal, low
        """
        subsystem = params.get("subsystem")
        priority_str = params.get("priority", "normal")

        if not subsystem:
            return {"ok": False, "error": "Missing 'subsystem' parameter"}

        priority_map = {
            "critical": RepairPriority.CRITICAL,
            "high": RepairPriority.HIGH,
            "normal": RepairPriority.NORMAL,
            "low": RepairPriority.LOW,
        }
        priority = priority_map.get(priority_str.lower() if isinstance(priority_str, str) else "")
        if priority is None:
            return {
                "ok": False,
                "error": f"Invalid priority '{priority_str}'. "
                         f"Valid: {', '.join(priority_map.keys())}",
            }

        self.field_repair.set_priority(subsystem, priority)

        return {
            "ok": True,
            "status": f"Repair priority for {subsystem} set to {priority.name}",
            "subsystem": subsystem,
            "priority": priority.name.lower(),
        }

    def _cmd_set_system_priority(self, params: dict) -> dict:
        """Set the priority level for a subsystem.

        Higher priority systems get power first when reactor is impaired.

        Params:
            subsystem (str): Subsystem to prioritize
            priority (int): Priority level (0-10, higher = more important)
        """
        subsystem = params.get("subsystem")
        priority = params.get("priority")

        if not subsystem:
            return {"ok": False, "error": "Missing 'subsystem' parameter"}

        if priority is None:
            return {"ok": False, "error": "Missing 'priority' parameter (0-10)"}

        try:
            priority_val = int(priority)
            if priority_val < 0 or priority_val > 10:
                return {
                    "ok": False,
                    "error": "Priority must be between 0 and 10",
                }
        except (TypeError, ValueError):
            return {"ok": False, "error": f"Invalid priority value: {priority}"}

        self.system_priorities[subsystem] = priority_val

        # Return sorted priority list
        sorted_priorities = sorted(
            self.system_priorities.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        return {
            "ok": True,
            "status": f"Priority for {subsystem} set to {priority_val}",
            "priorities": dict(sorted_priorities),
        }

    def _cmd_report_status(self, params: dict) -> dict:
        """Full subsystem integrity readout with repair team status.

        Returns all subsystem health, status, heat, cascade effects,
        repair team assignments, and power allocation.
        """
        ship = params.get("_ship") or params.get("ship")

        result: Dict[str, Any] = {
            "ok": True,
            "power_allocation": {
                k: round(v, 3) for k, v in self.power_allocation.items()
            },
            "system_priorities": dict(
                sorted(
                    self.system_priorities.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
            ),
            "repair_teams": [t.to_dict() for t in self.repair_teams],
            "shutdown_systems": sorted(self.shutdown_systems),
            "total_repairs_applied": round(self._total_repairs, 1),
        }

        if ship and hasattr(ship, "damage_model"):
            result["subsystem_report"] = ship.damage_model.get_report()

            # Add effective factors (damage + heat + cascade)
            effective_factors = {}
            for name in ship.damage_model.subsystems:
                effective_factors[name] = round(
                    ship.get_effective_factor(name), 3
                )
            result["effective_factors"] = effective_factors

        if ship and hasattr(ship, "cascade_manager"):
            result["cascade_effects"] = ship.cascade_manager.get_report()

        return result

    def _cmd_emergency_shutdown(self, params: dict) -> dict:
        """Scram a system to prevent cascade failure.

        Forces a subsystem into overheat shutdown. Used to isolate
        a failing system before it causes cascading damage.

        Params:
            subsystem (str): System to scram
        """
        ship = params.get("_ship") or params.get("ship")
        subsystem = params.get("subsystem")

        if not subsystem:
            return {"ok": False, "error": "Missing 'subsystem' parameter"}

        # Validate subsystem exists
        if ship and hasattr(ship, "damage_model"):
            if subsystem not in ship.damage_model.subsystems:
                available = sorted(ship.damage_model.subsystems.keys())
                return {
                    "ok": False,
                    "error": f"Unknown subsystem '{subsystem}'",
                    "available_subsystems": available,
                }

        # Cannot shut down reactor (use reactor scram for that)
        if subsystem == "reactor":
            return {
                "ok": False,
                "error": "Cannot emergency-shutdown the reactor from OPS. "
                         "Use reactor scram from ENGINEERING.",
            }

        # Already shutdown?
        if subsystem in self.shutdown_systems:
            return {
                "ok": False,
                "error": f"Subsystem '{subsystem}' is already shut down",
            }

        self.shutdown_systems.add(subsystem)

        event_bus = params.get("event_bus")
        if event_bus and ship:
            event_bus.publish("emergency_shutdown", {
                "ship_id": ship.id,
                "subsystem": subsystem,
                "message": f"OPS: Emergency shutdown of {subsystem} "
                           "to prevent cascade failure",
            })

        logger.warning(f"Emergency shutdown: {subsystem}")

        return {
            "ok": True,
            "status": f"Emergency shutdown: {subsystem} scrammed",
            "subsystem": subsystem,
            "shutdown_systems": sorted(self.shutdown_systems),
        }

    def _cmd_restart_system(self, params: dict) -> dict:
        """Restart a previously scrammed system.

        Params:
            subsystem (str): System to restart
        """
        ship = params.get("_ship") or params.get("ship")
        subsystem = params.get("subsystem")

        if not subsystem:
            return {"ok": False, "error": "Missing 'subsystem' parameter"}

        if subsystem not in self.shutdown_systems:
            return {
                "ok": False,
                "error": f"Subsystem '{subsystem}' is not in emergency shutdown",
            }

        self.shutdown_systems.discard(subsystem)

        event_bus = params.get("event_bus")
        if event_bus and ship:
            event_bus.publish("system_restarted", {
                "ship_id": ship.id,
                "subsystem": subsystem,
                "message": f"OPS: {subsystem} restarted after emergency shutdown",
            })

        logger.info(f"System restarted: {subsystem}")

        return {
            "ok": True,
            "status": f"System restarted: {subsystem}",
            "subsystem": subsystem,
            "shutdown_systems": sorted(self.shutdown_systems),
        }

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Get ops system state for telemetry."""
        return {
            "enabled": self.enabled,
            "status": "online",
            "power_allocation": {
                k: round(v, 3) for k, v in self.power_allocation.items()
            },
            "system_priorities": dict(
                sorted(
                    self.system_priorities.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
            ),
            "repair_teams": [t.to_dict() for t in self.repair_teams],
            "shutdown_systems": sorted(self.shutdown_systems),
            "total_repairs_applied": round(self._total_repairs, 1),
            "field_repair": self.field_repair.get_state(),
        }
