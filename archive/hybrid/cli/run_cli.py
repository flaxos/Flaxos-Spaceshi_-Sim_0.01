# hybrid/cli/run_cli.py

import argparse
import json
from hybrid.systems.simulation import Simulation


def main():
    parser = argparse.ArgumentParser(description="Spaceship Simulator CLI")
    parser.add_argument("--config", required=True, help="Path to ships JSON config")
    parser.add_argument("--time", type=float, default=10.0, help="Total simulation time (seconds)")
    args = parser.parse_args()

    with open(args.config, "r") as f:
        ship_configs = json.load(f)

    sim = Simulation(ship_configs)
    sim.run(args.time)

if __name__ == "__main__":
    main()
