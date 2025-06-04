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
