# hybrid/systems/sensors/active.py
"""Active sensor system for high-accuracy detection.

Active sensors emit energy and detect the return signal:
- **Radar**: Broad-beam electromagnetic pulse. Inverse-square falloff
  both ways (1/r^4 round-trip). Detects anything with radar cross-section
  (RCS) — even cold, drifting targets. Reveals the pinging ship's position.
- **Lidar**: Narrow-beam laser pulse. Higher resolution than radar at
  close range but narrower field. Must be pointed at a known bearing.

Active pings always reveal the observer — you can't ping without
announcing your position to anyone listening.
"""

import logging
from typing import Dict, List
from hybrid.systems.sensors.contact import (
    ContactData, add_detection_noise, add_velocity_noise,
    calculate_detection_signature
)
from hybrid.systems.sensors.emission_model import (
    calculate_radar_cross_section, calculate_radar_detection_range,
    calculate_lidar_detection_range, calculate_detection_quality
)
from hybrid.utils.math_utils import calculate_distance, calculate_bearing

logger = logging.getLogger(__name__)


class ActiveSensor:
    """Active sensor for manual high-accuracy pings (radar/lidar)."""

    def __init__(self, config: dict):
        """Initialize active sensor.

        Args:
            config: Configuration dict with:
                - range: Maximum ping range in metres (hardware limit)
                - cooldown: Seconds between pings
                - power_cost: Power required per ping
                - resolution_boost: Accuracy multiplier vs passive
                - radar_power: Transmit power in watts
                - radar_sensitivity: Receiver noise floor in watts
        """
        self.range = config.get("active_range", config.get("scan_range", 500000))  # 500km default
        self.base_range = self.range
        self.cooldown = config.get("ping_cooldown", config.get("cooldown", 30.0))
        self.power_cost = config.get("ping_power_cost", config.get("power_cost", 50.0))
        self.resolution_boost = config.get("resolution_boost", 0.95)
        self.base_resolution_boost = self.resolution_boost

        # Radar transmitter/receiver parameters
        self.radar_power = config.get("radar_power", 1.0e6)  # 1 MW default
        self.radar_sensitivity = config.get("radar_sensitivity", 1.0e-12)

        self.last_ping_time = -1000.0  # Start ready
        self.contacts: Dict[str, ContactData] = {}

    def set_range_multiplier(self, multiplier: float):
        clamped = max(0.0, multiplier)
        self.range = max(0.0, self.base_range * clamped)
        self.resolution_boost = min(0.98, self.base_resolution_boost * max(0.2, clamped))

    def can_ping(self, current_time: float) -> bool:
        """Check if ping is available.

        Args:
            current_time: Current simulation time

        Returns:
            bool: True if can ping
        """
        return (current_time - self.last_ping_time) >= self.cooldown

    def get_cooldown_remaining(self, current_time: float) -> float:
        """Get remaining cooldown time.

        Args:
            current_time: Current simulation time

        Returns:
            float: Seconds remaining (0 if ready)
        """
        if self.can_ping(current_time):
            return 0.0

        return self.cooldown - (current_time - self.last_ping_time)

    def ping(self, observer_ship, all_ships: List, sim_time: float, event_bus) -> Dict[str, str]:
        """Execute an active sensor ping (radar).

        Radar ping: emits EM pulse, detects returns from targets based
        on their radar cross-section. Detection range follows the radar
        equation with 1/r^4 falloff. Reveals pinging ship to all listeners.

        Args:
            observer_ship: Ship executing the ping
            all_ships: List of all ships in simulation
            sim_time: Current simulation time
            event_bus: Event bus for publishing ping event

        Returns:
            dict: Result with ok/error and contacts detected
        """
        from hybrid.utils.errors import success_dict, error_dict

        # Cold-drift mode disables active sensors (reactor offline)
        if getattr(observer_ship, "_cold_drift_active", False):
            return error_dict(
                "COLD_DRIFT",
                "Active sensors offline — ship is in cold-drift mode"
            )

        # Check cooldown
        if not self.can_ping(sim_time):
            remaining = self.get_cooldown_remaining(sim_time)
            return error_dict(
                "PING_ON_COOLDOWN",
                f"Ping on cooldown: {remaining:.1f}s remaining"
            )

        # Check power (if power system available)
        power_system = observer_ship.systems.get("power_management") or observer_ship.systems.get("power")
        if power_system and hasattr(power_system, "request_power"):
            if not power_system.request_power(self.power_cost, "sensors"):
                return error_dict(
                    "INSUFFICIENT_POWER",
                    f"Insufficient power for ping (requires {self.power_cost})"
                )

        # Execute ping
        self.last_ping_time = sim_time
        detected = {}

        # Scale radar power by damage multiplier
        effective_radar_power = self.radar_power * (self.resolution_boost / self.base_resolution_boost)

        for target_ship in all_ships:
            # Don't detect self
            if target_ship.id == observer_ship.id:
                continue

            # Calculate distance
            distance = calculate_distance(observer_ship.position, target_ship.position)

            # Calculate target's radar cross-section
            rcs = calculate_radar_cross_section(target_ship)

            # ECM: Chaff inflates apparent RCS (target looks bigger on radar,
            # but the cloud adds position noise that degrades track quality)
            target_ecm = target_ship.systems.get("ecm")
            ecm_chaff_active = False
            ecm_chaff_noise = 0.0
            ecm_jam_factor = 1.0
            if target_ecm and hasattr(target_ecm, "is_chaff_active"):
                ecm_chaff_active = target_ecm.is_chaff_active()
                if ecm_chaff_active:
                    rcs *= target_ecm.get_chaff_rcs_multiplier()
                    ecm_chaff_noise = target_ecm.get_chaff_noise_radius()

                # Radar jamming: degrades radar quality at range
                if hasattr(target_ecm, "get_jammer_effect_at_range"):
                    ecm_jam_factor = target_ecm.get_jammer_effect_at_range(distance)

            # Calculate radar detection range for this target
            radar_range = calculate_radar_detection_range(
                rcs, effective_radar_power, self.radar_sensitivity
            )

            # Effective range: minimum of radar equation and hardware limit
            effective_range = min(radar_range, self.range)

            # Check if in range
            if distance > effective_range:
                continue

            # Calculate detection quality from radar equation
            quality = calculate_detection_quality(distance, effective_range)

            # ECM: Apply jamming degradation to quality
            quality *= ecm_jam_factor

            # Active radar gets a resolution boost over passive detection
            accuracy = min(0.98, quality * 1.2)
            accuracy = max(0.3, accuracy)  # Radar always gets decent accuracy if detected

            # Very minimal noise for active sensor
            noisy_position = add_detection_noise(target_ship.position, accuracy)
            noisy_velocity = add_velocity_noise(target_ship.velocity, accuracy)

            # ECM: Chaff adds additional position noise on top of accuracy noise
            if ecm_chaff_active and ecm_chaff_noise > 0:
                import random
                noisy_position = {
                    "x": noisy_position["x"] + random.gauss(0, ecm_chaff_noise),
                    "y": noisy_position["y"] + random.gauss(0, ecm_chaff_noise),
                    "z": noisy_position["z"] + random.gauss(0, ecm_chaff_noise),
                }

            bearing = calculate_bearing(observer_ship.position, target_ship.position)
            signature = calculate_detection_signature(target_ship)

            contact = ContactData(
                id=target_ship.id,  # Will be remapped by ContactTracker
                position=noisy_position,
                velocity=noisy_velocity,
                confidence=accuracy,
                last_update=sim_time,
                detection_method="radar",
                bearing=bearing,
                distance=distance,
                signature=signature,
                classification=target_ship.class_type if accuracy > 0.8 else "Unknown",
                name=getattr(target_ship, "name", None) if accuracy > 0.5 else None,
                faction=getattr(target_ship, "faction", None),
            )

            detected[target_ship.id] = contact

        # Update contacts
        self.contacts = detected

        # Publish ping event (makes us detectable!)
        if event_bus:
            event_bus.publish("sensor_ping", {
                "ship_id": observer_ship.id,
                "position": observer_ship.position,
                "range": self.range,
                "mode": "radar",
                "timestamp": sim_time
            })
            event_bus.publish("active_ping_complete", {
                "ship_id": observer_ship.id,
                "contacts_detected": len(detected),
                "contacts": list(detected.keys()),
                "mode": "radar",
                "timestamp": sim_time
            })
            for contact_id, contact in detected.items():
                event_bus.publish("sensor_contact_updated", {
                    "ship_id": observer_ship.id,
                    "contact_id": contact_id,
                    "contact": {
                        "position": contact.position,
                        "velocity": contact.velocity,
                        "confidence": contact.confidence,
                        "bearing": contact.bearing,
                        "distance": contact.distance,
                        "signature": contact.signature,
                        "classification": contact.classification,
                        "detection_method": contact.detection_method,
                    },
                })

        logger.info(f"Radar ping from {observer_ship.id}: {len(detected)} contacts detected")

        return success_dict(
            f"Radar ping complete: {len(detected)} contacts detected",
            contacts_detected=len(detected),
            cooldown=self.cooldown,
            next_ping_available=sim_time + self.cooldown,
            mode="radar"
        )

    def get_contacts(self) -> Dict[str, ContactData]:
        """Get current active sensor contacts.

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
