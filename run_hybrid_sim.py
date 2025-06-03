#!/usr/bin/env python3
# Hybrid Ship Simulator Runner
# This script runs the hybrid ship simulation with various options
#!/usr/bin/env python3
# run_hybrid_sim.py
"""
Main entry point for the hybrid ship simulator with GUI
"""
import tkinter as tk
import os
import sys
import argparse

def main():
    """Main function to run the simulator"""
    parser = argparse.ArgumentParser(description="Run the hybrid ship simulator")
    parser.add_argument("--no-gui", action="store_true", help="Run without GUI")
    parser.add_argument("--scenario", default="basic_scenario", help="Scenario to load")
    parser.add_argument("--dt", type=float, default=0.1, help="Simulation time step")
    args = parser.parse_args()
    
    if args.no_gui:
        from hybrid.cli import run_cli
        return run_cli(dt=args.dt, scenario=args.scenario)
    else:
        return run_gui_mode(args)

def run_gui_mode(args):
    """Run simulator with GUI"""
    try:
        from hybrid_runner import HybridRunner
        from gui_control import HybridGUI
        import tkinter as tk
        
        # Create and initialize the runner
        runner = HybridRunner(dt=args.dt)
        
        # Load scenario
        print(f"Loading scenario: {args.scenario}")
        ship_count = runner.load_scenario(args.scenario)
        if ship_count == 0:
            print("Falling back to default scenario...")
            runner.load_ships()  # Load from fleet directory as fallback
        
        # Create GUI
        root = tk.Tk()
        app = HybridGUI(root, runner)
        root.protocol("WM_DELETE_WINDOW", lambda: app.on_closing())
        
        # Start simulation
        runner.start()
        
        # Run GUI
        root.mainloop()
        return 0
        
    except Exception as e:
        print(f"Error starting GUI: {e}")
        import traceback
        traceback.print_exc()
        return 1
import os
import sys
import argparse
import logging
import time
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Output to console
    ]
)
logger = logging.getLogger("hybrid_sim")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Hybrid Ship Simulator")
    
    parser.add_argument("--nogui", action="store_true", help="Run without GUI (console mode)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--scenario", type=str, default="test_scenario", 
                        help="Load a specific scenario (e.g. test_scenario, sensor_test_scenario)")
    
    return parser.parse_args()

def run_console_mode(args):
    """Run simulator in console mode"""
    from hybrid_runner import HybridRunner
    
    try:
        runner = HybridRunner()
        print("Initializing simulator...")
        
        # Load the specified scenario
        scenario_name = args.scenario
        ship_count = runner.load_scenario(scenario_name)
        
        if ship_count == 0:
            print(f"Failed to load scenario: {scenario_name}")
            print("Falling back to test_scenario...")
            runner.load_scenario("test_scenario")
        
        print("Starting simulation...")
        runner.start()
        
        try:
            print("Interactive console mode (press Ctrl+C to stop)")
            print("Available commands:")
            print("  ships - List all ships")
            print("  status - Show simulation status")
            print("  send <ship_id> <command> [args] - Send command to ship")
            print("  ping <ship_id> - Ping sensors on ship")
            print("  contacts <ship_id> - Get sensor contacts for ship")
            
            while True:
                cmd = input("\nCommand> ")
                if cmd.lower() in ['q', 'quit', 'exit']:
                    break
                    
                if cmd == "ships":
                    states = runner.get_all_ship_states()
                    print(f"Active ships: {', '.join(states.keys())}")
                    
                elif cmd == "status":
                    print(f"Simulation running: {runner.running}")
                    print(f"Tick count: {runner.tick_count}")
                    
                elif cmd.startswith("send "):
                    parts = cmd.split(" ", 3)
                    if len(parts) < 3:
                        print("Usage: send <ship_id> <command> [args_json]")
                        continue
                        
                    ship_id = parts[1]
                    command = parts[2]
                    args = {}
                    
                    if len(parts) > 3:
                        try:
                            import json
                            args = json.loads(parts[3])
                        except json.JSONDecodeError:
                            args = {"value": parts[3]}
                    
                    print(f"Sending '{command}' to {ship_id}...")
                    result = runner.send_command(ship_id, command, args)
                    print(f"Result: {result}")
                    
                elif cmd.startswith("ping "):
                    parts = cmd.split(" ", 1)
                    if len(parts) < 2:
                        print("Usage: ping <ship_id>")
                        continue
                        
                    ship_id = parts[1]
                    print(f"Pinging sensors on {ship_id}...")
                    result = runner.send_command(ship_id, "ping_sensors")
                    print(f"Result: {result}")
                    
                elif cmd.startswith("contacts "):
                    parts = cmd.split(" ", 1)
                    if len(parts) < 2:
                        print("Usage: contacts <ship_id>")
                        continue
                        
                    ship_id = parts[1]
                    print(f"Getting sensor contacts for {ship_id}...")
                    result = runner.send_command(ship_id, "get_contacts")
                    
                    if result.get("success"):
                        contacts = result.get("result", {}).get("contacts", [])
                        print(f"Found {len(contacts)} contacts:")
                        
                        for i, contact in enumerate(contacts):
                            distance = contact.get("distance", "?")
                            target_id = contact.get("target_id", "Unknown")
                            method = contact.get("method", "unknown")
                            detected_at = contact.get("detected_at", "?")
                            
                            print(f"  {i+1}. {target_id} - Distance: {distance} - Method: {method}")
                    else:
                        print(f"Error: {result.get('error')}")
                
                else:
                    print("Unknown command. Try 'ships', 'status', 'send', 'ping', or 'contacts'")
                
        except KeyboardInterrupt:
            print("\nStopping simulation...")
            
        finally:
            runner.stop()
            print("Simulation stopped")
            
    except Exception as e:
        print(f"Error running simulation: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    return 0

def run_gui_mode(args):
    """Run simulator with GUI"""
    try:
        # Set the scenario as an environment variable for the GUI to read
        scenario_name = args.scenario
        os.environ['HYBRID_SCENARIO'] = scenario_name
        
        print(f"Starting GUI with scenario: {scenario_name}")
        
        # Start the GUI
        import gui_control
        gui_control.create_gui()
        
    except Exception as e:
        print(f"Error starting GUI: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    return 0

def main():
    """Main entry point"""
    # Parse command line arguments
    args = parse_arguments()
    
    # Set debug logging if requested
    if args.debug:
        logger.setLevel(logging.DEBUG)
        print("Debug logging enabled")
    
    # Run in console or GUI mode
    if args.nogui:
        return run_console_mode(args)
    else:
        return run_gui_mode(args)

if __name__ == "__main__":
    sys.exit(main())
