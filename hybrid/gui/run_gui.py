import json
import socket
import sys
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# Socket-based command sender (adjust to your send.py if needed)
def send_command_to_server(host, port, command_type, payload):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((host, port))
            message = json.dumps({'command_type': command_type, 'payload': payload})
            sock.sendall(message.encode('utf-8'))
            response = sock.recv(4096)
            return response.decode('utf-8')
    except Exception as e:
        return f"Error: {e}"

class ShipGUI(tk.Tk):
    def __init__(self, config_path, host='127.0.0.1', port=9999):
        # Load config before initializing GUI root
        self.ships = self.load_config(config_path)

        # Initialize the main window
        super().__init__()
        self.title("Spaceship Simulator Control")
        self.geometry("800x600")

        self.host = host
        self.port = port

        # State variables
        self.current_ship = tk.StringVar()
        self.command_type = tk.StringVar()
        self.payload_entry = tk.StringVar()
        self.power_mode = tk.BooleanVar()
        self.sensor_mode = tk.StringVar(value='passive')

        # Build UI
        self.create_widgets()

    def load_config(self, path):
        try:
            with open(path) as f:
                data = json.load(f)

            # Determine if the JSON is a dict of ships, has a 'ships' list, or is a list
            if isinstance(data, dict):
                if 'ships' in data and isinstance(data['ships'], list):
                    entries = data['ships']
                else:
                    # assume top-level mapping of id->ship objects
                    return data
            elif isinstance(data, list):
                entries = data
            else:
                raise ValueError("Config JSON must be an object or array of ships")

            # Convert list of ship dicts to id->dict
            return { ship['id']: ship for ship in entries }

        except Exception as e:
            # Use a temporary root to show the error
            temp = tk.Tk()
            temp.withdraw()
            messagebox.showerror("Error", f"Failed to load config: {e}")
            temp.destroy()
            sys.exit(1)

    def create_widgets(self):
        # Top controls frame
        frame_top = ttk.Frame(self)
        frame_top.pack(fill='x', padx=5, pady=5)

        # Ship selector
        ttk.Label(frame_top, text="Select Ship:").pack(side='left')
        ship_combo = ttk.Combobox(
            frame_top, values=list(self.ships.keys()), textvariable=self.current_ship
        )
        ship_combo.pack(side='left', padx=5)
        ship_combo.current(0)

        # Command dropdown
        ttk.Label(frame_top, text="Command:").pack(side='left', padx=(20, 0))
        cmd_list = [
            'get_state', 'get_position', 'get_velocity',
            'helm_override', 'sensor_ping', 'power_toggle', 'weapon_fire'
        ]
        cmd_combo = ttk.Combobox(
            frame_top, values=cmd_list, textvariable=self.command_type
        )
        cmd_combo.pack(side='left', padx=5)
        cmd_combo.current(0)

        # Payload entry
        ttk.Label(frame_top, text="Payload JSON:").pack(side='left', padx=(20, 0))
        ttk.Entry(frame_top, textvariable=self.payload_entry, width=30).pack(side='left', padx=5)

        ttk.Button(frame_top, text="Send", command=self.on_send).pack(side='left', padx=5)

        # Notebook for tabs
        tabs = ttk.Notebook(self)
        tabs.pack(expand=True, fill='both', padx=5, pady=5)

        # Control tab
        control_frame = ttk.Frame(tabs)
        tabs.add(control_frame, text='Control')
        self.create_control_tab(control_frame)

        # Debug tab
        debug_frame = ttk.Frame(tabs)
        tabs.add(debug_frame, text='Debug')
        self.debug_text = scrolledtext.ScrolledText(debug_frame, state='disabled')
        self.debug_text.pack(expand=True, fill='both', padx=5, pady=5)

    def create_control_tab(self, parent):
        # Sensor controls
        sensor_frame = ttk.LabelFrame(parent, text="Sensors")
        sensor_frame.pack(fill='x', padx=10, pady=10)
        ttk.Radiobutton(
            sensor_frame, text='Passive', variable=self.sensor_mode, value='passive'
        ).pack(side='left', padx=5)
        ttk.Radiobutton(
            sensor_frame, text='Active', variable=self.sensor_mode, value='active'
        ).pack(side='left', padx=5)
        ttk.Button(
            sensor_frame, text='Ping', command=self.on_sensor_ping
        ).pack(side='left', padx=10)

        # Power management
        power_frame = ttk.LabelFrame(parent, text="Power Management")
        power_frame.pack(fill='x', padx=10, pady=10)
        ttk.Checkbutton(
            power_frame, text='Enable Power Mode', variable=self.power_mode
        ).pack(side='left', padx=5)
        ttk.Button(
            power_frame, text='Refresh Power Status', command=self.on_power_status
        ).pack(side='left', padx=10)
        self.power_status_label = ttk.Label(power_frame, text='Status: unknown')
        self.power_status_label.pack(side='left', padx=10)

        # Weapons placeholder
        weapon_frame = ttk.LabelFrame(parent, text="Weapons")
        weapon_frame.pack(fill='x', padx=10, pady=10)
        ttk.Button(
            weapon_frame, text='Fire Weapon (placeholder)', command=self.on_weapon_fire
        ).pack(side='left', padx=5)

    def log_debug(self, message):
        self.debug_text.configure(state='normal')
        self.debug_text.insert('end', message + '\n')
        self.debug_text.see('end')
        self.debug_text.configure(state='disabled')

    def on_send(self):
        ship_id = self.current_ship.get()
        cmd = self.command_type.get()
        try:
            payload = json.loads(self.payload_entry.get()) if self.payload_entry.get() else {}
        except json.JSONDecodeError:
            messagebox.showerror("Error", "Invalid JSON payload")
            return
        payload['ship'] = ship_id
        response = send_command_to_server(self.host, self.port, cmd, payload)
        self.log_debug(f">> Sent: {cmd} {payload}\n<< Received: {response}")

    def on_sensor_ping(self):
        # Send ping with selected mode
        payload = {'mode': self.sensor_mode.get(), 'ship': self.current_ship.get()}
        response = send_command_to_server(self.host, self.port, 'sensor_ping', payload)
        self.log_debug(f">> Sensor ping ({payload['mode']})\n<< {response}")

    def on_power_status(self):
        response = send_command_to_server(
            self.host, self.port, 'get_power_status', {'ship': self.current_ship.get()}
        )
        self.power_status_label.config(text=f"Status: {response}")
        self.log_debug(f"Power status: {response}")

    def on_weapon_fire(self):
        # Placeholder for future weapon payloads
        payload = {'ship': self.current_ship.get()}
        response = send_command_to_server(self.host, self.port, 'weapon_fire', payload)
        self.log_debug(f"Weapon fire placeholder\n<< {response}")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True, help='Path to ships JSON config')
    parser.add_argument('--host', default='127.0.0.1', help='Simulator host')
    parser.add_argument('--port', type=int, default=9999, help='Simulator port')
    args = parser.parse_args()

    app = ShipGUI(args.config, host=args.host, port=args.port)
    app.mainloop()
