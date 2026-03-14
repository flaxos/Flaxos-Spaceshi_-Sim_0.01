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

        # Initialize fleet manager
        self.fleet_manager = FleetManager(simulator=self)

        # Event logging
        self.event_log = EventLogBuffer(maxlen=1000)
        self._event_bus = EventBus.get_instance()
        self._event_bus.subscribe_all(self._record_event)
        
    def load_ships_from_directory(self, directory):
        """
        Load ships from JSON files in a directory
        
        Args:
            directory (str): Path to directory containing ship JSON files
            
        Returns:
            int: Number of ships loaded
        """
        count = 0
        try:
            for filename in os.listdir(directory):
                if filename.endswith(".json"):
                    filepath = os.path.join(directory, filename)
                    try:
                        with open(filepath, 'r') as f:
                            config = json.load(f)
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
        3. Sensor interactions (cross-ship detection)
        4. Projectile advancement and intercept checks
        5. Remove destroyed ships
        6. Fleet manager update
        7. Advance simulation time

        Returns:
            float: Time elapsed in simulation
        """
        if not self.running:
            return self.time

        tick_start = time.monotonic()

        # Update all ships
        all_ships = list(self.ships.values())

        for ship in all_ships:
            try:
                ship._all_ships_ref = all_ships
                ship.tick(self.dt, all_ships, self.time)
            except Exception as e:
                logger.error(f"Error in ship {ship.id} tick: {e}")

        # Auto-repair: tick passive repair on all ships
        for ship in all_ships:
            try:
                ship.damage_model.tick_auto_repair(self.dt, ship.event_bus, ship.id)
            except Exception as e:
                logger.error(f"Error in auto-repair for {ship.id}: {e}")

        # Process sensor interactions
        self._process_sensor_interactions(all_ships)

        # Advance projectiles and check for intercepts
        if self.projectile_manager.active_count > 0:
            self.projectile_manager.tick(self.dt, self.time, self.ships)

        # D6: Remove destroyed ships
        destroyed_ships = [ship.id for ship in all_ships if ship.is_destroyed()]
        for ship_id in destroyed_ships:
            logger.info(f"Removing destroyed ship: {ship_id}")
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
