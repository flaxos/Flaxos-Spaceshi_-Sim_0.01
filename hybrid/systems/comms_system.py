# hybrid/systems/comms_system.py
"""Communications and IFF system.

Manages ship identity broadcasting, radio communications, contact hailing,
and distress signals.  IFF (Identify Friend or Foe) is a *broadcast* —
it can be spoofed, turned off, or simply ignored by the receiver.  Without
an active transponder, a contact must be identified by sensor analysis
(drive signature, RCS profile, visual ID at close range).

Design principles:
- IFF is NOT magic identification — it is a cooperative broadcast.
- Radio messages travel at speed of light: delay = distance / c.
- EMCON interacts with comms: full EMCON silences the transponder too.
- Hailing is one-way until the target responds.
- Transponder can be spoofed to broadcast a false identity.
"""

import logging
import math
from typing import Dict, Any, Optional, List
from hybrid.core.base_system import BaseSystem
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)

# Speed of light (m/s) — used for radio propagation delay
SPEED_OF_LIGHT = 299_792_458.0

# Default configuration for the comms system
DEFAULT_COMMS_CONFIG = {
    "transponder_enabled": True,       # IFF transponder broadcasting
    "transponder_code": "CIVILIAN",    # IFF code: faction/identity string
    "transponder_spoofable": True,     # Whether code can be changed at will
    "radio_power": 1000.0,             # Transmit power in watts
    "radio_range": 1_000_000_000.0,    # Max effective radio range (1M km)
    "max_message_log": 50,             # Messages to retain in log
    "distress_beacon_enabled": False,  # Emergency distress signal
    "power_draw": 0.5,                 # kW power draw
}


