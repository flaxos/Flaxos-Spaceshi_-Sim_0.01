import time
import logging
import json
import os
from datetime import datetime
import math
import random
from hybrid.ship import Ship

logger = logging.getLogger(__name__)

class Simulator:
    """
    Ship simulator that manages multiple ships and handles simulation ticks.
    """
    
    def __init__(self, dt=0.1):
        """
        Initialize the simulator
        
        Args:
            dt (float): Simulation time step in seconds
        """
        self.ships = {}
        self.dt = dt
        self.running = False
        self.time = 0.0
        
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
        """
        Run a single simulation tick
        
        Returns:
            float: Time elapsed in simulation
        """
        if not self.running:
            return self.time
            
        # Update all ships
        all_ships = list(self.ships.values())
        
        for ship in all_ships:
            ship.tick(self.dt, all_ships)
            
        # Process sensor interactions
        self._process_sensor_interactions(all_ships)
            
        # Update simulation time
        self.time += self.dt
        
        return self.time
        
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
                self.tick()
                
                # Check if we've reached the end time
                if end_time and time.time() >= end_time:
                    break
                    
                # Sleep to maintain real-time simulation if needed
                # Uncomment if you want real-time simulation
                # time.sleep(max(0, self.dt - (time.time() - tick_start)))
        except KeyboardInterrupt:
            logger.info("Simulation interrupted by user")
        except Exception as e:
            logger.error(f"Error in simulation loop: {e}")
            self.running = False
            
        return self.time
        
    def _process_sensor_interactions(self, all_ships):
        """
        Process sensor interactions between ships

        Args:
            all_ships (list): List of all ships in simulation
        """
        # Process active sensor pings
        for ship in all_ships:
            if "sensors" in ship.systems:
                sensor_system = ship.systems["sensors"]
                if hasattr(sensor_system, 'process_active_ping'):
                    sensor_system.process_active_ping(all_ships)

        # Handle passive detection between each pair of ships
        for i in range(len(all_ships)):
            for j in range(i + 1, len(all_ships)):
                self._check_passive_detection(all_ships[i], all_ships[j])
                self._check_passive_detection(all_ships[j], all_ships[i])

    def _check_passive_detection(self, observer_ship, target_ship):
        """Check if observer ship can detect target ship with passive sensors."""
        if "sensors" not in observer_ship.systems:
            return

        sensor_system = observer_ship.systems["sensors"]

        # Determine passive range (support old and new sensor implementations)
        passive_range = getattr(sensor_system, "passive_range", None)
        if passive_range is None and hasattr(sensor_system, "passive") and isinstance(sensor_system.passive, dict):
            passive_range = sensor_system.passive.get("range")

        if not passive_range:
            return

        # Calculate distance
        dx = target_ship.position["x"] - observer_ship.position["x"]
        dy = target_ship.position["y"] - observer_ship.position["y"]
        dz = target_ship.position["z"] - observer_ship.position["z"]
        distance = math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)

        if distance > passive_range or distance == 0:
            return

        detection_prob = min(0.95, (passive_range / distance) ** 2)
        if random.random() >= detection_prob:
            return

        yaw = math.degrees(math.atan2(dy, dx))
        pitch = math.degrees(math.asin(dz / distance))
        contact = {
            "id": target_ship.id,
            "distance": distance,
            "bearing": {"pitch": pitch, "yaw": yaw},
            "signature": 0.5,
            "detection_method": "passive",
            "last_updated": time.time(),
        }

        if hasattr(sensor_system, "passive") and isinstance(sensor_system.passive, dict):
            sensor_system.passive.setdefault("contacts", [])
            for i, existing in enumerate(sensor_system.passive["contacts"]):
                if existing.get("id") == target_ship.id:
                    sensor_system.passive["contacts"][i] = contact
                    break
            else:
                sensor_system.passive["contacts"].append(contact)

        if hasattr(sensor_system, "contacts") and isinstance(getattr(sensor_system, "contacts" ,None), list):
            for i, existing in enumerate(sensor_system.contacts):
                if existing.get("id") == target_ship.id:
                    sensor_system.contacts[i] = contact
                    break
            else:
                sensor_system.contacts.append(contact)
