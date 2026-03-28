# hybrid/command_handler.py
"""
Command handler for ship commands in hybrid architecture.
Provides functions for routing commands to appropriate systems.
"""

import logging
import json
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# System command mappings (system_name, action)
# This dict maps command names to (system, action) tuples for routing
system_commands = {
    # Primary gameplay API (scalar throttle)
    "set_thrust": ("propulsion", "set_throttle"),
    # Debug-only API (arbitrary vector thrust in world-frame)
    "set_thrust_vector": ("propulsion", "set_thrust_vector"),
    # Attitude control - sets target orientation (RCS-driven rotation over time)
    "set_orientation": ("helm", "set_orientation_target"),
    "set_angular_velocity": ("helm", "set_angular_velocity"),
    "rotate": ("helm", "rotate"),
    "point_at": ("helm", "point_at"),
    "maneuver": ("helm", "maneuver"),
    # RCS direct commands (for advanced control)
    "rcs_attitude_target": ("rcs", "set_attitude_target"),
    "rcs_angular_velocity": ("rcs", "set_angular_velocity"),
    "rcs_clear": ("rcs", "clear_target"),
    # Navigation and autopilot
    "set_course": ("navigation", "set_course"),
    "autopilot": ("navigation", "set_autopilot"),
    "set_plan": ("navigation", "set_plan"),
    "get_nav_solutions": ("navigation", "get_nav_solutions"),
    # Helm navigation commands
    "execute_burn": ("helm", "execute_burn"),
    "plot_intercept": ("helm", "plot_intercept"),
    "flip_and_burn": ("helm", "flip_and_burn"),
    "emergency_burn": ("helm", "emergency_burn"),
    "emergency_stop": ("propulsion", "emergency_stop"),
    # Helm control authority
    "helm_override": ("helm", "set_mode"),
    "take_manual_control": ("helm", "take_manual_control"),
    "release_to_autopilot": ("helm", "release_to_autopilot"),
    # Helm command queue
    "queue_helm_command": ("helm", "queue_command"),
    "queue_helm_commands": ("helm", "queue_commands"),
    "clear_helm_queue": ("helm", "clear_queue"),
    "interrupt_helm_queue": ("helm", "interrupt_queue"),
    "helm_queue_status": ("helm", "queue_status"),
    "ping_sensors": ("sensors", "ping"),
    "set_power_profile": ("power_management", "set_power_profile"),
    "get_power_profiles": ("power_management", "get_power_profiles"),
    "set_power_allocation": ("power_management", "set_power_allocation"),
    "get_draw_profile": ("power_management", "get_draw_profile"),
    "request_docking": ("docking", "request_docking"),
    "cancel_docking": ("docking", "cancel_docking"),
    "undock": ("docking", "undock"),
    # Targeting commands (Sprint C)
    "lock_target": ("targeting", "lock"),
    "unlock_target": ("targeting", "unlock"),
    "get_target_solution": ("targeting", "get_solution"),
    "get_weapon_solution": ("targeting", "get_weapon_solution"),
    "best_weapon": ("targeting", "best_weapon"),
    "set_target_subsystem": ("targeting", "set_target_subsystem"),
    # Legacy weapon system
    "fire": ("weapons", "fire"),
    "fire_weapon": ("weapons", "fire"),
    # Combat system commands (Sprint C - truth weapons)
    "fire_railgun": ("combat", "fire"),
    "fire_pdc": ("combat", "fire"),
    "fire_combat": ("combat", "fire"),
    "fire_all": ("combat", "fire_all"),
    "ready_weapons": ("combat", "ready_weapons"),
    "combat_status": ("combat", "status"),
    "weapon_status": ("combat", "weapon_status"),
    "resupply": ("combat", "resupply"),
    # Thermal management commands
    "activate_heat_sink": ("thermal", "activate_heat_sink"),
    "deactivate_heat_sink": ("thermal", "deactivate_heat_sink"),
    "cold_drift": ("thermal", "cold_drift"),
    "exit_cold_drift": ("thermal", "exit_cold_drift"),
    # Tactical station commands
    "designate_target": ("targeting", "lock"),
    "request_solution": ("targeting", "get_solution"),
    "set_pdc_mode": ("combat", "set_pdc_mode"),
    "launch_torpedo": ("combat", "launch_torpedo"),
    "torpedo_status": ("combat", "torpedo_status"),
    "assess_damage": ("targeting", "assess_damage"),
    # ECCM commands (routed through sensors — ECCM is a sensor capability)
    "eccm_frequency_hop": ("sensors", "eccm_frequency_hop"),
    "eccm_burn_through": ("sensors", "eccm_burn_through"),
    "eccm_off": ("sensors", "eccm_off"),
    "eccm_multispectral": ("sensors", "eccm_multispectral"),
    "eccm_home_on_jam": ("sensors", "eccm_home_on_jam"),
    "analyze_jamming": ("sensors", "analyze_jamming"),
    "eccm_status": ("sensors", "eccm_status"),
    # Multi-target tracking commands
    "cycle_target": ("targeting", "cycle_target"),
    "add_track": ("targeting", "add_track"),
    "remove_track": ("targeting", "remove_track"),
    "assign_pdc_target": ("targeting", "assign_pdc_target"),
    "split_fire": ("targeting", "split_fire"),
    "clear_assignments": ("targeting", "clear_assignments"),
    "track_list": ("targeting", "track_list"),
    # ECM commands
    "activate_jammer": ("ecm", "activate_jammer"),
    "deactivate_jammer": ("ecm", "deactivate_jammer"),
    "deploy_chaff": ("ecm", "deploy_chaff"),
    "deploy_flare": ("ecm", "deploy_flare"),
    "set_emcon": ("ecm", "set_emcon"),
    "ecm_status": ("ecm", "ecm_status"),
    # Ops station commands
    "allocate_power": ("ops", "allocate_power"),
    "dispatch_repair": ("ops", "dispatch_repair"),
    "cancel_repair": ("ops", "cancel_repair"),
    "repair_status": ("ops", "repair_status"),
    "set_repair_priority": ("ops", "set_repair_priority"),
    "set_system_priority": ("ops", "set_system_priority"),
    "report_status": ("ops", "report_status"),
    "emergency_shutdown": ("ops", "emergency_shutdown"),
    "restart_system": ("ops", "restart_system"),
    # Engineering station commands
    "set_reactor_output": ("engineering", "set_reactor_output"),
    "throttle_drive": ("engineering", "throttle_drive"),
    "manage_radiators": ("engineering", "manage_radiators"),
    "monitor_fuel": ("engineering", "monitor_fuel"),
    "emergency_vent": ("engineering", "emergency_vent"),
    # Comms station commands
    "set_transponder": ("comms", "set_transponder"),
    "hail_contact": ("comms", "hail_contact"),
    "broadcast_message": ("comms", "broadcast_message"),
    "set_distress": ("comms", "set_distress"),
    "comms_status": ("comms", "comms_status"),
    # Mission branching comms commands
    "comms_respond": ("comms", "comms_respond"),
    "get_comms_choices": ("comms", "get_comms_choices"),
    "get_branch_status": ("comms", "get_branch_status"),
    # Crew fatigue commands
    "crew_rest": ("crew_fatigue", "crew_rest"),
    "cancel_rest": ("crew_fatigue", "cancel_rest"),
    "crew_fatigue_status": ("crew_fatigue", "crew_status"),
    # Crew-station binding commands
    "assign_crew": ("crew_binding", "assign_crew"),
    "transfer_crew": ("crew_binding", "transfer_crew"),
    "unassign_crew": ("crew_binding", "unassign_crew"),
    "crew_station_status": ("crew_binding", "crew_station_status"),
    # Science station commands
    "analyze_contact": ("science", "analyze_contact"),
    "spectral_analysis": ("science", "spectral_analysis"),
    "estimate_mass": ("science", "estimate_mass"),
    "assess_threat": ("science", "assess_threat"),
    "science_status": ("science", "science_status"),
    # Flight computer
    "flight_computer": ("flight_computer", "flight_computer"),
    # Fleet coordination commands
    "fleet_create": ("fleet_coord", "fleet_create"),
    "fleet_add_ship": ("fleet_coord", "fleet_add_ship"),
    "fleet_form": ("fleet_coord", "fleet_form"),
    "fleet_break_formation": ("fleet_coord", "fleet_break_formation"),
    "fleet_target": ("fleet_coord", "fleet_target"),
    "fleet_fire": ("fleet_coord", "fleet_fire"),
    "fleet_cease_fire": ("fleet_coord", "fleet_cease_fire"),
    "fleet_maneuver": ("fleet_coord", "fleet_maneuver"),
    "fleet_status": ("fleet_coord", "fleet_status"),
    "fleet_tactical": ("fleet_coord", "fleet_tactical"),
    "share_contact": ("fleet_coord", "share_contact"),
}

