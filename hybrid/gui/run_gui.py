#!/usr/bin/env python3
"""
Spaceship Simulator GUI & Headless Client

QUICKSTART:

1. Start the Simulator Server:
   python socket_listener.py --host 127.0.0.1 --port 9999

2. Start the GUI (default, recommended):
   python run_gui.py --config ships.json

3. Headless Mode (no UI, for tests/scripts):
   python run_gui.py --config ships.json --headless

ARGUMENTS:
  --config  Path to ships config JSON (required)
  --host    Simulator server host (default: 127.0.0.1)
  --port    Simulator server port (default: 9999)
  --headless  Run in headless (no-GUI) mode

The server must be running and listening on the specified host/port before starting the GUI or headless client.

Config file format: see ships.json.example or your server docs.

All simulator commands are mapped to explicit controls/tabs in GUI or CLI flags in headless mode.

"""

import json
import socket
import sys
import threading
import argparse
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

SERVER_TIMEOUT = 3

# --- SERVER COMMANDS ---

COMMANDS = [
    'get_state',
    'get_position',
    'get_velocity',
    'helm_override',
    'sensor_ping',
    'power_toggle',
    'get_power_status',
    'weapon_fire'
    # Add future commands here
]

# --- SERVER COMMUNICATION ---

def send_command_to_server(host, port, command_type, payload, timeout=SERVER_TIMEOUT):
    """Send a command to the simulator server and return its response."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((host, port))
            msg = json.dumps({'command_type': command_type, 'payload': payload})
            sock.sendall(msg.encode('utf-8'))
            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            return data.decode('utf-8')
    except Exception as e:
        return json.dumps({"error": str(e)})

def test_server_connection(host, port):
    """Return (connected, error) when testing server availability."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(SERVER_TIMEOUT)
            sock.connect((host, port))
            return True, None
    except Exception as e:
        return False, str(e)

# --- GUI APPLICATION ---

