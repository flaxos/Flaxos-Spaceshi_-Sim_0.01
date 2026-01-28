# hybrid/command_handler.py
"""
Command handler for ship commands in hybrid architecture.
Provides functions for routing commands to appropriate systems.
"""

import logging
import json
from datetime import datetime

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
    "override_bio_monitor": ("bio_monitor", "override"),
    "set_power_allocation": ("power_management", "set_power_allocation"),
    "request_docking": ("docking", "request_docking"),
    "cancel_docking": ("docking", "cancel_docking"),
    # Targeting commands (Sprint C)
    "lock_target": ("targeting", "lock"),
    "unlock_target": ("targeting", "unlock"),
    "get_target_solution": ("targeting", "get_solution"),
    "get_weapon_solution": ("targeting", "get_weapon_solution"),
    "best_weapon": ("targeting", "best_weapon"),
    "set_target_subsystem": ("targeting", "set_target_subsystem"),
    # Legacy weapon system
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

        # Validate ship
        if ship_id != ship.id:
            return {"error": f"Command sent to wrong ship. Expected {ship.id}, got {ship_id}"}

        # Execute command
        response = execute_command(ship, cmd, command_data, all_ships)
        
        # Add timestamp to response
        if isinstance(response, dict):
            if "timestamp" not in response:
                response["timestamp"] = datetime.utcnow().isoformat()
        else:
            # Convert non-dict responses to dict
            response = {
                "result": response,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        return response
        
    except Exception as e:
        logger.error(f"Error routing command: {e}")
        return {
            "error": f"Command processing error: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
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
            "timestamp": datetime.utcnow().isoformat()
        }
        return format_response(error_response)
# hybrid/command_handler.py
"""
Command handler for the hybrid architecture.
This module provides a central registry for command handlers.
"""

class CommandHandler:
    """Registry for command handlers"""
    
    def __init__(self):
        """Initialize the command handler registry"""
        self.handlers = {}
    
    def register_handler(self, command_type, handler_function):
        """
        Register a handler for a command type
        
        Args:
            command_type (str): The command type to handle
            handler_function (callable): Function to call with command parameters
            
        Returns:
            bool: True if registered, False if already exists
        """
        if command_type in self.handlers:
            return False
            
        self.handlers[command_type] = handler_function
        return True
    
    def handle_command(self, command_type, params=None):
        """
        Handle a command by dispatching to the appropriate handler
        
        Args:
            command_type (str): The command type to handle
            params (dict): Parameters for the command
            
        Returns:
            dict: Response from the handler, or error if not found
        """
        if params is None:
            params = {}
            
        if command_type in self.handlers:
            try:
                return self.handlers[command_type](params)
            except Exception as e:
                return {"error": f"Error handling command {command_type}: {e}"}
        else:
            return {"error": f"No handler for command type: {command_type}"}
