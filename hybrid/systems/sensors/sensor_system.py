# hybrid/systems/sensors/sensor_system.py
"""Enhanced sensor system with physics-based detection.

Detection is driven by physical emissions:
- **IR (passive)**: Detects drive plumes, radiator heat, hull thermal.
  Range is emission-dependent — a thrusting ship is visible system-wide.
- **Radar (active)**: Broad-beam EM pulse with 1/r^4 round-trip falloff.
  Detects targets by radar cross-section (RCS). Reveals pinging ship.
- **Lidar (active)**: Narrow-beam laser, higher resolution, shorter range.

Resolution degrades with distance: at long range you get bearing + rough
range, not a detailed track.
"""

import logging
from typing import List

from hybrid.core.event_bus import EventBus
from hybrid.core.base_system import BaseSystem
from hybrid.systems.sensors.passive import PassiveSensor
from hybrid.systems.sensors.active import ActiveSensor
from hybrid.systems.sensors.contact import ContactTracker
from hybrid.systems.sensors.eccm import ECCMState
from hybrid.systems.sensors.emission_model import get_ship_emissions
from hybrid.systems.sensors.sensor_probe import (
    SensorProbe, MAX_PROBES_PER_SHIP, bearing_to_unit_vector,
    _next_probe_id, PROBE_DELTA_V,
)
from hybrid.utils.math_utils import add_vectors, scale_vector
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)

