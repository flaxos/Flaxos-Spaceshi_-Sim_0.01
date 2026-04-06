# hybrid/systems/sensors/sensor_probe.py
"""Deployable sensor probe for extended passive detection coverage.

Sensor probes are small, expendable packages launched from a ship to
extend its passive IR detection envelope. Each probe carries a reduced-
range PassiveSensor and drifts on a ballistic trajectory after an
optional positioning burn.

Physics:
- Launched with parent ship velocity + impulse along commanded bearing
- 50 kg mass, 100 m/s delta-v from a small cold-gas thruster
- No station-keeping: probe drifts after launch
- 300-second lifespan (battery limit on a 50 kg package)

Tactical use:
- Deploy probes to cover blind spots or picket approach vectors
- Probe contacts merge into the parent ship's contact tracker with
  detection_method="probe", so the operator knows the source
- Max 4 active probes per ship (launcher magazine limit)
"""

import logging
import math
from typing import Dict, List, Optional

from hybrid.systems.sensors.passive import PassiveSensor
from hybrid.systems.sensors.contact import ContactData
from hybrid.utils.math_utils import (
    add_vectors, scale_vector, normalize_vector, magnitude,
)

logger = logging.getLogger(__name__)

# -- Probe constants --------------------------------------------------------
MAX_PROBES_PER_SHIP = 4
PROBE_MASS_KG = 50.0
PROBE_DELTA_V = 100.0        # m/s total from cold-gas thruster
PROBE_LIFESPAN_S = 300.0     # 5 minutes of battery
PROBE_SENSOR_RANGE_M = 100_000.0  # 100 km passive IR range (vs 300 km ship)
_COUNTER = 0


def _next_probe_id(ship_id: str) -> str:
    """Generate a unique probe ID scoped to the parent ship.

    Args:
        ship_id: Parent ship's ID.

    Returns:
        Unique probe identifier string.
    """
    global _COUNTER
    _COUNTER += 1
    return f"{ship_id}_probe_{_COUNTER}"


def bearing_to_unit_vector(bearing: Dict[str, float]) -> Dict[str, float]:
    """Convert azimuth/elevation bearing to a unit direction vector.

    Azimuth is measured from +X toward +Y (right-hand rule around Z).
    Elevation is measured upward from the XY plane toward +Z.

    Args:
        bearing: Dict with 'azimuth' and 'elevation' in degrees.

    Returns:
        Unit direction vector {x, y, z}.
    """
    az_rad = math.radians(bearing.get("azimuth", 0.0))
    el_rad = math.radians(bearing.get("elevation", 0.0))
    cos_el = math.cos(el_rad)
    return {
        "x": cos_el * math.cos(az_rad),
        "y": cos_el * math.sin(az_rad),
        "z": math.sin(el_rad),
    }


class SensorProbe:
    """A lightweight deployable passive-sensor package.

    Once launched, the probe drifts ballistically (Newtonian) and runs
    its onboard PassiveSensor each tick. Detected contacts are returned
    to the parent ship's sensor system for merging.
    """

    def __init__(
        self,
        probe_id: str,
        parent_ship_id: str,
        position: Dict[str, float],
        velocity: Dict[str, float],
        deploy_time: float,
    ):
        """Initialize a sensor probe.

        Args:
            probe_id: Unique identifier for this probe.
            parent_ship_id: ID of the ship that launched it.
            position: Initial position (copy of ship position at launch).
            velocity: Initial velocity (ship vel + launch impulse).
            deploy_time: Simulation time at deployment.
        """
        self.id = probe_id
        self.parent_ship_id = parent_ship_id
        self.position = dict(position)
        self.velocity = dict(velocity)
        self.deploy_time = deploy_time
        self.active = True
        self.mass = PROBE_MASS_KG

        # Passive sensor with reduced range -- a 50 kg probe can't
        # carry the same optics/processing as a full ship sensor suite.
        self.sensor = PassiveSensor({
            "passive_range": PROBE_SENSOR_RANGE_M,
            "sensor_tick_interval": 10,
            "min_signature": 1000.0,
            "ir_sensitivity": 1.0e-6,
        })

    @property
    def time_remaining(self) -> float:
        """Seconds of battery life left (computed from last update)."""
        # Stored after each update(); before first update falls back
        # to full lifespan.
        return getattr(self, "_time_remaining", PROBE_LIFESPAN_S)

    def update(
        self,
        dt: float,
        all_ships: List,
        sim_time: float,
    ) -> Dict[str, ContactData]:
        """Advance probe physics and run a passive scan.

        The probe drifts ballistically (no drag in vacuum) and scans
        for IR contacts using its onboard PassiveSensor.

        Args:
            dt: Simulation time step in seconds.
            all_ships: All ships in the simulation (for scanning).
            sim_time: Current simulation time.

        Returns:
            Dict mapping ship_id to ContactData for newly detected
            contacts, or empty dict if probe is inactive/expired.
        """
        if not self.active:
            return {}

        # Check lifespan -- battery dies after PROBE_LIFESPAN_S
        elapsed = sim_time - self.deploy_time
        self._time_remaining = max(0.0, PROBE_LIFESPAN_S - elapsed)
        if self._time_remaining <= 0.0:
            self.active = False
            logger.info(
                "Probe %s expired after %.0fs", self.id, PROBE_LIFESPAN_S
            )
            return {}

        # Newtonian drift: position += velocity * dt (no thrust, no drag)
        self.position = add_vectors(
            self.position, scale_vector(self.velocity, dt)
        )

        # Build a lightweight "observer" namespace that PassiveSensor
        # expects: .id, .position, .velocity.  The probe itself is the
        # observer, but it must not appear in the all_ships scan list.
        probe_observer = _ProbeObserver(self)

        # Tick the passive sensor -- it will populate self.sensor.contacts
        self.sensor.update(
            current_tick=int(sim_time * 10),  # synthetic tick counter
            dt=dt,
            observer_ship=probe_observer,
            all_ships=all_ships,
            sim_time=sim_time,
        )

        return self.sensor.get_contacts()

    def deactivate(self) -> None:
        """Manually deactivate the probe (recall command)."""
        self.active = False
        logger.info("Probe %s deactivated by recall", self.id)

    def get_state(self) -> Dict:
        """Serialisable snapshot for telemetry.

        Returns:
            Dict with id, position, time_remaining, contacts, active.
        """
        return {
            "id": self.id,
            "position": dict(self.position),
            "time_remaining": round(self.time_remaining, 1),
            "contacts": len(self.sensor.contacts),
            "active": self.active,
        }


class _ProbeObserver:
    """Minimal stand-in for a Ship, used by PassiveSensor.update().

    PassiveSensor expects an object with .id, .position, .velocity so
    it can calculate distance/bearing to targets and skip self-detection.
    A full Ship is too heavy to instantiate for a probe.
    """

    def __init__(self, probe: SensorProbe):
        self.id = probe.id
        self.position = probe.position
        self.velocity = probe.velocity
