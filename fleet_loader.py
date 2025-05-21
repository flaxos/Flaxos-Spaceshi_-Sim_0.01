import time
from scenario_loader import load_scenario
from simulation import simulation_loop

if __name__ == '__main__':
    print("[SYSTEM] Loading scenario...")
    ships = load_scenario("example_scenario.json")
    print(f"[INFO] Loaded {len(ships)} ships.")

    print("[SYSTEM] Starting simulation loop.")
    try:
        simulation_loop(ships)
    except KeyboardInterrupt:
        print("\n[SYSTEM] Simulation halted by user.")
