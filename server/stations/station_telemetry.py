"""
Station-based telemetry filtering.

Filters ship telemetry data based on station permissions, ensuring each
station only receives the data relevant to their role.
"""

from typing import Dict, Any, Set, Optional
import logging

from .station_types import StationType, get_station_displays, STATION_DEFINITIONS
from .station_manager import StationManager

logger = logging.getLogger(__name__)


class StationTelemetryFilter:
    """
    Filters telemetry data based on station permissions.
    """

    def __init__(self, station_manager: StationManager):
        self.station_manager = station_manager

        # Define which telemetry fields belong to which displays.
        # Keys = display names from STATION_DEFINITIONS.displays.
        # Values = telemetry field names from get_ship_telemetry().
        self.display_field_mapping = {
            # Navigation/Helm displays
            "nav_status": ["position", "velocity", "velocity_magnitude",
                           "orientation", "angular_velocity", "ponr",
                           "trajectory", "flight_computer"],
            "position": ["position", "id", "name"],
            "velocity": ["velocity", "velocity_magnitude", "acceleration",
                         "acceleration_magnitude"],
            "orientation": ["orientation", "angular_velocity"],
            "relative_motion": ["velocity", "position"],
            "fuel_status": ["fuel", "delta_v_remaining"],
            "autopilot_status": ["nav_mode", "autopilot_program",
                                 "autopilot_state", "course"],
            "helm_status": ["orientation", "angular_velocity", "velocity",
                            "helm_queue"],
            "propulsion_status": ["fuel", "systems"],

            # Tactical displays
            "weapons_status": ["weapons"],
            "ammunition": ["weapons", "ammo_mass"],
            "target_info": ["target_id", "target_subsystem", "targeting"],
            "targeting_status": ["target_id", "target_subsystem", "targeting"],
            "firing_solution": ["targeting", "weapons"],
            "threat_board": ["sensors", "targeting"],
            "ecm_status": ["ecm"],
            "eccm_status": ["ecm", "eccm"],
            "damage_assessment": ["sensors", "targeting"],
            "engagement_envelope": ["weapons", "targeting"],

            # Operations displays
            "contacts": ["sensors"],
            "sensor_status": ["sensors", "systems"],
            "contact_details": ["sensors"],
            "ops_status": ["ops"],
            "power_management_status": ["ops", "systems"],
            "crew_fatigue_status": ["crew_fatigue"],
            "crew_station_status": ["crew_fatigue"],

            # Engineering displays
            "power_grid": ["systems"],
            "reactor_status": ["systems"],
            "system_status": ["systems"],
            "engineering_status": ["engineering"],
            "damage_report": ["systems", "subsystem_health"],
            "heat_status": ["subsystem_health", "thermal"],
            "subsystem_health": ["subsystem_health", "cascade_effects"],
            "thermal_status": ["thermal"],
            "hull_integrity": ["hull_integrity", "max_hull_integrity",
                               "hull_percent", "armor_status"],

            # Comms displays
            "comms_status": ["comms"],
            "comm_log": ["comms"],

            # Science displays
            "science_status": ["sensors", "systems"],
            "signature_analysis": ["sensors", "emissions"],
            "sensor_coverage": ["sensors"],
            "detection_log": ["sensors"],

            # Auto-system displays (CPU-ASSIST tier)
            "auto_tactical_status": ["auto_tactical"],
            "auto_ops_status": ["auto_ops"],
            "auto_engineering_status": ["auto_engineering"],
            "auto_science_status": ["auto_science"],
            "auto_comms_status": ["auto_comms"],

            # Emissions / signature displays
            "emissions_status": ["emissions"],

            # Docking displays
            "docking_guidance": ["docking"],

            # Common displays (available to most stations)
            "basic_status": ["id", "name", "class", "faction", "timestamp"],
        }

    def filter_ship_telemetry(
        self,
        ship_telemetry: Dict[str, Any],
        station: StationType
    ) -> Dict[str, Any]:
        """
        Filter ship telemetry based on station permissions.

        Args:
            ship_telemetry: Full ship telemetry data
            station: Station requesting the data

        Returns:
            Filtered telemetry dictionary
        """
        # Captain gets everything
        if station == StationType.CAPTAIN:
            return ship_telemetry.copy()

        # Get allowed displays for this station
        allowed_displays = get_station_displays(station)

        # Build set of allowed fields
        allowed_fields = set()
        for display in allowed_displays:
            fields = self.display_field_mapping.get(display, [])
            allowed_fields.update(fields)

        # Always include basic status fields
        basic_fields = self.display_field_mapping.get("basic_status", [])
        allowed_fields.update(basic_fields)

        # Filter the telemetry
        filtered = {}
        for field in allowed_fields:
            if field in ship_telemetry:
                filtered[field] = ship_telemetry[field]

        return filtered

    def filter_telemetry_for_client(
        self,
        client_id: str,
        full_telemetry: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Filter complete telemetry snapshot for a specific client based on their station.

        Args:
            client_id: Client requesting telemetry
            full_telemetry: Full telemetry snapshot from get_telemetry_snapshot()

        Returns:
            Filtered telemetry dictionary
        """
        session = self.station_manager.get_session(client_id)

        if not session:
            logger.warning(f"Telemetry requested by unknown client: {client_id}")
            return {
                "error": "Client not registered",
                "timestamp": full_telemetry.get("timestamp", 0)
            }

        if not session.station:
            # Observer mode - minimal data
            return {
                "tick": full_telemetry.get("tick", 0),
                "sim_time": full_telemetry.get("sim_time", 0),
                "timestamp": full_telemetry.get("timestamp", 0),
                "message": "No station claimed - claim a station to view telemetry"
            }

        # Filter ship telemetry
        ships = full_telemetry.get("ships", {})
        filtered_ships = {}

        for ship_id, ship_data in ships.items():
            # Only show data for client's assigned ship
            if session.ship_id and ship_id == session.ship_id:
                filtered_ships[ship_id] = self.filter_ship_telemetry(
                    ship_data,
                    session.station
                )

        # Build filtered response
        filtered = {
            "tick": full_telemetry.get("tick", 0),
            "sim_time": full_telemetry.get("sim_time", 0),
            "dt": full_telemetry.get("dt", 0.1),
            "ships": filtered_ships,
            "timestamp": full_telemetry.get("timestamp", 0),
        }

        # Add events if this station should see them
        if self._can_see_events(session.station):
            filtered["events"] = full_telemetry.get("events", [])

        # Add projectiles and torpedoes for tactical station
        if session.station == StationType.TACTICAL or session.station == StationType.CAPTAIN:
            filtered["projectiles"] = full_telemetry.get("projectiles", [])
            filtered["torpedoes"] = full_telemetry.get("torpedoes", [])

        return filtered

    def filter_ship_state_for_client(
        self,
        client_id: str,
        ship_id: str,
        ship_telemetry: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Filter ship state for a specific client.

        Args:
            client_id: Client requesting the state
            ship_id: Ship being queried
            ship_telemetry: Full ship telemetry

        Returns:
            Filtered ship telemetry
        """
        session = self.station_manager.get_session(client_id)

        if not session:
            return {"error": "Client not registered"}

        # Check if client is assigned to this ship
        if session.ship_id != ship_id:
            return {
                "error": "Not assigned to this ship",
                "ship_id": ship_id
            }

        if not session.station:
            return {
                "error": "No station claimed",
                "message": "Claim a station to view telemetry"
            }

        return self.filter_ship_telemetry(ship_telemetry, session.station)

    def _can_see_events(self, station: StationType) -> bool:
        """
        Determine if a station should receive event log.

        Args:
            station: Station type

        Returns:
            True if station can see events
        """
        # Captain, Tactical (combat log), Ops (damage control),
        # Science (sensor events), Comms (hail/response events)
        return station in [
            StationType.CAPTAIN, StationType.TACTICAL, StationType.OPS,
            StationType.SCIENCE, StationType.COMMS,
        ]

    def get_telemetry_summary_for_client(self, client_id: str) -> Dict[str, Any]:
        """
        Get a summary of what telemetry data is available to a client.

        Args:
            client_id: Client to check

        Returns:
            Dictionary describing available telemetry
        """
        session = self.station_manager.get_session(client_id)

        if not session:
            return {"error": "Client not registered"}

        if not session.station:
            return {
                "station": None,
                "displays": [],
                "message": "No station claimed"
            }

        allowed_displays = get_station_displays(session.station)

        return {
            "station": session.station.value,
            "ship_id": session.ship_id,
            "displays": list(allowed_displays),
            "permission_level": session.permission_level.name,
        }
