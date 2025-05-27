# main.py
import time
from scenario_loader import load_scenario
from simulation import simulation_loop
from sector_manager import SectorManager
from command_server import CommandServer
from utils.logger import logger

def main():
    scenario_path = "config/example_scenario.json"
    sector_manager = SectorManager(sector_size=1000)
    ships = load_scenario(scenario_path, sector_manager=sector_manager)
    logger.info(f"Loaded {len(ships)} ships.")

    command_server = CommandServer(ships)
    command_server.start()

    sim = simulation_loop(sector_manager.sectors)

    try:
        while True:
            next(sim)
            time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("Simulation loop stopped.")

if __name__ == "__main__":
    main()
