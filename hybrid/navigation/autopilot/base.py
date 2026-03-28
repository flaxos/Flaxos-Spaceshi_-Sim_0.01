# hybrid/navigation/autopilot/base.py
"""Base autopilot class with fuel budget awareness.

All autopilot programs inherit fuel-budget checks from this base class.
Before committing to a burn, autopilots can query remaining delta-v and
compare it against the delta-v needed to brake to a stop. If the budget
is insufficient, the autopilot refuses the burn and sets a "fuel_insufficient"
status rather than stranding the ship at high velocity.
"""

import logging
import math
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple

from hybrid.utils.units import calculate_delta_v

logger = logging.getLogger(__name__)

# Fuel budget safety margin: autopilot reserves this fraction of delta-v
# beyond the braking budget so the ship is never *exactly* at the PONR.
# 10% reserve means the autopilot will refuse a burn that would leave
# less than 10% of the required braking delta-v as margin.
_FUEL_RESERVE_FRACTION = 0.10

# Below this delta-v (m/s) the ship is considered fuel-critical and
# autopilots should only perform braking maneuvers.
_FUEL_CRITICAL_DV = 50.0


class BaseAutopilot(ABC):
    """Abstract base class for all autopilot programs.

    Provides fuel-budget awareness: subclasses can call
    ``_check_fuel_budget()`` before committing to acceleration burns
    to ensure the ship retains enough delta-v to brake to a stop.
    """

    def __init__(self, ship, target_id: Optional[str] = None, params: Dict = None):
        """Initialize autopilot.

        Args:
            ship: Ship under autopilot control
            target_id: Target contact ID (if applicable)
            params: Additional parameters
        """
        self.ship = ship
        self.target_id = target_id
        self.params = params or {}
        self.status = "initializing"
        self.error_message = None
        self._target_warned = False
        self._fuel_warned = False

    @abstractmethod
    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute thrust command for this tick.

        Args:
            dt: Time delta
            sim_time: Current simulation time

        Returns:
            dict: Command with {thrust, heading} or None
        """
        pass

    def get_target(self):
        """Get target ship or contact.

        Resolves target by:
        1. Sensor contact (by stable ID like C001 or original ship ID)
        2. Direct ship lookup in _all_ships_ref (fallback for raw ship IDs)

        Returns:
            Target object or None
        """
        if not self.target_id:
            return None

        # Try sensor contacts first (handles both C001 and target_station via id_mapping)
        sensors = self.ship.systems.get("sensors")
        if sensors and hasattr(sensors, "get_contact"):
            contact = sensors.get_contact(self.target_id)
            if contact:
                self._target_warned = False
                return contact

        # Fallback: look up directly in all_ships (handles raw ship IDs like target_station)
        all_ships = getattr(self.ship, "_all_ships_ref", [])

        # If target_id is a stable contact ID (e.g. C001), resolve to the
        # original ship ID via the contact tracker's id_mapping so the
        # all_ships fallback can match.
        lookup_ids = {self.target_id}
        if sensors and hasattr(sensors, "contact_tracker"):
            tracker = sensors.contact_tracker
            # Reverse lookup: stable_id -> real_ship_id
            for real_id, stable_id in tracker.id_mapping.items():
                if stable_id == self.target_id:
                    lookup_ids.add(real_id)
            # Forward lookup: real_ship_id -> stable_id (in case target_id is a real id)
            mapped = tracker.id_mapping.get(self.target_id)
            if mapped:
                lookup_ids.add(mapped)

        for ship in all_ships:
            if getattr(ship, "id", None) in lookup_ids:
                if not self._target_warned:
                    logger.info(f"Autopilot: target '{self.target_id}' found via direct ship lookup (not in sensor contacts)")
                    self._target_warned = True
                return ship

        if not self._target_warned:
            logger.warning(f"Autopilot: target '{self.target_id}' not found in sensors or ships")
            self._target_warned = True
        return None

    # ── Fuel budget helpers ──────────────────────────────────────────

    def _has_fuel_tracking(self) -> bool:
        """Check whether the propulsion system tracks fuel.

        Returns False for mock/test propulsion systems that don't model
        fuel consumption, allowing fuel budget checks to be skipped
        gracefully.
        """
        propulsion = self.ship.systems.get("propulsion")
        return propulsion is not None and hasattr(propulsion, "fuel_level")

    def _get_fuel_state(self) -> Tuple[float, float, float, float]:
        """Read current fuel state from propulsion system.

        Returns:
            Tuple of (fuel_level_kg, max_fuel_kg, isp_seconds, exhaust_velocity_m_s).
            Returns high defaults if propulsion has no fuel tracking
            (effectively unlimited fuel for mock/test systems).
        """
        propulsion = self.ship.systems.get("propulsion")
        if not propulsion or not hasattr(propulsion, "fuel_level"):
            # No fuel tracking -- return high values so budget checks pass
            return (1e9, 1e9, 3000.0, 3000.0 * 9.81)
        return (
            getattr(propulsion, "fuel_level", 0.0),
            getattr(propulsion, "max_fuel", 0.0),
            getattr(propulsion, "isp", 3000.0),
            getattr(propulsion, "exhaust_velocity", 3000.0 * 9.81),
        )

    def _get_remaining_delta_v(self) -> float:
        """Calculate remaining delta-v from current fuel and ship mass.

        Uses the Tsiolkovsky rocket equation: dv = Isp * g0 * ln(m0 / m_dry).
        Returns a large value if the ship has no fuel tracking.

        Returns:
            Remaining delta-v in m/s.
        """
        if not self._has_fuel_tracking():
            return float("inf")
        fuel_level, _, isp, _ = self._get_fuel_state()
        dry_mass = getattr(self.ship, "dry_mass", None)
        # Guard against mock objects that don't have a real numeric dry_mass
        if dry_mass is None or not isinstance(dry_mass, (int, float)):
            try:
                dry_mass = float(self.ship.mass)
            except (TypeError, ValueError):
                return float("inf")
        return calculate_delta_v(dry_mass, fuel_level, isp)

    def _delta_v_to_stop(self) -> float:
        """Delta-v required to brake from current speed to zero.

        For a ship in free flight, this is simply the speed magnitude.
        When matching velocity with a target, subclasses should override
        to account for relative velocity instead.

        Returns:
            Delta-v in m/s needed to stop.
        """
        vel = self.ship.velocity
        return math.sqrt(vel["x"]**2 + vel["y"]**2 + vel["z"]**2)

    def _check_fuel_budget(self, additional_dv: float = 0.0) -> bool:
        """Check whether the ship has enough fuel to execute a burn and still brake.

        Compares remaining delta-v against:
            dv_to_stop + additional_dv + reserve_margin

        The reserve margin is _FUEL_RESERVE_FRACTION of dv_to_stop, ensuring
        the ship never commits to a burn that leaves it exactly at the PONR
        with no margin for course corrections.

        Returns True (unlimited budget) if the ship has no fuel tracking.

        Args:
            additional_dv: Extra delta-v the planned maneuver will consume
                           (e.g. an acceleration phase). Set to 0 for
                           brake-only checks.

        Returns:
            True if sufficient fuel exists, False if the burn would
            leave insufficient braking budget.
        """
        remaining_dv = self._get_remaining_delta_v()
        if remaining_dv == float("inf"):
            return True  # No fuel tracking -- unlimited budget
        dv_needed = self._delta_v_to_stop()
        reserve = dv_needed * _FUEL_RESERVE_FRACTION
        total_required = dv_needed + additional_dv + reserve

        if remaining_dv < total_required:
            if not self._fuel_warned:
                logger.warning(
                    "Autopilot %s on %s: fuel budget check FAILED "
                    "(remaining=%.0f m/s, needed=%.0f m/s [stop=%.0f + "
                    "burn=%.0f + reserve=%.0f])",
                    type(self).__name__, self.ship.id,
                    remaining_dv, total_required,
                    dv_needed, additional_dv, reserve,
                )
                self._fuel_warned = True
            return False
        self._fuel_warned = False
        return True

    def _is_fuel_critical(self) -> bool:
        """Check if remaining delta-v is below the critical threshold.

        When fuel is critical, autopilots should only perform braking
        maneuvers -- no new acceleration burns. Returns False if the
        ship has no fuel tracking.

        Returns:
            True if remaining delta-v is below _FUEL_CRITICAL_DV.
        """
        dv = self._get_remaining_delta_v()
        if dv == float("inf"):
            return False
        return dv < _FUEL_CRITICAL_DV

    def _is_fuel_depleted(self) -> bool:
        """Check if the main drive is locked out due to empty fuel tanks.

        Returns False if the propulsion system has no fuel tracking
        (e.g. mock ships in tests) -- assume unlimited fuel when the
        system doesn't model it.

        Returns:
            True if fuel level is zero (drive locked out).
        """
        propulsion = self.ship.systems.get("propulsion")
        if not propulsion:
            return False
        # If propulsion has no fuel_level attribute, it doesn't model fuel
        if not hasattr(propulsion, "fuel_level"):
            return False
        return propulsion.fuel_level <= 0

    def get_state(self) -> Dict:
        """Get autopilot state.

        Returns:
            dict: Current state including fuel budget info
        """
        remaining_dv = self._get_remaining_delta_v()
        dv_to_stop = self._delta_v_to_stop()

        # Handle inf for ships without fuel tracking (JSON-safe)
        if remaining_dv == float("inf"):
            fuel_budget = {
                "remaining_dv": None,
                "dv_to_stop": round(dv_to_stop, 1),
                "margin": None,
                "fuel_critical": False,
                "fuel_depleted": False,
            }
        else:
            fuel_budget = {
                "remaining_dv": round(remaining_dv, 1),
                "dv_to_stop": round(dv_to_stop, 1),
                "margin": round(remaining_dv - dv_to_stop, 1),
                "fuel_critical": self._is_fuel_critical(),
                "fuel_depleted": self._is_fuel_depleted(),
            }

        return {
            "status": self.status,
            "target_id": self.target_id,
            "error": self.error_message,
            "fuel_budget": fuel_budget,
        }

    def _clamp_thrust(self, thrust: float) -> float:
        """Clamp thrust to valid range [0, 1].

        Args:
            thrust: Thrust value

        Returns:
            float: Clamped thrust
        """
        return max(0.0, min(1.0, thrust))

    def _normalize_angle(self, angle: float) -> float:
        """Normalize angle to [-180, 180].

        Args:
            angle: Angle in degrees

        Returns:
            float: Normalized angle
        """
        while angle > 180:
            angle -= 360
        while angle < -180:
            angle += 360
        return angle
