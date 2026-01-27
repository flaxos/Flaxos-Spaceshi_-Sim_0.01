"""
Fleet telemetry filtering for FLEET_COMMANDER station.

Provides fleet-level tactical displays and data aggregation.
"""

from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class FleetTelemetryFilter:
    """
    Filters and formats fleet telemetry for FLEET_COMMANDER station.
    Aggregates data across multiple ships in a fleet.
    """

    def __init__(self, fleet_manager):
        """
        Initialize fleet telemetry filter.

        Args:
            fleet_manager: FleetManager instance
        """
        self.fleet_manager = fleet_manager

    def get_fleet_tactical_display(self, ship_id: str) -> Dict[str, Any]:
        """
        Get comprehensive fleet tactical display.

        Args:
            ship_id: Ship requesting the display

        Returns:
            Dictionary with fleet tactical information
        """
        # Find which fleet this ship belongs to
        fleet_id = self.fleet_manager.ship_to_fleet.get(ship_id)

        if not fleet_id:
            return {
                "error": "Ship not assigned to a fleet",
                "available_fleets": list(self.fleet_manager.fleets.keys())
            }

        # Get fleet status
        fleet_status = self.fleet_manager.get_fleet_status(fleet_id)
        if not fleet_status:
            return {"error": "Fleet not found"}

        # Get tactical summary
        tactical_summary = self.fleet_manager.get_fleet_tactical_summary(fleet_id)

        # Get shared contacts
        shared_contacts = self.fleet_manager.get_shared_contacts(fleet_id)

        # Format contact list
        contacts_list = []
        for contact in shared_contacts:
            contacts_list.append({
                "contact_id": contact.contact_id,
                "classification": contact.classification,
                "threat_level": contact.threat_level.name,
                "is_hostile": contact.is_hostile,
                "reporting_ship": contact.reporting_ship,
                "position": contact.position.tolist(),
                "velocity": contact.velocity.tolist(),
                "confidence": contact.confidence,
                "age": contact.last_update
            })

        # Get formation info
        formation_info = None
        fleet = self.fleet_manager.fleets[fleet_id]
        if fleet.formation_id:
            formation_info = self.fleet_manager.formation_manager.get_formation_status(fleet.formation_id)

            # Add formation positions
            if formation_info:
                positions = self.fleet_manager.get_formation_positions(fleet_id)
                formation_info["positions"] = [
                    {
                        "ship_id": pos.ship_id,
                        "slot": pos.slot_index,
                        "relative_position": pos.relative_position.tolist(),
                        "priority": pos.priority
                    }
                    for pos in positions
                ]

        return {
            "fleet_id": fleet_id,
            "fleet_status": fleet_status,
            "tactical_summary": tactical_summary,
            "shared_contacts": contacts_list,
            "formation": formation_info,
            "contact_count": len(contacts_list),
            "hostile_count": len([c for c in contacts_list if c["is_hostile"]])
        }

    def get_fleet_formation_view(self, ship_id: str) -> Dict[str, Any]:
        """
        Get fleet formation view showing ship positions.

        Args:
            ship_id: Ship requesting the view

        Returns:
            Dictionary with formation visualization data
        """
        fleet_id = self.fleet_manager.ship_to_fleet.get(ship_id)

        if not fleet_id:
            return {"error": "Ship not assigned to a fleet"}

        fleet = self.fleet_manager.fleets.get(fleet_id)
        if not fleet:
            return {"error": "Fleet not found"}

        # Get flagship position as reference point
        flagship = self._get_ship(fleet.flagship_id)
        if not flagship:
            return {"error": "Flagship not found"}

        flagship_pos = [flagship.x, flagship.y, flagship.z]
        flagship_vel = [flagship.vx, flagship.vy, flagship.vz]

        # Get all ship positions relative to flagship
        ship_positions = []
        for sid in fleet.ship_ids:
            ship = self._get_ship(sid)
            if ship:
                # Calculate relative position
                rel_x = ship.x - flagship.x
                rel_y = ship.y - flagship.y
                rel_z = ship.z - flagship.z

                ship_positions.append({
                    "ship_id": sid,
                    "is_flagship": sid == fleet.flagship_id,
                    "position": [ship.x, ship.y, ship.z],
                    "relative_position": [rel_x, rel_y, rel_z],
                    "velocity": [ship.vx, ship.vy, ship.vz],
                    "status": self._get_ship_status(ship)
                })

        # Get formation info
        formation_data = None
        if fleet.formation_id:
            positions = self.fleet_manager.get_formation_positions(fleet_id)
            formation_data = {
                "type": self.fleet_manager.formation_manager.formations[fleet.formation_id].formation_type.value,
                "target_positions": [
                    {
                        "ship_id": pos.ship_id,
                        "target_relative": pos.relative_position.tolist(),
                        "slot": pos.slot_index
                    }
                    for pos in positions
                ]
            }

        return {
            "fleet_id": fleet_id,
            "flagship_id": fleet.flagship_id,
            "flagship_position": flagship_pos,
            "flagship_velocity": flagship_vel,
            "ships": ship_positions,
            "formation": formation_data,
            "status": fleet.status.value
        }

    def get_fleet_status_board(self, ship_id: str) -> Dict[str, Any]:
        """
        Get fleet status board showing system health across all ships.

        Args:
            ship_id: Ship requesting the board

        Returns:
            Dictionary with fleet-wide system status
        """
        fleet_id = self.fleet_manager.ship_to_fleet.get(ship_id)

        if not fleet_id:
            return {"error": "Ship not assigned to a fleet"}

        fleet = self.fleet_manager.fleets.get(fleet_id)
        if not fleet:
            return {"error": "Fleet not found"}

        ship_statuses = []
        for sid in fleet.ship_ids:
            ship = self._get_ship(sid)
            if ship:
                # Get system status
                systems_online = 0
                systems_total = 0
                system_details = []

                if hasattr(ship, "systems"):
                    for sys_name, system in ship.systems.items():
                        systems_total += 1
                        is_online = getattr(system, "is_online", True)
                        if is_online:
                            systems_online += 1

                        system_details.append({
                            "name": sys_name,
                            "online": is_online,
                            "health": getattr(system, "health", 100.0)
                        })

                # Get weapons status
                weapons_ready = 0
                weapons_total = 0
                if hasattr(ship, "systems") and "weapons" in ship.systems:
                    weapon_sys = ship.systems["weapons"]
                    if hasattr(weapon_sys, "weapons"):
                        weapons_total = len(weapon_sys.weapons)
                        weapons_ready = len([w for w in weapon_sys.weapons.values()
                                            if getattr(w, "ready", True)])

                ship_statuses.append({
                    "ship_id": sid,
                    "is_flagship": sid == fleet.flagship_id,
                    "systems_online": systems_online,
                    "systems_total": systems_total,
                    "systems_percent": (systems_online / systems_total * 100) if systems_total > 0 else 0,
                    "weapons_ready": weapons_ready,
                    "weapons_total": weapons_total,
                    "system_details": system_details
                })

        # Calculate fleet totals
        total_systems = sum(s["systems_total"] for s in ship_statuses)
        online_systems = sum(s["systems_online"] for s in ship_statuses)
        total_weapons = sum(s["weapons_total"] for s in ship_statuses)
        ready_weapons = sum(s["weapons_ready"] for s in ship_statuses)

        return {
            "fleet_id": fleet_id,
            "ship_count": len(ship_statuses),
            "ships": ship_statuses,
            "fleet_totals": {
                "systems_online": online_systems,
                "systems_total": total_systems,
                "systems_percent": (online_systems / total_systems * 100) if total_systems > 0 else 0,
                "weapons_ready": ready_weapons,
                "weapons_total": total_weapons
            }
        }

    def get_threat_board(self, ship_id: str) -> Dict[str, Any]:
        """
        Get threat board showing all hostile contacts and threat assessment.

        Args:
            ship_id: Ship requesting the board

        Returns:
            Dictionary with threat information
        """
        fleet_id = self.fleet_manager.ship_to_fleet.get(ship_id)

        if not fleet_id:
            return {"error": "Ship not assigned to a fleet"}

        # Get all shared contacts
        contacts = self.fleet_manager.get_shared_contacts(fleet_id)

        # Filter hostiles and sort by threat
        hostiles = [c for c in contacts if c.is_hostile]
        hostiles.sort(key=lambda c: c.threat_level.value, reverse=True)

        # Format threat list
        threat_list = []
        for contact in hostiles:
            # Calculate range from flagship
            fleet = self.fleet_manager.fleets[fleet_id]
            flagship = self._get_ship(fleet.flagship_id)

            range_to_flagship = 0
            if flagship:
                import numpy as np
                flagship_pos = np.array([flagship.x, flagship.y, flagship.z])
                distance = np.linalg.norm(contact.position - flagship_pos)
                range_to_flagship = distance

            threat_list.append({
                "contact_id": contact.contact_id,
                "classification": contact.classification,
                "threat_level": contact.threat_level.name,
                "threat_value": contact.threat_level.value,
                "range": range_to_flagship,
                "position": contact.position.tolist(),
                "velocity": contact.velocity.tolist(),
                "reporting_ship": contact.reporting_ship,
                "confidence": contact.confidence
            })

        # Count by threat level
        threat_counts = {
            "critical": len([t for t in threat_list if t["threat_value"] == 4]),
            "high": len([t for t in threat_list if t["threat_value"] == 3]),
            "medium": len([t for t in threat_list if t["threat_value"] == 2]),
            "low": len([t for t in threat_list if t["threat_value"] == 1])
        }

        return {
            "fleet_id": fleet_id,
            "total_hostiles": len(threat_list),
            "threats": threat_list,
            "threat_counts": threat_counts,
            "highest_threat": threat_list[0] if threat_list else None
        }

    def get_engagement_summary(self, ship_id: str) -> Dict[str, Any]:
        """
        Get engagement summary showing current combat status.

        Args:
            ship_id: Ship requesting the summary

        Returns:
            Dictionary with engagement information
        """
        fleet_id = self.fleet_manager.ship_to_fleet.get(ship_id)

        if not fleet_id:
            return {"error": "Ship not assigned to a fleet"}

        fleet = self.fleet_manager.fleets.get(fleet_id)
        if not fleet:
            return {"error": "Fleet not found"}

        # Get current target
        current_target = None
        if fleet.target_contact and fleet.target_contact in self.fleet_manager.shared_contacts:
            target = self.fleet_manager.shared_contacts[fleet.target_contact]
            current_target = {
                "contact_id": target.contact_id,
                "classification": target.classification,
                "threat_level": target.threat_level.name,
                "position": target.position.tolist(),
                "velocity": target.velocity.tolist()
            }

        # Count ships engaging
        engaging_ships = []
        for sid in fleet.ship_ids:
            ship = self._get_ship(sid)
            if ship and hasattr(ship, "systems"):
                targeting = ship.systems.get("targeting")
                if targeting and hasattr(targeting, "current_target"):
                    if targeting.current_target == fleet.target_contact:
                        engaging_ships.append(sid)

        # Get weapons status across fleet
        total_weapons = 0
        ready_weapons = 0
        firing_weapons = 0

        for sid in fleet.ship_ids:
            ship = self._get_ship(sid)
            if ship and hasattr(ship, "systems"):
                weapon_sys = ship.systems.get("weapons")
                if weapon_sys and hasattr(weapon_sys, "weapons"):
                    for weapon in weapon_sys.weapons.values():
                        total_weapons += 1
                        if getattr(weapon, "ready", True):
                            ready_weapons += 1
                        if getattr(weapon, "firing", False):
                            firing_weapons += 1

        return {
            "fleet_id": fleet_id,
            "status": fleet.status.value,
            "current_target": current_target,
            "ships_engaging": len(engaging_ships),
            "total_ships": len(fleet.ship_ids),
            "weapons_total": total_weapons,
            "weapons_ready": ready_weapons,
            "weapons_firing": firing_weapons,
            "engaged": fleet.status.value == "engaging"
        }

    def _get_ship(self, ship_id: str):
        """Get ship object from simulator."""
        if hasattr(self.fleet_manager, "simulator") and self.fleet_manager.simulator:
            return self.fleet_manager.simulator.ships.get(ship_id)
        return None

    def _get_ship_status(self, ship) -> str:
        """
        Determine the operational status of a ship.

        Args:
            ship: Ship object

        Returns:
            Status string: "online", "damaged", "critical", "destroyed", "offline"
        """
        if not ship:
            return "offline"

        # Check if ship is destroyed (health <= 0 or explicitly marked)
        if hasattr(ship, "destroyed") and ship.destroyed:
            return "destroyed"

        if hasattr(ship, "health"):
            health = ship.health
            if health <= 0:
                return "destroyed"
            elif health < 25:
                return "critical"
            elif health < 60:
                return "damaged"

        # Check systems status - count how many are offline
        systems_total = 0
        systems_offline = 0

        if hasattr(ship, "systems"):
            for sys_name, system in ship.systems.items():
                systems_total += 1
                is_online = getattr(system, "is_online", True)
                if not is_online:
                    systems_offline += 1

        # If more than 50% of systems are offline, ship is critical
        if systems_total > 0:
            offline_ratio = systems_offline / systems_total
            if offline_ratio >= 0.75:
                return "critical"
            elif offline_ratio >= 0.40:
                return "damaged"

        # Check PowerManagementSystem - critical if no available power or reactors overheated/depleted
        if hasattr(ship, "systems") and "power_management" in ship.systems:
            power_management = ship.systems["power_management"]
            total_available = None
            reactor_statuses = []

            if hasattr(power_management, "get_state"):
                power_state = power_management.get_state()
                total_available = power_state.get("total_available")
                for reactor_state in power_state.get("reactors", {}).values():
                    reactor_statuses.append(reactor_state.get("status"))
            else:
                reactors = getattr(power_management, "reactors", {}) or {}
                if reactors:
                    total_available = sum(
                        getattr(reactor, "available", getattr(reactor, "capacity", 0.0))
                        for reactor in reactors.values()
                    )
                    reactor_statuses.extend(
                        getattr(reactor, "status", None) for reactor in reactors.values()
                    )

            if total_available is not None and total_available <= 1.0:
                return "critical"

            if reactor_statuses and all(
                status in ("overheated", "depleted") for status in reactor_statuses
            ):
                return "critical"

        # Check power system - if reactor is offline, ship is in trouble
        if hasattr(ship, "systems") and "power" in ship.systems:
            power_sys = ship.systems["power"]
            if hasattr(power_sys, "reactor"):
                reactor = power_sys.reactor
                reactor_state = getattr(reactor, "state", "READY")
                # If reactor is cold and no backup power, ship is offline
                if reactor_state == "COLD":
                    # Check if batteries have power
                    if hasattr(power_sys, "batteries"):
                        total_charge = sum(b.charge for b in power_sys.batteries.values())
                        if total_charge < 100:  # Less than 100 kW remaining
                            return "critical"

        # Check propulsion - if can't move, might be damaged
        if hasattr(ship, "systems") and "propulsion" in ship.systems:
            propulsion = ship.systems["propulsion"]
            if hasattr(propulsion, "is_online") and not propulsion.is_online:
                # Can't maneuver, but not critical if other systems work
                if systems_offline > 0:
                    return "damaged"

        # Default: ship is operational
        return "online"