class SensorSystem(BaseSystem):
    """Comprehensive sensor system with passive and active detection."""

    def __init__(self, config: dict):
        """Initialize sensor system.

        Args:
            config: Configuration dict with:
                - passive: Passive sensor config
                - active: Active sensor config
                - stale_threshold: Seconds before contacts go stale
        """
        super().__init__(config)
        self.config = config

        # Initialize subsystems
        passive_config = config.get("passive", config)  # Fallback to main config
        active_config = config.get("active", config)

        self.passive = PassiveSensor(passive_config)
        self.active = ActiveSensor(active_config)

        # Contact tracker for unified contact management
        stale_threshold = config.get("stale_threshold", 60.0)
        self.contact_tracker = ContactTracker(stale_threshold)

        # ECCM subsystem — provides counter-countermeasures for the
        # sensor pipeline (frequency hopping, burn-through, etc.)
        eccm_config = config.get("eccm", {})
        self.eccm = ECCMState(eccm_config)

        # Deployable sensor probes — launched from the ship to extend
        # passive detection coverage. Max MAX_PROBES_PER_SHIP active at once.
        self.probes: List[SensorProbe] = []

        # Simulation reference (set during tick)
        self.all_ships = []
        self.current_tick = 0
        self.sim_time = 0.0
        self._last_contact_ids = set()

    def tick(self, dt: float, ship, event_bus):
        """Update sensor system.

        Args:
            dt: Time delta
            ship: Ship with this sensor
            event_bus: Event bus for publishing events
        """
        damage_factor = 1.0
        if ship is not None and hasattr(ship, "get_effective_factor"):
            damage_factor = ship.get_effective_factor("sensors")
        elif ship is not None and hasattr(ship, "damage_model"):
            damage_factor = ship.damage_model.get_degradation_factor("sensors")

        if damage_factor <= 0.0:
            return

        # Crew skill: SCIENCE station crew affects effective sensor range.
        # A skilled science officer calibrates sensors for better resolution;
        # unmanned stations run at reduced AI-backup capability.
        from hybrid.systems.crew_binding_system import CrewBindingSystem
        from server.stations.station_types import StationType
        crew_factor = CrewBindingSystem.get_multiplier(ship.id, StationType.SCIENCE)
        effective_factor = damage_factor * crew_factor

        self.passive.set_range_multiplier(effective_factor)
        self.active.set_range_multiplier(effective_factor)

        # Update ECCM state (heat generation, sensor health tracking)
        self.eccm.set_sensor_health(damage_factor)
        self.eccm.tick(dt, ship, event_bus)

        if not self.enabled:
            return

        self.sim_time = getattr(ship, "sim_time", self.sim_time + dt)
        self.current_tick += 1

        # Get all ships from simulator (injected during simulator tick)
        # This will be set by the simulator when it calls tick
        if hasattr(ship, "_all_ships_ref"):
            self.all_ships = ship._all_ships_ref

        # Update passive sensor (pass ECCM for multi-spectral flare filtering,
        # and environment manager for radiation/nebula effects)
        env_mgr = getattr(ship, "_environment_manager_ref", None)
        self.passive.update(
            self.current_tick,
            dt,
            ship,
            self.all_ships,
            self.sim_time,
            eccm=self.eccm,
            environment_manager=env_mgr,
        )

        # Merge passive contacts into contact tracker
        for ship_id, contact in self.passive.get_contacts().items():
            self.contact_tracker.update_contact(ship_id, contact, self.sim_time)

        # Merge active contacts (from previous ping) into contact tracker
        for ship_id, contact in self.active.get_contacts().items():
            self.contact_tracker.update_contact(ship_id, contact, self.sim_time)

        # Update deployed sensor probes and merge their contacts.
        # Probes run their own PassiveSensor; we pull their detections
        # into the parent ship's contact tracker with detection_method
        # rewritten to "probe" so the operator knows the source.
        self._tick_probes(dt, self.sim_time)

        # Prune stale contacts periodically, preserving contacts whose
        # source ships still exist in the simulation
        if self.current_tick % 100 == 0:  # Every 100 ticks
            existing_ids = {s.id for s in self.all_ships if hasattr(s, "id")}
            self.contact_tracker.prune_stale_contacts(self.sim_time, existing_ids)

        # Publish sensor tick event
        event_bus.publish("sensor_tick", {
            "dt": dt,
            "ship_id": ship.id,
            "contacts": len(self.contact_tracker.get_all_contacts(self.sim_time))
        })

        self._emit_contact_events(ship, event_bus)

    def _emit_contact_events(self, ship, event_bus):
        current_contacts = self.contact_tracker.get_all_contacts(self.sim_time)
        current_ids = set(current_contacts.keys())

        new_contacts = current_ids - self._last_contact_ids
        lost_contacts = self._last_contact_ids - current_ids

        for contact_id in new_contacts:
            contact = current_contacts.get(contact_id)
            if contact:
                event_bus.publish("sensor_contact_detected", {
                    "ship_id": ship.id,
                    "contact_id": contact_id,
                    "contact": self._serialize_contact(contact),
                })

        for contact_id in lost_contacts:
            event_bus.publish("sensor_contact_lost", {
                "ship_id": ship.id,
                "contact_id": contact_id,
            })

        self._last_contact_ids = current_ids

    def _serialize_contact(self, contact):
        return {
            "id": contact.id,
            "position": contact.position,
            "velocity": contact.velocity,
            "confidence": contact.confidence,
            "last_update": contact.last_update,
            "detection_method": contact.detection_method,
            "bearing": contact.bearing,
            "distance": contact.distance,
            "signature": contact.signature,
            "classification": contact.classification,
            "name": getattr(contact, "name", None),
            "faction": getattr(contact, "faction", None),
        }

    def command(self, action: str, params: dict):
        """Handle sensor commands.

        Args:
            action: Command action
            params: Command parameters

        Returns:
            dict: Command result
        """
        if action == "ping":
            return self.ping(params)
        elif action == "get_contacts":
            return self.get_contacts_list(params)
        elif action == "status":
            return self.get_state()
        elif action == "deploy_probe":
            return self._cmd_deploy_probe(params)
        elif action == "recall_probe":
            return self._cmd_recall_probe(params)

        # ECCM commands are routed through the sensor system because
        # ECCM is a sensor capability, not an independent system.
        # The command dispatcher calls sensors.command(action, params)
        # for all eccm_* and analyze_jamming commands.
        eccm_actions = {
            "eccm_frequency_hop", "eccm_burn_through", "eccm_off",
            "eccm_multispectral", "eccm_home_on_jam", "analyze_jamming",
            "eccm_status",
        }
        if action in eccm_actions:
            # Delegate to dispatch layer (handler functions in eccm_commands.py
            # call back into self.eccm). Since the dispatch layer already
            # extracted and validated params, we just forward.
            return self._handle_eccm_command(action, params)

        return super().command(action, params)

    def _handle_eccm_command(self, action: str, params: dict) -> dict:
        """Route ECCM commands to the ECCMState.

        Args:
            action: ECCM command action.
            params: Command parameters.

        Returns:
            dict: Command result.
        """
        # Simple dispatch for stateless commands
        simple = {
            "eccm_frequency_hop": self.eccm.activate_frequency_hop,
            "eccm_burn_through": self.eccm.activate_burn_through,
            "eccm_off": self.eccm.deactivate_eccm_mode,
        }
        if action in simple:
            return simple[action]()

        if action == "eccm_multispectral":
            return self.eccm.set_multispectral(
                params.get("enabled", not self.eccm.multispectral_active))
        if action == "eccm_home_on_jam":
            return self.eccm.set_home_on_jam(
                params.get("enabled", not self.eccm.hoj_active))
        if action == "eccm_status":
            state = self.eccm.get_state()
            state["ok"] = True
            return state
        if action == "analyze_jamming":
            return self._analyze_jamming(params)

        return error_dict("UNKNOWN_ECCM_CMD", f"Unknown ECCM command: {action}")

    def _analyze_jamming(self, params: dict) -> dict:
        """Analyze target ECM emissions. Requires ship and contact_id in params."""
        ship = params.get("ship") or params.get("_ship")
        contact_id = params.get("contact_id")
        if not ship or not contact_id:
            return error_dict("MISSING_PARAMS", "Need ship and contact_id")

        contact = self.contact_tracker.get_contact(contact_id)
        original_id = contact.id if contact else contact_id
        target_ship = next(
            (s for s in (self.all_ships or [])
             if hasattr(s, "id") and s.id in (contact_id, original_id)),
            None,
        )
        if not target_ship:
            return error_dict("TARGET_NOT_FOUND", f"Cannot resolve contact '{contact_id}'")

        from hybrid.utils.math_utils import calculate_distance
        distance = calculate_distance(ship.position, target_ship.position)
        result = self.eccm.analyze_jamming(target_ship, distance)
        result["contact_id"] = contact_id
        result["distance"] = round(distance, 1)
        return result

    def ping(self, params: dict = None):
        """Execute active sensor ping.

        Args:
            params: Optional parameters

        Returns:
            dict: Ping result
        """
        if params is None:
            params = {}

        # Need ship reference from params or stored
        ship = params.get("ship")
        if not ship:
            return error_dict("NO_SHIP_REFERENCE", "Ship reference required for ping")

        # Need all_ships list (convert from dict if necessary)
        all_ships_param = self.all_ships or params.get("all_ships", [])
        # D6: Handle both dict and list formats for all_ships
        if isinstance(all_ships_param, dict):
            all_ships = list(all_ships_param.values())
        else:
            all_ships = all_ships_param

        # Need event bus
        event_bus = params.get("event_bus") or EventBus.get_instance()

        return self.active.ping(ship, all_ships, self.sim_time, event_bus,
                                eccm=self.eccm)

    def get_contacts(self) -> dict:
        """Get all current contacts.

        Returns:
            dict: Contact ID -> ContactData
        """
        return self.contact_tracker.get_all_contacts(self.sim_time)

    def get_contacts_list(self, params: dict = None):
        """Get contacts as a formatted list.

        Args:
            params: Optional parameters with:
                - observer_position: Position to calculate distance/bearing from
                - observer_velocity: Velocity to calculate closing speed (optional)
                - include_stale: Include stale contacts

        Returns:
            dict: Contact list response
        """
        if params is None:
            params = {}

        observer_position = params.get("observer_position", {"x": 0, "y": 0, "z": 0})
        observer_velocity = params.get("observer_velocity", None)
        include_stale = params.get("include_stale", False)

        if include_stale:
            contacts = self.contact_tracker.get_all_contacts(self.sim_time, include_stale=True)
            contacts_list = list(contacts.values())
        else:
            contacts_list = self.contact_tracker.get_sorted_contacts(observer_position, self.sim_time, observer_velocity)

        return success_dict(
            f"{len(contacts_list)} contacts",
            contacts=contacts_list,
            count=len(contacts_list)
        )

    def get_contact(self, contact_id: str):
        """Get a specific contact.

        Args:
            contact_id: Contact ID

        Returns:
            ContactData or None
        """
        return self.contact_tracker.get_contact(contact_id)

    def get_state(self) -> dict:
        """Get sensor system state.

        Returns:
            dict: Current state including emission data and detection modes
        """
        state = super().get_state()

        all_contacts = self.contact_tracker.get_all_contacts(self.sim_time)
        can_ping = self.active.can_ping(self.sim_time)
        ping_cooldown = self.active.get_cooldown_remaining(self.sim_time)

        # Convert contacts to serializable format
        contacts_list = [
            {
                "id": contact_id,
                "position": contact.position,
                "velocity": contact.velocity,
                "confidence": contact.confidence,
                "last_update": contact.last_update,
                "detection_method": contact.detection_method,
                "bearing": contact.bearing,
                "distance": contact.distance,
                "signature": contact.signature,
                "classification": contact.classification,
                "name": getattr(contact, "name", None),
                "faction": getattr(contact, "faction", None),
            }
            for contact_id, contact in all_contacts.items()
        ]

        # Calculate own-ship emissions (what others can see of us)
        own_emissions = None
        if self.all_ships:
            # Find own ship from all_ships list
            for s in self.all_ships:
                if hasattr(s, "id") and hasattr(s, "systems"):
                    # Check if this ship's sensor system is us
                    s_sensors = s.systems.get("sensors")
                    if s_sensors is self:
                        own_emissions = get_ship_emissions(s)
                        break

        state.update({
            "passive_range": self.passive.range,
            "active_range": self.active.range,
            "contacts": contacts_list,
            "contact_count": len(contacts_list),
            "can_ping": can_ping,
            "ping_cooldown_remaining": ping_cooldown,
            "ping_cooldown_total": self.active.cooldown,
            "detection_modes": {
                "passive": "ir",
                "active": "radar",
            },
            "own_emissions": own_emissions,
            "eccm": self.eccm.get_state(),
            "probes": [p.get_state() for p in self.probes],
        })

        return state

    # ------------------------------------------------------------------
    # Probe management
    # ------------------------------------------------------------------

    def _tick_probes(self, dt: float, sim_time: float) -> None:
        """Update all active probes and merge their contacts.

        Expired or inactive probes are pruned from the list.

        Args:
            dt: Simulation time step.
            sim_time: Current simulation time.
        """
        still_active = []
        for probe in self.probes:
            contacts = probe.update(dt, self.all_ships, sim_time)
            # Merge probe contacts into the parent ship's tracker,
            # rewriting detection_method so the operator knows the
            # contact was seen by a probe, not the ship's own sensors.
            for ship_id, contact in contacts.items():
                contact.detection_method = "probe"
                self.contact_tracker.update_contact(
                    ship_id, contact, sim_time
                )
            if probe.active:
                still_active.append(probe)
        self.probes = still_active

    def _cmd_deploy_probe(self, params: dict) -> dict:
        """Handle the deploy_probe command.

        Creates a new SensorProbe with the ship's current velocity plus
        an impulse along the commanded bearing.

        Args:
            params: Command parameters with 'bearing' and optional 'range'.

        Returns:
            Success/error dict.
        """
        ship = params.get("ship") or params.get("_ship")
        if not ship:
            return error_dict("NO_SHIP", "Ship reference required")

        # Enforce magazine limit
        active_count = sum(1 for p in self.probes if p.active)
        if active_count >= MAX_PROBES_PER_SHIP:
            return error_dict(
                "PROBE_LIMIT",
                f"Maximum {MAX_PROBES_PER_SHIP} active probes reached",
            )

        bearing = params.get("bearing", {"azimuth": 0.0, "elevation": 0.0})
        direction = bearing_to_unit_vector(bearing)

        # Launch velocity = ship velocity + impulse along bearing.
        # The full delta-v budget goes into the initial kick; the probe
        # has no further propulsion (cold-gas expended on launch).
        launch_impulse = scale_vector(direction, PROBE_DELTA_V)
        probe_velocity = add_vectors(ship.velocity, launch_impulse)

        probe_id = _next_probe_id(ship.id)
        probe = SensorProbe(
            probe_id=probe_id,
            parent_ship_id=ship.id,
            position=dict(ship.position),
            velocity=probe_velocity,
            deploy_time=self.sim_time,
        )
        self.probes.append(probe)

        logger.info(
            "Deployed probe %s from %s bearing az=%.0f el=%.0f",
            probe_id, ship.id,
            bearing.get("azimuth", 0), bearing.get("elevation", 0),
        )

        return success_dict(
            f"Probe {probe_id} deployed",
            probe_id=probe_id,
            deployment_vector=launch_impulse,
        )

    def _cmd_recall_probe(self, params: dict) -> dict:
        """Handle the recall_probe command.

        Deactivates a specific probe by ID. It will be pruned on the
        next tick.

        Args:
            params: Command parameters with 'probe_id'.

        Returns:
            Success/error dict.
        """
        probe_id = params.get("probe_id")
        if not probe_id:
            return error_dict("MISSING_PROBE_ID", "probe_id is required")

        for probe in self.probes:
            if probe.id == probe_id and probe.active:
                probe.deactivate()
                return success_dict(f"Probe {probe_id} recalled")

        return error_dict(
            "PROBE_NOT_FOUND",
            f"No active probe with id '{probe_id}'",
        )
