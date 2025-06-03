# simple_gui.py
import tkinter as tk
from tkinter import ttk, scrolledtext
import json
import time
import threading
from hybrid_runner import HybridRunner

# Constants
AUTO_REFRESH_INTERVAL = 1000  # milliseconds

class HybridSimGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Hybrid Ship Simulator")
        self.root.geometry("1400x800")
        
        # Create the hybrid runner
        self.runner = HybridRunner()
        self.selected_ship = None
        self.update_thread = None
        self.running = False
        self.auto_refresh = tk.BooleanVar(value=False)
        self.auto_refresh_id = None
        
        # State variables
        self.state_vars = {}
        self.nav_fields = {}
        self.thrust_fields = {}
        
        # Create the GUI
        self._create_widgets()
        
    def _create_widgets(self):
        # Main frames - use left and right panes
        left_frame = ttk.Frame(self.root, padding="5")
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        right_frame = ttk.Frame(self.root, padding="5")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create control panel
        control_frame = ttk.LabelFrame(left_frame, text="Control Panel", padding="5")
        control_frame.pack(fill=tk.X, pady=5)
        
        # Create buttons
        ttk.Button(control_frame, text="Load Ships", command=self._load_ships).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(control_frame, text="Load Scenario", command=self._load_scenario).grid(row=0, column=1, padx=5, pady=5)
        self.start_stop_button = ttk.Button(control_frame, text="Start Simulation", command=self._toggle_simulation)
        self.start_stop_button.grid(row=0, column=2, padx=5, pady=5)
        ttk.Button(control_frame, text="Save States", command=self._save_states).grid(row=0, column=3, padx=5, pady=5)
        
        # Create ship selection panel
        ship_frame = ttk.LabelFrame(left_frame, text="Ship Selection", padding="5")
        ship_frame.pack(fill=tk.X, pady=5)
        
        self.ship_listbox = tk.Listbox(ship_frame, height=3)
        self.ship_listbox.pack(fill=tk.X, padx=5, pady=5)
        self.ship_listbox.bind("<<ListboxSelect>>", self._on_ship_select)
        
        # Create navigation panel
        self._create_navigation_panel(left_frame)
        
        # Create thrust panel
        self._create_thrust_panel(left_frame)
        
        # Create sensors panel
        self._create_sensors_panel(left_frame)
        
        # Create custom command panel
        self._create_command_panel(left_frame)
        
        # Create refresh controls
        refresh_frame = ttk.Frame(left_frame)
        refresh_frame.pack(pady=8)
        
        ttk.Button(refresh_frame, text="Refresh Panels", 
                  command=self._refresh_panels).pack(side=tk.LEFT, padx=5)
        
        ttk.Checkbutton(refresh_frame, text="Auto Refresh", 
                       variable=self.auto_refresh, 
                       command=self._toggle_auto_refresh).pack(side=tk.LEFT)
        
        # Create output panel (right side)
        self._create_output_panel(right_frame)
        
        # Create state panel (right side)
        self._create_state_panel(right_frame)
        
        # Create contacts panel (right side)
        self._create_contacts_panel(right_frame)
        
        # Status bar at bottom
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_frame, textvariable=self.status_var, 
                 relief=tk.SUNKEN, anchor=tk.W).pack(fill=tk.X)
    
    def _create_navigation_panel(self, parent):
        """Create navigation controls"""
        nav_frame = ttk.LabelFrame(parent, text="Navigation", padding="5")
        nav_frame.pack(fill=tk.X, pady=5)
        
        coords_frame = ttk.Frame(nav_frame)
        coords_frame.pack(fill=tk.X, padx=5, pady=5)
        
        for axis in ["x", "y", "z"]:
            ttk.Label(coords_frame, text=f"{axis.upper()}: ").grid(
                row=0, column={"x":0, "y":2, "z":4}[axis], padx=2)
            self.nav_fields[axis] = ttk.Entry(coords_frame, width=8)
            self.nav_fields[axis].grid(
                row=0, column={"x":1, "y":3, "z":5}[axis], padx=2)
        
        buttons_frame = ttk.Frame(nav_frame)
        buttons_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(buttons_frame, text="Set Course", 
                  command=self._set_course).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Enable Autopilot", 
                  command=self._enable_autopilot).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Disable Autopilot", 
                  command=self._disable_autopilot).pack(side=tk.LEFT, padx=5)
    
    def _create_thrust_panel(self, parent):
        """Create thrust controls"""
        thrust_frame = ttk.LabelFrame(parent, text="Thrust Control", padding="5")
        thrust_frame.pack(fill=tk.X, pady=5)
        
        controls_frame = ttk.Frame(thrust_frame)
        controls_frame.pack(fill=tk.X, padx=5, pady=5)
        
        for axis in ["x", "y", "z"]:
            ttk.Label(controls_frame, text=f"{axis.upper()}: ").grid(
                row=0, column={"x":0, "y":2, "z":4}[axis], padx=2)
            self.thrust_fields[axis] = ttk.Entry(controls_frame, width=8)
            self.thrust_fields[axis].grid(
                row=0, column={"x":1, "y":3, "z":5}[axis], padx=2)
        
        buttons_frame = ttk.Frame(thrust_frame)
        buttons_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(buttons_frame, text="Set Thrust", 
                  command=self._set_thrust).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Manual Helm On", 
                  command=self._manual_helm_on).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Manual Helm Off", 
                  command=self._manual_helm_off).pack(side=tk.LEFT, padx=5)
    
    def _create_sensors_panel(self, parent):
        """Create sensors controls"""
        sensors_frame = ttk.LabelFrame(parent, text="Sensors & Bio", padding="5")
        sensors_frame.pack(fill=tk.X, pady=5)
        
        self.cooldown_label = ttk.Label(sensors_frame, text="Cooldown: N/A", foreground="blue")
        self.cooldown_label.pack(padx=5, pady=5)
        
        buttons_frame = ttk.Frame(sensors_frame)
        buttons_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(buttons_frame, text="Ping Sensors", 
                  command=self._ping_sensors).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Override Bio Monitor", 
                  command=self._override_bio).pack(side=tk.LEFT, padx=5)
    
    def _create_command_panel(self, parent):
        """Create custom command entry panel"""
        cmd_frame = ttk.LabelFrame(parent, text="Custom Command", padding="5")
        cmd_frame.pack(fill=tk.X, pady=5)
        
        # Help text
        help_text = "Enter command and JSON arguments"
        ttk.Label(cmd_frame, text=help_text, font=('TkDefaultFont', 8)).pack(padx=5, pady=2, anchor=tk.W)
        
        # Command entry
        entry_frame = ttk.Frame(cmd_frame)
        entry_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(entry_frame, text="Command:").grid(row=0, column=0, padx=5, pady=5)
        self.command_var = tk.StringVar()
        ttk.Entry(entry_frame, textvariable=self.command_var, width=25).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(entry_frame, text="Args (JSON):").grid(row=1, column=0, padx=5, pady=5)
        self.args_var = tk.StringVar(value="{}")
        ttk.Entry(entry_frame, textvariable=self.args_var, width=25).grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Button(entry_frame, text="Send Command", 
                  command=self._send_command).grid(row=1, column=2, padx=5, pady=5)
        
        # Examples frame
        examples_frame = ttk.Frame(cmd_frame)
        examples_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(examples_frame, text="Examples:", font=('TkDefaultFont', 8, 'bold')).pack(anchor=tk.W)
        
        examples = [
            ("get_state", "{}"),
            ("set_thrust", '{"x": 5, "y": 0, "z": 0}'),
            ("get_system_state", '{"system": "propulsion"}'),
            ("rotate", '{"axis": "yaw", "value": 10}')
        ]
        
        for i, (cmd, args) in enumerate(examples):
            example_btn = ttk.Button(examples_frame, text=cmd, 
                                    command=lambda c=cmd, a=args: self._load_example(c, a))
            example_btn.pack(anchor=tk.W, padx=5, pady=2)
    
    def _create_output_panel(self, parent):
        """Create output log area"""
        output_frame = ttk.LabelFrame(parent, text="Raw Output Log", padding="5")
        output_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.output_text = scrolledtext.ScrolledText(output_frame, height=10, wrap=tk.WORD)
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        button_frame = ttk.Frame(output_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Clear Log", 
                  command=self._clear_output_log).pack(side=tk.RIGHT, padx=5, pady=2)
    
    def _create_state_panel(self, parent):
        """Create ship state display"""
        state_frame = ttk.LabelFrame(parent, text="Live Ship State", padding="5")
        state_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Create rows for state data in a grid layout
        fields_grid = ttk.Frame(state_frame)
        fields_grid.pack(fill=tk.X, padx=5, pady=5)
        
        # Define the fields to display in the state panel
        row1 = ["position_x", "position_y", "position_z"]
        row2 = ["velocity_x", "velocity_y", "velocity_z"]
        row3 = ["orientation_pitch", "orientation_yaw", "orientation_roll"]
        row4 = ["thrust_x", "thrust_y", "thrust_z"]
        
        all_rows = [
            ("Position", row1),
            ("Velocity", row2),
            ("Orientation", row3),
            ("Thrust", row4)
        ]
        
        # Create the state display grid
        for row_idx, (section_name, fields) in enumerate(all_rows):
            ttk.Label(fields_grid, text=section_name, font=('TkDefaultFont', 9, 'bold')).grid(
                row=row_idx*2, column=0, sticky=tk.W, padx=5, pady=2, columnspan=6)
            
            for col_idx, field in enumerate(fields):
                display_name = field.split('_')[1].upper() if '_' in field else field.upper()
                ttk.Label(fields_grid, text=f"{display_name}:").grid(
                    row=row_idx*2+1, column=col_idx*2, sticky=tk.W, padx=5, pady=2)
                
                var = tk.StringVar(value="N/A")
                entry = ttk.Entry(fields_grid, textvariable=var, width=10, state="readonly")
                entry.grid(row=row_idx*2+1, column=col_idx*2+1, padx=5, pady=2, sticky=tk.W)
                
                self.state_vars[field] = var
        
        # Systems status section
        systems_frame = ttk.LabelFrame(state_frame, text="Systems Status")
        systems_frame.pack(fill=tk.X, padx=5, pady=5)
        
        systems_grid = ttk.Frame(systems_frame)
        systems_grid.pack(fill=tk.X, padx=5, pady=5)
        
        systems = ["power", "propulsion", "sensors", "nav", "helm", "bio"]
        for i, system in enumerate(systems):
            ttk.Label(systems_grid, text=f"{system.capitalize()}:").grid(
                row=i//3, column=(i%3)*2, sticky=tk.W, padx=5, pady=2)
            
            var = tk.StringVar(value="Unknown")
            entry = ttk.Entry(systems_grid, textvariable=var, width=10, state="readonly")
            entry.grid(row=i//3, column=(i%3)*2+1, padx=5, pady=2, sticky=tk.W)
            
            self.state_vars[f"system_{system}"] = var
    
    def _create_contacts_panel(self, parent):
        """Create sensor contacts display"""
        contacts_frame = ttk.LabelFrame(parent, text="Sensor Contacts", padding="5")
        contacts_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.contacts_output = scrolledtext.ScrolledText(contacts_frame, height=6, wrap=tk.WORD)
        self.contacts_output.pack(fill=tk.X, padx=5, pady=5)
    
    def _load_ships(self):
        """Load ships from the fleet directory"""
        self.ship_listbox.delete(0, tk.END)
        count = self.runner.load_ships()
        
        if count > 0:
            # Get ship IDs from the simulator
            for ship_id in self.runner.simulator.ships.keys():
                self.ship_listbox.insert(tk.END, ship_id)
            self.status_var.set(f"Loaded {count} ships")
        else:
            self.status_var.set("No ships found")
            
    def _load_scenario(self):
        """Load a test scenario with multiple ships"""
        self.ship_listbox.delete(0, tk.END)
        
        # Create a simple scenario selection dialog
        scenarios = ["test_scenario"]  # Add more scenarios as they are created
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Select Scenario")
        dialog.geometry("300x200")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Choose a scenario:").pack(pady=10)
        
        scenario_var = tk.StringVar(value=scenarios[0])
        scenario_listbox = tk.Listbox(dialog, height=5)
        scenario_listbox.pack(fill=tk.X, padx=10, pady=5)
        
        for scenario in scenarios:
            scenario_listbox.insert(tk.END, scenario)
        
        def on_select():
            selection = scenario_listbox.curselection()
            if selection:
                selected_scenario = scenario_listbox.get(selection[0])
                count = self.runner.load_scenario(selected_scenario)
                
                if count > 0:
                    # Update ship listbox
                    self.ship_listbox.delete(0, tk.END)
                    for ship_id in self.runner.simulator.ships.keys():
                        self.ship_listbox.insert(tk.END, ship_id)
                    self.status_var.set(f"Loaded {count} ships from scenario: {selected_scenario}")
                    self._log_output(f"Loaded scenario: {selected_scenario} with {count} ships")
                else:
                    self.status_var.set(f"Failed to load scenario: {selected_scenario}")
                    
                dialog.destroy()
        
        ttk.Button(dialog, text="Load Selected Scenario", command=on_select).pack(pady=10)
        ttk.Button(dialog, text="Cancel", command=dialog.destroy).pack(pady=5)
        
        # Wait for the dialog to be closed
        self.root.wait_window(dialog)
    
    def _toggle_simulation(self):
        """Start or stop the simulation"""
        if self.running:
            # Stop the simulation
            self.runner.stop()
            self.running = False
            self.start_stop_button.config(text="Start Simulation")
            self.status_var.set("Simulation stopped")
            
            if self.update_thread:
                self.update_thread.join(timeout=1.0)
                self.update_thread = None
        else:
            # Start the simulation
            self.runner.start()
            self.running = True
            self.start_stop_button.config(text="Stop Simulation")
            self.status_var.set("Simulation running")
            
            # Start the update thread
            self.update_thread = threading.Thread(target=self._update_loop)
            self.update_thread.daemon = True
            self.update_thread.start()
    
    def _update_loop(self):
        """Update the GUI with the latest ship state"""
        while self.running:
            if self.selected_ship:
                state = self.runner.get_ship_state(self.selected_ship)
                self._update_state_display(state)
            time.sleep(0.1)
    
    def _on_ship_select(self, event):
        """Handle ship selection from the listbox"""
        selection = self.ship_listbox.curselection()
        if selection:
            self.selected_ship = self.ship_listbox.get(selection[0])
            self.status_var.set(f"Selected ship: {self.selected_ship}")
            self._refresh_panels()
    
    def _update_state_display(self, state):
        """Update the raw state display with the current ship state"""
        if not state:
            return
            
        self.output_text.delete(1.0, tk.END)
        formatted_state = json.dumps(state, indent=2)
        self.output_text.insert(tk.END, formatted_state)
        
        # Also update the structured state display
        self._update_structured_state(state)
        
    def _update_structured_state(self, state):
        """Update the structured state display with current ship state"""
        if not state or not isinstance(state, dict):
            return
            
        # Update position
        if 'position' in state:
            pos = state['position']
            self.state_vars['position_x'].set(self._format_number(pos.get('x', 0)))
            self.state_vars['position_y'].set(self._format_number(pos.get('y', 0)))
            self.state_vars['position_z'].set(self._format_number(pos.get('z', 0)))
            
        # Update velocity
        if 'velocity' in state:
            vel = state['velocity']
            self.state_vars['velocity_x'].set(self._format_number(vel.get('x', 0)))
            self.state_vars['velocity_y'].set(self._format_number(vel.get('y', 0)))
            self.state_vars['velocity_z'].set(self._format_number(vel.get('z', 0)))
            
        # Update orientation
        if 'orientation' in state:
            ori = state['orientation']
            self.state_vars['orientation_pitch'].set(self._format_number(ori.get('pitch', 0)))
            self.state_vars['orientation_yaw'].set(self._format_number(ori.get('yaw', 0)))
            self.state_vars['orientation_roll'].set(self._format_number(ori.get('roll', 0)))
            
        # Update thrust
        if 'thrust' in state:
            thrust = state['thrust']
            self.state_vars['thrust_x'].set(self._format_number(thrust.get('x', 0)))
            self.state_vars['thrust_y'].set(self._format_number(thrust.get('y', 0)))
            self.state_vars['thrust_z'].set(self._format_number(thrust.get('z', 0)))
            
        # Update systems status
        systems = state.get('systems', {})
        for system in ['power', 'propulsion', 'sensors', 'nav', 'helm', 'bio']:
            if system in systems:
                status = systems[system].get('status', 'Unknown')
                self.state_vars[f'system_{system}'].set(status)
    
    def _send_command(self):
        """Send a command to the selected ship"""
        if not self.selected_ship:
            self.status_var.set("No ship selected")
            return
        
        command = self.command_var.get().strip()
        if not command:
            self.status_var.set("No command specified")
            return
        
        try:
            args = json.loads(self.args_var.get())
        except json.JSONDecodeError:
            self.status_var.set("Invalid JSON in args")
            return
        
        # Log the command
        self._log_output(f"Command: {command} {json.dumps(args)}")
        
        result = self.runner.send_command(self.selected_ship, command, args)
        
        if result.get("success"):
            self.status_var.set(f"Command sent: {command}")
            # Log the result
            self._log_output(f"Result: {json.dumps(result.get('result', {}), indent=2)}")
            # Update displays
            self._refresh_panels()
        else:
            error_msg = result.get('error', 'Unknown error')
            self.status_var.set(f"Command error: {error_msg}")
            self._log_output(f"ERROR: {error_msg}")
    
    def _save_states(self):
        """Save the current states of all ships"""
        result = self.runner.save_states()
        if result.get("success"):
            self.status_var.set(result.get("message", "States saved"))
            self._log_output("Ship states saved to files")
        else:
            self.status_var.set(f"Save error: {result.get('error', 'Unknown error')}")
    
    def _set_course(self):
        """Set navigation course"""
        if not self.selected_ship:
            self.status_var.set("No ship selected")
            return
            
        args = {}
        try:
            for axis in self.nav_fields:
                val = self.nav_fields[axis].get().strip()
                if val:
                    args[axis] = float(val)
        except ValueError:
            self.status_var.set("Invalid coordinate values")
            return
            
        if not args:
            self.status_var.set("No coordinates specified")
            return
            
        result = self.runner.send_command(self.selected_ship, "set_course", args)
        
        if result.get("success"):
            self.status_var.set("Course set successfully")
            self._log_output(f"Course set to {args}")
            self._refresh_panels()
        else:
            self.status_var.set(f"Failed to set course: {result.get('error', 'Unknown error')}")
    
    def _enable_autopilot(self):
        """Enable ship autopilot"""
        if not self.selected_ship:
            self.status_var.set("No ship selected")
            return
            
        result = self.runner.send_command(self.selected_ship, "autopilot", {"enabled": True})
        
        if result.get("success"):
            self.status_var.set("Autopilot enabled")
            self._log_output("Autopilot enabled")
            self._refresh_panels()
        else:
            self.status_var.set(f"Failed to enable autopilot: {result.get('error', 'Unknown error')}")
    
    def _disable_autopilot(self):
        """Disable ship autopilot"""
        if not self.selected_ship:
            self.status_var.set("No ship selected")
            return
            
        result = self.runner.send_command(self.selected_ship, "autopilot", {"enabled": False})
        
        if result.get("success"):
            self.status_var.set("Autopilot disabled")
            self._log_output("Autopilot disabled")
            self._refresh_panels()
        else:
            self.status_var.set(f"Failed to disable autopilot: {result.get('error', 'Unknown error')}")
    
    def _set_thrust(self):
        """Set ship thrust"""
        if not self.selected_ship:
            self.status_var.set("No ship selected")
            return
            
        args = {}
        try:
            for axis in self.thrust_fields:
                val = self.thrust_fields[axis].get().strip()
                if val:
                    args[axis] = float(val)
        except ValueError:
            self.status_var.set("Invalid thrust values")
            return
            
        if not args:
            self.status_var.set("No thrust values specified")
            return
            
        result = self.runner.send_command(self.selected_ship, "set_thrust", args)
        
        if result.get("success"):
            self.status_var.set("Thrust set successfully")
            self._log_output(f"Thrust set to {args}")
            self._refresh_panels()
        else:
            self.status_var.set(f"Failed to set thrust: {result.get('error', 'Unknown error')}")
    
    def _manual_helm_on(self):
        """Enable manual helm control"""
        if not self.selected_ship:
            self.status_var.set("No ship selected")
            return
            
        result = self.runner.send_command(self.selected_ship, "helm_override", {"enabled": True})
        
        if result.get("success"):
            self.status_var.set("Manual helm enabled")
            self._log_output("Manual helm control enabled")
            self._refresh_panels()
        else:
            self.status_var.set(f"Failed to enable manual helm: {result.get('error', 'Unknown error')}")
    
    def _manual_helm_off(self):
        """Disable manual helm control"""
        if not self.selected_ship:
            self.status_var.set("No ship selected")
            return
            
        result = self.runner.send_command(self.selected_ship, "helm_override", {"enabled": False})
        
        if result.get("success"):
            self.status_var.set("Manual helm disabled")
            self._log_output("Manual helm control disabled")
            self._refresh_panels()
        else:
            self.status_var.set(f"Failed to disable manual helm: {result.get('error', 'Unknown error')}")
    
    def _ping_sensors(self):
        """Ping ship sensors"""
        if not self.selected_ship:
            self.status_var.set("No ship selected")
            return
            
        result = self.runner.send_command(self.selected_ship, "ping_sensors", {})
        
        if result.get("success"):
            self.status_var.set("Sensors pinged")
            self._log_output("Active sensor ping initiated")
            
            # Update cooldown display
            cooldown = "Active"
            if "result" in result and isinstance(result["result"], dict):
                cooldown = result["result"].get("cooldown", "Unknown")
            self.cooldown_label.config(text=f"Cooldown: {cooldown}")
            
            # Refresh to show contacts
            self._refresh_panels()
        else:
            self.status_var.set(f"Failed to ping sensors: {result.get('error', 'Unknown error')}")
    
    def _override_bio(self):
        """Override bio monitor safety"""
        if not self.selected_ship:
            self.status_var.set("No ship selected")
            return
            
        result = self.runner.send_command(self.selected_ship, "override_bio_monitor", {"override": True})
        
        if result.get("success"):
            self.status_var.set("Bio monitor overridden")
            self._log_output("Bio safety monitors overridden - CAUTION!")
            self._refresh_panels()
        else:
            self.status_var.set(f"Failed to override bio monitor: {result.get('error', 'Unknown error')}")
    
    def _load_example(self, command, args):
        """Load an example command into the entry fields"""
        self.command_var.set(command)
        self.args_var.set(args)
    
    def _clear_output_log(self):
        """Clear output log"""
        self.output_text.delete(1.0, tk.END)
    
    def _log_output(self, message):
        """Add a message to the output log"""
        timestamp = time.strftime("%H:%M:%S")
        self.output_text.insert(tk.END, f"[{timestamp}] {message}\n\n")
        self.output_text.see(tk.END)
    
    def _refresh_panels(self):
        """Refresh all data panels"""
        if not self.selected_ship:
            return
            
        self.status_var.set("Refreshing data...")
        
        # Get ship state
        state = self.runner.get_ship_state(self.selected_ship)
        self._update_state_display(state)
        
        # Update contacts display
        self._update_contacts_display(state)
        
        self.status_var.set("Data refreshed")
    
    def _update_contacts_display(self, state):
        """Update the contacts display with sensor data"""
        self.contacts_output.delete(1.0, tk.END)
        
        if not state or not isinstance(state, dict):
            self.contacts_output.insert(tk.END, "No sensor data available")
            return
            
        # Extract contacts from state
        sensors = state.get('systems', {}).get('sensors', {})
        contacts = sensors.get('contacts', [])
        
        if not contacts:
            self.contacts_output.insert(tk.END, "No contacts detected")
            return
            
        # Display each contact
        for contact in contacts:
            target_id = contact.get('id', 'Unknown')
            distance = contact.get('distance', 'Unknown')
            method = contact.get('detection_method', 'Unknown')
            
            self.contacts_output.insert(tk.END, 
                f"{target_id} @ {distance} km [{method}]\n")
    
    def _toggle_auto_refresh(self):
        """Toggle automatic refresh"""
        if self.auto_refresh.get():
            # Start auto refresh
            self._schedule_auto_refresh()
            self.status_var.set("Auto-refresh enabled")
        else:
            # Stop auto refresh
            if self.auto_refresh_id:
                self.root.after_cancel(self.auto_refresh_id)
                self.auto_refresh_id = None
            self.status_var.set("Auto-refresh disabled")
    
    def _schedule_auto_refresh(self):
        """Schedule the next auto refresh"""
        if self.auto_refresh.get():
            self._refresh_panels()
            self.auto_refresh_id = self.root.after(AUTO_REFRESH_INTERVAL, self._schedule_auto_refresh)
    
    def on_closing(self):
        """Handle window closing"""
        if self.running:
            self.runner.stop()
        
        # Cancel any scheduled auto-refresh
        if self.auto_refresh_id:
            self.root.after_cancel(self.auto_refresh_id)
            
        self.root.destroy()
    
    @staticmethod
    def _format_number(value):
        """Format a number for display"""
        if isinstance(value, (int, float)):
            return f"{value:.2f}" if isinstance(value, float) else str(value)
        return str(value)


if __name__ == "__main__":
    root = tk.Tk()
    app = HybridSimGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
