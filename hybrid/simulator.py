import time
import logging
import json
import os
from datetime import datetime
import math
import random
from hybrid.ship import Ship
from hybrid.fleet.fleet_manager import FleetManager
from hybrid.core.event_bus import EventBus
from hybrid.systems.combat.projectile_manager import ProjectileManager
from hybrid.systems.combat.torpedo_manager import TorpedoManager
from hybrid.environment.environment_manager import EnvironmentManager

logger = logging.getLogger(__name__)

class EventLogBuffer:
    """Ring buffer for simulator events."""

    def __init__(self, maxlen=1000):
        self.maxlen = maxlen
        self._events = []
        self._next_id = 1

    def append(self, event: dict):
        event = dict(event)
        event.setdefault("id", self._next_id)
        self._next_id += 1
        self._events.append(event)
        if len(self._events) > self.maxlen:
            del self._events[:-self.maxlen]

    def get_recent(self, limit=100):
        if limit is None:
            return list(self._events)
        return self._events[-limit:]

    def __len__(self):
        return len(self._events)

    def __iter__(self):
        return iter(self._events)

    def __getitem__(self, item):
        return self._events[item]

class Simulator:
    """
    Ship simulator that manages multiple ships and handles simulation ticks.
    """
    
    def __init__(self, dt=0.1, time_scale=1.0):
        """
        Initialize the simulator

        Args:
            dt (float): Simulation time step in seconds
            time_scale (float): Time scale multiplier (1.0 = real-time,
                2.0 = double speed, 0.5 = half speed). Allows decoupling
                physics from wall-clock for testing.
        """
        self.ships = {}
        self.dt = dt
        self.time_scale = max(0.01, float(time_scale))
        self.running = False
        self.time = 0.0

        # Tick tracking for performance metrics
        self.tick_count = 0
        self._tick_times = []  # recent tick durations for avg calculation
        self._max_tick_samples = 100

        # Projectile simulation
        self.projectile_manager = ProjectileManager()

        # Torpedo simulation
        self.torpedo_manager = TorpedoManager()

        # Environmental hazards (asteroid fields, radiation, debris, nebulae)
        self.environment_manager = EnvironmentManager()

        # Initialize fleet manager
        self.fleet_manager = FleetManager(simulator=self)

        # Event logging
        self.event_log = EventLogBuffer(maxlen=1000)
        self._event_bus = EventBus.get_instance()
        self._event_bus.subscribe_all(self._record_event)

        # Combat feedback log (causal chain narratives)
        from hybrid.systems.combat.combat_log import get_combat_log
        self.combat_log = get_combat_log()
        
    def load_ships_from_directory(self, directory):
        """
        Load ships from JSON files in a directory.

        If a ship config contains a ``ship_class`` field, its class template
        is resolved from the ship class registry before creating the ship.

        Args:
            directory (str): Path to directory containing ship JSON files

        Returns:
            int: Number of ships loaded
        """
        from hybrid.ship_class_registry import resolve_ship_config

        count = 0
        try:
            for filename in os.listdir(directory):
                if filename.endswith(".json"):
                    filepath = os.path.join(directory, filename)
                    try:
                        with open(filepath, 'r') as f:
                            config = json.load(f)
                        config = resolve_ship_config(config)
                        ship_id = config.get("id") or os.path.splitext(filename)[0]
                        self.add_ship(ship_id, config)
                        count += 1
                        logger.info(f"Loaded ship {ship_id} from {filepath}")
                    except Exception as e:
                        logger.error(f"Failed to load ship from {filepath}: {e}")
        except Exception as e:
            logger.error(f"Failed to load ships from directory {directory}: {e}")

        return count
        
    def add_ship(self, ship_id, config):
        """
        Add a ship to the simulation
        
        Args:
            ship_id (str): Unique identifier for the ship
            config (dict): Ship configuration
            
        Returns:
            Ship: The created ship
        """
        ship = Ship(ship_id, config)
        if hasattr(ship, "event_bus"):
            ship.event_bus.subscribe_all(
                lambda event_name, payload, ship_id=ship.id: self._record_event(
                    event_name,
                    payload,
                    ship_id=ship_id
                )
            )
        self.ships[ship_id] = ship
        # Inject fleet manager into fleet_coord system if present
        fleet_coord = ship.systems.get("fleet_coord")
        if fleet_coord and hasattr(fleet_coord, "set_fleet_manager"):
            fleet_coord.set_fleet_manager(self.fleet_manager)
        return ship
        
    def remove_ship(self, ship_id):
        """
        Remove a ship from the simulation
        
        Args:
            ship_id (str): Unique identifier for the ship to remove
            
        Returns:
            bool: True if ship was removed, False otherwise
        """
        if ship_id in self.ships:
            del self.ships[ship_id]
            return True
        return False
        
    def get_ship(self, ship_id):
        """
        Get a ship by ID
        
        Args:
            ship_id (str): Unique identifier for the ship
            
        Returns:
            Ship: The ship, or None if not found
        """
        return self.ships.get(ship_id)
        
    def start(self):
        """
        Start the simulation
        
        Returns:
            bool: True if simulation was started, False otherwise
        """
        if self.running:
            return False
            
        self.running = True
        logger.info(f"Simulation started with {len(self.ships)} ships")
        return True
        
    def stop(self):
        """
        Stop the simulation
        
        Returns:
            bool: True if simulation was stopped, False otherwise
        """
        if not self.running:
            return False
            
        self.running = False
        logger.info("Simulation stopped")
        return True
        
    def tick(self):
        """Run a single simulation tick.

        Tick order:
        1. Ship systems update (propulsion sets acceleration, RCS sets angular vel)
        2. Auto-repair tick (gradual passive repair)
        3. Environment tick (asteroid drift, ship-asteroid collisions)
        4. Sensor interactions (cross-ship detection)
        5. Projectile advancement and intercept checks
        6. Remove destroyed ships
        7. Fleet manager update
        8. Advance simulation time

        Returns:
            float: Time elapsed in simulation
        """
        if not self.running:
            return self.time

        tick_start = time.monotonic()

        # Stamp combat log with current sim_time before any events fire
        self.combat_log.update_time(self.time)

        # Update all ships
        all_ships = list(self.ships.values())

        for ship in all_ships:
            try:
                ship._all_ships_ref = all_ships
                ship._environment_manager_ref = self.environment_manager
                ship._simulator_ref = self
                # Inject projectile_manager and torpedo_manager into combat system
                combat = ship.systems.get("combat")
                if combat and hasattr(combat, "_projectile_manager"):
                    combat._projectile_manager = self.projectile_manager
                if combat and hasattr(combat, "_torpedo_manager"):
                    combat._torpedo_manager = self.torpedo_manager
                # Inject fleet manager into fleet_coord system
                fleet_coord = ship.systems.get("fleet_coord")
                if fleet_coord and hasattr(fleet_coord, "set_fleet_manager"):
                    fleet_coord.set_fleet_manager(self.fleet_manager)
                ship.tick(self.dt, all_ships, self.time)
            except Exception as e:
                logger.error(f"Error in ship {ship.id} tick: {e}")

        # Auto-repair: tick passive repair on all ships
        for ship in all_ships:
            try:
                ship.damage_model.tick_auto_repair(self.dt, ship.event_bus, ship.id)
            except Exception as e:
                logger.error(f"Error in auto-repair for {ship.id}: {e}")

        # Environment: advance asteroid drift, check ship-asteroid collisions
        self.environment_manager.tick(self.dt)
        self.environment_manager.check_ship_collisions(
            all_ships, self.dt, self._event_bus,
        )

        # Process sensor interactions
        self._process_sensor_interactions(all_ships)

        # Advance projectiles and check for intercepts.
        # Pass environment_manager so slugs that hit asteroids are absorbed.
        self.projectile_manager.tick(
            self.dt, self.time, self.ships, self.environment_manager,
        )

        # Advance torpedoes (guided munitions with their own drive).
        # Pass environment_manager so debris degrades guidance and
        # nebulae sever datalink.
        self.torpedo_manager.tick(
            self.dt, self.time, self.ships, self.environment_manager,
        )

        # PDC auto-interception of incoming torpedoes
        self._process_pdc_torpedo_intercept(all_ships)

        # D6: Remove destroyed ships.
        # Publish ship_destroyed on the global event bus BEFORE removal so
        # that subscribers (targeting, AI, mission logic) hear about it.
        # The ship's own event_bus fires ship_destroyed in Ship.apply_damage,
        # but systems subscribed to the simulator-level bus never see that.
        destroyed_ships = [ship.id for ship in all_ships if ship.is_destroyed()]
        for ship_id in destroyed_ships:
            logger.info(f"Removing destroyed ship: {ship_id}")
            self._event_bus.publish("ship_destroyed", {
                "ship_id": ship_id,
                "source": "hull_destroyed",
            })
            self.remove_ship(ship_id)

        # Update fleet manager
        self.fleet_manager.update(self.dt)

        # Update simulation time
        self.time += self.dt
        self.tick_count += 1

        # Track tick performance
        tick_duration = time.monotonic() - tick_start
        self._tick_times.append(tick_duration)
        if len(self._tick_times) > self._max_tick_samples:
            del self._tick_times[:-self._max_tick_samples]

        return self.time

    def get_tick_metrics(self) -> dict:
        """Get physics tick performance metrics.

        Returns:
            dict: Tick rate, average tick time, time_scale, etc.
        """
        avg_tick = (
            sum(self._tick_times) / len(self._tick_times)
            if self._tick_times else 0.0
        )
        return {
            "tick_count": self.tick_count,
            "physics_dt": self.dt,
            "tick_rate_hz": 1.0 / self.dt if self.dt > 0 else 0,
            "time_scale": self.time_scale,
            "sim_time": self.time,
            "avg_tick_ms": avg_tick * 1000,
            "active_projectiles": self.projectile_manager.active_count,
            "active_torpedoes": self.torpedo_manager.active_count,
            "asteroid_fields": len(self.environment_manager.asteroid_fields),
            "hazard_zones": len(self.environment_manager.hazard_zones),
        }

    def _record_event(self, event_name, payload, ship_id=None):
        payload = payload or {}
        event_ship_id = payload.get("ship_id") or ship_id
        self.event_log.append({
            "type": event_name,
            "ship_id": event_ship_id,
            "t": self.time,
            "timestamp": time.time(),
            "data": payload,
        })

    def get_recent_events(self, limit=100):
        return self.event_log.get_recent(limit)
        
    def run(self, duration=None):
        """
        Run the simulation for a specified duration
        
        Args:
            duration (float, optional): Duration to run in seconds
            
        Returns:
            float: Time elapsed in simulation
        """
        if not self.running:
            self.start()
            
        start_time = time.time()
        end_time = start_time + duration if duration else None

        try:
            while self.running:
                tick_start = time.time()
                self.tick()

                # Check if we've reached the end time
                if end_time and time.time() >= end_time:
                    break

                # Throttle to real-time: sleep the remainder of dt so
                # simulation seconds match wall-clock seconds.
                elapsed = time.time() - tick_start
                sleep_time = self.dt - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
        except KeyboardInterrupt:
            logger.info("Simulation interrupted by user")
        except Exception as e:
            logger.error(f"Error in simulation loop: {e}")
            self.running = False
            
        return self.time
        
    def _process_pdc_torpedo_intercept(self, all_ships):
        """Process PDC interception of incoming torpedoes across all defense modes.

        Modes:
            auto     -- Engage closest incoming torpedo, one target per PDC
            priority -- Engage targets in human-specified priority order,
                        fall back to closest-first for unlisted threats
            network  -- Coordinate 2+ PDCs to avoid double-engaging the same
                        torpedo; round-robin assignment across the threat list
            manual   -- No auto-engagement; PDCs only fire on explicit command
            hold_fire-- All PDCs disabled, cease fire

        After destroying a target, a PDC enters a 0.2 s re-acquisition delay
        that models realistic tracker slew time before engaging the next threat.
        All engagements are logged to the combat log for the weapons status panel.

        Args:
            all_ships: List of all ships in simulation
        """
        from hybrid.utils.math_utils import calculate_distance
        from hybrid.systems.weapons.truth_weapons import pdc_range_accuracy

        for ship in all_ships:
            combat = ship.systems.get("combat") if hasattr(ship, "systems") else None
            if not combat or not hasattr(combat, "truth_weapons"):
                continue

            # Get torpedoes targeting this ship
            incoming = self.torpedo_manager.get_torpedoes_targeting(ship.id)
            if not incoming:
                # No threats — clear stale network engagements
                combat._pdc_engagements.clear()
                continue

            sim_time = getattr(ship, "sim_time", self.time)

            # Collect enabled PDC mounts and their current mode
            pdc_mounts = []
            for mount_id, weapon in combat.truth_weapons.items():
                if not mount_id.startswith("pdc"):
                    continue
                if not weapon.enabled:
                    continue
                mode = getattr(weapon, "pdc_mode", "auto")
                if mode in ("manual", "hold_fire"):
                    continue
                pdc_mounts.append((mount_id, weapon, mode))

            if not pdc_mounts:
                continue

            # Pre-compute distances for every incoming torpedo
            torp_distances = {}
            for torp in incoming:
                torp_distances[torp.id] = calculate_distance(ship.position, torp.position)

            # Sort incoming by distance (closest first) — used by auto and
            # as fallback for priority mode
            sorted_by_dist = sorted(incoming, key=lambda t: torp_distances[t.id])

            # Build a lookup for fast torpedo access by ID
            torp_by_id = {t.id: t for t in incoming}

            # ---- Determine target assignment per PDC based on mode ----
            # assignments: {mount_id: torpedo_object | None}
            assignments: dict = {}

            # Detect if any PDC is in network mode — if so, coordinate all
            # auto/network PDCs together so they don't double-engage.
            any_network = any(m == "network" for _, _, m in pdc_mounts)

            if any_network:
                # Network mode: distribute threats across PDCs round-robin.
                # Existing engagements are preserved until the target is
                # destroyed or moves out of range.
                in_range = [
                    t for t in sorted_by_dist
                    if torp_distances[t.id] < pdc_mounts[0][1].specs.effective_range
                ]
                # Remove stale engagements (target destroyed or out of range)
                live_ids = {t.id for t in in_range}
                stale = [
                    mid for mid, tid in combat._pdc_engagements.items()
                    if tid not in live_ids
                ]
                for mid in stale:
                    del combat._pdc_engagements[mid]

                # Already-assigned torpedo IDs
                assigned_torps = set(combat._pdc_engagements.values())
                # PDCs that need a new target
                unassigned_pdcs = [
                    (mid, w) for mid, w, _ in pdc_mounts
                    if mid not in combat._pdc_engagements
                ]
                # Torpedoes not yet covered by any PDC
                uncovered = [t for t in in_range if t.id not in assigned_torps]

                # Round-robin: assign one uncovered torpedo per free PDC
                for (mid, w), torp in zip(unassigned_pdcs, uncovered):
                    combat._pdc_engagements[mid] = torp.id

                # Build final assignments from engagement map
                for mid, w, _ in pdc_mounts:
                    tid = combat._pdc_engagements.get(mid)
                    assignments[mid] = torp_by_id.get(tid) if tid else None

            else:
                # Per-PDC independent assignment (auto or priority)
                for mount_id, weapon, mode in pdc_mounts:
                    if mode == "priority":
                        target = self._pick_priority_target(
                            combat.pdc_priority_targets,
                            sorted_by_dist,
                            torp_distances,
                            weapon.specs.effective_range,
                        )
                    else:
                        # Auto mode: closest in range
                        target = None
                        for torp in sorted_by_dist:
                            if torp_distances[torp.id] < weapon.specs.effective_range:
                                target = torp
                                break
                    assignments[mount_id] = target

            # ---- Fire each PDC at its assigned target ----
            # Each PDC fires a full burst (burst_count rounds). Every
            # round gets its own hit roll, consumes 1 ammo, and generates
            # heat. The torpedo is destroyed if ANY round in the burst
            # connects. This models realistic CIWS suppression fire rather
            # than the old single-roll binary outcome.
            for mount_id, weapon, mode in pdc_mounts:
                target = assignments.get(mount_id)
                if target is None:
                    continue

                # Re-acquisition delay: PDC is slewing to new target after a kill
                if mount_id in combat._pdc_reacquire_timers:
                    continue

                if not weapon.can_fire(sim_time):
                    continue

                dist = torp_distances.get(target.id, float("inf"))
                hit_chance = pdc_range_accuracy(dist)

                # Ensure per-PDC stats exist (safety net for hot-added mounts)
                if mount_id not in combat.pdc_stats:
                    combat.pdc_stats[mount_id] = {
                        "intercepts": 0, "misses": 0, "engagements": 0,
                    }
                combat.pdc_stats[mount_id]["engagements"] += 1

                # -- Per-round burst loop --
                # burst_count rounds, each with independent hit roll,
                # ammo consumption, and heat generation.
                rounds_fired = 0
                burst_hits = 0
                destroyed = False

                for _round_i in range(weapon.specs.burst_count):
                    # Stop if out of ammo
                    if weapon.ammo is not None and weapon.ammo <= 0:
                        break

                    rounds_fired += 1

                    # Consume 1 round of ammo
                    if weapon.ammo is not None:
                        weapon.ammo -= 1

                    # Per-round heat: PDC turret generates modest heat per
                    # round. 10 rounds * 1.0 heat = 10 heat per burst, which
                    # is sustainable (max_heat=100, dissipation=5/s) but
                    # continuous defensive fire will accumulate.
                    weapon.heat += 1.0

                    # Independent hit roll for this round
                    if not destroyed and random.random() < hit_chance:
                        burst_hits += 1
                        # Apply single-round damage to the torpedo
                        result = self.torpedo_manager.apply_pdc_damage(
                            target.id, weapon.specs.base_damage,
                            source=f"{ship.id}:{mount_id}",
                        )
                        if result.get("destroyed", False):
                            destroyed = True
                            # Remaining rounds in the burst still fire into
                            # debris (ammo/heat consumed) but cannot hit again.

                    # Stop burst if weapon overheats mid-burst
                    if weapon.heat >= weapon.max_heat * 0.95:
                        break

                # Record cooldown — weapon has fired its burst
                weapon.last_fired = sim_time

                # Update stats
                if burst_hits > 0:
                    combat.pdc_stats[mount_id]["intercepts"] += 1
                else:
                    combat.pdc_stats[mount_id]["misses"] += 1

                if destroyed:
                    # Start re-acquisition delay before engaging next threat
                    combat._pdc_reacquire_timers[mount_id] = combat._pdc_reacquire_delay
                    # Free network engagement slot so another PDC can assist
                    if mount_id in combat._pdc_engagements:
                        del combat._pdc_engagements[mount_id]

                # Publish engagement event — the combat log subscribes to
                # pdc_torpedo_engage via EventBus and builds narrative entries
                # automatically (see combat_log.py _on_pdc_torpedo_engage).
                self._event_bus.publish("pdc_torpedo_engage", {
                    "ship_id": ship.id,
                    "pdc_mount": mount_id,
                    "torpedo_id": target.id,
                    "distance": dist,
                    "hit": burst_hits > 0,
                    "destroyed": destroyed,
                    "rounds_fired": rounds_fired,
                    "burst_hits": burst_hits,
                    "mode": mode,
                })

    @staticmethod
    def _pick_priority_target(
        priority_list: list,
        sorted_by_dist: list,
        torp_distances: dict,
        effective_range: float,
    ):
        """Select the highest-priority torpedo within PDC range.

        Walks the human-specified priority list first. If none of those
        are in range, falls back to closest-first (auto behaviour).

        Args:
            priority_list: Ordered torpedo IDs from set_pdc_priority command
            sorted_by_dist: Torpedoes sorted closest-first
            torp_distances: {torpedo_id: distance_m} lookup
            effective_range: PDC effective range in metres

        Returns:
            Torpedo object or None
        """
        torp_by_id = {t.id: t for t in sorted_by_dist}
        # Walk priority list: first one that is in range wins
        for tid in priority_list:
            if tid in torp_by_id and torp_distances.get(tid, float("inf")) < effective_range:
                return torp_by_id[tid]
        # Fallback: closest in range (same as auto)
        for torp in sorted_by_dist:
            if torp_distances[torp.id] < effective_range:
                return torp
        return None

    def _process_sensor_interactions(self, all_ships):
        """Process sensor interactions between ships.

        Passive detection is handled by SensorSystem.tick() via PassiveSensor,
        which runs during the ship tick phase above.  This method only handles
        active sensor pings that need cross-ship visibility (e.g. ping results
        arriving from the physics step).

        Historical note: an old code path duplicated passive detection here
        using raw dicts, bypassing the ContactTracker pipeline.  That path was
        dead code once SensorSystem replaced plain-dict sensors — removed to
        avoid confusion.

        Args:
            all_ships (list): List of all ships in simulation
        """
        for ship in all_ships:
            if "sensors" in ship.systems:
                sensor_system = ship.systems["sensors"]
                if hasattr(sensor_system, 'process_active_ping'):
                    sensor_system.process_active_ping(all_ships)
