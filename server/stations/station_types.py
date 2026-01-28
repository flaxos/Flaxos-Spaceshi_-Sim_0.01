"""
Station types and definitions for multi-crew ship control.

Defines the different crew stations, their permissions, and command mappings.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Set, Optional, Dict, Any


class StationType(Enum):
    """Ship crew stations - each can be claimed by a different client"""
    CAPTAIN = "captain"      # Command authority, can override any station
    HELM = "helm"            # Navigation, flight control, docking
    TACTICAL = "tactical"    # Weapons, targeting, PDC
    OPS = "ops"              # Sensors, contacts, electronic warfare
    ENGINEERING = "engineering"  # Power, damage control, repairs
    COMMS = "comms"          # Fleet coordination, hailing, jamming
    FLEET_COMMANDER = "fleet_commander"  # Multi-ship coordination, fleet tactics


class PermissionLevel(Enum):
    """Hierarchy for command authority"""
    OBSERVER = 0    # Can view, cannot issue commands
    CREW = 1        # Can issue commands for their station
    OFFICER = 2     # Can issue commands + configure station
    CAPTAIN = 3     # Full authority, can override any station


@dataclass
class StationDefinition:
    """Defines what a station can do"""
    station_type: StationType
    commands: Set[str]           # Commands this station can issue
    displays: Set[str]           # Telemetry views this station receives
    can_override: Set[StationType] = field(default_factory=set)  # Stations this can override
    required_systems: Set[str] = field(default_factory=set)  # Ship systems needed


# Station definitions - this is the source of truth for station capabilities
STATION_DEFINITIONS: Dict[StationType, StationDefinition] = {
    StationType.CAPTAIN: StationDefinition(
        station_type=StationType.CAPTAIN,
        commands={
            # Captain can issue ANY command (populated dynamically)
            "all_commands",
        },
        displays={"all_displays"},
        can_override={StationType.HELM, StationType.TACTICAL, StationType.OPS,
                      StationType.ENGINEERING, StationType.COMMS, StationType.FLEET_COMMANDER},
    ),

    StationType.HELM: StationDefinition(
        station_type=StationType.HELM,
        commands={
            # Implemented helm commands (registered with dispatcher)
            "set_thrust",
            "set_thrust_vector",
            "set_orientation",
            "set_angular_velocity",
            "rotate",
            "point_at",
            "maneuver",
            "rcs_attitude_target",
            "rcs_angular_velocity",
            "rcs_clear",
            "set_course",
            "set_plan",
            "autopilot",
            "helm_override",
            "queue_helm_command",
            "queue_helm_commands",
            "clear_helm_queue",
            "interrupt_helm_queue",
            "helm_queue_status",
            "request_docking",
            "cancel_docking",
        },
        displays={
            "nav_status", "position", "velocity", "orientation",
            "relative_motion", "docking_guidance", "fuel_status",
            "autopilot_status", "waypoints", "course_plot",
            "helm_status", "propulsion_status",
        },
        required_systems={"propulsion", "helm", "navigation"},
    ),

    StationType.TACTICAL: StationDefinition(
        station_type=StationType.TACTICAL,
        commands={
            # Implemented tactical commands (registered with dispatcher)
            "lock_target",
            "unlock_target",
            "get_target_solution",
            "set_target_subsystem",
            "fire_weapon",
        },
        displays={
            "weapons_status", "ammunition", "hardpoints",
            "target_info", "firing_solution", "threat_board",
            "pdc_status", "weapon_arcs", "targeting_status",
        },
        required_systems={"weapons", "targeting"},
    ),

    StationType.OPS: StationDefinition(
        station_type=StationType.OPS,
        commands={
            # Implemented ops commands (registered with dispatcher)
            "ping_sensors",
        },
        displays={
            "contacts", "sensor_status", "contact_details",
            "signature_analysis", "ecm_status", "eccm_status",
            "sensor_coverage", "detection_log",
        },
        required_systems={"sensors"},
    ),

    StationType.ENGINEERING: StationDefinition(
        station_type=StationType.ENGINEERING,
        commands={
            # Implemented engineering commands (registered with dispatcher)
            "override_bio_monitor",
            "set_power_profile",
            "get_power_profiles",
            "set_power_allocation",
        },
        displays={
            "power_grid", "reactor_status", "system_status",
            "damage_report", "repair_queue", "hull_integrity",
            "compartment_status", "fuel_status", "heat_status",
            "power_management_status",
        },
        required_systems={"power", "power_management"},
    ),

    StationType.COMMS: StationDefinition(
        station_type=StationType.COMMS,
        commands=set(),
        displays={
            "comm_log", "channels", "fleet_status",
            "message_queue", "encryption_status",
            "iff_contacts", "jamming_status",
        },
        required_systems={"comms"},
    ),

    StationType.FLEET_COMMANDER: StationDefinition(
        station_type=StationType.FLEET_COMMANDER,
        commands={
            # Implemented fleet commands (registered with dispatcher)
            "fleet_create",
            "fleet_add_ship",
            "fleet_form",
            "fleet_break_formation",
            "fleet_target",
            "fleet_fire",
            "fleet_cease_fire",
            "fleet_maneuver",
            "fleet_status",
            "fleet_tactical",
            "share_contact",
        },
        displays={
            # Fleet overview
            "fleet_tactical_display", "fleet_formation_view",
            "fleet_status_board", "squadron_roster", "ship_positions",
            # Shared data
            "shared_contacts", "tactical_data_link", "threat_board",
            "engagement_summary", "fleet_firepower",
            # Communications
            "fleet_comms", "command_channel", "message_queue",
            # Target coordination
            "fleet_targets", "target_assignments", "firing_coordination",
            # Also sees COMMS and TACTICAL displays
            "comm_log", "weapons_status", "target_info",
        },
        can_override={StationType.TACTICAL, StationType.COMMS},
        required_systems={"comms"},
    ),
}


def get_station_commands(station: StationType) -> Set[str]:
    """
    Get all commands available to a station.

    Args:
        station: The station type

    Returns:
        Set of command names this station can issue
    """
    definition = STATION_DEFINITIONS[station]
    if "all_commands" in definition.commands:
        # Captain gets everything
        all_cmds = set()
        for sdef in STATION_DEFINITIONS.values():
            all_cmds.update(sdef.commands)
        all_cmds.discard("all_commands")
        return all_cmds
    return definition.commands.copy()


def get_station_for_command(command: str) -> Optional[StationType]:
    """
    Find which station owns a command (for routing).
    Returns the first non-Captain station that owns the command.

    Args:
        command: Command name to look up

    Returns:
        StationType that owns this command, or None if not found
    """
    for station_type, definition in STATION_DEFINITIONS.items():
        # Skip captain (we want the primary station)
        if station_type == StationType.CAPTAIN:
            continue
        if command in definition.commands:
            return station_type
    return None


def get_all_stations_for_command(command: str) -> List[StationType]:
    """
    Get all stations that can issue a command (including Captain).

    Args:
        command: Command name to look up

    Returns:
        List of station types that can issue this command
    """
    stations = []
    for station_type, definition in STATION_DEFINITIONS.items():
        if command in definition.commands or "all_commands" in definition.commands:
            stations.append(station_type)
    return stations


def can_station_issue_command(station: StationType, command: str) -> bool:
    """
    Check if a station can issue a specific command.

    Args:
        station: The station type
        command: Command name to check

    Returns:
        True if the station can issue this command
    """
    available_commands = get_station_commands(station)
    return command in available_commands


def get_station_displays(station: StationType) -> Set[str]:
    """
    Get all telemetry displays available to a station.

    Args:
        station: The station type

    Returns:
        Set of display/telemetry view names this station can see
    """
    definition = STATION_DEFINITIONS[station]
    if "all_displays" in definition.displays:
        # Captain gets everything
        all_displays = set()
        for sdef in STATION_DEFINITIONS.values():
            all_displays.update(sdef.displays)
        all_displays.discard("all_displays")
        return all_displays
    return definition.displays.copy()


def get_required_systems(station: StationType) -> Set[str]:
    """
    Get the ship systems required for a station to function.

    Args:
        station: The station type

    Returns:
        Set of system names required
    """
    definition = STATION_DEFINITIONS[station]
    return definition.required_systems.copy()