class ShipGUI(tk.Tk):
    def __init__(self, config_path, host='127.0.0.1', port=9999):
        self.host = host
        self.port = port
        self.ships = self.load_config(config_path)

        super().__init__()
        self.title("Spaceship Simulator Control")
        self.geometry("960x700")

        # State vars
        self.current_ship = tk.StringVar(value=list(self.ships.keys())[0])
        self.connection_state = tk.StringVar()
        self.last_server_error = None

        # Build GUI
        self.create_widgets()
        self.test_server_connection()

    def load_config(self, path):
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                if 'ships' in data and isinstance(data['ships'], list):
                    entries = data['ships']
                else:
                    return data
            elif isinstance(data, list):
                entries = data
            else:
                raise ValueError("Config JSON must be object or array")
            return {ship['id']: ship for ship in entries}
        except Exception as e:
            temp = tk.Tk(); temp.withdraw()
            messagebox.showerror("Config Error", f"Failed to load config: {e}")
            temp.destroy(); sys.exit(1)

    def test_server_connection(self):
        ok, err = test_server_connection(self.host, self.port)
        if ok:
            self.connection_state.set("Connected")
            self.last_server_error = None
        else:
            self.connection_state.set("!! NOT CONNECTED !!")
            self.last_server_error = err
        self.status_label.config(text=f"Server: {self.connection_state.get()}")

    def create_widgets(self):
        top = ttk.Frame(self); top.pack(fill='x', pady=5)
        ttk.Label(top, text="Ship:").pack(side='left')
        ship_combo = ttk.Combobox(top, values=list(self.ships.keys()), textvariable=self.current_ship, state="readonly")
        ship_combo.pack(side='left', padx=5)
        ship_combo.current(0)
        ttk.Button(top, text="Test Server", command=self.test_server_connection).pack(side='left', padx=5)
        self.status_label = ttk.Label(top, text="")
        self.status_label.pack(side='left', padx=20)

        # Tabs
        tabs = ttk.Notebook(self)
        tabs.pack(fill='both', expand=True, padx=5, pady=5)
        # --- General State Tab
        state_tab = ttk.Frame(tabs); tabs.add(state_tab, text="General State")
        self.create_state_tab(state_tab)
        # --- Navigation/Helm Tab
        nav_tab = ttk.Frame(tabs); tabs.add(nav_tab, text="Navigation/Helm")
        self.create_nav_tab(nav_tab)
        # --- Sensors Tab
        sensor_tab = ttk.Frame(tabs); tabs.add(sensor_tab, text="Sensors")
        self.create_sensors_tab(sensor_tab)
        # --- Power Tab
        power_tab = ttk.Frame(tabs); tabs.add(power_tab, text="Power")
        self.create_power_tab(power_tab)
        # --- Weapons Tab
        weapon_tab = ttk.Frame(tabs); tabs.add(weapon_tab, text="Weapons")
        self.create_weapons_tab(weapon_tab)
        # --- 2D Map Tab
        map_tab = ttk.Frame(tabs); tabs.add(map_tab, text="2D Map")
        self.create_map_tab(map_tab)
        # --- Debug Tab
        debug_tab = ttk.Frame(tabs); tabs.add(debug_tab, text="Debug")
        self.debug_text = scrolledtext.ScrolledText(debug_tab, state='disabled', height=16)
        self.debug_text.pack(expand=True, fill='both', padx=3, pady=3)

    def _parse_response(self, resp):
        try:
            return json.loads(resp)
        except Exception:
            return {"raw": resp}

    ### TAB BUILDERS ###

    def create_state_tab(self, parent):
        frame = ttk.Frame(parent); frame.pack(fill='both', expand=True, padx=8, pady=8)
        ttk.Button(frame, text="Get Full State", command=self.on_get_state).pack(anchor='w')
        ttk.Button(frame, text="Get Position", command=self.on_get_position).pack(anchor='w')
        ttk.Button(frame, text="Get Velocity", command=self.on_get_velocity).pack(anchor='w')
        self.state_display = scrolledtext.ScrolledText(frame, height=12, width=80, state='disabled')
        self.state_display.pack(fill='both', expand=True, pady=5)
    def create_nav_tab(self, parent):
        frame = ttk.LabelFrame(parent, text="Helm/NAV Controls"); frame.pack(fill='both', expand=True, padx=8, pady=8)
        # Throttle
        ttk.Label(frame, text="Throttle (0-100):").grid(row=0, column=0, sticky='w')
        self.throttle_var = tk.IntVar(value=50)
        throttle_slider = ttk.Scale(frame, from_=0, to=100, variable=self.throttle_var, orient='horizontal')
        throttle_slider.grid(row=0, column=1, sticky='ew')
        # Direction
        ttk.Label(frame, text="Direction (deg):").grid(row=1, column=0, sticky='w')
        self.direction_var = tk.DoubleVar(value=0.0)
        dir_entry = ttk.Entry(frame, textvariable=self.direction_var, width=8)
        dir_entry.grid(row=1, column=1, sticky='w')
        # Target Ship
        ttk.Label(frame, text="Target Ship:").grid(row=2, column=0, sticky='w')
        self.target_ship_var = tk.StringVar()
        target_combo = ttk.Combobox(frame, values=list(self.ships.keys()), textvariable=self.target_ship_var, state='readonly')
        target_combo.grid(row=2, column=1, sticky='w')
        target_combo.set(list(self.ships.keys())[0])
        # Send Button
        ttk.Button(frame, text="Helm Override", command=self.on_helm_override).grid(row=3, column=0, columnspan=2, pady=4)
        frame.grid_columnconfigure(1, weight=1)

    def create_sensors_tab(self, parent):
        frame = ttk.LabelFrame(parent, text="Sensors"); frame.pack(fill='both', expand=True, padx=8, pady=8)
        # Mode
        self.sensor_mode = tk.StringVar(value="passive")
        ttk.Label(frame, text="Sensor Mode:").pack(anchor='w')
        modes = ttk.Frame(frame); modes.pack(anchor='w')
        ttk.Radiobutton(modes, text='Passive', variable=self.sensor_mode, value='passive').pack(side='left')
        ttk.Radiobutton(modes, text='Active', variable=self.sensor_mode, value='active').pack(side='left', padx=10)
        # Ping
        ttk.Button(frame, text="Sensor Ping", command=self.on_sensor_ping).pack(anchor='w', pady=4)
        self.sensor_output = scrolledtext.ScrolledText(frame, width=60, height=8, state='disabled')
        self.sensor_output.pack(fill='both', expand=True, pady=2)

    def create_power_tab(self, parent):
        frame = ttk.LabelFrame(parent, text="Power Management"); frame.pack(fill='both', expand=True, padx=8, pady=8)
        self.power_state = tk.StringVar(value="Unknown")
        # Toggle
        self.power_mode_var = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Power ON/OFF", variable=self.power_mode_var, command=self.on_power_toggle).pack(anchor='w')
        ttk.Button(frame, text="Refresh Power State", command=self.on_get_power_status).pack(anchor='w', pady=3)
        ttk.Label(frame, textvariable=self.power_state).pack(anchor='w')

    def create_weapons_tab(self, parent):
        frame = ttk.LabelFrame(parent, text="Weapons Systems"); frame.pack(fill='both', expand=True, padx=8, pady=8)
        ttk.Button(frame, text="Fire Weapon", command=self.on_weapon_fire).pack(anchor='w')
        ttk.Label(frame, text="(Future: Add weapon selector/payload)").pack(anchor='w')

    def create_map_tab(self, parent):
        frame = ttk.Frame(parent); frame.pack(fill='both', expand=True, padx=8, pady=8)
        self.map_canvas = tk.Canvas(frame, bg='black', width=500, height=500)
        self.map_canvas.pack(fill='both', expand=True)
        ttk.Button(frame, text="Refresh Map", command=self.on_draw_map).pack(anchor='w')
        self.map_ships = {}

    ### COMMAND HANDLERS ###

    def on_get_state(self):
        payload = {"ship": self.current_ship.get()}
        resp = send_command_to_server(self.host, self.port, "get_state", payload)
        self.log_debug(f">> get_state {payload}\n<< {resp}")
        self._display_state(resp)

    def on_get_position(self):
        payload = {"ship": self.current_ship.get()}
        resp = send_command_to_server(self.host, self.port, "get_position", payload)
        self.log_debug(f">> get_position {payload}\n<< {resp}")
        self._display_state(resp)

    def on_get_velocity(self):
        payload = {"ship": self.current_ship.get()}
        resp = send_command_to_server(self.host, self.port, "get_velocity", payload)
        self.log_debug(f">> get_velocity {payload}\n<< {resp}")
        self._display_state(resp)

    def on_helm_override(self):
        payload = {
            "ship": self.current_ship.get(),
            "throttle": self.throttle_var.get(),
            "direction": self.direction_var.get(),
            "target": self.target_ship_var.get()
        }
        resp = send_command_to_server(self.host, self.port, "helm_override", payload)
        self.log_debug(f">> helm_override {payload}\n<< {resp}")
        data = self._parse_response(resp)
        if 'error' in data:
            messagebox.showerror("Helm", data['error'])
        else:
            messagebox.showinfo("Helm", json.dumps(data))

    def on_sensor_ping(self):
        payload = {"ship": self.current_ship.get(), "mode": self.sensor_mode.get()}
        resp = send_command_to_server(self.host, self.port, "sensor_ping", payload)
        self.log_debug(f">> sensor_ping {payload}\n<< {resp}")
        self._update_sensor_output(resp)

    def on_power_toggle(self):
        payload = {"ship": self.current_ship.get(), "state": "on" if self.power_mode_var.get() else "off"}
        resp = send_command_to_server(self.host, self.port, "power_toggle", payload)
        self.log_debug(f">> power_toggle {payload}\n<< {resp}")
        data = self._parse_response(resp)
        self.power_state.set(str(data))

    def on_get_power_status(self):
        payload = {"ship": self.current_ship.get()}
        resp = send_command_to_server(self.host, self.port, "get_power_status", payload)
        self.log_debug(f">> get_power_status {payload}\n<< {resp}")
        data = self._parse_response(resp)
        self.power_state.set(json.dumps(data))

    def on_weapon_fire(self):
        payload = {"ship": self.current_ship.get()}
        resp = send_command_to_server(self.host, self.port, "weapon_fire", payload)
        self.log_debug(f">> weapon_fire {payload}\n<< {resp}")
        data = self._parse_response(resp)
        messagebox.showinfo("Weapon", json.dumps(data))

    def on_draw_map(self):
        # Get all ship positions and draw them
        ships = list(self.ships.keys())
        positions = {}
        for sid in ships:
            payload = {"ship": sid}
            resp = send_command_to_server(self.host, self.port, "get_position", payload)
            try:
                data = json.loads(resp) if resp and not resp.startswith("Error:") else {}
                positions[sid] = data.get('position', (0,0))
            except Exception:
                positions[sid] = (0,0)
        self._draw_ships_on_canvas(positions)

    ### DISPLAY HELPERS ###

    def _display_state(self, msg):
        self.state_display.config(state='normal')
        self.state_display.delete("1.0", "end")
        if isinstance(msg, str):
            data = self._parse_response(msg)
        else:
            data = msg
        self.state_display.insert("end", json.dumps(data, indent=2))
        self.state_display.config(state='disabled')

    def _update_sensor_output(self, msg):
        self.sensor_output.config(state='normal')
        self.sensor_output.delete("1.0", "end")
        if isinstance(msg, str):
            data = self._parse_response(msg)
        else:
            data = msg
        self.sensor_output.insert("end", json.dumps(data, indent=2))
        self.sensor_output.config(state='disabled')

    def _draw_ships_on_canvas(self, positions):
        c = self.map_canvas
        c.delete("all")
        w, h = int(c['width']), int(c['height'])
        cx, cy = w//2, h//2
        scale = 5  # pixels per unit (adjust as needed)
        for i, (sid, pos) in enumerate(positions.items()):
            x, y = pos if isinstance(pos, (tuple, list)) and len(pos)==2 else (0,0)
            px, py = cx + scale*x, cy - scale*y
            color = 'yellow' if sid == self.current_ship.get() else 'cyan'
            c.create_oval(px-10, py-10, px+10, py+10, fill=color)
            c.create_text(px, py, text=sid, fill='black')

    def log_debug(self, message):
        self.debug_text.configure(state='normal')
        self.debug_text.insert('end', message + '\n')
        self.debug_text.see('end')
        self.debug_text.configure(state='disabled')

