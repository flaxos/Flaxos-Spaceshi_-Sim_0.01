# hybrid/gui/run_gui.py
import threading
import tkinter as tk
import json
from tkinter import filedialog
from hybrid.systems.simulation import Simulation


def start_sim(sim, total_time):
    sim.run(total_time)


def launch():
    path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
    if not path:
        return
    with open(path) as f:
        configs = json.load(f)
    sim = Simulation(configs)
    t = threading.Thread(target=start_sim, args=(sim, 10.0), daemon=True)
    t.start()


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Spaceship Simulator")
    btn = tk.Button(root, text="Load Config and Run", command=launch)
    btn.pack(padx=20, pady=20)
    root.mainloop()
