# hybrid_runner.py
import time
import threading
import json
import os
from datetime import datetime
from hybrid.simulator import Simulator
from hybrid.scenarios.loader import ScenarioLoader
from hybrid.fleet.fleet_manager import FleetManager

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
        self.mission = None
        self.last_mission_status = None
        self.player_ship_id = None

        # Scenario loading state - prevents concurrent loads
        self._loading_scenario = False
        self._current_scenario_path = None

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
        scenario_path = self._resolve_scenario_path(scenario_name)
        if not scenario_path:
            print(f"Scenario file not found: {scenario_name}")
            return 0

        return self._load_scenario_file(scenario_path)

    def list_scenarios(self):
        """List available scenarios with metadata."""
        scenarios = []
        for path in ScenarioLoader.list_scenarios(self.scenarios_dir):
            scenario_id = os.path.splitext(os.path.basename(path))[0]
            summary = {
                "id": scenario_id,
                "file": os.path.basename(path),
            }
            try:
                data = ScenarioLoader.load(path)
                summary["name"] = data.get("name", scenario_id)
                summary["description"] = data.get("description", "")
                mission = data.get("mission")
                if mission:
                    summary["mission_name"] = mission.name
                    summary["mission_description"] = mission.description
            except Exception as exc:
                summary["error"] = str(exc)
            scenarios.append(summary)
        return scenarios

    def get_mission_status(self, include_hints=False, clear_hints=False):
        """Return current mission status and metadata."""
        if not self.mission:
            return {"available": False}
        status = self.mission.get_status(sim_time=self.simulator.time)
        status.update({
            "available": True,
            "briefing": self.mission.briefing,
            "success_message": self.mission.success_message,
            "failure_message": self.mission.failure_message,
        })
        if include_hints:
            status["hints"] = self.mission.get_hints(clear=clear_hints)
        return status

    def get_mission_hints(self, clear=False):
        """Return queued mission hints."""
        if not self.mission:
            return []
        return self.mission.get_hints(clear=clear)

    def _resolve_scenario_path(self, scenario_name):
        if not scenario_name:
            return None
        if os.path.isabs(scenario_name) and os.path.exists(scenario_name):
            return scenario_name
        if os.path.sep in scenario_name or "/" in scenario_name:
            candidate = os.path.join(self.root_dir, scenario_name)
            if os.path.exists(candidate):
                return candidate
        base = os.path.join(self.scenarios_dir, scenario_name)
        if os.path.splitext(base)[1]:
            return base if os.path.exists(base) else None
        for ext in (".json", ".yaml", ".yml"):
            candidate = base + ext
            if os.path.exists(candidate):
                return candidate
        return None

    def _reset_simulation(self):
        self.simulator.ships.clear()
        self.simulator.time = 0.0
        self.tick_count = 0
        self.state_cache = {}
        self.last_update_time = 0
        self.last_mission_status = None
        self._current_scenario_path = None
        self.simulator.fleet_manager = FleetManager(simulator=self.simulator)

    def _select_player_ship(self, ships_data):
        for ship in ships_data:
            if ship.get("player_controlled"):
                return ship.get("id")
        return ships_data[0].get("id") if ships_data else None

    def _load_scenario_file(self, scenario_path):
        # Prevent concurrent scenario loads
        if self._loading_scenario:
            print(f"Scenario load already in progress, ignoring request for: {scenario_path}")
            return 0

        # Skip if same scenario is already loaded and simulation is running
        if self._current_scenario_path == scenario_path and self.running:
            print(f"Scenario already loaded: {scenario_path}")
            return len(self.simulator.ships)

        try:
            self._loading_scenario = True
            was_running = self.running
            if was_running:
                self.stop()

            scenario_data = ScenarioLoader.load(scenario_path)
            ships_data = scenario_data.get("ships", [])
            if not ships_data:
                print(f"Scenario has no ships: {scenario_path}")
                return 0

            if scenario_data.get("dt"):
                self.dt = scenario_data["dt"]
                self.simulator.dt = self.dt

            self._reset_simulation()

            ship_count = 0
            for ship_data in ships_data:
                ship_id = ship_data.get("id")
                if not ship_id:
                    continue
                self.simulator.add_ship(ship_id, ship_data)
                ship_count += 1

            # Initialize all_ships reference on each ship immediately after adding
            # This ensures sensors can detect contacts even before the first tick
            all_ships = list(self.simulator.ships.values())
            for ship in all_ships:
                ship._all_ships_ref = all_ships

            fleets = scenario_data.get("config", {}).get("fleets") if isinstance(scenario_data.get("config"), dict) else scenario_data.get("fleets")
            if fleets:
                for fleet in fleets:
                    self.simulator.fleet_manager.create_fleet(
                        fleet_id=fleet.get("fleet_id", fleet.get("id")),
                        name=fleet.get("name", fleet.get("fleet_id", "Fleet")),
                        flagship_id=fleet.get("flagship", fleet.get("flagship_id")),
                        ship_ids=fleet.get("ships", []),
                    )

            self.mission = scenario_data.get("mission")
            self.last_mission_status = None
            self.player_ship_id = None
            if isinstance(scenario_data.get("config"), dict):
                self.player_ship_id = scenario_data["config"].get("player_ship_id")
            if not self.player_ship_id:
                self.player_ship_id = self._select_player_ship(ships_data)
            if self.mission:
                self.mission.start(self.simulator.time)
                self.last_mission_status = self.mission.tracker.mission_status

            # Store current scenario path for deduplication
            self._current_scenario_path = scenario_path

            if was_running:
                self.start()

            print(f"Loaded {ship_count} ships from scenario: {scenario_path}")
            return ship_count
        except Exception as e:
            print(f"Error loading scenario: {e}")
            return 0
        finally:
            self._loading_scenario = False
    
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
                self._update_mission()
                
                # Update the state cache every 10 ticks (or as needed)
                if self.tick_count % 10 == 0:
                    self._update_state_cache()
                
                # Sleep to limit CPU usage
                time.sleep(0.001)
            except Exception as e:
                print(f"Error in simulation tick: {e}")
                time.sleep(0.1)  # Sleep longer on error
        
        self.simulator.stop()

    def _update_mission(self):
        if not self.mission:
            return
        player_ship = None
        if self.player_ship_id:
            player_ship = self.simulator.ships.get(self.player_ship_id)
        if not player_ship and self.simulator.ships:
            player_ship = next(iter(self.simulator.ships.values()))
        if player_ship:
            previous_status = self.last_mission_status or self.mission.tracker.mission_status
            self.mission.update(self.simulator, player_ship)
            current_status = self.mission.tracker.mission_status
            if current_status != previous_status:
                event_name = "mission_complete" if current_status in ("success", "failure") else "mission_update"
                payload = {
                    "type": event_name,
                    "ship_id": player_ship.id,
                    "mission": self.get_mission_status(),
                    "mission_status": current_status,
                    "name": self.mission.name,
                    "description": self.mission.description,
                    "message": self.mission.get_result_message() if current_status in ("success", "failure") else "Mission updated.",
                    "sim_time": self.simulator.time,
                }
                player_ship.event_bus.publish(event_name, payload)
            self.last_mission_status = current_status
    
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
                        if (
                            not hasattr(sensor_system.active, "last_ping_time")
                            or sensor_system.active.last_ping_time is None
                        ):
                            sensor_system.active.last_ping_time = 0
                            
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
                
                # Get state with fixed fields (include current sim time for flight path)
                state = ship.get_state()
                # Ensure flight_path is included if ship has it
                if hasattr(ship, 'get_flight_path'):
                    try:
                        # Use current simulation time for accurate flight path
                        current_sim_time = self.simulator.time if hasattr(self.simulator, 'time') else None
                        state["flight_path"] = ship.get_flight_path(60, current_sim_time=current_sim_time)
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Error getting flight path for {ship_id}: {e}")
                        state["flight_path"] = []
                elif "flight_path" not in state:
                    # Ensure flight_path exists even if method doesn't
                    state["flight_path"] = []
                self.state_cache[ship_id] = state
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