# --- HEADLESS MODE ---

def run_headless(args, ships):
    print("Headless mode: 1:1 command mapping, no GUI")
    print(f"Connecting to {args.host}:{args.port}")
    ok, err = test_server_connection(args.host, args.port)
    if not ok:
        print(f"ERROR: Could not connect to server: {err}")
        sys.exit(2)
    print("Available ships:", ", ".join(ships.keys()))
    print("Available commands:", ", ".join(COMMANDS))
    print("Sample usage: --cmd get_state --ship SHIPID")
    parser = argparse.ArgumentParser()
    parser.add_argument('--cmd', required=True, choices=COMMANDS)
    parser.add_argument('--ship', required=True, help="Ship ID")
    parser.add_argument('--throttle', type=int)
    parser.add_argument('--direction', type=float)
    parser.add_argument('--target')
    parser.add_argument('--mode')
    parser.add_argument('--state')
    parser.add_argument('--json', help="Raw JSON payload (overrides others)")
    cli = parser.parse_args(sys.argv[sys.argv.index('--headless')+1:])

    # Build payload
    if cli.json:
        payload = json.loads(cli.json)
    else:
        payload = {'ship': cli.ship}
        if cli.throttle is not None: payload['throttle'] = cli.throttle
        if cli.direction is not None: payload['direction'] = cli.direction
        if cli.target: payload['target'] = cli.target
        if cli.mode: payload['mode'] = cli.mode
        if cli.state: payload['state'] = cli.state
    resp = send_command_to_server(args.host, args.port, cli.cmd, payload)
    print(f">> {cli.cmd} {payload}\n<< {resp}")

# --- MAIN ENTRY POINT ---

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Spaceship Simulator GUI/Headless Client")
    parser.add_argument('--config', required=True, help='Path to ships JSON config')
    parser.add_argument('--host', default='127.0.0.1', help='Simulator host')
    parser.add_argument('--port', type=int, default=9999, help='Simulator port')
    parser.add_argument('--headless', action='store_true', help='Run in headless (no-GUI) mode')
    args = parser.parse_args()

    # Load ships config first (needed both for GUI and headless)
    try:
        with open(args.config) as f:
            ships_data = json.load(f)
        if isinstance(ships_data, dict) and 'ships' in ships_data:
            ships = {ship['id']: ship for ship in ships_data['ships']}
        elif isinstance(ships_data, dict):
            ships = ships_data
        elif isinstance(ships_data, list):
            ships = {ship['id']: ship for ship in ships_data}
        else:
            raise ValueError("config JSON should be object or array of ships")
    except Exception as e:
        print(f"Config load error: {e}")
        sys.exit(1)

    if args.headless:
        run_headless(args, ships)
    else:
        app = ShipGUI(args.config, host=args.host, port=args.port)
        app.mainloop()
