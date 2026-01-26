"""
Helm station command handlers.

Provides queue management commands for sequential helm maneuvers.
"""

from typing import Dict, Any, Optional, Callable, Iterable, Mapping
import logging

from .station_dispatch import CommandResult
from .station_types import StationType

logger = logging.getLogger(__name__)


def register_helm_commands(
    dispatcher,
    ship_provider: Optional[Callable[[], Iterable[Any]]] = None,
):
    """Register helm queue commands with the dispatcher."""

    def _resolve_ship(target_ship_id: str):
        ships = ship_provider() if ship_provider else []
        if isinstance(ships, Mapping):
            return ships.get(target_ship_id)
        for ship in ships:
            if getattr(ship, "id", None) == target_ship_id:
                return ship
        return None

    def _get_helm(ship):
        if not ship:
            return None
        return ship.systems.get("helm")

    def _dispatch_to_helm(ship, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        helm = _get_helm(ship)
        if not helm or not hasattr(helm, "command"):
            return {"error": "Helm system not available"}
        payload = dict(payload)
        payload["_ship"] = ship
        payload["ship"] = ship
        return helm.command(action, payload)

    def cmd_queue_helm_command(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        ship = _resolve_ship(ship_id)
        if not ship:
            return CommandResult(success=False, message=f"Ship not found: {ship_id}")

        action = args.get("command") or args.get("action")
        params = args.get("params") if isinstance(args.get("params"), dict) else None
        if params is None:
            params = {
                key: value
                for key, value in args.items()
                if key not in {"command", "action", "params"}
            }

        result = _dispatch_to_helm(ship, "queue_command", {"command": action, "params": params})
        if isinstance(result, dict) and "error" in result:
            return CommandResult(success=False, message=result["error"], data=result)
        return CommandResult(success=True, message="Helm command queued", data=result)

    def cmd_queue_helm_commands(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        ship = _resolve_ship(ship_id)
        if not ship:
            return CommandResult(success=False, message=f"Ship not found: {ship_id}")

        commands = args.get("commands")
        if not isinstance(commands, list):
            return CommandResult(success=False, message="commands must be a list")

        result = _dispatch_to_helm(ship, "queue_commands", {"commands": commands})
        if isinstance(result, dict) and "error" in result:
            return CommandResult(success=False, message=result["error"], data=result)
        return CommandResult(success=True, message="Helm commands queued", data=result)

    def cmd_clear_helm_queue(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        ship = _resolve_ship(ship_id)
        if not ship:
            return CommandResult(success=False, message=f"Ship not found: {ship_id}")

        result = _dispatch_to_helm(ship, "clear_queue", {})
        if isinstance(result, dict) and "error" in result:
            return CommandResult(success=False, message=result["error"], data=result)
        return CommandResult(success=True, message="Helm queue cleared", data=result)

    def cmd_interrupt_helm_queue(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        ship = _resolve_ship(ship_id)
        if not ship:
            return CommandResult(success=False, message=f"Ship not found: {ship_id}")

        result = _dispatch_to_helm(ship, "interrupt_queue", {})
        if isinstance(result, dict) and "error" in result:
            return CommandResult(success=False, message=result["error"], data=result)
        return CommandResult(success=True, message="Helm queue interrupted", data=result)

    def cmd_helm_queue_status(client_id: str, ship_id: str, args: Dict[str, Any]) -> CommandResult:
        ship = _resolve_ship(ship_id)
        if not ship:
            return CommandResult(success=False, message=f"Ship not found: {ship_id}")

        result = _dispatch_to_helm(ship, "queue_status", {})
        if isinstance(result, dict) and "error" in result:
            return CommandResult(success=False, message=result["error"], data=result)
        return CommandResult(success=True, message="Helm queue status", data=result)

    dispatcher.register_command(
        "queue_helm_command",
        cmd_queue_helm_command,
        station=StationType.HELM
    )

    dispatcher.register_command(
        "queue_helm_commands",
        cmd_queue_helm_commands,
        station=StationType.HELM
    )

    dispatcher.register_command(
        "clear_helm_queue",
        cmd_clear_helm_queue,
        station=StationType.HELM
    )

    dispatcher.register_command(
        "interrupt_helm_queue",
        cmd_interrupt_helm_queue,
        station=StationType.HELM
    )

    dispatcher.register_command(
        "helm_queue_status",
        cmd_helm_queue_status,
        station=StationType.HELM
    )

    logger.info("Registered helm queue commands")
