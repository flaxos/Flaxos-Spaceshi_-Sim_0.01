# hybrid/commands/eccm_commands.py
"""ECCM station commands: frequency hop, burn-through, multi-spectral, home-on-jam.

Commands:
    eccm_frequency_hop: Enable frequency hopping to counter noise jamming
    eccm_burn_through: Enable burn-through mode (high power radar)
    eccm_off: Deactivate ECCM mode (frequency hop or burn-through)
    eccm_multispectral: Toggle multi-spectral correlation
    eccm_home_on_jam: Toggle home-on-jam mode
    analyze_jamming: Analyze target's ECM emissions and recommend counter
    eccm_status: Full ECCM system readout
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)


def _get_eccm(sensor_system):
    """Extract ECCMState from sensor system.

    Args:
        sensor_system: SensorSystem instance.

    Returns:
        ECCMState or None.
    """
    return getattr(sensor_system, "eccm", None)


def cmd_eccm_frequency_hop(sensors, ship, params: dict) -> dict:
    """Enable frequency hopping ECCM.

    Args:
        sensors: SensorSystem instance.
        ship: Ship object.
        params: Validated parameters.

    Returns:
        dict: Activation result.
    """
    eccm = _get_eccm(sensors)
    if not eccm:
        return error_dict("NO_ECCM", "ECCM capability not available on this sensor suite")
    return eccm.activate_frequency_hop()


def cmd_eccm_burn_through(sensors, ship, params: dict) -> dict:
    """Enable burn-through ECCM mode.

    Args:
        sensors: SensorSystem instance.
        ship: Ship object.
        params: Validated parameters.

    Returns:
        dict: Activation result.
    """
    eccm = _get_eccm(sensors)
    if not eccm:
        return error_dict("NO_ECCM", "ECCM capability not available on this sensor suite")
    return eccm.activate_burn_through()


def cmd_eccm_off(sensors, ship, params: dict) -> dict:
    """Deactivate ECCM mode.

    Args:
        sensors: SensorSystem instance.
        ship: Ship object.
        params: Validated parameters.

    Returns:
        dict: Deactivation result.
    """
    eccm = _get_eccm(sensors)
    if not eccm:
        return error_dict("NO_ECCM", "ECCM capability not available on this sensor suite")
    return eccm.deactivate_eccm_mode()


def cmd_eccm_multispectral(sensors, ship, params: dict) -> dict:
    """Toggle multi-spectral correlation.

    Args:
        sensors: SensorSystem instance.
        ship: Ship object.
        params: Validated parameters with optional 'enabled' bool.

    Returns:
        dict: Result.
    """
    eccm = _get_eccm(sensors)
    if not eccm:
        return error_dict("NO_ECCM", "ECCM capability not available on this sensor suite")

    # Toggle if not specified
    enabled = params.get("enabled", not eccm.multispectral_active)
    return eccm.set_multispectral(enabled)


def cmd_eccm_home_on_jam(sensors, ship, params: dict) -> dict:
    """Toggle home-on-jam mode.

    Args:
        sensors: SensorSystem instance.
        ship: Ship object.
        params: Validated parameters with optional 'enabled' bool.

    Returns:
        dict: Result.
    """
    eccm = _get_eccm(sensors)
    if not eccm:
        return error_dict("NO_ECCM", "ECCM capability not available on this sensor suite")

    enabled = params.get("enabled", not eccm.hoj_active)
    return eccm.set_home_on_jam(enabled)


def cmd_analyze_jamming(sensors, ship, params: dict) -> dict:
    """Analyze target's ECM emissions and recommend countermeasure.

    Requires a contact_id to identify which target to analyze.

    Args:
        sensors: SensorSystem instance.
        ship: Ship object.
        params: Validated parameters with 'contact_id'.

    Returns:
        dict: Analysis results with ECM type and recommendation.
    """
    eccm = _get_eccm(sensors)
    if not eccm:
        return error_dict("NO_ECCM", "ECCM capability not available on this sensor suite")

    contact_id = params.get("contact_id")
    if not contact_id:
        return error_dict("NO_TARGET", "Specify contact_id to analyze")

    # Resolve contact to ship object
    # We need the actual ship object to inspect its ECM state.
    # The sensor system tracks contacts; we need to find the underlying ship.
    all_ships = getattr(sensors, "all_ships", [])
    target_ship = None

    # First try resolving via contact tracker (stable ID -> original ship ID)
    contact = sensors.contact_tracker.get_contact(contact_id)
    original_id = contact_id
    if contact:
        original_id = contact.id

    for s in all_ships:
        if hasattr(s, "id") and (s.id == contact_id or s.id == original_id):
            target_ship = s
            break

    if not target_ship:
        return error_dict("TARGET_NOT_FOUND", f"Cannot resolve contact '{contact_id}' to a ship")

    from hybrid.utils.math_utils import calculate_distance
    distance = calculate_distance(ship.position, target_ship.position)

    result = eccm.analyze_jamming(target_ship, distance)
    result["contact_id"] = contact_id
    result["distance"] = round(distance, 1)
    return result


def cmd_eccm_status(sensors, ship, params: dict) -> dict:
    """Full ECCM system readout.

    Args:
        sensors: SensorSystem instance.
        ship: Ship object.
        params: Validated parameters.

    Returns:
        dict: Complete ECCM status.
    """
    eccm = _get_eccm(sensors)
    if not eccm:
        return error_dict("NO_ECCM", "ECCM capability not available on this sensor suite")

    state = eccm.get_state()
    state["ok"] = True
    return state


def register_commands(dispatcher) -> None:
    """Register all ECCM commands with the dispatcher."""

    dispatcher.register("eccm_frequency_hop", CommandSpec(
        handler=cmd_eccm_frequency_hop,
        args=[],
        help_text="Enable frequency hopping ECCM to counter radar noise jamming (60-80% reduction)",
        system="sensors",
    ))

    dispatcher.register("eccm_burn_through", CommandSpec(
        handler=cmd_eccm_burn_through,
        args=[],
        help_text="Enable burn-through mode: brute-force radar power increase (high heat, reveals position)",
        system="sensors",
    ))

    dispatcher.register("eccm_off", CommandSpec(
        handler=cmd_eccm_off,
        args=[],
        help_text="Deactivate ECCM mode (frequency hop or burn-through)",
        system="sensors",
    ))

    dispatcher.register("eccm_multispectral", CommandSpec(
        handler=cmd_eccm_multispectral,
        args=[
            ArgSpec("enabled", "bool", required=False,
                    description="True to enable, False to disable (toggles if omitted)"),
        ],
        help_text="Toggle multi-spectral correlation to filter chaff and flares",
        system="sensors",
    ))

    dispatcher.register("eccm_home_on_jam", CommandSpec(
        handler=cmd_eccm_home_on_jam,
        args=[
            ArgSpec("enabled", "bool", required=False,
                    description="True to enable, False to disable (toggles if omitted)"),
        ],
        help_text="Toggle home-on-jam: use enemy jammer emissions as bearing source",
        system="sensors",
    ))

    dispatcher.register("analyze_jamming", CommandSpec(
        handler=cmd_analyze_jamming,
        args=[
            ArgSpec("contact_id", "str", required=True,
                    description="Contact ID to analyze for ECM emissions"),
        ],
        help_text="Analyze target ECM emissions and recommend countermeasure",
        system="sensors",
    ))

    dispatcher.register("eccm_status", CommandSpec(
        handler=cmd_eccm_status,
        args=[],
        help_text="Full ECCM system status readout",
        system="sensors",
    ))
