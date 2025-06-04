# hybrid/simulator.py
"""
Ship simulator for the hybrid architecture.
Manages multiple ships and handles simulation ticks.
"""
# hybrid/simulator.py
"""
Simulator implementation for the hybrid architecture.
Manages multiple ships and handles physics and interaction.
"""
import os
import json
import time
import math
import random

class Simulator:
    """Manages multiple ships and handles physics simulation"""
    
    def __init__(self, dt=0.1):
        """
        Initialize the simulator
        
        Args:
            dt (float): Time step in seconds
        """
        self.dt = dt
        self.ships = {}
        self.start_time = None
        self.current_time = 0
        self.tick_count = 0
    
    def load_ships_from_directory(self, directory):
        """
        Load ships from a directory of JSON files
        
        Args:
            directory (str): Directory path containing ship JSON files
            
        Returns:
            int: Number of ships loaded
        """
        if not os.path.exists(directory):
            print(f"Directory not found: {directory}")
            return 0
            
        count = 0
        for filename in os.listdir(directory):
            if filename.endswith('.json'):
                ship_path = os.path.join(directory, filename)
                
                try:
                    with open(ship_path, 'r') as f:
                        ship_data = json.load(f)
                        
                    # Get ship ID from filename or data
                    ship_id = ship_data.get('id', filename.split('.')[0])
                    
                    # Add ship to simulator
                    self.add_ship(ship_id, ship_data)
                    count += 1
                    
                except Exception as e:
                    print(f"Error loading ship from {ship_path}: {e}")
        
        return count
    
    def add_ship(self, ship_id, config):
        """
        Add a ship to the simulator
        
        Args:
            ship_id (str): Unique ID for the ship
            config (dict): Ship configuration
            
        Returns:
            Ship: The created ship
        """
        from hybrid.ship import Ship
        
        # Create the ship
        ship = Ship(ship_id, config)
        
        # Add to ships dictionary
        self.ships[ship_id] = ship
        
        return ship
    
    def remove_ship(self, ship_id):
        """
        Remove a ship from the simulator
        
        Args:
            ship_id (str): ID of the ship to remove
            
        Returns:
            bool: True if removed, False if not found
        """
        if ship_id in self.ships:
            del self.ships[ship_id]
            return True
        return False
    
    def start(self):
        """Start the simulation"""
        self.start_time = time.time()
        self.current_time = 0
        self.tick_count = 0
        return True
    
    def stop(self):
        """Stop the simulation"""
        self.start_time = None
        return True
    
    def tick(self):
        """
        Advance the simulation by one time step
        
        Returns:
            float: Time elapsed in seconds
        """
        # Increment simulation time
        self.current_time += self.dt
        self.tick_count += 1
        
        # Process ship interactions (detect proximity)
        self._process_ship_interactions()
        
        # Update each ship
        for ship_id, ship in self.ships.items():
            ship.tick(self.dt)
        
        return self.dt
    
    def _process_ship_interactions(self):
        """Process interactions between ships (collision detection, sensor detection, etc.)"""
        # Skip if fewer than 2 ships
        if len(self.ships) < 2:
            return
            
        # Get list of ship IDs
        ship_ids = list(self.ships.keys())
        
        # Check each pair of ships
        for i in range(len(ship_ids)):
            for j in range(i + 1, len(ship_ids)):
                ship_id1 = ship_ids[i]
                ship_id2 = ship_ids[j]
                
                ship1 = self.ships[ship_id1]
                ship2 = self.ships[ship_id2]
                
                # Calculate distance between ships
                distance = math.sqrt(
                    (ship1.position["x"] - ship2.position["x"]) ** 2 +
                    (ship1.position["y"] - ship2.position["y"]) ** 2 +
                    (ship1.position["z"] - ship2.position["z"]) ** 2
                )
                
                # Check for collisions (simple sphere collision)
                collision_threshold = 10.0  # Simplified collision distance
                if distance < collision_threshold:
                    self._handle_collision(ship1, ship2)
                
                # Check for passive sensor detection
                self._check_passive_detection(ship1, ship2, distance)
                self._check_passive_detection(ship2, ship1, distance)
    
    def _handle_collision(self, ship1, ship2):
        """Handle collision between two ships"""
        # Calculate collision response (simple elastic collision)
        total_mass = ship1.mass + ship2.mass
        
        # Simplified collision response - just bounce away from each other
        # In a real simulator, this would be more sophisticated
        for axis in ["x", "y", "z"]:
            # Calculate relative velocity
            rel_vel = ship1.velocity[axis] - ship2.velocity[axis]
            
            # Calculate impulse
            impulse = 2 * rel_vel / total_mass
            
            # Apply impulse to ships based on their mass
            ship1.velocity[axis] -= impulse * ship2.mass
            ship2.velocity[axis] += impulse * ship1.mass
            
        # Publish collision events to both ships
        if hasattr(ship1, "event_bus"):
            ship1.event_bus.publish("collision", {
                "other_ship": ship2.id,
                "distance": 0
            })
            
        if hasattr(ship2, "event_bus"):
            ship2.event_bus.publish("collision", {
                "other_ship": ship1.id,
                "distance": 0
            })
    
    def _check_passive_detection(self, observer_ship, target_ship, distance):
        """Check if observer ship can detect target ship with passive sensors"""
        # Skip if observer doesn't have sensors
        if "sensors" not in observer_ship.systems:
            return
            
        # Get sensor system
        sensor_system = observer_ship.systems["sensors"]
        
        # Determine the passive sensor range. Older sensor implementations used
        # a `passive_range` attribute while newer versions store the range in
        # the `passive` configuration dictionary.  Support both so tests can
        # rely on passive detection working regardless of which sensor class
        # variant is loaded.
        passive_range = getattr(sensor_system, "passive_range", None)
        if passive_range is None and hasattr(sensor_system, "passive") and isinstance(sensor_system.passive, dict):
            passive_range = sensor_system.passive.get("range")

        # If no passive range is available we cannot perform detection
        if passive_range is None:
            return

        # Calculate detection probability based on distance
        if passive_range:
            
            # Check if within passive sensor range
            if distance <= passive_range:
                # Calculate detection probability (inverse square law)
                detection_prob = (passive_range / distance) ** 2
                detection_prob = min(0.95, detection_prob)  # Cap at 95%
                
                # Random detection based on probability
                if random.random() < detection_prob:
                    # Calculate bearing to target
                    dx = target_ship.position["x"] - observer_ship.position["x"]
                    dy = target_ship.position["y"] - observer_ship.position["y"]
                    dz = target_ship.position["z"] - observer_ship.position["z"]
                    
                    # Calculate yaw (azimuth) and pitch (elevation)
                    yaw = math.degrees(math.atan2(dy, dx))
                    pitch = math.degrees(math.asin(dz / distance))
                    
                    # Create contact data
                    contact = {
                        "id": target_ship.id,
                        "distance": distance,
                        "bearing": {
                            "pitch": pitch,
                            "yaw": yaw
                        },
                        "signature": 0.5,  # Simplified signature
                        "detection_method": "passive",
                        "last_updated": time.time()
                    }
                    
                    # Add to passive contacts
                    if hasattr(sensor_system, "passive") and isinstance(sensor_system.passive, dict):
                        if "contacts" not in sensor_system.passive:
                            sensor_system.passive["contacts"] = []
                        
                        # Replace if already exists, add if new
                        found = False
                        for i, existing in enumerate(sensor_system.passive["contacts"]):
                            if existing.get("id") == target_ship.id:
                                sensor_system.passive["contacts"][i] = contact
                                found = True
                                break
                                
                        if not found:
                            sensor_system.passive["contacts"].append(contact)
                            
                    # Also add to combined contacts
                    if hasattr(sensor_system, "contacts") and isinstance(sensor_system.contacts, list):
                        # Replace if already exists, add if new
                        found = False
                        for i, existing in enumerate(sensor_system.contacts):
                            if existing.get("id") == target_ship.id:
                                sensor_system.contacts[i] = contact
                                found = True
                                break
                                
                        if not found:
                            sensor_system.contacts.append(contact)
import time
import logging
import json
import os
from datetime import datetime
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
