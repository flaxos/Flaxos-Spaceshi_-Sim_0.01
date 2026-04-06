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
    OPS = "ops"              # Power management, damage control, system priorities
    ENGINEERING = "engineering"  # Reactor, drive, repair crews
    COMMS = "comms"          # Communications, IFF, transponder
    SCIENCE = "science"      # Sensor analysis, contact classification
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
                      StationType.ENGINEERING, StationType.COMMS, StationType.SCIENCE,
                      StationType.FLEET_COMMANDER},
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
            "rcs_fire_thruster",
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
            "undock",
            "get_nav_solutions",
            "execute_burn",
            "plot_intercept",
            "flip_and_burn",
            "emergency_burn",
            "emergency_stop",
            # Helm control authority
            "take_manual_control",
            "release_to_autopilot",
            # Flight computer
            "flight_computer",
            # Stealth maneuver
            "cold_drift",
            "exit_cold_drift",
            # Inter-station comms
            "station_message",
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
            # Targeting pipeline commands
            "lock_target",
            "unlock_target",
            "get_target_solution",
            "get_weapon_solution",
            "best_weapon",
            "set_target_subsystem",
            # Tactical station commands (designate, solution, fire, PDC, assess)
            "designate_target",
            "request_solution",
            "set_pdc_mode",
            "set_pdc_priority",
            "launch_torpedo",
            "torpedo_status",
            "launch_missile",
            "launch_salvo",
            "missile_status",
            "program_munition",
            "assess_damage",
            # Multi-target tracking commands
            "cycle_target",
            "add_track",
            "remove_track",
            "assign_pdc_target",
            "split_fire",
            "clear_assignments",
            "track_list",
            # Resupply
            "resupply",
            # Weapon fire commands
            "fire",
            "fire_weapon",
            "fire_railgun",
            "fire_pdc",
            "fire_combat",
            "fire_all",
            "fire_unguided",
            # Weapon status commands
            "ready_weapons",
            "combat_status",
            "weapon_status",
            # Sensor commands (TACTICAL needs contacts for targeting)
            "ping_sensors",
            # ECM commands (electronic warfare is a tactical function)
            "activate_jammer",
            "deactivate_jammer",
            "deploy_chaff",
            "deploy_flare",
            "set_emcon",
            "ecm_status",
            # ECCM commands (counter-countermeasures)
            "eccm_frequency_hop",
            "eccm_burn_through",
            "eccm_off",
            "eccm_multispectral",
            "eccm_home_on_jam",
            "analyze_jamming",
            "eccm_status",
            # Auto-tactical commands (CPU-ASSIST tier)
            "enable_auto_tactical",
            "disable_auto_tactical",
            "set_engagement_rules",
            "approve_tactical",
            "deny_tactical",
            # Inter-station comms
            "station_message",
        },
        displays={
            "weapons_status", "ammunition", "hardpoints",
            "target_info", "firing_solution", "threat_board",
            "pdc_status", "weapon_arcs", "targeting_status",
            "damage_assessment", "engagement_envelope",
            "ecm_status", "eccm_status", "emissions_status",
            "auto_tactical_status",
        },
        required_systems={"weapons", "targeting"},
    ),

    StationType.OPS: StationDefinition(
        station_type=StationType.OPS,
        commands={
            # Power management and damage control
            "set_power_profile",
            "get_power_profiles",
            "set_power_allocation",
            "get_draw_profile",
            # Thermal management
            "activate_heat_sink",
            "deactivate_heat_sink",
            "cold_drift",
            "exit_cold_drift",
            # Ops station commands
            "allocate_power",
            "dispatch_repair",
            "cancel_repair",
            "repair_status",
            "set_repair_priority",
            "set_system_priority",
            "report_status",
            "emergency_shutdown",
            "restart_system",
            # ECM (OPS can also manage countermeasures)
            "set_emcon",
            "ecm_status",
            # Transponder (OPS can manage identity spoofing)
            "set_transponder",
            # Crew fatigue management
            "crew_rest",
            "cancel_rest",
            "crew_fatigue_status",
            # Crew-station assignment
            "assign_crew",
            "transfer_crew",
            "unassign_crew",
            "crew_station_status",
            # Auto-ops commands (CPU-ASSIST tier)
            "enable_auto_ops",
            "disable_auto_ops",
            "set_ops_mode",
            "approve_ops",
            "deny_ops",
            # Boarding commands (Phase 3B)
            "begin_boarding",
            "cancel_boarding",
            "boarding_status",
            # Drone bay commands (Phase 3A)
            "launch_drone",
            "recall_drone",
            "set_drone_behavior",
            "drone_status",
            # Inter-station comms
            "station_message",
        },
        displays={
            "power_grid", "reactor_status", "system_status",
            "damage_report", "repair_queue", "hull_integrity",
            "compartment_status", "heat_status", "thermal_status",
            "power_management_status", "ops_status", "ecm_status",
            "crew_fatigue_status", "crew_station_status",
            "subsystem_health", "boarding_status",
            "auto_ops_status",
            "drone_bay_status",
        },
        required_systems={"power", "power_management"},
    ),

    StationType.ENGINEERING: StationDefinition(
        station_type=StationType.ENGINEERING,
        commands={
            # Reactor, drive, repair crews
            "set_power_profile",
            "get_power_profiles",
            "get_draw_profile",
            # Thermal management
            "activate_heat_sink",
            "deactivate_heat_sink",
            # Shared ops commands (engineering can also dispatch repairs)
            "dispatch_repair",
            "cancel_repair",
            "repair_status",
            "set_repair_priority",
            "report_status",
            # Thermal stealth
            "cold_drift",
            "exit_cold_drift",
            # Engineering station commands
            "set_reactor_output",
            "throttle_drive",
            "manage_radiators",
            "monitor_fuel",
            "emergency_vent",
            # Crew fatigue (view only + rest authority)
            "crew_rest",
            "cancel_rest",
            "crew_fatigue_status",
            # Auto-engineering commands (CPU-ASSIST tier)
            "enable_auto_engineering",
            "disable_auto_engineering",
            "set_engineering_mode",
            "approve_engineering",
            "deny_engineering",
            # Inter-station comms
            "station_message",
        },
        displays={
            "reactor_status", "system_status", "fuel_status",
            "propulsion_status", "heat_status", "thermal_status",
            "damage_report", "hull_integrity", "engineering_status",
            "crew_fatigue_status", "subsystem_health",
            "auto_engineering_status",
        },
        required_systems={"power", "propulsion", "engineering"},
    ),

    StationType.COMMS: StationDefinition(
        station_type=StationType.COMMS,
        commands={
            # IFF transponder control
            "set_transponder",
            # Radio communications
            "hail_contact",
            "broadcast_message",
            # Distress beacon
            "set_distress",
            # Status readout
            "comms_status",
            # EMCON control (comms officer can also manage emissions)
            "set_emcon",
            "ecm_status",
            # Mission branching comms choices
            "comms_respond",
            "get_comms_choices",
            "get_branch_status",
            # Auto-comms commands (CPU-ASSIST tier)
            "enable_auto_comms",
            "disable_auto_comms",
            "set_comms_policy",
            "approve_comms",
            "deny_comms",
            # Inter-station comms
            "station_message",
        },
        displays={
            "comm_log", "channels", "fleet_status",
            "message_queue", "encryption_status",
            "iff_contacts", "jamming_status",
            "comms_status",
            "auto_comms_status",
        },
        required_systems={"comms"},
    ),

    StationType.SCIENCE: StationDefinition(
        station_type=StationType.SCIENCE,
        commands={
            # Sensor analysis and contact classification
            "ping_sensors",
            # Science analysis commands
            "analyze_contact",
            "spectral_analysis",
            "estimate_mass",
            "assess_threat",
            "science_status",
            # Active science scans (range-limited)
            "science_spectral_analysis",
            "science_composition_scan",
            # ECCM analysis (science officer can analyze jamming)
            "analyze_jamming",
            "eccm_status",
            # Auto-science commands (CPU-ASSIST tier)
            "enable_auto_science",
            "disable_auto_science",
            "set_science_mode",
            "approve_science",
            "deny_science",
            # Inter-station comms
            "station_message",
        },
        displays={
            "contacts", "sensor_status", "contact_details",
            "signature_analysis", "sensor_coverage",
            "detection_log", "science_status",
            "auto_science_status",
        },
        required_systems={"sensors"},
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
            # Auto-fleet commands (CPU-ASSIST tier)
            "enable_auto_fleet",
            "disable_auto_fleet",
            "set_fleet_auto_mode",
            "approve_fleet",
            "deny_fleet",
            "auto_fleet_status",
            # Inter-station comms
            "station_message",
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
            # Auto-fleet status
            "auto_fleet_status",
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