def filter_fleet_telemetry(telemetry: Dict[str, Any], displays: set, fleet_manager, ship_id: str) -> Dict[str, Any]:
    """
    Filter and augment telemetry with fleet-specific displays.

    Args:
        telemetry: Base telemetry dictionary
        displays: Set of display names the station can see
        fleet_manager: FleetManager instance
        ship_id: Ship ID

    Returns:
        Filtered telemetry with fleet displays added
    """
    filter_obj = FleetTelemetryFilter(fleet_manager)
    result = dict(telemetry)

    # Add fleet displays if requested
    if "fleet_tactical_display" in displays:
        result["fleet_tactical_display"] = filter_obj.get_fleet_tactical_display(ship_id)

    if "fleet_formation_view" in displays:
        result["fleet_formation_view"] = filter_obj.get_fleet_formation_view(ship_id)

    if "fleet_status_board" in displays:
        result["fleet_status_board"] = filter_obj.get_fleet_status_board(ship_id)

    if "threat_board" in displays:
        result["threat_board"] = filter_obj.get_threat_board(ship_id)

    if "engagement_summary" in displays:
        result["engagement_summary"] = filter_obj.get_engagement_summary(ship_id)

    if "shared_contacts" in displays or "tactical_data_link" in displays:
        contacts = fleet_manager.get_shared_contacts(
            fleet_manager.ship_to_fleet.get(ship_id)
        ) if ship_id in fleet_manager.ship_to_fleet else []

        result["shared_contacts"] = [
            {
                "contact_id": c.contact_id,
                "classification": c.classification,
                "threat_level": c.threat_level.name,
                "is_hostile": c.is_hostile,
                "reporting_ship": c.reporting_ship,
                "position": c.position.tolist(),
                "velocity": c.velocity.tolist(),
                "confidence": c.confidence
            }
            for c in contacts
        ]

    return result
