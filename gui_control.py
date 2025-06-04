# PHASE 5 GUI ENHANCEMENT: Command uplift with variable inputs and tabbed panels

import tkinter as tk
from tkinter import ttk, scrolledtext
import subprocess
import json
import threading
import time
from functools import partial

# Configuration
SHIP_IDS = ["test_ship_001", "test_ship_002", "player_ship", "enemy_probe"]
AUTO_REFRESH_INTERVAL = 5000  # milliseconds

# Command Templates
COMMAND_TEMPLATES = {
    "Navigation": [
        {
            "name": "Set Course",
            "command": "set_course",
            "params": [
                {"name": "x", "type": "float", "default": "0.0"},
                {"name": "y", "type": "float", "default": "0.0"},
                {"name": "z", "type": "float", "default": "0.0"}
            ]
        },
        {
            "name": "Autopilot",
            "command": "autopilot",
            "params": [
                {"name": "enabled", "type": "bool", "default": "1"}
            ]
        },
        {
            "name": "Set Orientation",
            "command": "set_orientation",
            "params": [
                {"name": "pitch", "type": "float", "default": "0.0"},
                {"name": "yaw", "type": "float", "default": "0.0"},
                {"name": "roll", "type": "float", "default": "0.0"}
            ]
        }
    ],
    "Propulsion": [
        {
            "name": "Set Thrust",
            "command": "set_thrust",
            "params": [
                {"name": "x", "type": "float", "default": "0.0"},
                {"name": "y", "type": "float", "default": "0.0"},
                {"name": "z", "type": "float", "default": "0.0"}
            ]
        },
        {
            "name": "Manual Helm",
            "command": "helm_override",
            "params": [
                {"name": "enabled", "type": "bool", "default": "1"}
            ]
        },
        {
            "name": "Emergency Stop",
            "command": "emergency_stop",
            "params": []
        }
    ],
    "Sensors": [
        {
            "name": "Ping Sensors",
            "command": "ping_sensors",
            "params": []
        },
        {
            "name": "Get Contacts",
            "command": "get_contacts",
            "params": []
        },
        {
            "name": "Set Sensor Mode",
            "command": "set_sensor_mode",
            "params": [
                {"name": "mode", "type": "choice", "options": ["passive", "active", "stealth"], "default": "passive"}
            ]
        }
    ],
    "Power & Systems": [
        {
            "name": "Power System",
            "command": "power_system",
            "params": [
                {"name": "system", "type": "choice", "options": ["propulsion", "sensors", "navigation", "shields"], "default": "propulsion"},
                {"name": "state", "type": "bool", "default": "1"}
            ]
        },
        {
            "name": "Override Bio Monitor",
            "command": "override_bio_monitor",
            "params": []
        },
        {
            "name": "Trigger Signature Spike",
            "command": "trigger_signature_spike",
            "params": [
                {"name": "duration", "type": "float", "default": "3.0"}
            ]
        }
    ],
    "Misc": [
        {
            "name": "Get State",
            "command": "get_state",
            "params": []
        },
        {
            "name": "Custom Command",
            "command": "custom",
            "params": [
                {"name": "command", "type": "string", "default": ""}
            ]
        }
    ]
}

class CommandPanel:
    """Represents a single command panel with its parameters"""
    
    def __init__(self, parent, template, command_runner, ship_var, output_box, status_var):
        """Initialize a command panel from a template"""
        self.parent = parent
        self.template = template
        self.command_runner = command_runner
        self.ship_var = ship_var
        self.output_box = output_box
        self.status_var = status_var
        self.param_fields = {}
        
        self.frame = ttk.Frame(parent)
        self.create_panel()
        
    def create_panel(self):
        """Create the command panel UI"""
        # Command name as header
        ttk.Label(self.frame, text=self.template["name"], 
                 font=('TkDefaultFont', 10, 'bold')).pack(anchor=tk.W, padx=5, pady=2)
        
        # Parameters section (if any)
        if self.template["params"]:
            params_frame = ttk.Frame(self.frame)
            params_frame.pack(fill=tk.X, padx=10, pady=2)
            
            # Create input fields for each parameter
            for i, param in enumerate(self.template["params"]):
                row = i // 2
                col = (i % 2) * 2
                
                # Parameter label
                ttk.Label(params_frame, text=f"{param['name']}:").grid(
                    row=row, column=col, sticky=tk.W, padx=5, pady=2)
                
                # Create appropriate input field based on parameter type
                if param["type"] == "bool":
                    var = tk.StringVar(value=param["default"])
                    field = ttk.Combobox(params_frame, textvariable=var, width=8,
                                      values=["1", "0"])
                    
                elif param["type"] == "choice":
                    var = tk.StringVar(value=param["default"])
                    field = ttk.Combobox(params_frame, textvariable=var, width=12,
                                      values=param["options"])
                    
                elif param["type"] == "string":
                    var = tk.StringVar(value=param["default"])
                    field = ttk.Entry(params_frame, textvariable=var, width=20)
                    
                else:  # float, int, etc.
                    var = tk.StringVar(value=param["default"])
                    field = ttk.Entry(params_frame, textvariable=var, width=8)
                
                field.grid(row=row, column=col+1, padx=5, pady=2, sticky=tk.W)
                self.param_fields[param["name"]] = var
        
        # Execute button
        ttk.Button(self.frame, text="Execute", 
                  command=self.execute_command).pack(anchor=tk.E, padx=5, pady=5)
        
        # Add separator
        ttk.Separator(self.frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=5, pady=5)
    
    def execute_command(self):
        """Execute the command with parameters"""
        try:
            # If this is a custom command panel
            if self.template["command"] == "custom":
                custom_cmd = self.param_fields["command"].get()
                if not custom_cmd:
                    self.status_var.set("Error: Empty custom command")
                    return
                    
                result = self.command_runner.run_custom_command(
                    custom_cmd, 
                    self.ship_var.get(), 
                    self.output_box
                )
                self.status_var.set(f"Custom command executed: {custom_cmd}")
                return
            
            # For regular commands
            args = {}
            for param in self.template["params"]:
                param_name = param["name"]
                if param_name in self.param_fields:
                    value = self.param_fields[param_name].get()
                    if value:  # Only add non-empty values
                        args[param_name] = value
            
            result = self.command_runner.run_command(
                self.template["command"],
                args,
                self.ship_var.get(),
                self.output_box
            )
            
            self.status_var.set(f"Command executed: {self.template['name']}")
            
        except Exception as e:
            self.status_var.set(f"Error executing command: {str(e)}")
    
    def get_frame(self):
        """Get the frame containing the panel"""
        return self.frame


