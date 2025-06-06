# hybrid/gui/run_gui.py

import threading
import json
import tkinter as tk
from hybrid.systems.simulation import Simulation

class SimulatorGUI(tk.Tk):
    def __init__(self, ship_configs):
        super().__init__()
        self.title("Spaceship Simulator")
        self.sim = Simulation(ship_configs)
        self._build_widgets()
        self._start_simulation_thread()

    def _build_widgets(self):
        # Add GUI elements (buttons, labels, etc.) to interact with the simulation
        pass

    def _start_simulation_thread(self):
        thread = threading.Thread(target=self.sim.run, args=(60.0,), daemon=True)
        thread.start()

def main():
    with open("ships_config.json", "r") as f:
        ship_configs = json.load(f)
    app = SimulatorGUI(ship_configs)
    app.mainloop()

if __name__ == "__main__":
    main()
