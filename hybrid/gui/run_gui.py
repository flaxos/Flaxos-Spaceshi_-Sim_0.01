# hybrid/gui/run_gui.py

import argparse
import json
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
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

        # Keep references to config and selection
        self.ship_configs = ship_configs
        self.selected_ship_id = next(iter(self.sim.ships)) if self.sim.ships else None

        self._build_widgets()
        self._start_simulation_thread()

    def _build_widgets(self):
        """Create all main GUI widgets."""

        # Ship selector
        selector_frame = tk.Frame(self)
        selector_frame.pack(padx=10, pady=5, fill="x")

        tk.Label(selector_frame, text="Ship:").pack(side=tk.LEFT)
        self.ship_var = tk.StringVar(value=self.selected_ship_id)
        ship_ids = list(self.sim.ships.keys())
        self.ship_menu = tk.OptionMenu(selector_frame, self.ship_var, *ship_ids, command=self._on_ship_select)
        self.ship_menu.pack(side=tk.LEFT, padx=5)

        # Navigation controls
        nav_frame = tk.LabelFrame(self, text="Navigation")
        nav_frame.pack(padx=10, pady=5, fill="x")

        self.autopilot_var = tk.BooleanVar()
        tk.Checkbutton(nav_frame, text="Autopilot", variable=self.autopilot_var,
                       command=self._toggle_autopilot).grid(row=0, column=0, columnspan=2, sticky="w")

        tk.Label(nav_frame, text="Target X:").grid(row=1, column=0, sticky="e")
        self.target_x = tk.Entry(nav_frame, width=8)
        self.target_x.grid(row=1, column=1)
        tk.Label(nav_frame, text="Target Y:").grid(row=2, column=0, sticky="e")
        self.target_y = tk.Entry(nav_frame, width=8)
        self.target_y.grid(row=2, column=1)
        tk.Label(nav_frame, text="Target Z:").grid(row=3, column=0, sticky="e")
        self.target_z = tk.Entry(nav_frame, width=8)
        self.target_z.grid(row=3, column=1)

        tk.Button(nav_frame, text="Set Course", command=self._set_course).grid(row=4, column=0, columnspan=2, pady=4)

        # Control buttons
        ctrl_frame = tk.LabelFrame(self, text="Controls")
        ctrl_frame.pack(padx=10, pady=5, fill="x")

        tk.Button(ctrl_frame, text="Thrust +", command=lambda: self._adjust_thrust(1)).grid(row=0, column=0, padx=2, pady=2)
        tk.Button(ctrl_frame, text="Thrust -", command=lambda: self._adjust_thrust(-1)).grid(row=0, column=1, padx=2, pady=2)
        tk.Button(ctrl_frame, text="Pitch +", command=lambda: self._rotate('pitch', 5)).grid(row=1, column=0, padx=2, pady=2)
        tk.Button(ctrl_frame, text="Pitch -", command=lambda: self._rotate('pitch', -5)).grid(row=1, column=1, padx=2, pady=2)
        tk.Button(ctrl_frame, text="Yaw +", command=lambda: self._rotate('yaw', 5)).grid(row=2, column=0, padx=2, pady=2)
        tk.Button(ctrl_frame, text="Yaw -", command=lambda: self._rotate('yaw', -5)).grid(row=2, column=1, padx=2, pady=2)
        tk.Button(ctrl_frame, text="Roll +", command=lambda: self._rotate('roll', 5)).grid(row=3, column=0, padx=2, pady=2)
        tk.Button(ctrl_frame, text="Roll -", command=lambda: self._rotate('roll', -5)).grid(row=3, column=1, padx=2, pady=2)

        # Status display
        status_frame = tk.LabelFrame(self, text="Status")
        status_frame.pack(padx=10, pady=5, fill="x")

        self.pos_var = tk.StringVar(value="0,0,0")
        tk.Label(status_frame, textvariable=self.pos_var).pack(anchor="w")
        self.vel_var = tk.StringVar(value="0,0,0")
        tk.Label(status_frame, textvariable=self.vel_var).pack(anchor="w")
        self.ori_var = tk.StringVar(value="0,0,0")
        tk.Label(status_frame, textvariable=self.ori_var).pack(anchor="w")

        # Sensor controls
        sensor_frame = tk.LabelFrame(self, text="Sensors")
        sensor_frame.pack(padx=10, pady=5, fill="both", expand=True)

        btn_frame = tk.Frame(sensor_frame)
        btn_frame.pack(anchor="w")
        tk.Button(btn_frame, text="Ping", command=self._ping_sensors).pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(btn_frame, text="Refresh", command=self._refresh_contacts).pack(side=tk.LEFT, padx=2, pady=2)

        self.contact_box = scrolledtext.ScrolledText(sensor_frame, height=5, width=40)
        self.contact_box.pack(fill="both", expand=True, padx=5, pady=2)

        # Kick off periodic updates
        self.after(500, self._update_status)

    def _start_simulation_thread(self):
        thread = threading.Thread(target=self.sim.run, args=(60.0,), daemon=True)
        thread.start()

    # --- Command callbacks -------------------------------------------------

    def _current_ship(self):
        ship_id = self.ship_var.get()
        return self.sim.get_ship(ship_id)

    def _on_ship_select(self, ship_id):
        """Callback when the user selects a different ship."""
        self.selected_ship_id = ship_id
        # Update autopilot checkbox based on ship state if available
        ship = self._current_ship()
        if ship and 'navigation' in ship.systems:
            nav_state = ship.systems['navigation']
            if isinstance(nav_state, dict):
                enabled = nav_state.get('autopilot_enabled', False)
            else:
                enabled = getattr(nav_state, 'autopilot_enabled', False)
            self.autopilot_var.set(enabled)

    def _toggle_autopilot(self):
        ship = self._current_ship()
        if not ship:
            return
        ship.command("autopilot", {"enabled": self.autopilot_var.get()})

    def _set_course(self):
        ship = self._current_ship()
        if not ship:
            return
        try:
            coords = {
                "x": float(self.target_x.get()),
                "y": float(self.target_y.get()),
                "z": float(self.target_z.get()),
            }
        except ValueError:
            messagebox.showerror("Invalid Input", "Target coordinates must be numbers")
            return
        ship.command("set_course", coords)

    def _adjust_thrust(self, delta):
        ship = self._current_ship()
        if not ship:
            return
        current = ship.thrust.get("z", 0)
        ship.command("set_thrust", {"z": current + delta})

    def _rotate(self, axis, amount):
        ship = self._current_ship()
        if not ship:
            return
        ship.command("rotate", {"axis": axis, "value": amount})

    def _ping_sensors(self):
        """Trigger an active sensor ping on the selected ship."""
        ship = self._current_ship()
        if ship:
            ship.command("ping_sensors", {})

    def _refresh_contacts(self):
        """Update the contact list from the ship's sensors."""
        ship = self._current_ship()
        self.contact_box.delete("1.0", tk.END)
        if not ship:
            return
        result = ship.command("get_contacts", {})
        contacts = result.get("contacts", []) if isinstance(result, dict) else []
        for c in contacts:
            cid = c.get("id", "unknown")
            dist = c.get("distance", 0)
            method = c.get("method", c.get("detection_method", "?"))
            self.contact_box.insert(tk.END, f"{cid} @ {dist:.1f} [{method}]\n")

    def _update_status(self):
        ship = self._current_ship()
        if ship:
            state = ship.get_state()
            pos = state.get("position", {})
            vel = state.get("velocity", {})
            ori = state.get("orientation", {})
            self.pos_var.set(f"Pos: {pos.get('x',0):.1f}, {pos.get('y',0):.1f}, {pos.get('z',0):.1f}")
            self.vel_var.set(f"Vel: {vel.get('x',0):.1f}, {vel.get('y',0):.1f}, {vel.get('z',0):.1f}")
            self.ori_var.set(f"Ori: {ori.get('pitch',0):.1f}, {ori.get('yaw',0):.1f}, {ori.get('roll',0):.1f}")
            self._refresh_contacts()
        self.after(500, self._update_status)

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