class CommandPanelManager:
    """Manages multiple command panels organized in tabs"""
    
    def __init__(self, parent, command_runner, ship_var, output_box, status_var):
        """Initialize the command panel manager"""
        self.parent = parent
        self.command_runner = command_runner
        self.ship_var = ship_var
        self.output_box = output_box
        self.status_var = status_var
        self.panels = {}
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create tabs for each category
        self.create_command_tabs()
    
    def create_command_tabs(self):
        """Create tabs for each command category"""
        for category, templates in COMMAND_TEMPLATES.items():
            # Create a scrollable frame for this category
            tab = ttk.Frame(self.notebook)
            self.notebook.add(tab, text=category)
            
            # Add a canvas with scrollbar for many commands
            canvas = tk.Canvas(tab)
            scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
            scrollable_frame = ttk.Frame(canvas)
            
            scrollable_frame.bind(
                "<Configure>",
                lambda e, canvas=canvas: canvas.configure(scrollregion=canvas.bbox("all"))
            )
            
            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            
            # Pack the scrolling components
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
            
            # Create panels for each command in this category
            for template in templates:
                panel = CommandPanel(
                    scrollable_frame, 
                    template, 
                    self.command_runner, 
                    self.ship_var, 
                    self.output_box, 
                    self.status_var
                )
                panel_frame = panel.get_frame()
                panel_frame.pack(fill=tk.X, padx=5, pady=5)
                
                # Store the panel
                self.panels[f"{category}_{template['name']}"] = panel


class CommandRunner:
    """Handles command execution and response processing"""
    
    @staticmethod
    def run_command(command, args, ship, box=None, return_json=False):
        cmd = ["python", "send.py", "--ship", ship, command]
        for k, v in args.items():
            if v != "":
                cmd.extend([f"--{k}", str(v)])
        try:
            out = subprocess.run(cmd, capture_output=True, text=True)
            result = out.stdout.strip()
            parsed = None
            try:
                parsed = json.loads(result.replace("[RESPONSE]", "", 1).strip())
            except json.JSONDecodeError:
                parsed = None

            if box:
                box.config(state='normal')
                box.insert(tk.END, f"\n$ {' '.join(cmd)}\n{json.dumps(parsed, indent=2) if parsed else result}\n")
                box.see(tk.END)
                box.config(state='disabled')

            if return_json:
                return parsed
            return result

        except Exception as e:
            if box:
                box.config(state='normal')
                box.insert(tk.END, f"\n[ERROR] {e}\n")
                box.see(tk.END)
                box.config(state='disabled')
            return ""
    
    @staticmethod
    def run_custom_command(command_str, ship, box=None, return_json=False):
        """Run a custom command string by parsing it into arguments"""
        try:
            # Split the command string into parts
            parts = command_str.split()
            if not parts:
                raise ValueError("Empty command")
            
            # First part is the command name
            command = parts[0]
            args = {}
            
            # Parse remaining parts as --key value pairs
            i = 1
            while i < len(parts):
                if parts[i].startswith('--'):
                    key = parts[i][2:]  # Remove -- prefix
                    if i + 1 < len(parts) and not parts[i+1].startswith('--'):
                        args[key] = parts[i+1]
                        i += 2
                    else:
                        args[key] = ""
                        i += 1
                else:
                    # Skip any values not preceded by --key
                    i += 1
            
            # Run the command
            return CommandRunner.run_command(command, args, ship, box, return_json)
        
        except Exception as e:
            if box:
                box.config(state='normal')
                box.insert(tk.END, f"\n[ERROR] Parsing command failed: {e}\n")
                box.see(tk.END)
                box.config(state='disabled')
            return ""