class CommsSystem(BaseSystem):
    """Ship communications and IFF transponder system.

    Provides:
    - IFF transponder control (enable/disable/set code/spoof)
    - Transponder spoofing (broadcast false identity)
    - Radio message broadcasting to all ships in range
    - Directed hailing with speed-of-light delay and AI responses
    - Distress beacon activation
    """

    def __init__(self, config: Optional[dict] = None):
        config = config if config is not None else {}

        # Merge defaults
        for key, default in DEFAULT_COMMS_CONFIG.items():
            if key not in config:
                config[key] = default

        super().__init__(config)

        # IFF transponder state
        self.transponder_enabled: bool = bool(config.get("transponder_enabled", True))
        self.transponder_code: str = str(config.get("transponder_code", "CIVILIAN"))
        self.transponder_spoofable: bool = bool(config.get("transponder_spoofable", True))

        # Transponder spoofing: track real vs declared identity
        self._real_code: str = self.transponder_code
        self._real_class: str = str(config.get("ship_class", ""))
        self._real_faction: str = str(config.get("faction", ""))
        self.declared_class: str = self._real_class
        self.declared_faction: str = self._real_faction
        self.is_spoofed: bool = False

        # Radio state
        self.radio_power: float = float(config.get("radio_power", 1000.0))
        self.radio_range: float = float(config.get("radio_range", 1_000_000_000.0))

        # Distress beacon
        self.distress_beacon_enabled: bool = bool(config.get("distress_beacon_enabled", False))

        # Message log (received + sent)
        self.message_log: List[Dict[str, Any]] = []
        self.max_message_log: int = int(config.get("max_message_log", 50))

        # Pending outbound hails awaiting light-speed response
        # Each entry: {target_id, target_ship_id, send_time,
        #              response_due_time, responded, delay_seconds}
        self._pending_hails: Dict[str, Dict[str, Any]] = {}

        # Track simulation time for message timestamps
        self._sim_time: float = 0.0

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def tick(self, dt: float, ship=None, event_bus=None):
        """Update comms system each tick.

        - EMCON override: if ECM system has EMCON active, transponder is
          silenced regardless of local setting.
        - Distress beacon is continuous once activated.
        - Process pending hails: deliver AI responses after light-delay.
        """
        if not self.enabled or ship is None or dt <= 0:
            return

        self._sim_time += dt

        # Sync real identity from ship (may change at runtime)
        self._real_class = getattr(ship, "class_type", self._real_class)
        self._real_faction = getattr(ship, "faction", self._real_faction)
        if not self.is_spoofed:
            self.declared_class = self._real_class
            self.declared_faction = self._real_faction

        # Check EMCON override from ECM system
        ecm = ship.systems.get("ecm") if hasattr(ship, "systems") else None
        emcon_active = False
        if ecm and hasattr(ecm, "emcon_active"):
            emcon_active = ecm.emcon_active

        # If EMCON is active, suppress transponder and distress beacon
        # (but don't change the user's desired setting — just suppress output)
        self._emcon_suppressed = emcon_active

        # Publish distress beacon event if active and not suppressed
        if self.distress_beacon_enabled and not emcon_active and event_bus and ship:
            event_bus.publish("distress_beacon", {
                "ship_id": ship.id,
                "ship_name": getattr(ship, "name", ship.id),
                "position": getattr(ship, "position", {"x": 0, "y": 0, "z": 0}),
                "time": self._sim_time,
            })

        # Process pending hails — deliver responses after light-speed delay
        self._process_pending_hails(ship, event_bus)

    # ------------------------------------------------------------------
    # Query methods (called by OTHER ships' sensors)
    # ------------------------------------------------------------------

    def get_transponder_broadcast(self) -> Optional[Dict[str, Any]]:
        """Get current IFF transponder broadcast data.

        Returns None if transponder is off or suppressed by EMCON.
        Other ships call this to read our IFF.  If spoofed, returns
        the declared (false) identity, not the real one.
        """
        if not self.enabled or not self.transponder_enabled:
            return None
        if getattr(self, "_emcon_suppressed", False):
            return None
        return {
            "code": self.transponder_code,
            "ship_class": self.declared_class,
            "faction": self.declared_faction,
            "active": True,
        }

    def is_distress_active(self) -> bool:
        """Check if distress beacon is broadcasting."""
        if not self.enabled or not self.distress_beacon_enabled:
            return False
        if getattr(self, "_emcon_suppressed", False):
            return False
        return True

    @staticmethod
    def calculate_signal_delay(distance: float) -> float:
        """Calculate one-way speed-of-light delay for radio.

        Args:
            distance: Distance in metres between sender and receiver.

        Returns:
            Delay in seconds.
        """
        if distance <= 0:
            return 0.0
        return distance / SPEED_OF_LIGHT

    # ------------------------------------------------------------------
    # Command dispatcher
    # ------------------------------------------------------------------

    def command(self, action: str, params: dict = None) -> dict:
        """Dispatch comms commands."""
        params = params or {}
        if action == "set_transponder":
            return self._cmd_set_transponder(params)
        elif action == "hail_contact":
            return self._cmd_hail_contact(params)
        elif action == "broadcast_message":
            return self._cmd_broadcast_message(params)
        elif action == "set_distress":
            return self._cmd_set_distress(params)
        elif action == "comms_status":
            return self._cmd_comms_status(params)
        elif action in ("comms_respond", "get_comms_choices", "get_branch_status"):
            # Mission branching commands -- delegated to mission_commands module
            # which accesses the BranchingMission via the ship's runner reference.
            return self._delegate_mission_command(action, params)
        return error_dict("UNKNOWN_COMMAND", f"Unknown comms command: {action}")

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    def _cmd_set_transponder(self, params: dict) -> dict:
        """Set IFF transponder state, code, and spoofing.

        Params:
            enabled (bool, optional): Turn transponder on/off.
            code (str, optional): Set transponder IFF code.
            spoofed (bool, optional): If True, broadcast false identity.
            declared_class (str, optional): False ship class to broadcast.
            declared_faction (str, optional): False faction to broadcast.
        """
        ship = params.get("ship") or params.get("_ship")
        event_bus = params.get("event_bus")

        changed = False

        if "enabled" in params:
            new_enabled = bool(params["enabled"])
            if new_enabled != self.transponder_enabled:
                self.transponder_enabled = new_enabled
                changed = True

        if "code" in params:
            new_code = str(params["code"]).strip()
            if not new_code:
                return error_dict("INVALID_CODE", "Transponder code cannot be empty")
            if not self.transponder_spoofable and new_code != self._real_code:
                return error_dict("SPOOF_DENIED",
                                  "This transponder cannot be recoded (hardware locked)")
            if new_code != self.transponder_code:
                self.transponder_code = new_code
                changed = True

        # Handle spoofing toggle
        if "spoofed" in params:
            want_spoof = bool(params["spoofed"])
            if want_spoof and not self.transponder_spoofable:
                return error_dict("SPOOF_DENIED",
                                  "This transponder cannot be spoofed (hardware locked)")
            if want_spoof != self.is_spoofed:
                self.is_spoofed = want_spoof
                if not want_spoof:
                    # Revert to real identity
                    self.transponder_code = self._real_code
                    self.declared_class = self._real_class
                    self.declared_faction = self._real_faction
                changed = True

        # Set declared (false) identity fields when spoofing
        if self.is_spoofed:
            if "declared_class" in params:
                self.declared_class = str(params["declared_class"])
                changed = True
            if "declared_faction" in params:
                self.declared_faction = str(params["declared_faction"])
                changed = True

        if changed and event_bus and ship:
            event_bus.publish("transponder_changed", {
                "ship_id": ship.id,
                "transponder_enabled": self.transponder_enabled,
                "transponder_code": self.transponder_code,
                "is_spoofed": self.is_spoofed,
                "time": self._sim_time,
            })

        emcon_note = ""
        if getattr(self, "_emcon_suppressed", False):
            emcon_note = " (EMCON active — transponder suppressed)"
        spoof_note = " [SPOOFED]" if self.is_spoofed else ""

        status = "ON" if self.transponder_enabled else "OFF"
        return success_dict(
            f"Transponder {status}, code: {self.transponder_code}{spoof_note}{emcon_note}",
            transponder_enabled=self.transponder_enabled,
            transponder_code=self.transponder_code,
            is_spoofed=self.is_spoofed,
            declared_class=self.declared_class,
            declared_faction=self.declared_faction,
            emcon_suppressed=getattr(self, "_emcon_suppressed", False),
        )

    def _cmd_hail_contact(self, params: dict) -> dict:
        """Hail a specific contact by ID.

        Resolves contact_id -> real ship_id via sensor contact tracker,
        calculates light-speed delay, and queues the hail for an async
        AI response delivered after the round-trip delay elapses.

        Params:
            target (str): Contact ID or ship ID to hail.
            message (str, optional): Message to include in hail.
        """
        ship = params.get("ship") or params.get("_ship")
        event_bus = params.get("event_bus")
        target = params.get("target")

        if not target:
            return error_dict("NO_TARGET", "Must specify a target to hail")

        if getattr(self, "_emcon_suppressed", False):
            return error_dict("EMCON_ACTIVE",
                              "Cannot transmit while EMCON is active")

        message = str(params.get("message", "Unidentified vessel, respond."))

        # Resolve contact_id to real ship via sensor tracker + _all_ships_ref
        target_ship = None
        target_ship_id = target
        if ship:
            target_ship, target_ship_id = self._resolve_hail_target(
                ship, target
            )

        # Calculate one-way propagation delay
        delay = 0.0
        if target_ship and ship:
            from hybrid.utils.math_utils import calculate_distance
            dist = calculate_distance(ship.position, target_ship.position)
            delay = self.calculate_signal_delay(dist)

        # Round-trip delay: hail travels out, response travels back
        round_trip_delay = delay * 2.0

        # Log the hail
        hail_entry = {
            "type": "hail_sent",
            "from": ship.id if ship else "unknown",
            "from_name": getattr(ship, "name", "Unknown") if ship else "Unknown",
            "to": target,
            "message": message,
            "delay_seconds": round(delay, 3),
            "time": self._sim_time,
        }
        self._add_to_log(hail_entry)

        # Queue pending hail for async response
        self._pending_hails[target] = {
            "target_contact_id": target,
            "target_ship_id": target_ship_id,
            "send_time": self._sim_time,
            "one_way_delay": delay,
            "response_due_time": self._sim_time + round_trip_delay,
            "responded": False,
            "message": message,
        }

        if event_bus and ship:
            event_bus.publish("hail_sent", hail_entry)

        delay_str = f" (signal delay: {delay:.1f}s)" if delay > 0.5 else ""
        return success_dict(
            f"Hailing {target}{delay_str}",
            target=target,
            hail_message=message,
            delay_seconds=round(delay, 3),
        )

    def _cmd_broadcast_message(self, params: dict) -> dict:
        """Broadcast a radio message to all ships in range.

        Params:
            message (str): Message to broadcast.
            channel (str, optional): Radio channel/frequency (default "GUARD").
        """
        ship = params.get("ship") or params.get("_ship")
        event_bus = params.get("event_bus")

        if getattr(self, "_emcon_suppressed", False):
            return error_dict("EMCON_ACTIVE",
                              "Cannot transmit while EMCON is active")

        message = params.get("message")
        if not message:
            return error_dict("NO_MESSAGE", "Must specify a message to broadcast")
        message = str(message)

        channel = str(params.get("channel", "GUARD"))

        broadcast_entry = {
            "type": "broadcast_sent",
            "from": ship.id if ship else "unknown",
            "from_name": getattr(ship, "name", "Unknown") if ship else "Unknown",
            "channel": channel,
            "message": message,
            "time": self._sim_time,
        }
        self._add_to_log(broadcast_entry)

        if event_bus and ship:
            event_bus.publish("radio_broadcast", broadcast_entry)

        return success_dict(
            f"Broadcasting on {channel}: {message[:60]}",
            channel=channel,
            broadcast_message=message,
        )

    def _cmd_set_distress(self, params: dict) -> dict:
        """Activate or deactivate the distress beacon.

        Params:
            enabled (bool, optional): True to activate, False to deactivate.
                                       Toggles if omitted.
        """
        ship = params.get("ship") or params.get("_ship")
        event_bus = params.get("event_bus")

        if "enabled" in params:
            new_state = bool(params["enabled"])
        else:
            new_state = not self.distress_beacon_enabled

        was_active = self.distress_beacon_enabled
        self.distress_beacon_enabled = new_state

        if new_state and not was_active:
            distress_entry = {
                "type": "distress_activated",
                "ship_id": ship.id if ship else "unknown",
                "ship_name": getattr(ship, "name", "Unknown") if ship else "Unknown",
                "time": self._sim_time,
            }
            self._add_to_log(distress_entry)
            if event_bus and ship:
                event_bus.publish("distress_activated", distress_entry)

        elif not new_state and was_active:
            cancel_entry = {
                "type": "distress_cancelled",
                "ship_id": ship.id if ship else "unknown",
                "time": self._sim_time,
            }
            self._add_to_log(cancel_entry)
            if event_bus and ship:
                event_bus.publish("distress_cancelled", cancel_entry)

        status = "ACTIVE" if new_state else "OFF"
        emcon_note = ""
        if new_state and getattr(self, "_emcon_suppressed", False):
            emcon_note = " (suppressed by EMCON)"

        return success_dict(
            f"Distress beacon {status}{emcon_note}",
            distress_beacon_enabled=self.distress_beacon_enabled,
            emcon_suppressed=getattr(self, "_emcon_suppressed", False),
        )

    def _cmd_comms_status(self, params: dict) -> dict:
        """Return full comms system status."""
        state = self.get_state()
        state["ok"] = True
        return state

    # ------------------------------------------------------------------
    # State / telemetry
    # ------------------------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        """Return serializable comms telemetry."""
        emcon_suppressed = getattr(self, "_emcon_suppressed", False)
        return {
            "enabled": self.enabled,
            "power_draw": self.power_draw,
            "transponder_enabled": self.transponder_enabled,
            "transponder_code": self.transponder_code,
            "transponder_active": self.transponder_enabled and not emcon_suppressed,
            "is_spoofed": self.is_spoofed,
            "declared_class": self.declared_class,
            "declared_faction": self.declared_faction,
            "emcon_suppressed": emcon_suppressed,
            "distress_beacon_enabled": self.distress_beacon_enabled,
            "distress_active": self.is_distress_active(),
            "radio_power": self.radio_power,
            "radio_range": self.radio_range,
            "pending_hails": len(self._pending_hails),
            "message_count": len(self.message_log),
            "recent_messages": self.message_log[-10:] if self.message_log else [],
            "status": self._get_status_string(),
        }

    def _get_status_string(self) -> str:
        """Human-readable status summary."""
        if not self.enabled:
            return "offline"
        if getattr(self, "_emcon_suppressed", False):
            return "EMCON"
        if self.distress_beacon_enabled:
            return "DISTRESS"
        if self.transponder_enabled:
            return "active"
        return "silent"

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def add_system_message(self, message: str, from_source: str = "COMMAND",
                           time: float = None) -> None:
        """Add a system-generated message to the comms log.

        Used by the mission system and other server-side subsystems to
        inject notifications into the player's comms feed without
        requiring a radio broadcast or hail.

        Args:
            message: Human-readable notification text.
            from_source: Sender label shown in the comms log entry.
            time: Simulation timestamp; defaults to 0 if not provided.
        """
        self._add_to_log({
            "type": "system",
            "from": from_source,
            "to": "ALL",
            "message": message,
            "time": time or 0,
        })

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _delegate_mission_command(self, action: str, params: dict) -> dict:
        """Delegate mission branching commands to the mission_commands module.

        These commands need access to the BranchingMission via the ship's
        runner reference.  The comms system itself is stateless with respect
        to mission branching -- it just provides the routing.
        """
        from hybrid.commands import mission_commands

        ship = params.get("ship") or params.get("_ship")
        if not ship:
            return error_dict("NO_SHIP", "Ship reference required for mission commands")

        handler_map = {
            "comms_respond": mission_commands.cmd_comms_respond,
            "get_comms_choices": mission_commands.cmd_get_comms_choices,
            "get_branch_status": mission_commands.cmd_get_branch_status,
        }

        handler = handler_map.get(action)
        if not handler:
            return error_dict("UNKNOWN_COMMAND", f"Unknown mission command: {action}")

        return handler(self, ship, params)

    def _resolve_hail_target(self, ship, contact_id: str):
        """Delegate to comms_hail module for contact resolution."""
        from hybrid.systems.comms_hail import resolve_hail_target
        return resolve_hail_target(ship, contact_id)

    def _process_pending_hails(self, ship, event_bus) -> None:
        """Delegate to comms_hail module for pending hail processing."""
        from hybrid.systems.comms_hail import process_pending_hails
        completed = process_pending_hails(
            self._pending_hails, self._sim_time,
            ship, event_bus, self._add_to_log,
        )
        for cid in completed:
            self._pending_hails.pop(cid, None)

    def _add_to_log(self, entry: dict):
        """Add a message to the comms log, trimming old entries."""
        self.message_log.append(entry)
        if len(self.message_log) > self.max_message_log:
            self.message_log = self.message_log[-self.max_message_log:]
