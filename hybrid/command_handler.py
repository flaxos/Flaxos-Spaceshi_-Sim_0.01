# hybrid/command_handler.py
"""
Command handler for ship commands in hybrid architecture.
Provides functions for routing commands to appropriate systems.
"""

import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)

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

def route_command(ship, command_data):
    """
    Route a command to the appropriate ship or system
    
    Args:
        ship (Ship): The ship to execute the command on
        command_data (dict): The command data
        
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
        response = execute_command(ship, cmd, command_data)
        
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

def execute_command(ship, command_type, command_data):
    """
    Execute a command on a ship
    
    Args:
        ship (Ship): The ship to execute the command on
        command_type (str): The type of command to execute
        command_data (dict): The command data
        
    Returns:
        dict: Command response
    """
    # Special handling for system-specific commands
    system_commands = {
        "set_thrust": ("propulsion", "set_thrust"),
        "set_orientation": ("helm", "set_orientation"),
        "set_angular_velocity": ("helm", "set_angular_velocity"),
        "rotate": ("helm", "rotate"),
        "set_course": ("navigation", "set_course"),
        "autopilot": ("navigation", "set_autopilot"),
        "helm_override": ("helm", "set_mode"),
        "ping_sensors": ("sensors", "ping"),
        "override_bio_monitor": ("bio_monitor", "override")
    }
    
    # Check if this is a system-specific command
    if command_type in system_commands:
        system_name, action = system_commands[command_type]
        
        # Make sure the system exists
        if system_name not in ship.systems:
            return {"error": f"System {system_name} not found on ship {ship.id}"}
            
        # Execute the command on the system
        return ship.systems[system_name].command(action, command_data)
        
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
