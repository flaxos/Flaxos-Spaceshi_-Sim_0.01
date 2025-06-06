# hybrid/gui/run_gui.py

import argparse
import json
import os
import threading
import tkinter as tk
from tkinter import filedialog
# Use the newer Simulator class instead of the deprecated Simulation
from hybrid.simulator import Simulator

class SimulatorGUI(tk.Tk):
    def __init__(self, ship_configs):
        super().__init__()
        self.title("Spaceship Simulator")
        # Create the simulator and load ships from the provided config
        self.sim = Simulator()
        for ship_id, config in ship_configs.items():
            self.sim.add_ship(ship_id, config)
        self._build_widgets()
        self._start_simulation_thread()

    def _build_widgets(self):
        # Add GUI elements (buttons, labels, etc.) to interact with the simulation
        pass

    def _start_simulation_thread(self):
        thread = threading.Thread(target=self.sim.run, args=(60.0,), daemon=True)
        thread.start()

def main():
    parser = argparse.ArgumentParser(description="Run the simulator GUI")
    parser.add_argument(
        "--config",
        "-c",
        help="Path to ship configuration JSON file",
    )
    args = parser.parse_args()

    config_path = args.config
    if not config_path:
        if os.path.exists("ships_config.json"):
            config_path = "ships_config.json"
        else:
            root = tk.Tk()
            root.withdraw()
            config_path = filedialog.askopenfilename(
                title="Select ship configuration file",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if not config_path:
                print("No configuration file selected")
                return

    with open(config_path, "r") as f:
        ship_configs = json.load(f)

    app = SimulatorGUI(ship_configs)
    app.mainloop()

if __name__ == "__main__":
    main()
