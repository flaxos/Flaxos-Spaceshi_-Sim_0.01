# main.py — Entry point for simulation with scenario and sector support

import time
from scenario_loader import load_scenario
from simulation import simulation_loop
from sector_manager import SectorManager
from command_server import CommandServer  # ← Add this near the top



import os
import sys

print("[DEBUG] Starting main.py")
print(f"[DEBUG] Current working directory: {os.getcwd()}")

scenario_path = "example_scenario.json"

if not os.path.exists(scenario_path):
    print(f"[ERROR] Scenario file not found: {scenario_path}")
    sys.exit(1)

print("[SYSTEM] Initializing sector manager...")
sector_manager = SectorManager(sector_size=1000)

print("[SYSTEM] Loading scenario...")
ships = load_scenario(scenario_path, sector_manager=sector_manager)
print(f"[INFO] Loaded {len(ships)} ships.")

if not ships:
    print("[WARN] No ships loaded. Exiting.")
    sys.exit(0)

for ship in ships:
    sector_manager.add_ship(ship)

# After sector_manager and ship loading:
command_server = CommandServer(ships)
command_server.start()

print("[SYSTEM] Starting simulation loop.")
try:
    simulation_loop(ships, sector_manager)
except KeyboardInterrupt:
    print("\n[SYSTEM] Simulation halted by user.")
