# hybrid/cli.py
"""
Command-line interface for the hybrid ship simulation.
Allows loading and controlling ships from the command line.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
import time
from hybrid_runner import HybridRunner

from hybrid.simulator import Simulator
from hybrid.command_handler import handle_command_request

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_config(config_file):
    """
    Load configuration from a JSON file
    
    Args:
        config_file (str): Path to configuration file
        
    Returns:
        dict: Loaded configuration
    """
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config from {config_file}: {e}")
        return {}

def save_ship_state(ship, output_dir="fleet_state"):
    """
    Save ship state to a JSON file
    
    Args:
        ship (Ship): Ship to save
        output_dir (str): Directory to save to
        
    Returns:
        str: Path to saved file
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
        
        filename = f"{ship.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w') as f:
            json.dump(ship.get_state(), f, indent=2)
            
        logger.info(f"Saved ship state to {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Failed to save ship state: {e}")
        return None

def print_ship_state(state, detailed=False):
    """Print ship state in a readable format"""
    if not state:
        print("No state available")
        return
        
    print(f"Position: ({state['position']['x']:.1f}, {state['position']['y']:.1f}, {state['position']['z']:.1f})")
    print(f"Velocity: ({state['velocity']['x']:.1f}, {state['velocity']['y']:.1f}, {state['velocity']['z']:.1f})")
    print(f"Orientation: Pitch {state['orientation']['pitch']:.1f}° Yaw {state['orientation']['yaw']:.1f}° Roll {state['orientation']['roll']:.1f}°")
    
    if detailed:
        print("\nSystems Status:")
        systems = state.get("systems", {})
        for system_name, system_data in systems.items():
            status = "Unknown"
            if isinstance(system_data, dict):
                status = system_data.get("status", "Unknown")
            print(f"  {system_name.capitalize()}: {status}")
        
        # Show sensor contacts if available
        if "sensors" in systems:
            sensors = systems["sensors"]
            contacts = sensors.get("contacts", [])
            if contacts:
                print("\nSensor Contacts:")
                for contact in contacts:
                    contact_id = contact.get("id", "Unknown")
                    distance = contact.get("distance", "Unknown")
                    method = contact.get("detection_method", "Unknown")
                    if isinstance(distance, (int, float)):
                        formatted_distance = f"{distance:.1f}"
                    else:
                        formatted_distance = str(distance)
                    print(f"  {contact_id} @ {formatted_distance} km [{method}]")

