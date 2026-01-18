# hybrid/commands/dispatch.py
"""Central command dispatch table with validation."""

import logging
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass
from hybrid.commands.validators import ArgSpec
from hybrid.utils.errors import error_dict, success_dict

logger = logging.getLogger(__name__)

@dataclass
class CommandSpec:
    """Specification for a command."""
    handler: Callable
    args: List[ArgSpec]
    help_text: str
    system: Optional[str] = None  # Which system handles this command (None = ship level)

class CommandDispatcher:
    """Central command dispatcher with validation and routing."""

    def __init__(self):
        """Initialize the command dispatcher."""
        self.commands: Dict[str, CommandSpec] = {}

    def register(self, command_name: str, spec: CommandSpec):
        """Register a command with its specification.

        Args:
            command_name (str): Name of the command
            spec (CommandSpec): Command specification
        """
        self.commands[command_name] = spec
        logger.debug(f"Registered command: {command_name}")

    def validate_args(self, command_name: str, params: dict) -> tuple[bool, dict, Optional[str]]:
        """Validate command arguments against specification.

        Args:
            command_name (str): Command name
            params (dict): Parameters to validate

        Returns:
            tuple: (is_valid, validated_params, error_message)
        """
        if command_name not in self.commands:
            return False, {}, f"Unknown command: {command_name}"

        spec = self.commands[command_name]
        validated = {}
        errors = []

        for arg_spec in spec.args:
            value = params.get(arg_spec.name)

            is_valid, converted_value, error_msg = arg_spec.validate(value)

            if not is_valid:
                errors.append(error_msg)
            else:
                validated[arg_spec.name] = converted_value

        if errors:
            return False, {}, "; ".join(errors)

        return True, validated, None

    def dispatch(self, command_name: str, ship, params: dict = None) -> dict:
        """Dispatch a command with validation.

        Args:
            command_name (str): Command to execute
            ship: Ship object to execute command on
            params (dict): Command parameters

        Returns:
            dict: Command result or error
        """
        if params is None:
            params = {}

        # Check if command exists
        if command_name not in self.commands:
            available = ", ".join(sorted(self.commands.keys()))
            return error_dict(
                "UNKNOWN_COMMAND",
                f"Unknown command: '{command_name}'",
                available_commands=available
            )

        spec = self.commands[command_name]

        # Validate arguments
        is_valid, validated_params, error_msg = self.validate_args(command_name, params)

        if not is_valid:
            return error_dict("VALIDATION_ERROR", error_msg)

        # Route to appropriate handler
        try:
            if spec.system:
                # System-level command
                if spec.system not in ship.systems:
                    return error_dict(
                        "SYSTEM_NOT_FOUND",
                        f"System '{spec.system}' not available on ship {ship.id}"
                    )

                system = ship.systems[spec.system]
                result = spec.handler(system, ship, validated_params)
            else:
                # Ship-level command
                result = spec.handler(ship, validated_params)

            # Ensure result is a dict
            if not isinstance(result, dict):
                result = {"result": result}

            # Add ok flag if not present
            if "ok" not in result:
                result["ok"] = "error" not in result

            return result

        except Exception as e:
            logger.error(f"Error executing command {command_name}: {e}", exc_info=True)
            return error_dict("EXECUTION_ERROR", f"Command failed: {e}")

    def get_help(self, command_name: str = None) -> str:
        """Get help text for a command or all commands.

        Args:
            command_name (str, optional): Specific command to get help for

        Returns:
            str: Help text
        """
        if command_name:
            if command_name not in self.commands:
                return f"Unknown command: {command_name}"

            spec = self.commands[command_name]
            help_text = [f"{command_name}: {spec.help_text}"]

            if spec.args:
                help_text.append("Arguments:")
                for arg in spec.args:
                    required_str = "required" if arg.required else "optional"
                    range_str = ""
                    if arg.min_val is not None or arg.max_val is not None:
                        range_str = f" ({arg.min_val} to {arg.max_val})"
                    elif arg.choices:
                        range_str = f" (choices: {', '.join(arg.choices)})"

                    help_text.append(
                        f"  {arg.name} ({arg.arg_type}, {required_str}){range_str}: {arg.description}"
                    )

            return "\n".join(help_text)

        else:
            # List all commands
            help_text = ["Available commands:"]
            for cmd_name in sorted(self.commands.keys()):
                spec = self.commands[cmd_name]
                help_text.append(f"  {cmd_name}: {spec.help_text}")

            help_text.append("\nUse 'help <command>' for detailed information")
            return "\n".join(help_text)

def create_default_dispatcher() -> CommandDispatcher:
    """Create a dispatcher with all default commands registered.

    Returns:
        CommandDispatcher: Configured dispatcher
    """
    dispatcher = CommandDispatcher()

    # Import command handlers
    from hybrid.commands import ship_commands
    from hybrid.commands import navigation_commands
    from hybrid.commands import sensor_commands
    from hybrid.commands import weapon_commands

    # Register all commands from modules
    ship_commands.register_commands(dispatcher)
    navigation_commands.register_commands(dispatcher)
    sensor_commands.register_commands(dispatcher)
    weapon_commands.register_commands(dispatcher)

    return dispatcher