def parse_command(data):
    """
    Parse a command string or dictionary
    
    Args:
        data (str or dict): Command data
        
    Returns:
        dict: Parsed command
    """
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON command: {e}")
            return {"error": "Invalid JSON command"}
    return data

def route_command(ship, command_data, all_ships=None):
    """
    Route a command to the appropriate ship or system

    Args:
        ship (Ship): The ship to execute the command on
        command_data (dict): The command data
        all_ships (dict, optional): Dictionary of all ships (for sensor commands)

    Returns:
        dict: Command response
    """
    try:
        # Extract command details
        cmd = command_data.get("command")
        ship_id = command_data.get("ship")

        # Validate command
        if not cmd:
            return {"error": "Missing command parameter"}

        # Validate ship when provided; default to the target ship if omitted
        if ship_id:
            if ship_id != ship.id:
                return {"error": f"Command sent to wrong ship. Expected {ship.id}, got {ship_id}"}
        else:
            command_data["ship"] = ship.id
            ship_id = ship.id

        # Execute command
        response = execute_command(ship, cmd, command_data, all_ships)
        
        # Add timestamp to response
        if isinstance(response, dict):
            if "timestamp" not in response:
                response["timestamp"] = datetime.now(timezone.utc).isoformat()
        else:
            # Convert non-dict responses to dict
            response = {
                "result": response,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        return response
        
    except Exception as e:
        logger.error(f"Error routing command: {e}")
        return {
            "error": f"Command processing error: {str(e)}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

def execute_command(ship, command_type, command_data, all_ships=None):
    """
    Execute a command on a ship

    Args:
        ship (Ship): The ship to execute the command on
        command_type (str): The type of command to execute
        command_data (dict): The command data
        all_ships (dict, optional): Dictionary of all ships

    Returns:
        dict: Command response
    """
    # Check if this is a system-specific command (uses module-level system_commands)
    if command_type in system_commands:
        system_name, action = system_commands[command_type]

        # Make sure the system exists
        if system_name not in ship.systems:
            return {"error": f"System {system_name} not found on ship {ship.id}"}

        # Inject ship object, event bus, and all_ships into command_data for systems that need it
        command_data_with_ship = command_data.copy()
        command_data_with_ship["ship"] = ship
        command_data_with_ship["_ship"] = ship  # Some systems use _ship
        command_data_with_ship["event_bus"] = ship.event_bus
        if all_ships is not None:
            # D6: Keep all_ships as dict for target resolution in weapon system
            command_data_with_ship["all_ships"] = all_ships

        # Execute the command on the system
        try:
            result = ship.systems[system_name].command(action, command_data_with_ship)
            logger.debug(f"Command {command_type} -> {system_name}.{action} returned: {result}")
            return result
        except Exception as e:
            logger.error(f"Error executing {command_type} -> {system_name}.{action}: {e}", exc_info=True)
            return {"error": f"Command execution failed: {e}"}
        
    # Handle direct ship commands
    return ship.command(command_type, command_data)

def format_response(response):
    """
    Format a response for sending to client
    
    Args:
        response (dict): Command response
        
    Returns:
        str: Formatted response
    """
    if isinstance(response, dict) and "error" in response:
        return json.dumps(response)
        
    if isinstance(response, (dict, list)):
        return json.dumps(response)
        
    return str(response)

def handle_command_request(request, ship):
    """
    Handle a command request from a client
    
    Args:
        request (str): Raw command request
        ship (Ship): The ship to execute the command on
        
    Returns:
        str: Formatted response
    """
    try:
        # Parse the command
        command = parse_command(request)
        
        # Execute the command
        response = route_command(ship, command)
        
        # Format the response
        return format_response(response)
        
    except Exception as e:
        logger.error(f"Error handling command request: {e}")
        error_response = {
            "error": f"Command processing error: {str(e)}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        return format_response(error_response)
