# hybrid/commands/crew_binding_commands.py
"""Commands for crew-station assignment and status.

Commands:
    assign_crew: Assign a crew member to a station
    transfer_crew: Move a crew member between stations
    unassign_crew: Remove a crew member from their station
    crew_station_status: Get crew assignment and performance report
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)


def cmd_assign_crew(system, ship, params: dict) -> dict:
    """Assign a crew member to a station.

    The crew binding system is stored on the ship as ship._crew_binder.
    The 'system' arg here is the crew_binding pseudo-system which is
    just the CrewStationBinder instance.

    Args:
        system: CrewStationBinder instance (routed as a pseudo-system)
        ship: Ship object
        params: {crew_id: str, station: str}

    Returns:
        dict: Assignment result
    """
    from server.stations.station_types import StationType

    crew_id = params["crew_id"]
    station_str = params["station"]

    try:
        station = StationType(station_str)
    except ValueError:
        valid = [s.value for s in StationType]
        return error_dict(
            "INVALID_STATION",
            f"Unknown station '{station_str}'. Valid: {', '.join(valid)}",
        )

    ok, msg = system.assign_crew(ship.id, crew_id, station)
    if ok:
        return success_dict(msg)
    return error_dict("ASSIGN_FAILED", msg)


def cmd_transfer_crew(system, ship, params: dict) -> dict:
    """Transfer a crew member to a different station.

    Args:
        system: CrewStationBinder instance
        ship: Ship object
        params: {crew_id: str, to_station: str}

    Returns:
        dict: Transfer result
    """
    from server.stations.station_types import StationType

    crew_id = params["crew_id"]
    station_str = params["to_station"]

    try:
        station = StationType(station_str)
    except ValueError:
        valid = [s.value for s in StationType]
        return error_dict(
            "INVALID_STATION",
            f"Unknown station '{station_str}'. Valid: {', '.join(valid)}",
        )

    ok, msg = system.transfer_crew(ship.id, crew_id, station)
    if ok:
        return success_dict(msg)
    return error_dict("TRANSFER_FAILED", msg)


def cmd_unassign_crew(system, ship, params: dict) -> dict:
    """Remove crew from a station, reverting to AI backup.

    Args:
        system: CrewStationBinder instance
        ship: Ship object
        params: {station: str}

    Returns:
        dict: Unassignment result
    """
    from server.stations.station_types import StationType

    station_str = params["station"]

    try:
        station = StationType(station_str)
    except ValueError:
        valid = [s.value for s in StationType]
        return error_dict(
            "INVALID_STATION",
            f"Unknown station '{station_str}'. Valid: {', '.join(valid)}",
        )

    ok, msg = system.unassign_crew(ship.id, station)
    if ok:
        return success_dict(msg)
    return error_dict("UNASSIGN_FAILED", msg)


def cmd_crew_station_status(system, ship, params: dict) -> dict:
    """Get crew assignment and performance report for all stations.

    Args:
        system: CrewStationBinder instance
        ship: Ship object
        params: {} (no params)

    Returns:
        dict: Full crew-station status
    """
    status = system.get_ship_crew_status(ship.id)
    return success_dict("Crew station report", stations=status)


def register_commands(dispatcher) -> None:
    """Register all crew-station binding commands with the dispatcher."""

    valid_stations = [
        "helm", "tactical", "ops", "engineering",
        "science", "comms", "captain", "fleet_commander",
    ]

    dispatcher.register("assign_crew", CommandSpec(
        handler=cmd_assign_crew,
        args=[
            ArgSpec("crew_id", "str", required=True,
                    description="ID of the crew member to assign"),
            ArgSpec("station", "str", required=True,
                    choices=valid_stations,
                    description="Station to assign crew to"),
        ],
        help_text="Assign a crew member to a station",
        system="crew_binding",
    ))

    dispatcher.register("transfer_crew", CommandSpec(
        handler=cmd_transfer_crew,
        args=[
            ArgSpec("crew_id", "str", required=True,
                    description="ID of the crew member to transfer"),
            ArgSpec("to_station", "str", required=True,
                    choices=valid_stations,
                    description="Target station for transfer"),
        ],
        help_text="Transfer a crew member to a different station",
        system="crew_binding",
    ))

    dispatcher.register("unassign_crew", CommandSpec(
        handler=cmd_unassign_crew,
        args=[
            ArgSpec("station", "str", required=True,
                    choices=valid_stations,
                    description="Station to remove crew from"),
        ],
        help_text="Remove crew from a station (AI backup takes over)",
        system="crew_binding",
    ))

    dispatcher.register("crew_station_status", CommandSpec(
        handler=cmd_crew_station_status,
        args=[],
        help_text="Get crew assignment and performance report for all stations",
        system="crew_binding",
    ))
