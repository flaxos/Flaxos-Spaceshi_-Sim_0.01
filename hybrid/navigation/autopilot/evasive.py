# hybrid/navigation/autopilot/evasive.py
"""Evasive autopilot - random jink pattern to avoid incoming fire."""

import logging
import math
import random
from typing import Dict, Optional

from hybrid.navigation.autopilot.base import BaseAutopilot
from hybrid.navigation.relative_motion import vector_to_heading
from hybrid.utils.math_utils import magnitude

logger = logging.getLogger(__name__)


class EvasiveAutopilot(BaseAutopilot):
    """Autopilot that executes random jink maneuvers.

    Changes thrust direction and magnitude at random intervals so
    the ship's trajectory is hard to predict from an attacker's
    perspective. Uses both main drive and random heading changes.

    The jink pattern runs continuously until cancelled or until
    an optional duration expires.
    """

    def __init__(self, ship, target_id: Optional[str] = None, params: Dict = None):
        """Initialize evasive autopilot.

        Args:
            ship: Ship under control.
            target_id: Unused.
            params: Additional parameters:
                - duration: Duration in seconds (None/0 = indefinite).
                - min_interval: Minimum jink interval in seconds (default 2.0).
                - max_interval: Maximum jink interval in seconds (default 5.0).
                - min_thrust: Minimum thrust fraction (default 0.3).
                - max_thrust: Maximum thrust fraction (default 1.0).
                - seed: Optional RNG seed for deterministic testing.
        """
        super().__init__(ship, target_id, params or {})

        self.duration: Optional[float] = self.params.get("duration")
        if self.duration is not None:
            self.duration = float(self.duration)
            if self.duration <= 0:
                self.duration = None

        self.min_interval = float(self.params.get("min_interval", 2.0))
        self.max_interval = float(self.params.get("max_interval", 5.0))
        self.min_thrust = float(self.params.get("min_thrust", 0.3))
        self.max_thrust = float(self.params.get("max_thrust", 1.0))

        # RNG
        seed = self.params.get("seed")
        self._rng = random.Random(seed)

        # State
        self._start_time: Optional[float] = None
        self._next_jink_time: float = 0.0
        self._current_heading: Dict[str, float] = dict(ship.orientation)
        self._current_thrust: float = self.max_thrust
        self._jink_count: int = 0
        self.completed = False
        self.status = "active"

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------

    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute jink maneuver command.

        Args:
            dt: Time delta.
            sim_time: Current simulation time.

        Returns:
            dict with thrust and heading.
        """
        # Record start time on first call
        if self._start_time is None:
            self._start_time = sim_time
            self._pick_jink(sim_time)

        # Check duration expiry
        if self.duration is not None:
            elapsed = sim_time - self._start_time
            if elapsed >= self.duration:
                self.status = "complete"
                self.completed = True
                return {"thrust": 0.0, "heading": self.ship.orientation}

        # Time for a new jink?
        if sim_time >= self._next_jink_time:
            self._pick_jink(sim_time)

        self.status = "evading"
        return {
            "thrust": self._clamp_thrust(self._current_thrust),
            "heading": self._current_heading,
        }

    def _pick_jink(self, sim_time: float) -> None:
        """Select a new random heading and thrust level."""
        # Random heading: pick yaw and pitch offsets from current
        yaw = self._rng.uniform(-180, 180)
        pitch = self._rng.uniform(-45, 45)
        self._current_heading = {"pitch": pitch, "yaw": yaw, "roll": 0.0}

        # Random thrust magnitude
        self._current_thrust = self._rng.uniform(self.min_thrust, self.max_thrust)

        # Schedule next jink
        interval = self._rng.uniform(self.min_interval, self.max_interval)
        self._next_jink_time = sim_time + interval
        self._jink_count += 1

        logger.debug(
            f"Evasive jink #{self._jink_count}: yaw={yaw:.1f} pitch={pitch:.1f} "
            f"thrust={self._current_thrust:.2f} next in {interval:.1f}s"
        )

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> Dict:
        """Get evasive autopilot state."""
        state = super().get_state()
        elapsed = 0.0
        if self._start_time is not None and hasattr(self.ship, "sim_time"):
            elapsed = getattr(self.ship, "sim_time", 0.0) - self._start_time

        state.update({
            "phase": "evading" if not self.completed else "complete",
            "jink_count": self._jink_count,
            "elapsed": elapsed,
            "duration": self.duration,
            "complete": self.completed,
        })
        return state
