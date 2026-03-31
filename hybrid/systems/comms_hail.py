# hybrid/systems/comms_hail.py
"""Hail response generation for the comms system.

Handles the AI logic for generating responses to player hails.
Responses depend on diplomatic state, EMCON status, and target
ship configuration.  Separated from comms_system.py to keep
module sizes manageable.
"""

import logging
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger(__name__)


def resolve_hail_target(ship, contact_id: str) -> Tuple[Optional[Any], str]:
    """Resolve a contact ID to a target Ship object.

    Uses the sensor contact tracker's id_mapping to convert stable
    contact IDs (C001) to real ship IDs, then looks up the ship
    via _all_ships_ref.

    Args:
        ship: The hailing ship (source).
        contact_id: Stable contact ID or raw ship ID.

    Returns:
        Tuple of (target_ship_or_None, resolved_ship_id).
    """
    resolved_id = contact_id
    sensors = ship.systems.get("sensors")
    if sensors and hasattr(sensors, "contact_tracker"):
        tracker = sensors.contact_tracker
        # Reverse lookup: stable_contact_id -> real_ship_id
        for real_id, stable_id in tracker.id_mapping.items():
            if stable_id == contact_id:
                resolved_id = real_id
                break

    all_ships = getattr(ship, "_all_ships_ref", None)
    if all_ships:
        for s in all_ships:
            if s.id == resolved_id or s.id == contact_id:
                return s, s.id
            if getattr(s, "name", None) == contact_id:
                return s, s.id
    return None, resolved_id


def process_pending_hails(
    pending_hails: Dict[str, Dict[str, Any]],
    sim_time: float,
    ship: Any,
    event_bus: Any,
    add_to_log_fn,
) -> List[str]:
    """Process pending hails and deliver AI responses after delay.

    Called each tick by CommsSystem.  When a hail's round-trip
    light-delay has elapsed, generates an AI response.

    Args:
        pending_hails: Dict of contact_id -> hail data.
        sim_time: Current simulation time.
        ship: The hailing (player) ship.
        event_bus: Event bus for publishing comm_received events.
        add_to_log_fn: Callable to add entries to the comms log.

    Returns:
        List of contact_ids whose hails completed (to remove).
    """
    completed: List[str] = []
    for contact_id, hail in pending_hails.items():
        if hail["responded"]:
            completed.append(contact_id)
            continue
        if sim_time < hail["response_due_time"]:
            continue

        # Time to deliver a response
        hail["responded"] = True
        response = generate_hail_response(ship, hail, sim_time)
        add_to_log_fn(response)

        if event_bus:
            event_bus.publish("comm_received", response)

        completed.append(contact_id)

    return completed


def generate_hail_response(
    ship: Any,
    hail: Dict[str, Any],
    sim_time: float,
) -> Dict[str, Any]:
    """Generate an AI ship's response to a hail.

    Response depends on:
    - Whether the target ship exists and has a comms system
    - Whether the target is in EMCON mode
    - The diplomatic state between factions

    Args:
        ship: The player's ship (hail sender).
        hail: Pending hail data dict.
        sim_time: Current simulation time.

    Returns:
        Comms log entry dict for the response.
    """
    from hybrid.fleet.faction_rules import get_diplomatic_state, DiplomaticState

    target_ship_id = hail["target_ship_id"]
    contact_id = hail["target_contact_id"]
    delay = hail["one_way_delay"]

    # Try to find the target ship
    target = None
    all_ships = getattr(ship, "_all_ships_ref", None)
    if all_ships:
        for s in all_ships:
            if s.id == target_ship_id:
                target = s
                break

    if not target:
        return _make_response_entry(
            contact_id, None, "no_response",
            "No response — target not found", delay, sim_time,
        )

    # Check if target has comms and transponder
    target_comms = target.systems.get("comms") if hasattr(target, "systems") else None

    # Check EMCON — target in EMCON won't respond
    if target_comms and getattr(target_comms, "_emcon_suppressed", False):
        return _make_response_entry(
            contact_id, target, "no_response",
            "No response (target may be in EMCON)", delay, sim_time,
        )

    # Check diplomatic state
    our_faction = getattr(ship, "faction", "")
    their_faction = getattr(target, "faction", "")
    diplo = get_diplomatic_state(our_faction, their_faction)

    target_name = getattr(target, "name", target.id)
    target_class = getattr(target, "class_type", "Unknown")

    # Get IFF code from target's transponder
    iff_code = "UNKNOWN"
    if target_comms and hasattr(target_comms, "transponder_code"):
        if target_comms.transponder_enabled:
            iff_code = target_comms.transponder_code

    if diplo == DiplomaticState.HOSTILE:
        return _make_response_entry(
            contact_id, target, "warning",
            f"This is {target_name}. You are targeted. "
            f"Break off or be destroyed.",
            delay, sim_time, iff_code=iff_code, faction=their_faction,
            ship_class=target_class, diplomatic_state=diplo.value,
        )

    if diplo == DiplomaticState.ALLIED:
        return _make_response_entry(
            contact_id, target, "identify",
            f"{target_name}, {target_class}-class, "
            f"{their_faction.upper()}. IFF {iff_code}. "
            f"Friendly. Standing by.",
            delay, sim_time, iff_code=iff_code, faction=their_faction,
            ship_class=target_class, diplomatic_state=diplo.value,
        )

    if diplo == DiplomaticState.NEUTRAL:
        return _make_response_entry(
            contact_id, target, "identify",
            f"This is {target_name}, {target_class}-class. "
            f"IFF {iff_code}. We are neutral. State your intentions.",
            delay, sim_time, iff_code=iff_code, faction=their_faction,
            ship_class=target_class, diplomatic_state=diplo.value,
        )

    # UNKNOWN
    return _make_response_entry(
        contact_id, target, "identify",
        f"Vessel {target_name} responding. IFF {iff_code}. "
        f"Identify yourself.",
        delay, sim_time, iff_code=iff_code, faction=their_faction,
        ship_class=target_class, diplomatic_state=diplo.value,
    )


def _make_response_entry(
    contact_id: str,
    target_ship: Any,
    response_type: str,
    message: str,
    delay: float,
    sim_time: float,
    iff_code: str = "UNKNOWN",
    faction: str = "",
    ship_class: str = "",
    diplomatic_state: str = "unknown",
) -> Dict[str, Any]:
    """Build a comms log entry for a hail response.

    Args:
        contact_id: The stable contact ID of the responding ship.
        target_ship: The Ship object (or None if not found).
        response_type: One of "identify", "warning", "no_response".
        message: Human-readable response text.
        delay: One-way light-speed delay in seconds.
        sim_time: Current simulation time.
        iff_code: IFF transponder code.
        faction: Faction of the responding ship.
        ship_class: Ship class of the responding ship.
        diplomatic_state: Diplomatic state string.

    Returns:
        Comms log entry dict.
    """
    ship_name = (
        getattr(target_ship, "name", contact_id) if target_ship else contact_id
    )
    return {
        "type": "hail_response",
        "from": ship_name,
        "from_id": contact_id,
        "response_type": response_type,
        "message": message,
        "iff_code": iff_code,
        "faction": faction,
        "ship_class": ship_class,
        "diplomatic_state": diplomatic_state,
        "delay_seconds": round(delay, 3),
        "time": sim_time,
    }
