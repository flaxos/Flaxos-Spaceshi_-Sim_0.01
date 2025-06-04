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
from systems_tick import tick_all_systems

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
        
        # Snapshot ships list for this tick
        all_ships = list(self.ships.values())

        # Process ship interactions (collision detection, etc.)
        self._process_ship_interactions()

        # Update each ship and tick their systems
        for ship in all_ships:
            ship.tick(self.dt, all_ships)
            tick_all_systems(ship, all_ships, self.dt)

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
    
