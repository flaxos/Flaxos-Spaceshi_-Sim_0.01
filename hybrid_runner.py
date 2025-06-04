# hybrid_runner.py
import time
import threading
import json
import os
from datetime import datetime
from hybrid.simulator import Simulator

class HybridRunner:
    def __init__(self, fleet_dir="hybrid_fleet", dt=0.1):
        """
        Initialize the hybrid runner
        
        Args:
            fleet_dir (str): Directory containing ship JSON files
            dt (float): Simulation time step in seconds
        """
        self.root_dir = os.path.dirname(os.path.abspath(__file__))
        self.fleet_dir = os.path.join(self.root_dir, fleet_dir)
        self.scenarios_dir = os.path.join(self.root_dir, "scenarios")
        self.dt = dt
        self.simulator = Simulator(dt=dt)
        self.running = False
        self.thread = None
        self.ships = {}
        self.tick_count = 0
        self.state_cache = {}
        self.last_update_time = 0
        
        # Create fleet_state directory if it doesn't exist
        os.makedirs(os.path.join(self.root_dir, "fleet_state"), exist_ok=True)

        # Create scenarios directory if it doesn't exist
        os.makedirs(self.scenarios_dir, exist_ok=True)
        
    def load_ships(self):
        """Load ships from the fleet directory"""
        ship_count = self.simulator.load_ships_from_directory(self.fleet_dir)
        print(f"Loaded {ship_count} ships from {self.fleet_dir}")
        return ship_count
        
    def load_scenario(self, scenario_name):
        """
        Load a predefined scenario with multiple ships
        
        Args:
            scenario_name (str): Name of the scenario file (without extension)
            
        Returns:
            int: Number of ships loaded
        """
        scenario_path = os.path.join(self.scenarios_dir, f"{scenario_name}.json")
        if not os.path.exists(scenario_path):
            print(f"Scenario file not found: {scenario_path}")
            return 0
            
        try:
            with open(scenario_path, 'r') as f:
                scenario_data = json.load(f)
                
            # Clear existing ships
            self.simulator.ships.clear()
            
            # Load ships from scenario
            ship_count = 0
            ships_data = scenario_data.get("ships", [])
            
            for ship_data in ships_data:
                ship_id = ship_data.get("id")
                if not ship_id:
                    continue
                    
                self.simulator.add_ship(ship_id, ship_data)
                ship_count += 1
                
            print(f"Loaded {ship_count} ships from scenario: {scenario_name}")
            return ship_count
            
        except Exception as e:
            print(f"Error loading scenario: {e}")
            return 0
    
    def start(self):
        """Start the simulation in a background thread"""
        if self.running:
            return False
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop)
        self.thread.daemon = True
        self.thread.start()
        return True
    
    def stop(self):
        """Stop the simulation"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
        return True
    
    def _run_loop(self):
        """Internal method to run the simulation loop"""
        self.simulator.start()
        
        while self.running:
            try:
                # Run a single simulation step (using tick method)
                self.simulator.tick()
                self.tick_count += 1
                
                # Update the state cache every 10 ticks (or as needed)
                if self.tick_count % 10 == 0:
                    self._update_state_cache()
                
                # Sleep to limit CPU usage
                time.sleep(0.001)
            except Exception as e:
                print(f"Error in simulation tick: {e}")
                time.sleep(0.1)  # Sleep longer on error
        
        self.simulator.stop()
    
    def _update_state_cache(self):
        """Update the internal state cache"""
        self.state_cache = {}
        self.last_update_time = time.time()
        
        for ship_id, ship in self.simulator.ships.items():
            try:
                # Handle sensor system initialization
                if "sensors" in ship.systems:
                    sensor_system = ship.systems["sensors"]
                    
                    # If it's a SensorSystem object
                    if hasattr(sensor_system, "active") and hasattr(sensor_system, "passive"):
                        # Ensure required fields exist in sensor system object
                        if not hasattr(sensor_system, "config"):
                            sensor_system.config = {}
                            
                        # Check active sensor fields
                        if not hasattr(sensor_system.active, "last_ping_time") or sensor_system.active["last_ping_time"] is None:
                            sensor_system.active["last_ping_time"] = 0
                            
                        # Ensure contacts list exists
                        if "contacts" not in sensor_system.config:
                            sensor_system.config["contacts"] = []
                            
                    # If it's a dictionary
                    elif isinstance(sensor_system, dict):
                        # Add empty contacts list if missing
                        if "contacts" not in sensor_system:
                            sensor_system["contacts"] = []
                            
                        # Add active section if missing
                        if "active" not in sensor_system:
                            sensor_system["active"] = {"contacts": [], "last_ping_time": 0}
                        # Add last_ping_time if missing
                        elif "last_ping_time" not in sensor_system["active"]:
                            sensor_system["active"]["last_ping_time"] = 0
                
                # Get state with fixed fields
                self.state_cache[ship_id] = ship.get_state()
            except Exception as e:
                print(f"Error getting state for {ship_id}: {e}")
                # Create a minimal valid state to avoid cascading errors
                self.state_cache[ship_id] = {
                    "position": {"x": 0, "y": 0, "z": 0},
                    "velocity": {"x": 0, "y": 0, "z": 0},
                    "orientation": {"pitch": 0, "yaw": 0, "roll": 0},
                    "angular_velocity": {"pitch": 0, "yaw": 0, "roll": 0},
                    "thrust": {"x": 0, "y": 0, "z": 0},
                    "sensors": {
                        "passive": {"contacts": []},
                        "active": {"contacts": [], "last_ping_time": 0},
                        "contacts": []
                    }
                }
    
    def get_ship_state(self, ship_id):
        """Get the current state of a specific ship"""
        # If it's been a while since the last update, refresh the cache
        if time.time() - self.last_update_time > 0.5:
            self._update_state_cache()
            
        if ship_id in self.state_cache:
            return self.state_cache[ship_id]
            
        # If not in cache, try to get directly from the ship
        if ship_id in self.simulator.ships:
            try:
                return self.simulator.ships[ship_id].get_state()
            except Exception as e:
                return {"error": f"Error getting state: {e}"}
        else:
            return {"error": f"Ship {ship_id} not found"}
    
    def get_all_ship_states(self):
        """Get the current state of all ships"""
        self._update_state_cache()
        return self.state_cache
    
    def send_command(self, ship_id, command, args=None):
        """Send a command to a specific ship"""
        if args is None:
            args = {}
            
        if ship_id in self.simulator.ships:
            try:
                result = self.simulator.ships[ship_id].command(command, args)
                return {"success": True, "result": result}
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            return {"success": False, "error": f"Ship {ship_id} not found"}
    
    def save_states(self):
        """Save the current state of all ships to JSON files"""
        states = self.get_all_ship_states()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        fleet_state_dir = os.path.join(self.root_dir, "fleet_state")
        for ship_id, state in states.items():
            filename = os.path.join(fleet_state_dir, f"{ship_id}_{timestamp}.json")
            with open(filename, "w") as f:
                json.dump(state, f, indent=2)
                
        return {"success": True, "message": f"Saved {len(states)} ship states"}


# Simple usage example
if __name__ == "__main__":
    runner = HybridRunner()
    ship_count = runner.load_ships()
    
    if ship_count > 0:
        print("Starting simulation...")
        runner.start()
        
        try:
            # Run for 30 seconds
            for i in range(30):
                time.sleep(1)
                states = runner.get_all_ship_states()
                print(f"Tick {runner.tick_count}: {len(states)} ships active")
                
                # Example command to the first ship
                if i == 10 and states and runner.simulator.ships:
                    ship_id = list(runner.simulator.ships.keys())[0]
                    print(f"Sending command to {ship_id}...")
                    result = runner.send_command(ship_id, "get_system_state", {"system": "propulsion"})
                    print(f"Command result: {json.dumps(result, indent=2)}")
            
            # Save final states
            runner.save_states()
            
        finally:
            print("Stopping simulation...")
            runner.stop()
    else:
        print(f"No ships found in {runner.fleet_dir}")
