"""
Station-aware command dispatcher with permission enforcement.

Wraps existing command handlers with station permission checks to ensure
commands are only executed if the client has the appropriate station claim.
"""

from typing import Dict, Any, Callable, Optional, Tuple
from dataclasses import dataclass
import logging

from .station_manager import StationManager
from .station_types import StationType, get_station_for_command

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of a command execution"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "ok": self.success,
            "message": self.message,
        }
        if self.data is not None:
            result["response"] = self.data
        return result


# Type for command handlers
# Signature: (client_id, ship_id, command_data) -> CommandResult
CommandHandler = Callable[[str, str, Dict[str, Any]], CommandResult]


class StationAwareDispatcher:
    """
    Command dispatcher that enforces station permissions.
    Wraps existing command handlers with permission checks.
    """

    def __init__(self, station_manager: StationManager):
        self.station_manager = station_manager
        self.handlers: Dict[str, CommandHandler] = {}
        self.command_metadata: Dict[str, Dict[str, Any]] = {}

    def register_command(
        self,
        command: str,
        handler: CommandHandler,
        station: Optional[StationType] = None,
        requires_target: bool = False,
        requires_power: Optional[str] = None,
        requires_ship: bool = True,
        bypass_permission_check: bool = False,
    ):
        """
        Register a command handler with metadata.

        Args:
            command: Command name
            handler: Function to handle the command
            station: Station that owns this command (auto-detected if None)
            requires_target: Whether command requires a target
            requires_power: System that must have power
            bypass_permission_check: If True, skip station permission check
        """
        self.handlers[command] = handler
        self.command_metadata[command] = {
            "station": station or get_station_for_command(command),
            "requires_target": requires_target,
            "requires_power": requires_power,
            "requires_ship": requires_ship,
            "bypass_permission_check": bypass_permission_check,
        }
        logger.debug(f"Registered command: {command} -> {station}")

    def dispatch(
        self,
        client_id: str,
        ship_id: str,
        command: str,
        args: Dict[str, Any],
    ) -> CommandResult:
        """
        Dispatch a command with station permission checking.

        Args:
            client_id: Client issuing the command
            ship_id: Target ship
            command: Command name
            args: Command arguments

        Returns:
            CommandResult with success/failure and message
        """
        # 1. Check if command exists
        if command not in self.handlers:
            logger.warning(f"Unknown command from {client_id}: {command}")
            return CommandResult(
                success=False,
                message=f"Unknown command: {command}",
            )

        metadata = self.command_metadata[command]

        # 2. Check station permission (unless bypassed)
        if not metadata.get("bypass_permission_check", False):
            can_issue, reason = self.station_manager.can_issue_command(
                client_id, ship_id, command
            )

            if not can_issue:
                logger.info(f"Permission denied for {client_id}: {command} on {ship_id} - {reason}")
                return CommandResult(
                    success=False,
                    message=f"Permission denied: {reason}",
                )

        # 3. Update client activity
        self.station_manager.update_activity(client_id)

        # 4. Execute the command
        try:
            handler = self.handlers[command]
            result = handler(client_id, ship_id, args)
            logger.debug(f"Command executed: {command} by {client_id} on {ship_id} - {result.success}")
            return result
        except Exception as e:
            logger.error(f"Error executing command {command}: {e}", exc_info=True)
            return CommandResult(
                success=False,
                message=f"Command execution failed: {str(e)}",
            )

    def get_available_commands(self, client_id: str) -> Dict[str, Any]:
        """
        Get list of commands available to a client based on their station.

        Args:
            client_id: Client to check

        Returns:
            Dictionary with available commands and metadata
        """
        session = self.station_manager.get_session(client_id)
        if not session or not session.station:
            return {
                "station": None,
                "commands": [],
                "message": "No station claimed"
            }

        from .station_types import get_station_commands
        available = get_station_commands(session.station)

        # Filter to only registered commands
        registered_available = [
            {
                "command": cmd,
                "metadata": self.command_metadata.get(cmd, {})
            }
            for cmd in available
            if cmd in self.handlers
        ]

        return {
            "station": session.station.value,
            "permission_level": session.permission_level.name,
            "commands": registered_available,
        }


def create_legacy_command_wrapper(runner, command_name: str) -> CommandHandler:
    """
    Create a wrapper for legacy command handlers that work with the old system.

    Args:
        runner: HybridRunner instance
        command_name: Name of the command

    Returns:
        CommandHandler function
    """
    def wrapper(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        """Wrapper for legacy command"""
        try:
            # Import here to avoid circular dependency
            from hybrid.command_handler import route_command

            # Get the ship
            ship = runner.simulator.ships.get(ship_id)
            if not ship:
                return CommandResult(
                    success=False,
                    message=f"Ship not found: {ship_id}"
                )

            # Build command_data dict for legacy system
            command_data = {"command": command_name, **args}

            # Route through legacy system
            response = route_command(ship, command_data)

            # Convert legacy response format to CommandResult
            if isinstance(response, dict):
                # Legacy responses have various formats, try to normalize
                success = response.get("status") != "error"
                message = response.get("status", response.get("message", "OK"))
                return CommandResult(
                    success=success,
                    message=str(message),
                    data=response
                )
            else:
                # Non-dict response
                return CommandResult(
                    success=True,
                    message="OK",
                    data={"response": response}
                )

        except Exception as e:
            logger.error(f"Error in legacy command wrapper for {command_name}: {e}", exc_info=True)
            return CommandResult(
                success=False,
                message=f"Command failed: {str(e)}"
            )

    return wrapper


def register_legacy_commands(dispatcher: StationAwareDispatcher, runner):
    """
    Register all legacy commands with the station-aware dispatcher.

    Args:
        dispatcher: StationAwareDispatcher instance
        runner: HybridRunner instance
    """
    # Import here to avoid circular dependency
    from hybrid.command_handler import system_commands

    # Register all system commands from the legacy system
    for command_name, (system, action) in system_commands.items():
        handler = create_legacy_command_wrapper(runner, command_name)
        dispatcher.register_command(
            command=command_name,
            handler=handler,
            # Station will be auto-detected from station_types.py
        )
        logger.debug(f"Registered legacy command: {command_name}")

    logger.info(f"Registered {len(system_commands)} legacy commands")
