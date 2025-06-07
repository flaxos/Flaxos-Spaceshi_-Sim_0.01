# hybrid/gui/run_gui.py

import argparse
import json
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from hybrid.simulator import Simulator
from hybrid.command_handler import handle_command_request


class SimulatorGUI(tk.Tk):
    def __init__(self, ship_configs):
        super().__init__()
        self.title("Spaceship Simulator")
        self.sim = Simulator()
        for ship_id, config in ship_configs.items():
            self.sim.add_ship(ship_id, config)

        self.ship_configs = ship_configs
        self.selected_ship_id = next(iter(self.sim.ships)) if self.sim.ships else None

        self._build_widgets()
        self._start_simulation_thread()

    def _build_widgets(self):
        """Create all main GUI widgets."""
        selector_frame = tk.Frame(self)
        selector_frame.pack(padx=10, pady=5, fill="x")

        tk.Label(selector_frame, text="Ship:").pack(side=tk.LEFT)
        self.ship_var = tk.StringVar(value=self.selected_ship_id)
        ship_ids = list(self.sim.ships.keys())
        self.ship_menu = tk.OptionMenu(selector_frame, self.ship_var, *ship_ids, command=lambda _:_)
        self.ship_menu.pack(side=tk.LEFT, padx=5)

        nav_frame = tk.LabelFrame(self, text="Navigation")
        nav_frame.pack(padx=10, pady=5, fill="x")

        self.autopilot_var = tk.BooleanVar()
        tk.Checkbutton(
            nav_frame,
            text="Autopilot",
            variable=self.autopilot_var,
            command=self._toggle_autopilot,
        ).grid(row=0, column=0, columnspan=2, sticky="w")

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

        status_frame = tk.LabelFrame(self, text="Status")
        status_frame.pack(padx=10, pady=5, fill="x")

        self.pos_var = tk.StringVar(value="0,0,0")
        tk.Label(status_frame, textvariable=self.pos_var).pack(anchor="w")
        self.vel_var = tk.StringVar(value="0,0,0")
        tk.Label(status_frame, textvariable=self.vel_var).pack(anchor="w")
        self.ori_var = tk.StringVar(value="0,0,0")
        tk.Label(status_frame, textvariable=self.ori_var).pack(anchor="w")

        cmd_frame = tk.LabelFrame(self, text="Command")
        cmd_frame.pack(padx=10, pady=5, fill="x")

        self.command_entry = tk.Entry(cmd_frame)
        self.command_entry.pack(side=tk.LEFT, expand=True, fill="x", padx=5)
        tk.Button(cmd_frame, text="Send", command=self._send_command).pack(side=tk.LEFT)
        self.command_output = tk.Text(cmd_frame, height=4, state="disabled")
        self.command_output.pack(padx=5, pady=5, fill="x")

        self.after(500, self._update_status)

    def _start_simulation_thread(self):
        thread = threading.Thread(target=self.sim.run, args=(60.0,), daemon=True)
        thread.start()

    def _current_ship(self):
        ship_id = self.ship_var.get()
        return self.sim.get_ship(ship_id)

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

    def _send_command(self):
        ship = self._current_ship()
        if not ship:
            return

        data = self.command_entry.get()
        if not data:
            return
        try:
            cmd = json.loads(data)
            if "ship" not in cmd:
                cmd["ship"] = ship.id
            response = handle_command_request(cmd, ship)
        except json.JSONDecodeError:
            response = ship.command(data)

        self.command_output.configure(state="normal")
        self.command_output.delete("1.0", tk.END)
        if isinstance(response, str):
            self.command_output.insert(tk.END, response)
        else:
            self.command_output.insert(tk.END, json.dumps(response, indent=2))
        self.command_output.configure(state="disabled")

    def _update_status(self):
        ship = self._current_ship()
        if ship:
            state = ship.get_state()
            pos = state.get("position", {})
            vel = state.get("velocity", {})
            ori = state.get("orientation", {})
            self.pos_var.set(
                f"Pos: {pos.get('x',0):.1f}, {pos.get('y',0):.1f}, {pos.get('z',0):.1f}"
            )
            self.vel_var.set(
                f"Vel: {vel.get('x',0):.1f}, {vel.get('y',0):.1f}, {vel.get('z',0):.1f}"
            )
            self.ori_var.set(
                f"Ori: {ori.get('pitch',0):.1f}, {ori.get('yaw',0):.1f}, {ori.get('roll',0):.1f}"
            )
        self.after(500, self._update_status)


def main():
    parser = argparse.ArgumentParser(description="Run the simulator GUI")
    parser.add_argument(
        "--config",
        "-c",
        help="Path to ship configuration JSON file",
    )
    parser.add_argument(
        "--fleet-dir",
        "-f",
        help="Directory containing ship JSON files",
    )
    args = parser.parse_args()

    ships = {}
    if args.fleet_dir:
        if not os.path.isdir(args.fleet_dir):
            print(f"Fleet directory not found: {args.fleet_dir}")
            return
        for filename in os.listdir(args.fleet_dir):
            if filename.endswith(".json"):
                path = os.path.join(args.fleet_dir, filename)
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "id" in data:
                        ships[data["id"]] = data
                    elif isinstance(data, dict):
                        ships.update(data)
                except Exception as e:
                    print(f"Failed to load {path}: {e}")
    else:
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
            data = json.load(f)
            if isinstance(data, dict) and "id" in data:
                ships[data["id"]] = data
            else:
                ships.update(data)

    if not ships:
        print("No ship configurations loaded")
        return

    app = SimulatorGUI(ships)
    app.mainloop()


if __name__ == "__main__":
    main()