class ShipConsoleGUI:
    """Main GUI application for ship control"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Spaceship Command Console")
        self.root.geometry("1400x800")
        
        # Apply theme if available
        try:
            self.root.tk.call("source", "azure.tcl")
            self.root.tk.call("set_theme", "dark")
        except:
            pass  # Continue with default theme if custom theme not available
        
        self.ship_var = tk.StringVar(value=SHIP_IDS[0])
        self.auto_refresh = tk.BooleanVar(value=False)
        self.output_box = None
        self.contacts_output = None
        self.cooldown_label = None
        self.state_vars = {}
        self.command_runner = CommandRunner()
        self.status_var = tk.StringVar(value="Ready")

        # Create and configure the main layout
        self.create_layout()
        
        # Start with a refresh
        self.refresh_panels()
        
    def create_layout(self):
        """Create the main GUI layout with a modern design"""
        # Configure root grid
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=2)
        self.root.grid_rowconfigure(0, weight=1)
        
        # Create PanedWindow for resizable layout
        main_panes = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_panes.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        
        # Create left frame (for commands)
        left_frame = ttk.Frame(main_panes)
        left_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create right frame (for output and telemetry)
        right_frame = ttk.Frame(main_panes)
        right_frame.pack(fill=tk.BOTH, expand=True)
        
        # Add frames to paned window
        main_panes.add(left_frame, weight=1)
        main_panes.add(right_frame, weight=2)
        
        # Create top controls in left frame
        self.create_ship_selector(left_frame)
        
        # Create command panel manager
        commands_frame = ttk.LabelFrame(left_frame, text="Command Center")
        commands_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.command_panel_manager = CommandPanelManager(
            commands_frame,
            self.command_runner,
            self.ship_var,
            None,  # Will set output_box after creation
            self.status_var
        )
        
        # Create refresh controls
        refresh_frame = ttk.Frame(left_frame)
        refresh_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(refresh_frame, text="Refresh Data", 
                  command=self.refresh_panels).pack(side=tk.LEFT, padx=5)
        
        ttk.Checkbutton(refresh_frame, text="Auto Refresh", 
                      variable=self.auto_refresh, 
                      command=self.toggle_auto_refresh).pack(side=tk.LEFT, padx=5)
        
        # Create right panels (output and telemetry)
        # Right frame has two sections vertically
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_rowconfigure(1, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)
        
        # Upper section for telemetry
        telemetry_frame = ttk.Frame(right_frame)
        telemetry_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Lower section for output logs
        output_frame = ttk.Frame(right_frame)
        output_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        # Create telemetry panels
        self.create_state_panel(telemetry_frame)
        self.create_contacts_panel(telemetry_frame)
        
        # Create output panel
        self.create_output_panel(output_frame)
        
        # Now set the output_box to the command panel manager
        self.command_panel_manager.output_box = self.output_box
        
        # Status bar
        status_frame = ttk.Frame(self.root)
        status_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        
        self.status_var.set("Ready")
        status_label = ttk.Label(status_frame, textvariable=self.status_var,
                                 relief=tk.SUNKEN, anchor=tk.W)
        status_label.pack(fill=tk.X)
        
        # Initialize auto-refresh
        self.auto_refresh_id = None
    
    def create_ship_selector(self, parent):
        """Create ship selection dropdown"""
        ship_frame = ttk.LabelFrame(parent, text="Ship Selection")
        ship_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ship_combo = ttk.Combobox(ship_frame, textvariable=self.ship_var, values=SHIP_IDS)
        ship_combo.pack(pady=5, padx=5, fill=tk.X)
        
        # Add a callback when ship changes
        ship_combo.bind("<<ComboboxSelected>>", lambda e: self.on_ship_change())
        
        # Add ship information display
        ship_info_frame = ttk.Frame(ship_frame)
        ship_info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Ship type and status indicators
        ship_type_frame = ttk.Frame(ship_info_frame)
        ship_type_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(ship_type_frame, text="Type:").pack(side=tk.LEFT, padx=2)
        self.ship_type_var = tk.StringVar(value="Unknown")
        ttk.Label(ship_type_frame, textvariable=self.ship_type_var, width=20).pack(side=tk.LEFT, padx=2)
        
        # Status indicators using colored canvas elements
        status_frame = ttk.Frame(ship_info_frame)
        status_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(status_frame, text="Systems:").pack(side=tk.LEFT, padx=2)
        
        # Create system status indicators
        self.system_indicators = {}
        for system in ["power", "nav", "prop", "sens"]:
            frame = ttk.Frame(status_frame)
            frame.pack(side=tk.LEFT, padx=5)
            
            ttk.Label(frame, text=system.capitalize(), font=('TkDefaultFont', 7)).pack(anchor=tk.CENTER)
            canvas = tk.Canvas(frame, width=12, height=12, bg="gray")
            canvas.pack(anchor=tk.CENTER)
            
            self.system_indicators[system] = canvas
    
    def on_ship_change(self):
        """Handle ship selection change"""
        self.status_var.set(f"Selected ship: {self.ship_var.get()}")
        self.refresh_panels()
    
    def create_output_panel(self, parent):
        """Create output log area"""
        output_frame = ttk.LabelFrame(parent, text="Command Output Log")
        output_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create output log with modern styling
        self.output_box = scrolledtext.ScrolledText(
            output_frame, 
            height=10, 
            state='disabled',
            wrap=tk.WORD,
            font=('Consolas', 9)
        )
        self.output_box.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add styling to the output text
        self.output_box.tag_configure("command", foreground="#6a9955")
        self.output_box.tag_configure("response", foreground="#4ec9b0")
        self.output_box.tag_configure("error", foreground="#f14c4c")
        
        # Control buttons
        button_frame = ttk.Frame(output_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(button_frame, text="Clear Log", 
                  command=self.clear_output_log).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Save Log", 
                  command=self.save_output_log).pack(side=tk.RIGHT, padx=5)
    
    def create_state_panel(self, parent):
        """Create ship state display with modern design"""
        # Create a frame for state displays (50% width)
        state_frame = ttk.LabelFrame(parent, text="Ship Telemetry")
        state_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create a notebook for different telemetry views
        telemetry_notebook = ttk.Notebook(state_frame)
        telemetry_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Basic telemetry tab
        basic_tab = ttk.Frame(telemetry_notebook)
        telemetry_notebook.add(basic_tab, text="Basic")
        
        # Advanced telemetry tab
        advanced_tab = ttk.Frame(telemetry_notebook)
        telemetry_notebook.add(advanced_tab, text="Advanced")
        
        # Systems tab
        systems_tab = ttk.Frame(telemetry_notebook)
        telemetry_notebook.add(systems_tab, text="Systems")
        
        # Create a grid of telemetry values for basic tab
        self._create_telemetry_grid(basic_tab)
        
        # Advanced telemetry (performance, energy, etc)
        self._create_advanced_telemetry(advanced_tab)
        
        # Systems status grid
        self._create_systems_status_grid(systems_tab)
        
        # Cooldown indicator
        cooldown_frame = ttk.Frame(state_frame)
        cooldown_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.cooldown_label = ttk.Label(
            cooldown_frame, 
            text="Sensor Cooldown: Ready", 
            foreground="green"
        )
        self.cooldown_label.pack(side=tk.LEFT, padx=5)
    
    def _create_telemetry_grid(self, parent):
        """Create the basic telemetry grid"""
        grid_frame = ttk.Frame(parent)
        grid_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Define telemetry sections
        sections = [
            ("Position", ["x", "y", "z"]),
            ("Velocity", ["vx", "vy", "vz"]),
            ("Orientation", ["pitch", "yaw", "roll"]),
            ("Thrust", ["tx", "ty", "tz"])
        ]
        
        # Create each section
        for section_idx, (section_name, fields) in enumerate(sections):
            # Section header
            ttk.Label(grid_frame, text=section_name, 
                     font=('TkDefaultFont', 9, 'bold')).grid(
                row=section_idx*3, column=0, sticky=tk.W, padx=5, pady=(10,2), columnspan=6)
            
            # Separator
            ttk.Separator(grid_frame, orient=tk.HORIZONTAL).grid(
                row=section_idx*3+1, column=0, sticky="ew", columnspan=6, padx=5)
            
            # Fields
            for field_idx, field in enumerate(fields):
                ttk.Label(grid_frame, text=field.upper()).grid(
                    row=section_idx*3+2, column=field_idx*2, sticky=tk.W, padx=5, pady=2)
                
                var = tk.StringVar(value="N/A")
                entry = ttk.Entry(grid_frame, textvariable=var, width=10, state="readonly")
                entry.grid(row=section_idx*3+2, column=field_idx*2+1, padx=5, pady=2, sticky=tk.W)
                
                self.state_vars[field] = var
    
    def _create_advanced_telemetry(self, parent):
        """Create advanced telemetry display"""
        advanced_frame = ttk.Frame(parent)
        advanced_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Define advanced telemetry items
        advanced_items = [
            ("Angular Velocity", ["wx", "wy", "wz"]),
            ("G-Forces", ["gx", "gy", "gz"]),
            ("Power Status", ["current", "capacity", "draw"]),
            ("Efficiency", ["thrust_eff", "fuel_rate", "heat"])
        ]
        
        # Create advanced items display
        for section_idx, (section_name, fields) in enumerate(advanced_items):
            ttk.Label(advanced_frame, text=section_name, 
                     font=('TkDefaultFont', 9, 'bold')).grid(
                row=section_idx*3, column=0, sticky=tk.W, padx=5, pady=(10,2), columnspan=6)
            
            ttk.Separator(advanced_frame, orient=tk.HORIZONTAL).grid(
                row=section_idx*3+1, column=0, sticky="ew", columnspan=6, padx=5)
            
            for field_idx, field in enumerate(fields):
                ttk.Label(advanced_frame, text=field.upper()).grid(
                    row=section_idx*3+2, column=field_idx*2, sticky=tk.W, padx=5, pady=2)
                
                var = tk.StringVar(value="N/A")
                entry = ttk.Entry(advanced_frame, textvariable=var, width=10, state="readonly")
                entry.grid(row=section_idx*3+2, column=field_idx*2+1, padx=5, pady=2, sticky=tk.W)
                
                self.state_vars[field] = var
    
    def _create_systems_status_grid(self, parent):
        """Create systems status display"""
        systems_frame = ttk.Frame(parent)
        systems_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Systems to display
        systems = [
            "power", "propulsion", "sensors", "navigation", 
            "shields", "comms", "life_support", "helm"
        ]
        
        # Create a grid of system statuses
        for i, system in enumerate(systems):
            row, col = divmod(i, 2)
            
            system_frame = ttk.Frame(systems_frame)
            system_frame.grid(row=row, column=col, padx=10, pady=5, sticky="w")
            
            # System name
            ttk.Label(system_frame, text=f"{system.capitalize()}:", 
                     width=12, anchor="e").pack(side=tk.LEFT, padx=2)
            
            # Status display
            status_var = tk.StringVar(value="Unknown")
            status_label = ttk.Label(system_frame, textvariable=status_var, width=10)
            status_label.pack(side=tk.LEFT, padx=2)
            
            # Store the variable
            self.state_vars[f"system_{system}"] = status_var
    
    def create_contacts_panel(self, parent):
        """Create advanced sensor contacts display with sortable table"""
        contacts_frame = ttk.LabelFrame(parent, text="Sensor Operations")
        contacts_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create notebook for different sensor views
        sensor_notebook = ttk.Notebook(contacts_frame)
        sensor_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Contacts table tab
        contacts_tab = ttk.Frame(sensor_notebook)
        sensor_notebook.add(contacts_tab, text="Contacts")
        
        # Sensor control tab
        control_tab = ttk.Frame(sensor_notebook)
        sensor_notebook.add(control_tab, text="Controls")
        
        # Signature analysis tab
        analysis_tab = ttk.Frame(sensor_notebook)
        sensor_notebook.add(analysis_tab, text="Analysis")
        
        # Create the contacts table
        self._create_contacts_table(contacts_tab)
        
        # Create sensor controls
        self._create_sensor_controls(control_tab)
        
        # Create signature analysis tools
        self._create_signature_analysis(analysis_tab)
    
    def _create_contacts_table(self, parent):
        """Create sortable contacts table"""
        # Table frame with toolbar
        table_frame = ttk.Frame(parent)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
        # Toolbar for table actions
        toolbar = ttk.Frame(table_frame)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        # Contact filter
        ttk.Label(toolbar, text="Filter:").pack(side=tk.LEFT, padx=2)
        self.contact_filter_var = tk.StringVar()
        filter_entry = ttk.Entry(toolbar, textvariable=self.contact_filter_var, width=15)
        filter_entry.pack(side=tk.LEFT, padx=2)
        
        # Display mode
        ttk.Label(toolbar, text="Show:").pack(side=tk.LEFT, padx=5)
        self.contact_mode_var = tk.StringVar(value="all")
        contact_mode = ttk.Combobox(toolbar, textvariable=self.contact_mode_var, width=10, 
                      values=["all", "active", "passive", "recent"])
        contact_mode.pack(side=tk.LEFT, padx=2)
        contact_mode.bind("<<ComboboxSelected>>", lambda e: self.refresh_contacts_table())
            
        # Sort by
        ttk.Label(toolbar, text="Sort by:").pack(side=tk.LEFT, padx=5)
        self.sort_by_var = tk.StringVar(value="distance")
        sort_by = ttk.Combobox(toolbar, textvariable=self.sort_by_var, width=10,
                 values=["distance", "name", "timestamp", "signature"])
        sort_by.pack(side=tk.LEFT, padx=2)
        sort_by.bind("<<ComboboxSelected>>", lambda e: self.refresh_contacts_table())
        
        # Clear contacts button
        ttk.Button(toolbar, text="Clear All", 
              command=self.clear_contacts).pack(side=tk.RIGHT, padx=5)
        
        # Refresh button
        ttk.Button(toolbar, text="Refresh", 
              command=self.refresh_contacts_table).pack(side=tk.RIGHT, padx=5)
            
        # Create the table with Treeview
        columns = ("id", "distance", "bearing", "signature", "method", "timestamp")
        self.contacts_table = ttk.Treeview(table_frame, columns=columns, show="headings", 
                             selectmode="browse", height=10)
        
        # Define column headings
        self.contacts_table.heading("id", text="Contact ID", command=lambda: self.sort_contacts("id"))
        self.contacts_table.heading("distance", text="Distance", command=lambda: self.sort_contacts("distance"))
        self.contacts_table.heading("bearing", text="Bearing", command=lambda: self.sort_contacts("bearing"))
        self.contacts_table.heading("signature", text="Signature", command=lambda: self.sort_contacts("signature"))
        self.contacts_table.heading("method", text="Method", command=lambda: self.sort_contacts("method"))
        self.contacts_table.heading("timestamp", text="Last Updated", command=lambda: self.sort_contacts("timestamp"))
        
        # Set column widths
        self.contacts_table.column("id", width=100)
        self.contacts_table.column("distance", width=80)
        self.contacts_table.column("bearing", width=80)
        self.contacts_table.column("signature", width=80)
        self.contacts_table.column("method", width=80)
        self.contacts_table.column("timestamp", width=150)
        
        # Add a scrollbar
        table_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.contacts_table.yview)
        self.contacts_table.configure(yscrollcommand=table_scroll.set)
        
        # Pack the table and scrollbar
        self.contacts_table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        table_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Add selection event
        self.contacts_table.bind("<<TreeviewSelect>>", self.on_contact_selected)

        # Details panel below the table
        details_frame = ttk.LabelFrame(parent, text="Contact Details")
        details_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Create text widget for contact details
        self.contact_details = scrolledtext.ScrolledText(
            details_frame, 
            height=4, 
            wrap=tk.WORD,
            font=('Consolas', 9)
        )
        self.contact_details.pack(fill=tk.X, padx=5, pady=5)
        
        # Action buttons for selected contact
        actions_frame = ttk.Frame(details_frame)
        actions_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(actions_frame, text="Set Course", 
              command=self.set_course_to_contact).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions_frame, text="Track", 
              command=self.track_contact).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions_frame, text="Delete", 
              command=self.delete_contact).pack(side=tk.LEFT, padx=5)
        
    def _create_sensor_controls(self, parent):
        """Create sensor mode controls"""
        # Sensor status and controls
        controls_frame = ttk.Frame(parent)
        controls_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create sensor status display
        status_frame = ttk.LabelFrame(controls_frame, text="Sensor Status")
        status_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Sensor power status
        power_frame = ttk.Frame(status_frame)
        power_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(power_frame, text="Power:").grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.sensor_power_var = tk.StringVar(value="Online")
        power_label = ttk.Label(power_frame, textvariable=self.sensor_power_var, foreground="green")
        power_label.grid(row=0, column=1, padx=5, pady=2, sticky=tk.W)
        
        # Sensor mode
        ttk.Label(power_frame, text="Mode:").grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
        self.sensor_mode_var = tk.StringVar(value="Passive")
        mode_label = ttk.Label(power_frame, textvariable=self.sensor_mode_var, foreground="blue")
        mode_label.grid(row=1, column=1, padx=5, pady=2, sticky=tk.W)
        
        # Cooldown status
        ttk.Label(power_frame, text="Cooldown:").grid(row=2, column=0, padx=5, pady=2, sticky=tk.W)
        self.cooldown_var = tk.StringVar(value="Ready")
        self.cooldown_label = ttk.Label(power_frame, textvariable=self.cooldown_var, foreground="green")
        self.cooldown_label.grid(row=2, column=1, padx=5, pady=2, sticky=tk.W)
        
        # Last ping time
        ttk.Label(power_frame, text="Last Ping:").grid(row=3, column=0, padx=5, pady=2, sticky=tk.W)
        self.last_ping_var = tk.StringVar(value="N/A")
        ttk.Label(power_frame, textvariable=self.last_ping_var).grid(row=3, column=1, padx=5, pady=2, sticky=tk.W)
        
        # Sensor range information
        range_frame = ttk.LabelFrame(controls_frame, text="Sensor Ranges")
        range_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Passive range
        ttk.Label(range_frame, text="Passive Range:").grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.passive_range_var = tk.StringVar(value="1000 km")
        ttk.Label(range_frame, textvariable=self.passive_range_var).grid(row=0, column=1, padx=5, pady=2, sticky=tk.W)
        
        # Active range
        ttk.Label(range_frame, text="Active Range:").grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
        self.active_range_var = tk.StringVar(value="8000 km")
        ttk.Label(range_frame, textvariable=self.active_range_var).grid(row=1, column=1, padx=5, pady=2, sticky=tk.W)
        
        # FOV
        ttk.Label(range_frame, text="Scan FOV:").grid(row=2, column=0, padx=5, pady=2, sticky=tk.W)
        self.scan_fov_var = tk.StringVar(value="180°")
        ttk.Label(range_frame, textvariable=self.scan_fov_var).grid(row=2, column=1, padx=5, pady=2, sticky=tk.W)
        
        # Sensor control buttons
        control_frame = ttk.LabelFrame(controls_frame, text="Sensor Controls")
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Active sensor ping button
        ttk.Button(control_frame, text="Active Ping", 
              command=self.ping_sensors).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Toggle passive mode
        self.passive_mode_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(control_frame, text="Passive Mode", 
                   variable=self.passive_mode_var,
                   command=self.toggle_passive_mode).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Toggle stealth mode
        self.stealth_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(control_frame, text="Stealth Mode", 
                   variable=self.stealth_mode_var,
                   command=self.toggle_stealth_mode).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Set scan parameters
        scan_frame = ttk.Frame(control_frame)
        scan_frame.pack(side=tk.RIGHT, padx=5, pady=5)
        
        ttk.Label(scan_frame, text="Scan Direction:").grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.scan_direction_var = tk.StringVar(value="0")
        ttk.Entry(scan_frame, textvariable=self.scan_direction_var, width=5).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Button(scan_frame, text="Set Direction", 
              command=self.set_scan_direction).grid(row=0, column=2, padx=5, pady=2)

    def _create_signature_analysis(self, parent):
        """Create signature analysis tools"""
        # Signature analysis frame
        analysis_frame = ttk.Frame(parent)
        analysis_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Ship signature display
        signature_frame = ttk.LabelFrame(analysis_frame, text="Ship Signature")
        signature_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Base signature
        ttk.Label(signature_frame, text="Base Signature:").grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.base_signature_var = tk.StringVar(value="0.8")
        ttk.Label(signature_frame, textvariable=self.base_signature_var).grid(row=0, column=1, padx=5, pady=2, sticky=tk.W)
        
        # Current signature
        ttk.Label(signature_frame, text="Current Signature:").grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
        self.current_signature_var = tk.StringVar(value="1.2")
        ttk.Label(signature_frame, textvariable=self.current_signature_var).grid(row=1, column=1, padx=5, pady=2, sticky=tk.W)
        
        # EM spike status
        ttk.Label(signature_frame, text="EM Spike:").grid(row=2, column=0, padx=5, pady=2, sticky=tk.W)
        self.spike_var = tk.StringVar(value="None")
        ttk.Label(signature_frame, textvariable=self.spike_var).grid(row=2, column=1, padx=5, pady=2, sticky=tk.W)
        
        # Signature control
        control_frame = ttk.LabelFrame(analysis_frame, text="Signature Control")
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Trigger EM spike
        spike_frame = ttk.Frame(control_frame)
        spike_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(spike_frame, text="Spike Duration (s):").pack(side=tk.LEFT, padx=5)
        self.spike_duration_var = tk.StringVar(value="3.0")
        ttk.Entry(spike_frame, textvariable=self.spike_duration_var, width=5).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(spike_frame, text="Trigger EM Spike", 
              command=self.trigger_signature_spike).pack(side=tk.LEFT, padx=5)
        
        # Signature analysis
        analysis_output_frame = ttk.LabelFrame(analysis_frame, text="Signature Analysis")
        analysis_output_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.signature_analysis = scrolledtext.ScrolledText(
            analysis_output_frame, 
            height=6, 
            wrap=tk.WORD,
            font=('Consolas', 9)
        )
        self.signature_analysis.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def save_output_log(self):
        """Save the output log to a file"""
        try:
            from datetime import datetime
            from tkinter import filedialog
            
            # Get a filename to save to
            default_filename = f"ship_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filename = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                initialfile=default_filename
            )
            
            if not filename:
                return
                
            # Get the content and save it
            content = self.output_box.get("1.0", tk.END)
            with open(filename, 'w') as f:
                f.write(content)
                
            self.status_var.set(f"Log saved to {filename}")
            
        except Exception as e:
            self.status_var.set(f"Error saving log: {str(e)}")
    
    def create_output_panel(self, parent):
        """Create output log area"""
        output_frame = ttk.LabelFrame(parent, text="Raw Output Log")
        output_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.output_box = scrolledtext.ScrolledText(output_frame, height=10, state='disabled')
        self.output_box.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        button_frame = ttk.Frame(output_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Clear Log", 
                  command=self.clear_output_log).pack(side=tk.RIGHT, padx=5, pady=2)
    
    def create_state_panel(self, parent):
        """Create ship state display"""
        state_frame = ttk.LabelFrame(parent, text="Live Ship State")
        state_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Create rows for state data in a grid layout
        fields_grid = ttk.Frame(state_frame)
        fields_grid.pack(fill=tk.X, padx=5, pady=5)
        
        row1 = ["pitch", "yaw", "roll", "spike"]
        row2 = ["vx", "vy", "vz", "gx"]
        row3 = ["tx", "ty", "tz"]
        row4 = ["wx", "wy", "wz"]
        
        all_rows = [row1, row2, row3, row4]
        
        for row_idx, row_fields in enumerate(all_rows):
            for col_idx, field in enumerate(row_fields):
                ttk.Label(fields_grid, text=f"{field.upper()}:").grid(
                    row=row_idx*2, column=col_idx, sticky=tk.W, padx=5, pady=2)
                
                var = tk.StringVar(value="N/A")
                entry = ttk.Entry(fields_grid, textvariable=var, width=10, state="readonly")
                entry.grid(row=row_idx*2+1, column=col_idx, padx=5, pady=2, sticky=tk.W)
                
                self.state_vars[field] = var
    
    def create_contacts_panel(self, parent):
        """Create sensor contacts display"""
        contacts_frame = ttk.LabelFrame(parent, text="Sensor Contacts")
        contacts_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.contacts_output = scrolledtext.ScrolledText(contacts_frame, height=6, state='disabled')
        self.contacts_output.pack(fill=tk.X, padx=5, pady=5)
    
    # Command handlers
    def set_course(self):
        """Set navigation course"""
        try:
            args = {k: self.nav_fields[k].get() for k in self.nav_fields}
            # Basic validation
            for k, v in args.items():
                if v and not self.is_valid_number(v):
                    self.status_var.set(f"Error: Invalid value for {k}")
                    return
                    
            CommandRunner.run_command("set_course", args, self.ship_var.get(), self.output_box)
            self.status_var.set("Course set")
            self.refresh_panels()
        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")
    
    def enable_autopilot(self):
        """Enable ship autopilot"""
        CommandRunner.run_command("autopilot", {"enabled": 1}, self.ship_var.get(), self.output_box)
        self.status_var.set("Autopilot enabled")
        self.refresh_panels()
    
    def disable_autopilot(self):
        """Disable ship autopilot"""
        CommandRunner.run_command("autopilot", {"enabled": 0}, self.ship_var.get(), self.output_box)
        self.status_var.set("Autopilot disabled")
        self.refresh_panels()
    
    def set_thrust(self):
        """Set ship thrust"""
        try:
            args = {k: self.thrust_fields[k].get() for k in self.thrust_fields}
            # Basic validation
            for k, v in args.items():
                if v and not self.is_valid_number(v):
                    self.status_var.set(f"Error: Invalid value for {k}")
                    return
                    
            CommandRunner.run_command("set_thrust", args, self.ship_var.get(), self.output_box)
            self.status_var.set("Thrust set")
            self.refresh_panels()
        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")
    
    def manual_helm_on(self):
        """Enable manual helm control"""
        CommandRunner.run_command("helm_override", {"enabled": 1}, self.ship_var.get(), self.output_box)
        self.status_var.set("Manual helm enabled")
        self.refresh_panels()
    
    def manual_helm_off(self):
        """Disable manual helm control"""
        CommandRunner.run_command("helm_override", {"enabled": 0}, self.ship_var.get(), self.output_box)
        self.status_var.set("Manual helm disabled")
        self.refresh_panels()
    
    def ping_sensors(self):
        """Ping ship sensors"""
        parsed = CommandRunner.run_command("ping_sensors", {}, self.ship_var.get(), 
                                         self.output_box, return_json=True)
        if parsed:
            cooldown = parsed.get("cooldown_started") or parsed.get("error")
            self.cooldown_label.config(text=f"Cooldown: {cooldown}")
            self.status_var.set("Sensors pinged")
        else:
            self.status_var.set("Sensor ping failed")
        self.refresh_panels()
    
    def override_bio(self):
        """Override bio monitor safety"""
        CommandRunner.run_command("override_bio_monitor", {}, self.ship_var.get(), self.output_box)
        self.status_var.set("Bio monitor overridden")
        self.refresh_panels()
    
    def send_custom_command(self):
        """Send a custom command"""
        command_str = self.command_entry.get().strip()
        if not command_str:
            self.status_var.set("Error: Empty command")
            return
            
        self.status_var.set(f"Sending command: {command_str}")
        result = CommandRunner.run_custom_command(command_str, self.ship_var.get(), self.output_box)
        
        if result:
            self.status_var.set(f"Command executed: {command_str}")
        else:
            self.status_var.set(f"Command failed: {command_str}")
            
        self.refresh_panels()
    
    def load_example(self, example):
        """Load an example command into the entry field"""
        self.command_entry.delete(0, tk.END)
        self.command_entry.insert(0, example)
    
    def clear_output_log(self):
        """Clear output log"""
        if self.output_box:
            self.output_box.config(state='normal')
            self.output_box.delete("1.0", tk.END)
            self.output_box.config(state='disabled')
    
    def refresh_panels(self):
        """Refresh all data panels"""
        self.status_var.set("Refreshing data...")
        
        # Get ship state
        parsed = CommandRunner.run_command("get_state", {}, self.ship_var.get(), 
                                         self.output_box, return_json=True)
        if parsed:
            # Update orientation
            self.state_vars["pitch"].set(parsed["orientation"].get("pitch", 0))
            self.state_vars["yaw"].set(parsed["orientation"].get("yaw", 0))
            self.state_vars["roll"].set(parsed["orientation"].get("roll", 0))
            
            # Update velocity
            self.state_vars["vx"].set(parsed["velocity"].get("x", 0))
            self.state_vars["vy"].set(parsed["velocity"].get("y", 0))
            self.state_vars["vz"].set(parsed["velocity"].get("z", 0))
            
            # Update bio monitor
            self.state_vars["gx"].set(parsed["bio_monitor"].get("current_g", 0))
            
            # Update thrust
            thrust = parsed.get("thrust", {})
            self.state_vars["tx"].set(thrust.get("x", 0))
            self.state_vars["ty"].set(thrust.get("y", 0))
            self.state_vars["tz"].set(thrust.get("z", 0))
            
            # Update angular velocity
            angv = parsed.get("angular_velocity", {})
            self.state_vars["wx"].set(angv.get("pitch", 0))
            self.state_vars["wy"].set(angv.get("yaw", 0))
            self.state_vars["wz"].set(angv.get("roll", 0))
            
            # Update sensors
            self.state_vars["spike"].set(parsed.get("sensors", {}).get("spike_until", ""))
            
            # Update cooldown
            cooldown_val = parsed.get("sensors", {}).get("active", {}).get("cooldown")
            if cooldown_val is not None:
                self.cooldown_label.config(text=f"Cooldown: {cooldown_val:.1f}s")

        # Get contacts
        contacts = CommandRunner.run_command("get_contacts", {}, self.ship_var.get(), 
                                           None, return_json=True)
        if self.contacts_output:
            self.contacts_output.config(state='normal')
            self.contacts_output.delete("1.0", tk.END)
            if contacts and contacts.get("contacts"):
                for c in contacts["contacts"]:
                    self.contacts_output.insert(tk.END, 
                        f"{c.get('target_id', '?')} @ {c.get('distance', '?')} km [{c.get('method', '?')}]\n")
            else:
                self.contacts_output.insert(tk.END, "No contacts or sensor failure.\n")
            self.contacts_output.config(state='disabled')
        
        self.status_var.set("Data refreshed")
    
    def toggle_auto_refresh(self):
        """Toggle automatic refresh"""
        if self.auto_refresh.get():
            # Start auto refresh
            self.schedule_auto_refresh()
            self.status_var.set("Auto-refresh enabled")
        else:
            # Stop auto refresh
            if self.auto_refresh_id:
                self.root.after_cancel(self.auto_refresh_id)
                self.auto_refresh_id = None
            self.status_var.set("Auto-refresh disabled")
    
    def schedule_auto_refresh(self):
        """Schedule the next auto refresh"""
        if self.auto_refresh.get():
            self.refresh_panels()
            self.auto_refresh_id = self.root.after(AUTO_REFRESH_INTERVAL, self.schedule_auto_refresh)
    
    def refresh_contacts_table(self):
        """Refresh the contacts table with latest data"""
        # Get contacts from ship
        parsed = CommandRunner.run_command("get_contacts", {}, self.ship_var.get(), 
                                         None, return_json=True)
        
        # Clear the table
        if hasattr(self, 'contacts_table'):
            for item in self.contacts_table.get_children():
                self.contacts_table.delete(item)
            
            # Add contacts if available
            if parsed and "contacts" in parsed:
                contacts = parsed["contacts"]
                
                # Filter contacts based on mode
                mode = self.contact_mode_var.get()
                if mode == "active":
                    contacts = [c for c in contacts if c.get("method") == "active"]
                elif mode == "passive":
                    contacts = [c for c in contacts if c.get("method") == "passive"]
                elif mode == "recent":
                    # Get contacts from last 60 seconds
                    import datetime
                    now = datetime.datetime.now()
                    contacts = [c for c in contacts if c.get("detected_at") and 
                               (now - datetime.datetime.fromisoformat(c.get("detected_at"))).seconds < 60]
                
                # Filter contacts based on filter text
                filter_text = self.contact_filter_var.get().lower()
                if filter_text:
                    contacts = [c for c in contacts if filter_text in str(c.get("target_id", "")).lower()]
                
                # Sort contacts
                sort_by = self.sort_by_var.get()
                if sort_by == "distance":
                    contacts.sort(key=lambda c: float(c.get("distance", 99999)))
                elif sort_by == "name":
                    contacts.sort(key=lambda c: str(c.get("target_id", "")))
                elif sort_by == "timestamp":
                    contacts.sort(key=lambda c: str(c.get("detected_at", "")), reverse=True)
                elif sort_by == "signature":
                    contacts.sort(key=lambda c: float(c.get("signature", 0)), reverse=True)
                
                # Add to table
                for contact in contacts:
                    contact_id = contact.get("target_id", "Unknown")
                    distance = f"{contact.get('distance', '?')} km"
                    bearing = f"{contact.get('bearing', '?')}°"
                    signature = contact.get("signature", "?")
                    method = contact.get("method", "unknown")
                    timestamp = contact.get("detected_at", "?")
                    
                    self.contacts_table.insert("", tk.END, values=(
                        contact_id, distance, bearing, signature, method, timestamp
                    ))
        
        self.status_var.set("Contacts refreshed")
    
    def on_contact_selected(self, event):
        """Handle contact selection in the table"""
        selected = self.contacts_table.selection()
        if not selected:
            return
            
        # Get the selected contact data
        values = self.contacts_table.item(selected[0], "values")
        if not values:
            return
            
        # Format the details
        contact_id = values[0]
        distance = values[1]
        bearing = values[2]
        signature = values[3]
        method = values[4]
        timestamp = values[5]
        
        details = f"Contact ID: {contact_id}\n"
        details += f"Distance: {distance}\n"
        details += f"Bearing: {bearing}\n"
        details += f"Signature: {signature}\n"
        details += f"Detection Method: {method}\n"
        details += f"Last Updated: {timestamp}\n"
        
        # Update the details panel
        self.contact_details.delete(1.0, tk.END)
        self.contact_details.insert(tk.END, details)
    
    def set_course_to_contact(self):
        """Set course to the selected contact"""
        selected = self.contacts_table.selection()
        if not selected:
            self.status_var.set("No contact selected")
            return
            
        # Get the selected contact data
        values = self.contacts_table.item(selected[0], "values")
        if not values:
            return
            
        contact_id = values[0]
        self.status_var.set(f"Setting course to {contact_id}...")
        
        # Execute set_course_to_target command
        result = CommandRunner.run_command(
            "set_course_to_target", 
            {"target_id": contact_id}, 
            self.ship_var.get(), 
            self.output_box,
            return_json=True
        )
        
        if result and result.get("success"):
            self.status_var.set(f"Course set to {contact_id}")
        else:
            self.status_var.set(f"Failed to set course to {contact_id}")
    
    def track_contact(self):
        """Enable tracking for the selected contact"""
        selected = self.contacts_table.selection()
        if not selected:
            self.status_var.set("No contact selected")
            return
            
        # Get the selected contact data
        values = self.contacts_table.item(selected[0], "values")
        if not values:
            return
            
        contact_id = values[0]
        self.status_var.set(f"Tracking {contact_id}...")
        
        # Execute track_target command
        result = CommandRunner.run_command(
            "track_target", 
            {"target_id": contact_id, "enabled": "1"}, 
            self.ship_var.get(), 
            self.output_box,
            return_json=True
        )
        
        if result and result.get("success"):
            self.status_var.set(f"Now tracking {contact_id}")
        else:
            self.status_var.set(f"Failed to track {contact_id}")
    
    def delete_contact(self):
        """Delete the selected contact from the list"""
        selected = self.contacts_table.selection()
        if not selected:
            self.status_var.set("No contact selected")
            return
            
        # Get the selected contact data
        values = self.contacts_table.item(selected[0], "values")
        if not values:
            return
            
        contact_id = values[0]
        self.status_var.set(f"Removing {contact_id} from contacts...")
        
        # Execute remove_contact command
        result = CommandRunner.run_command(
            "remove_contact", 
            {"target_id": contact_id}, 
            self.ship_var.get(), 
            self.output_box,
            return_json=True
        )
        
        # Remove from table regardless of command result
        self.contacts_table.delete(selected[0])
        self.status_var.set(f"Removed {contact_id} from contacts list")
    
    def clear_contacts(self):
        """Clear all contacts from the list"""
        if hasattr(self, 'contacts_table'):
            # Clear the table
            for item in self.contacts_table.get_children():
                self.contacts_table.delete(item)
            
            # Execute clear_contacts command
            CommandRunner.run_command(
                "clear_contacts", 
                {}, 
                self.ship_var.get(), 
                self.output_box
            )
            
            self.status_var.set("All contacts cleared")
    
    def ping_sensors(self):
        """Ping ship sensors"""
        parsed = CommandRunner.run_command("ping_sensors", {}, self.ship_var.get(), 
                                         self.output_box, return_json=True)
        if parsed:
            cooldown = parsed.get("cooldown_started", "?")
            self.cooldown_var.set(f"Active ({cooldown}s)")
            self.cooldown_label.config(foreground="orange")
            self.status_var.set("Sensors pinged")
            
            # Update the last ping time
            from datetime import datetime
            self.last_ping_var.set(datetime.now().strftime("%H:%M:%S"))
            
            # Refresh contacts after a short delay to allow processing
            self.root.after(1000, self.refresh_contacts_table)
        else:
            self.status_var.set("Sensor ping failed")
    
    def toggle_passive_mode(self):
        """Toggle passive sensor mode"""
        if self.passive_mode_var.get():
            # Enable passive mode
            CommandRunner.run_command(
                "set_sensor_mode", 
                {"mode": "passive"}, 
                self.ship_var.get(), 
                self.output_box
            )
            self.stealth_mode_var.set(False)
            self.sensor_mode_var.set("Passive")
            self.status_var.set("Passive sensor mode enabled")
        else:
            # If both passive and stealth are off, default to active
            if not self.stealth_mode_var.get():
                CommandRunner.run_command(
                    "set_sensor_mode", 
                    {"mode": "active"}, 
                    self.ship_var.get(), 
                    self.output_box
                )
                self.sensor_mode_var.set("Active")
                self.status_var.set("Active sensor mode enabled")
    
    def toggle_stealth_mode(self):
        """Toggle stealth sensor mode"""
        if self.stealth_mode_var.get():
            # Enable stealth mode
            CommandRunner.run_command(
                "set_sensor_mode", 
                {"mode": "stealth"}, 
                self.ship_var.get(), 
                self.output_box
            )
            self.passive_mode_var.set(False)
            self.sensor_mode_var.set("Stealth")
            self.status_var.set("Stealth mode enabled")
        else:
            # If both passive and stealth are off, default to active
            if not self.passive_mode_var.get():
                CommandRunner.run_command(
                    "set_sensor_mode", 
                    {"mode": "active"}, 
                    self.ship_var.get(), 
                    self.output_box
                )
                self.sensor_mode_var.set("Active")
                self.status_var.set("Active sensor mode enabled")
    
    def set_scan_direction(self):
        """Set the scan direction for active sensors"""
        try:
            direction = float(self.scan_direction_var.get())
            CommandRunner.run_command(
                "set_scan_direction", 
                {"direction": direction}, 
                self.ship_var.get(), 
                self.output_box
            )
            self.status_var.set(f"Scan direction set to {direction}°")
        except ValueError:
            self.status_var.set("Invalid scan direction value")
    
    def trigger_signature_spike(self):
        """Trigger an EM signature spike"""
        try:
            duration = float(self.spike_duration_var.get())
            CommandRunner.run_command(
                "trigger_signature_spike", 
                {"duration": duration}, 
                self.ship_var.get(), 
                self.output_box
            )
            self.status_var.set(f"EM signature spike triggered for {duration}s")
            self.spike_var.set(f"Active ({duration}s)")
            
            # Update signature analysis
            self.signature_analysis.delete(1.0, tk.END)
            self.signature_analysis.insert(tk.END, 
                f"EM SPIKE ACTIVE\n"
                f"Duration: {duration} seconds\n"
                f"WARNING: Significantly increased detection range\n"
                f"Useful for emergency distress signals")
            
            # Refresh after spike duration
            self.root.after(int(duration * 1000) + 500, self.refresh_panels)
        except ValueError:
            self.status_var.set("Invalid duration value")
    
    def sort_contacts(self, column):
        """Sort contacts table by the specified column"""
        # Map column names to sort_by values
        column_map = {
            "id": "name",
            "distance": "distance",
            "signature": "signature",
            "timestamp": "timestamp"
        }
        
        if column in column_map:
            self.sort_by_var.set(column_map[column])
            self.refresh_contacts_table()
    
    @staticmethod
    def is_valid_number(value):
        """Validate if a string represents a valid number"""
        try:
            float(value)
            return True
        except ValueError:
            return False


def create_gui():
    """Create and run the main GUI.

    This version of ``create_gui`` does **not** start an internal simulation.
    The GUI relies on ``send.py`` to communicate with an external command
    server (e.g. started via ``main.py``).  It simply launches the Tkinter
    interface so the user can connect to that running simulator.
    """

    # Create the GUI window
    root = tk.Tk()
    app = ShipConsoleGUI(root)

    # Set a sensible window title
    root.title("Spaceship Command Console")
    
    # Initialize state variables if needed
    if not hasattr(app, 'state_vars'):
        app.state_vars = {}
        
    # Add empty values for any missing state variables
    required_vars = ["pitch", "yaw", "roll", "vx", "vy", "vz", "tx", "ty", "tz", "wx", "wy", "wz", "gx", "spike"]
    for var in required_vars:
        if var not in app.state_vars:
            app.state_vars[var] = tk.StringVar(value="0")
    
    # Initialize contact-related variables if they don't exist
    if not hasattr(app, 'contact_filter_var'):
        app.contact_filter_var = tk.StringVar(value="")
    if not hasattr(app, 'contact_mode_var'):
        app.contact_mode_var = tk.StringVar(value="all")
    if not hasattr(app, 'sort_by_var'):
        app.sort_by_var = tk.StringVar(value="distance")
    if not hasattr(app, 'cooldown_var'):
        app.cooldown_var = tk.StringVar(value="Ready")
    if not hasattr(app, 'last_ping_var'):
        app.last_ping_var = tk.StringVar(value="N/A")
    if not hasattr(app, 'passive_range_var'):
        app.passive_range_var = tk.StringVar(value="500 km")
    if not hasattr(app, 'active_range_var'):
        app.active_range_var = tk.StringVar(value="5000 km")
    if not hasattr(app, 'scan_fov_var'):
        app.scan_fov_var = tk.StringVar(value="120°")
    if not hasattr(app, 'sensor_mode_var'):
        app.sensor_mode_var = tk.StringVar(value="Passive")
    if not hasattr(app, 'spike_var'):
        app.spike_var = tk.StringVar(value="None")
    
    # Initialise ship selector with known ship IDs
    if hasattr(app, 'ship_var') and app.ship_var:
        if hasattr(app, 'ship_combo') and app.ship_combo:
            app.ship_combo['values'] = SHIP_IDS

        # Default to the first ship in the list
        if SHIP_IDS:
            app.ship_var.set(SHIP_IDS[0])

        if hasattr(app, 'refresh_panels'):
            app.refresh_panels()
    
    # Define cleanup function for when window is closed
    def on_closing():
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # Start the main loop
    try:
        root.mainloop()
    finally:
        pass


if __name__ == "__main__":
    create_gui()