def run_cli(fleet_dir="hybrid_fleet", dt=0.1):
    """Run the simulator in CLI mode"""
    print("Hybrid Ship Simulator - CLI Mode")
    print("--------------------------------")
    
    # Create the hybrid runner
    runner = HybridRunner(fleet_dir=fleet_dir, dt=dt)
    
    # Load ships
    ship_count = runner.load_ships()
    if ship_count == 0:
        print(f"No ships found in {fleet_dir}")
        return 1
    
    print(f"Loaded {ship_count} ships")
    
    # List available ships
    ship_ids = list(runner.simulator.ships.keys())
    print("\nAvailable ships:")
    for i, ship_id in enumerate(ship_ids):
        print(f"{i+1}. {ship_id}")
    
    # Select a ship
    selected_ship = None
    while selected_ship is None:
        try:
            choice = int(input("\nSelect a ship (number): "))
            if 1 <= choice <= len(ship_ids):
                selected_ship = ship_ids[choice-1]
            else:
                print("Invalid selection")
        except ValueError:
            print("Invalid input, please enter a number")
        except KeyboardInterrupt:
            print("\nExiting...")
            return 0
    
    print(f"\nSelected ship: {selected_ship}")
    
    # Start the simulation
    runner.start()
    print("Simulation started")
    
    try:
        # Main CLI loop
        while True:
            # Get ship state
            state = runner.get_ship_state(selected_ship)
            
            # Print the current state
            print("\n" + "="*50)
            print(f"Ship: {selected_ship} (Tick: {runner.tick_count})")
            print("-"*50)
            print_ship_state(state, detailed=True)
            
            # Show command menu
            print("\nCommands:")
            print("1. Get state")
            print("2. Set thrust")
            print("3. Set course")
            print("4. Toggle autopilot")
            print("5. Ping sensors")
            print("6. Set power profile")
            print("7. Custom command")
            print("8. Switch ship")
            print("9. Save states")
            print("10. Exit")
            
            try:
                choice = input("\nEnter command: ")
                
                if choice == "1":
                    # Get state (already shown above)
                    pass
                    
                elif choice == "2":
                    # Set thrust
                    x = float(input("X thrust: "))
                    y = float(input("Y thrust: "))
                    z = float(input("Z thrust: "))
                    
                    result = runner.send_command(selected_ship, "set_thrust", {"x": x, "y": y, "z": z})
                    print("Result:", json.dumps(result, indent=2))
                    
                elif choice == "3":
                    # Set course
                    x = float(input("X coordinate: "))
                    y = float(input("Y coordinate: "))
                    z = float(input("Z coordinate: "))
                    
                    result = runner.send_command(selected_ship, "set_course", {"x": x, "y": y, "z": z})
                    print("Result:", json.dumps(result, indent=2))
                    
                elif choice == "4":
                    # Toggle autopilot
                    current = state.get("systems", {}).get("navigation", {}).get("autopilot_enabled", False)
                    new_state = not current
                    
                    result = runner.send_command(selected_ship, "autopilot", {"enabled": new_state})
                    print("Result:", json.dumps(result, indent=2))
                    
                elif choice == "5":
                    # Ping sensors
                    result = runner.send_command(selected_ship, "ping_sensors", {})
                    print("Result:", json.dumps(result, indent=2))
                    
                elif choice == "6":
                    profile = input("Power profile (offensive/defensive): ").strip()
                    if not profile:
                        print("Profile name required")
                        continue
                    result = runner.send_command(
                        selected_ship,
                        "set_power_profile",
                        {"profile": profile}
                    )
                    print("Result:", json.dumps(result, indent=2))

                elif choice == "7":
                    # Custom command
                    cmd = input("Command: ")
                    args_str = input("Args (JSON): ")
                    
                    try:
                        args = json.loads(args_str)
                        result = runner.send_command(selected_ship, cmd, args)
                        print("Result:", json.dumps(result, indent=2))
                    except json.JSONDecodeError:
                        print("Invalid JSON args")
                        
                elif choice == "8":
                    # Switch ship
                    print("\nAvailable ships:")
                    for i, ship_id in enumerate(ship_ids):
                        print(f"{i+1}. {ship_id}")
                        
                    try:
                        choice = int(input("\nSelect a ship (number): "))
                        if 1 <= choice <= len(ship_ids):
                            selected_ship = ship_ids[choice-1]
                            print(f"Switched to ship: {selected_ship}")
                        else:
                            print("Invalid selection")
                    except ValueError:
                        print("Invalid input, please enter a number")
                        
                elif choice == "9":
                    # Save states
                    result = runner.save_states()
                    print("Result:", json.dumps(result, indent=2))
                    
                elif choice == "10":
                    # Exit
                    print("Exiting...")
                    break
                    
                else:
                    print("Invalid command")
                    
            except ValueError as e:
                print(f"Invalid input: {e}")
                
            except KeyboardInterrupt:
                print("\nExiting...")
                break
                
            # Pause between commands
            time.sleep(0.5)
            
    finally:
        # Stop the simulation
        runner.stop()
        print("Simulation stopped")
    
    return 0
def main():
    """
    Main entry point for the CLI
    """
    parser = argparse.ArgumentParser(description="Ship Simulation CLI")
    
    # General options
    parser.add_argument('--fleet-dir', default='fleet', help='Directory containing ship configuration files')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    # Simulation options
    parser.add_argument('--dt', type=float, default=0.1, help='Simulation time step in seconds')
    parser.add_argument('--run', type=float, help='Run simulation for specified duration (seconds)')
    
    # Command options
    parser.add_argument('--ship', help='Ship ID to command')
    parser.add_argument('--command', help='Command to send (JSON string or file path)')
    
    args = parser.parse_args()
    
    # Set logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        
    # If no command options provided, drop into interactive CLI
    if not args.command and not args.run:
        return run_cli(fleet_dir=args.fleet_dir, dt=args.dt)

    simulator = Simulator(dt=args.dt)

    num_ships = simulator.load_ships_from_directory(args.fleet_dir)
    logger.info(f"Loaded {num_ships} ships")

    if num_ships == 0:
        logger.error(f"No ships found in {args.fleet_dir}")
        return 1

    simulator.start()
    
    # Handle command if specified
    if args.ship and args.command:
        ship = simulator.get_ship(args.ship)
        if not ship:
            logger.error(f"Ship {args.ship} not found")
            return 1
            
        # Parse command
        command = args.command
        try:
            # Check if command is a file path
            if os.path.isfile(command):
                with open(command, 'r') as f:
                    command = f.read()
                    
            # Try to parse as JSON
            command_data = json.loads(command)
        except json.JSONDecodeError:
            # Not JSON, treat as command type
            command_data = {"command": command, "ship": args.ship}
        except Exception as e:
            logger.error(f"Failed to parse command: {e}")
            return 1
            
        # Execute command
        response = handle_command_request(command_data, ship)
        print(json.dumps(json.loads(response), indent=2))
        
    # Run simulation if requested
    if args.run:
        logger.info(f"Running simulation for {args.run} seconds")
        simulator.run(args.run)
        
        # Save ship states
        for ship_id, ship in simulator.ships.items():
            save_ship_state(ship)
            
    simulator.stop()
    return 0

if __name__ == "__main__":
    sys.exit(main())
