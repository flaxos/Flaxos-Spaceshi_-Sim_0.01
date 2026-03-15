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
    - Radio message broadcasting to all ships in range
    - Directed hailing of specific contacts
    - Distress beacon activation
    - Speed-of-light propagation delay calculation
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

        # Radio state
        self.radio_power: float = float(config.get("radio_power", 1000.0))
        self.radio_range: float = float(config.get("radio_range", 1_000_000_000.0))

        # Distress beacon
        self.distress_beacon_enabled: bool = bool(config.get("distress_beacon_enabled", False))

        # Message log (received + sent)
        self.message_log: List[Dict[str, Any]] = []
        self.max_message_log: int = int(config.get("max_message_log", 50))

        # Pending outbound hails (contact_id -> hail data)
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
        """
        if not self.enabled or ship is None or dt <= 0:
            return

        self._sim_time += dt

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

    # ------------------------------------------------------------------
    # Query methods (called by OTHER ships' sensors)
    # ------------------------------------------------------------------

    def get_transponder_broadcast(self) -> Optional[Dict[str, Any]]:
        """Get current IFF transponder broadcast data.

        Returns None if transponder is off or suppressed by EMCON.
        Other ships call this to read our IFF.
        """
        if not self.enabled or not self.transponder_enabled:
            return None
        if getattr(self, "_emcon_suppressed", False):
            return None
        return {
            "code": self.transponder_code,
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
        return error_dict("UNKNOWN_COMMAND", f"Unknown comms command: {action}")

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    def _cmd_set_transponder(self, params: dict) -> dict:
        """Set IFF transponder state and/or code.

        Params:
            enabled (bool, optional): Turn transponder on/off.
            code (str, optional): Set transponder IFF code (spoof).
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
            if not self.transponder_spoofable and new_code != self.transponder_code:
                return error_dict("SPOOF_DENIED",
                                  "This transponder cannot be recoded (hardware locked)")
            if new_code != self.transponder_code:
                self.transponder_code = new_code
                changed = True

        if changed and event_bus and ship:
            event_bus.publish("transponder_changed", {
                "ship_id": ship.id,
                "transponder_enabled": self.transponder_enabled,
                "transponder_code": self.transponder_code,
                "time": self._sim_time,
            })

        emcon_note = ""
        if getattr(self, "_emcon_suppressed", False):
            emcon_note = " (EMCON active — transponder suppressed)"

        status = "ON" if self.transponder_enabled else "OFF"
        return success_dict(
            f"Transponder {status}, code: {self.transponder_code}{emcon_note}",
            transponder_enabled=self.transponder_enabled,
            transponder_code=self.transponder_code,
            emcon_suppressed=getattr(self, "_emcon_suppressed", False),
        )

    def _cmd_hail_contact(self, params: dict) -> dict:
        """Hail a specific contact by ID.

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

        # Calculate propagation delay if we can determine distance
        delay = 0.0
        all_ships = getattr(ship, "_all_ships_ref", None) if ship else None
        target_ship = None
        if all_ships:
            for s in all_ships:
                if getattr(s, "id", None) == target or getattr(s, "name", None) == target:
                    target_ship = s
                    break
        if target_ship and ship:
            from hybrid.utils.math_utils import calculate_distance
            dist = calculate_distance(ship.position, target_ship.position)
            delay = self.calculate_signal_delay(dist)

        # Log the hail
        hail_entry = {
            "type": "hail_sent",
            "from": ship.id if ship else "unknown",
            "to": target,
            "message": message,
            "delay_seconds": round(delay, 3),
            "time": self._sim_time,
        }
        self._add_to_log(hail_entry)
        self._pending_hails[target] = hail_entry

        if event_bus and ship:
            event_bus.publish("hail_sent", hail_entry)

        delay_str = f" (signal delay: {delay:.1f}s)" if delay > 0.5 else ""
        return success_dict(
            f"Hailing {target}{delay_str}",
            target=target,
            message=message,
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
            message=message,
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
            "emcon_suppressed": emcon_suppressed,
            "distress_beacon_enabled": self.distress_beacon_enabled,
            "distress_active": self.is_distress_active(),
            "radio_power": self.radio_power,
            "radio_range": self.radio_range,
            "pending_hails": len(self._pending_hails),
            "message_count": len(self.message_log),
            "recent_messages": self.message_log[-5:] if self.message_log else [],
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
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_to_log(self, entry: dict):
        """Add a message to the comms log, trimming old entries."""
        self.message_log.append(entry)
        if len(self.message_log) > self.max_message_log:
            self.message_log = self.message_log[-self.max_message_log:]
