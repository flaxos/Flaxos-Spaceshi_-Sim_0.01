# hybrid/systems/sensors/passive.py
"""Passive sensor system for background detection.

Passive sensors detect targets based on their physical emissions:
- **IR (infrared)**: Detects drive plumes, radiator heat, hull thermal.
  A ship burning hard at 5g is visible across the system; a cold drifter
  might only appear at short range.

Detection range is emission-driven — the sensor doesn't have an arbitrary
range cap. Instead, it detects anything whose IR flux exceeds the sensor's
noise floor at the given distance. The hardware ``passive_range`` acts as
an upper bound (sensor saturation / processing limit).

Resolution degrades with distance: at long range you get a bearing and
maybe a rough range, not a detailed track.
"""

import logging
import random
from typing import Dict, List
from hybrid.systems.sensors.contact import (
    ContactData, ContactState, add_detection_noise, add_velocity_noise,
    calculate_detection_signature, calculate_detection_accuracy
)
from hybrid.systems.sensors.emission_model import (
    calculate_ir_signature, calculate_ir_detection_range,
    calculate_detection_quality
)
from hybrid.utils.math_utils import calculate_distance, calculate_bearing

logger = logging.getLogger(__name__)


class PassiveSensor:
    """Passive sensor for continuous background scanning.

    Detection is emission-driven: the sensor detects IR sources whose
    flux exceeds the noise floor at the target's distance. A thrusting
    ship has an enormous IR signature and can be seen system-wide;
    a cold drifting ship might only appear at close range.
    """

    # How long a LOST contact persists before removal (seconds).
    # 30s gives the player time to react to "we lost track of something
    # that was there a moment ago" without cluttering the display with
    # ancient ghost returns.
    LOST_PERSISTENCE_SECONDS: float = 30.0

    def __init__(self, config: dict):
        """Initialize passive sensor.

        Args:
            config: Configuration dict with:
                - range: Maximum hardware detection range in metres
                - update_interval: Ticks between updates
                - min_signature: Minimum IR watts to attempt detection
                - ir_sensitivity: Sensor noise floor (W/m^2), lower = better
        """
        # Hardware cap: max range sensor electronics can process.
        # 300km default — a burning ship's IR is detectable at hundreds of km
        # in vacuum; the limit is sensor processing, not physics.
        self.range = config.get("passive_range", config.get("range", 300000))
        self.base_range = self.range
        self.update_interval = config.get("sensor_tick_interval", config.get("update_interval", 10))
        # Minimum IR emission (watts) to even attempt detection
        self.min_signature = config.get("min_signature", 1000.0)
        # Sensor noise floor — lower = more sensitive IR detector
        self.ir_sensitivity = config.get("ir_sensitivity", 1.0e-6)

        self.contacts: Dict[str, ContactData] = {}
        # Initialize to negative value so first tick triggers immediate scan
        self.last_update_tick = -self.update_interval

    def set_range_multiplier(self, multiplier: float):
        self.range = max(0.0, self.base_range * max(0.0, multiplier))

    def update(self, current_tick: int, dt: float, observer_ship,
               all_ships: List, sim_time: float, eccm=None,
               environment_manager=None):
        """Update passive sensor contacts.

        Detection is emission-based: for each potential target, calculate
        its IR signature, determine the range at which that signature is
        detectable by this sensor, and check if the target is within that
        range. Resolution degrades with distance.

        Environmental modifiers:
        - Radiation zones reduce effective detection range (IR noise floor
          is raised by ambient radiation, drowning out weaker signatures).
        - Nebulae block LOS entirely: if the line between observer and
          target passes through a nebula, detection fails regardless of
          signal strength.

        Args:
            current_tick: Current simulation tick
            dt: Time delta
            observer_ship: Ship with this sensor
            all_ships: List of all ships in simulation
            sim_time: Current simulation time
            eccm: Optional ECCMState for multi-spectral flare filtering
            environment_manager: Optional EnvironmentManager for sensor
                range modifiers and LOS blocking
        """
        # Only update at specified interval
        if current_tick - self.last_update_tick < self.update_interval:
            return

        initial_scan = self.last_update_tick < 0
        self.last_update_tick = current_tick

        # Scan for contacts.
        # Use spatial grid if available for O(n*k) instead of O(n^2).
        # The grid returns candidates in nearby cells; exact distance
        # checks still happen below, so correctness is unchanged.
        spatial_grid = getattr(observer_ship, '_spatial_grid', None)
        if spatial_grid is not None:
            candidates = spatial_grid.query_radius(
                observer_ship.position, self.range
            )
        else:
            candidates = all_ships

        detected = {}

        for target_ship in candidates:
            # Don't detect self
            if target_ship.id == observer_ship.id:
                continue

            # Calculate distance
            distance = calculate_distance(observer_ship.position, target_ship.position)

            # Calculate target's IR emission
            ir_watts = calculate_ir_signature(target_ship)

            # ECM: If target has active flares, the flare IR competes with
            # real signature, degrading passive lock quality (not range).
            # Flares create a decoy source that adds noise to bearing.
            ecm_flare_active = False
            ecm_flare_ir = 0.0
            target_ecm = target_ship.systems.get("ecm")
            if target_ecm and hasattr(target_ecm, "is_flare_active"):
                ecm_flare_active = target_ecm.is_flare_active()
                if ecm_flare_active:
                    ecm_flare_ir = target_ecm.get_flare_ir_power()

            # Skip targets with negligible emissions
            if ir_watts < self.min_signature:
                continue

            # Calculate the range at which this target's IR is detectable
            # by this sensor's noise floor
            ir_range = calculate_ir_detection_range(ir_watts, self.ir_sensitivity)

            # Effective detection range: minimum of emission-based range and
            # sensor hardware limit (processing/saturation cap)
            effective_range = min(ir_range, self.range)

            # Environment: radiation zones raise the IR noise floor,
            # reducing effective detection range.  Apply modifier for
            # the observer's position (the sensor is in the noisy zone).
            if environment_manager is not None:
                env_mod = environment_manager.get_sensor_modifier(
                    observer_ship.position,
                )
                effective_range *= env_mod

                # Nebula LOS block: if a nebula sits between observer
                # and target, the signal is fully absorbed.
                if environment_manager.check_los_blocked(
                    observer_ship.position, target_ship.position,
                ):
                    continue

            # Check if target is within detection range
            if distance > effective_range:
                continue

            # Calculate detection quality (resolution degrades with distance).
            # Use the emission-based IR range, not the hardware-capped range,
            # as the quality denominator. The hardware cap gates whether we
            # detect the target at all (yes/no), but quality should reflect
            # actual signal-to-noise: a 10 MW drive plume at 200km is an
            # absurdly bright source even if our sensor electronics max out
            # at 200km processing range. Capping quality to hardware range
            # would make a burning ship at 200km look like a barely-visible
            # contact when it's actually blindingly obvious.
            quality_range = max(ir_range, effective_range)
            quality = calculate_detection_quality(distance, quality_range)

            # ECM: Flares degrade tracking quality — the decoy confuses
            # bearing/range resolution. More effective when flare IR is
            # comparable to target's real signature.
            if ecm_flare_active and ecm_flare_ir > 0:
                # ECCM: Multi-spectral correlation reduces flare effect by
                # cross-referencing radar (flare has tiny RCS) and lidar
                # (small physical size) to distinguish decoy from real ship
                effective_flare_ir = ecm_flare_ir
                if eccm is not None:
                    flare_reduction = eccm.get_flare_reduction(
                        has_ir=True, has_radar=True, has_lidar=True
                    )
                    effective_flare_ir *= (1.0 - flare_reduction)

                # Ratio of flare IR to target IR — higher = more confusion
                flare_ratio = min(1.0, effective_flare_ir / max(ir_watts, 1.0))
                # At flare_ratio=1 (flare matches target), quality halved
                quality *= max(0.2, 1.0 - flare_ratio * 0.5)

            accuracy = min(0.95, max(0.1, quality))

            # Detection probability
            detection_probability = min(0.95, accuracy)

            # Random detection check (skip on initial scan to populate immediately)
            if not initial_scan:
                if random.random() > detection_probability:
                    continue

            # Determine detection method based on what's driving the detection
            detection_method = "ir"

            # Create contact with noise proportional to quality
            noisy_position = add_detection_noise(target_ship.position, accuracy)
            noisy_velocity = add_velocity_noise(target_ship.velocity, accuracy * 0.7)

            bearing = calculate_bearing(observer_ship.position, target_ship.position)

            contact = ContactData(
                id=target_ship.id,  # Will be remapped by ContactTracker
                position=noisy_position,
                velocity=noisy_velocity,
                confidence=accuracy,
                last_update=sim_time,
                detection_method=detection_method,
                bearing=bearing,
                distance=distance,
                signature=ir_watts,
                classification=self._classify_contact(target_ship, accuracy),
                name=getattr(target_ship, "name", None) if accuracy > 0.5 else None,
                faction=getattr(target_ship, "faction", None),
            )

            detected[target_ship.id] = contact

        # Merge new detections with existing contacts.
        # Contacts that fail re-detection transition to LOST with decaying
        # confidence instead of vanishing instantly. This gives the player
        # a "last-known position" with growing uncertainty circle, rather
        # than a target blinking in and out of existence.
        for existing_id, existing_contact in self.contacts.items():
            if existing_id not in detected:
                # First missed scan: transition to LOST, snapshot position
                if existing_contact.contact_state != ContactState.LOST.value:
                    existing_contact.contact_state = ContactState.LOST.value
                    existing_contact.lost_since = sim_time
                    existing_contact.last_known_position = dict(existing_contact.position)
                    logger.debug(
                        f"Contact {existing_id} -> LOST on {observer_ship.id}"
                    )

                # Decay confidence while LOST (faster than normal degradation
                # because we have no new data at all, not just noisy data)
                existing_contact.confidence *= 0.90
                existing_contact.confidence = max(existing_contact.confidence, 0.02)

                # Check LOST timeout: remove contacts that have been LOST
                # longer than the persistence window
                lost_age = sim_time - (existing_contact.lost_since or sim_time)
                if lost_age >= self.LOST_PERSISTENCE_SECONDS:
                    logger.debug(
                        f"Contact {existing_id} expired after "
                        f"{lost_age:.0f}s LOST on {observer_ship.id}"
                    )
                    continue  # Don't carry into detected — effectively removed

                detected[existing_id] = existing_contact
            else:
                new_contact = detected[existing_id]
                # Re-detection clears LOST state: the target is back
                if existing_contact.contact_state == ContactState.LOST.value:
                    logger.debug(
                        f"Contact {existing_id} re-acquired on {observer_ship.id}"
                    )
                new_contact.confidence = max(new_contact.confidence, existing_contact.confidence)
                # Clear LOST tracking on re-detection
                new_contact.lost_since = None
                new_contact.last_known_position = None

        self.contacts = detected

        logger.debug(f"Passive IR sensor on {observer_ship.id}: {len(detected)} contacts")

    def _classify_contact(self, target_ship, accuracy: float) -> str:
        """Attempt to classify a contact based on accuracy.

        At low accuracy (long range), classification is impossible.
        At medium accuracy, only size class is available.
        At high accuracy (close range or bright target), full class.

        Args:
            target_ship: Target ship object
            accuracy: Detection accuracy

        Returns:
            str: Classification or "Unknown"
        """
        if accuracy < 0.6:
            return "Unknown"

        if accuracy > 0.9:
            return target_ship.class_type  # Full classification
        elif accuracy > 0.7:
            if target_ship.mass > 100000:
                return "Large"
            elif target_ship.mass > 10000:
                return "Medium"
            else:
                return "Small"

        return "Unknown"

    def get_contacts(self) -> Dict[str, ContactData]:
        """Get current passive contacts.

        Returns:
            dict: Contact ID -> ContactData
        """
        return dict(self.contacts)

    def get_contact(self, contact_id: str) -> ContactData:
        """Get a specific contact.

        Args:
            contact_id: Contact ID

        Returns:
            ContactData or None
        """
        return self.contacts.get(contact_id)
