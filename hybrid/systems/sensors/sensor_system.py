from hybrid.core.base_system import BaseSystem
from datetime import datetime, timedelta
import math
import logging


class SensorSystem(BaseSystem):
    """
    Sensor system for ships. Handles active and passive detection.
    """
    
    def __init__(self, config=None):
        """
        Initialize the sensor system
        
        Args:
            config (dict): Sensor system configuration
        """
        super().__init__(config)
        
        # Store a reference to the config and ensure it exists
        self.config = config or {}
        
        # Power requirements
        self.power_draw = self.config.get("power_draw", 5.0)
        
        # Initialize contacts at the system level
        if "contacts" not in self.config:
            self.config["contacts"] = []
        
        # Passive sensors
        self.passive = self.config.get("passive", {
            "range": 500.0,
            "contacts": []
        })
        
        # Ensure passive contacts list exists
        if "contacts" not in self.passive:
            self.passive["contacts"] = []
        
        # Active sensors
        self.active = self.config.get("active", {
            "scan_range": 5000.0,
            "scan_fov": 120.0,  # degrees
            "cooldown": 0.0,
            "cooldown_time": 10.0,  # seconds between pings
            "contacts": [],
            "last_ping_time": 0,  # Initialize with 0 instead of None
            "processed": True,
            "scan_direction": 0.0  # Default scan direction
        })
        
        # Ensure active contacts list exists
        if "contacts" not in self.active:
            self.active["contacts"] = []
        
        # Ensure last_ping_time exists and is numeric
        if "last_ping_time" not in self.active or self.active["last_ping_time"] is None:
            self.active["last_ping_time"] = 0
        
        # Sensor operating mode
        self.mode = "passive"  # Default mode: passive, active, or stealth
        
        # Signature properties
        self.signature_base = self.config.get("signature_base", 1.0)
        self.original_signature_base = self.signature_base  # Store original for mode changes
        self.spike_until = None
        
    def tick(self, dt, ship, event_bus):
        """
        Update sensor system for current time step
        
        Args:
            dt (float): Time delta in seconds
            ship (Ship): The parent ship
            event_bus (EventBus): Event bus for system communication
        """
        if not self.enabled:
            return
            
        # Request power from the power system
        power_system = ship.systems.get("power")
        if power_system and not power_system.request_power(self.power_draw * dt, "sensors"):
            # Not enough power, disable temporarily
            logger.warning(f"Sensors on {ship.id} disabled due to power shortage")
            return
            
        # Update cooldowns
        if self.active["cooldown"] > 0:
            self.active["cooldown"] -= dt
            self.active["cooldown"] = max(0, self.active["cooldown"])
            
        # Check for active ping processing
        if self.active["last_ping_time"] and not self.active["processed"]:
            # This would be handled in a separate function that has access to all ships
            # For now, we'll just mark it as processed
            self.active["processed"] = True
            logger.debug(f"Active ping completed for {ship.id}")
            
        # Passive sensor updates would happen here
        # This requires access to all ships, so it's typically done externally
            
    def command(self, action, params):
        """
        Process sensor system commands
        
        Args:
            action (str): Command action
            params (dict): Command parameters
            
        Returns:
            dict: Command response
        """
        if action == "ping_sensors" or action == "ping":
            return self.ping_active_sensors()
        elif action == "get_contacts":
            return self.get_contacts()
        elif action == "status":
            return self.get_state()
        elif action == "power_on":
            return self.power_on()
        elif action == "power_off":
            return self.power_off()
        elif action == "set_sensor_mode":
            mode = params.get("mode", "passive")
            return self.set_sensor_mode(mode)
        elif action == "set_scan_direction":
            direction = params.get("direction", 0)
            return self.set_scan_direction(float(direction))
        elif action == "trigger_signature_spike":
            duration = params.get("duration", 3.0)
            self.trigger_signature_spike(float(duration))
            return {"status": "Signature spike triggered", "duration": duration}
        return super().command(action, params)
        
    def set_sensor_mode(self, mode):
        """
        Set sensor operation mode
        
        Args:
            mode (str): 'passive', 'active', or 'stealth'
            
        Returns:
            dict: Command response
        """
        if not self.enabled:
            return {"error": "Sensor system is disabled"}
            
        if mode not in ["passive", "active", "stealth"]:
            return {"error": f"Invalid sensor mode: {mode}"}
            
        self.mode = mode
        
        # Adjust parameters based on mode
        if mode == "passive":
            # Normal passive operation
            self.signature_base = self.config.get("signature_base", 1.0)
        elif mode == "active":
            # Active mode has higher signature
            self.signature_base = self.config.get("signature_base", 1.0) * 1.5
        elif mode == "stealth":
            # Stealth mode has lower signature but reduced range
            self.signature_base = self.config.get("signature_base", 1.0) * 0.5
            self.passive["range"] = self.config.get("passive", {}).get("range", 500.0) * 0.7
            
        return {
            "status": f"Sensor mode set to {mode}",
            "signature_base": self.signature_base
        }
        
    def set_scan_direction(self, direction):
        """
        Set direction for active scanning
        
        Args:
            direction (float): Direction in degrees (0-359)
            
        Returns:
            dict: Command response
        """
        if not self.enabled:
            return {"error": "Sensor system is disabled"}
            
        # Normalize to 0-359
        direction = direction % 360
        
        # Store scan direction
        self.active["scan_direction"] = direction
        
        return {
            "status": f"Scan direction set to {direction}°",
            "direction": direction
        }
        
    def ping_active_sensors(self):
        """
        Trigger an active sensor ping
        
        Returns:
            dict: Command response
        """
        if not self.enabled:
            return {"error": "Sensor system is disabled"}
            
        if self.active["cooldown"] > 0:
            return {
                "error": f"Active sensors cooling down",
                "cooldown": round(self.active["cooldown"], 1)
            }
            
        now = datetime.utcnow().isoformat()
        self.active["last_ping_time"] = now
        self.active["processed"] = False
        self.active["cooldown"] = self.active["cooldown_time"]
        
        return {
            "status": "Active sensor ping triggered",
            "cooldown_started": self.active["cooldown_time"],
            "timestamp": now
        }
        
    def process_active_ping(self, all_ships):
        """
        Process active sensor ping results
        
        Args:
            all_ships (list): List of all ships in the simulation
            
        Returns:
            list: List of detected contacts
        """
        if not self.active["last_ping_time"] or self.active["processed"]:
            return []
            
        ship_id = None
        position = None
        orientation = None
        
        # This would be handled better with direct ship reference
        # For now, we'll assume these are available
        for ship in all_ships:
            if hasattr(ship, 'systems') and 'sensors' in ship.systems:
                if ship.systems['sensors'] is self:
                    ship_id = ship.id
                    position = ship.position
                    orientation = ship.orientation
                    break
        
        if not ship_id:
            logger.error("Could not find ship for sensor system")
            return []
            
        # Get sensor parameters
        active_range = self.active["scan_range"]
        fov = self.active["scan_fov"]
        ship_yaw = orientation.get("yaw", 0.0)
        
        # Use custom scan direction if set, otherwise use ship yaw
        scan_direction = self.active.get("scan_direction", ship_yaw)
        
        now = datetime.utcnow().isoformat()
        contacts = []
        
        # Scan for other ships
        for other in all_ships:
            # Skip self
            if other.id == ship_id:
                continue
    
            # Calculate distance
            dx = other.position["x"] - position["x"]
            dy = other.position["y"] - position["y"]
            dz = other.position["z"] - position["z"]
            dist = math.sqrt(dx**2 + dy**2 + dz**2)
            
            # Skip if out of range
            if dist > active_range:
                continue
    
            # Calculate angle to target
            angle_to_target = math.degrees(math.atan2(dx, dz)) % 360
            
            # Calculate bearing for contact record
            bearing = angle_to_target
            
            # Check if in field of view using scan direction
            delta = abs((angle_to_target - scan_direction + 180) % 360 - 180)
            if delta > fov / 2:
                continue
            
            # Attempt to estimate target signature
            target_signature = 1.0  # Default value
            
            # If target has a sensor system, try to get its signature
            if hasattr(other, 'systems') and 'sensors' in other.systems:
                if hasattr(other.systems['sensors'], 'calculate_signature'):
                    target_signature = other.systems['sensors'].calculate_signature(other)
            
            # Add to contacts with enhanced information
            contacts.append({
                "target_id": other.id,
                "distance": round(dist, 1),
                "method": "active",
                "detected_at": now,
                "bearing": round(bearing, 1),
                "signature": round(target_signature, 2),
                "position": {
                    "x": other.position["x"],
                    "y": other.position["y"],
                    "z": other.position["z"]
                }
            })
        
        # Update sensor state
        self.active["contacts"] = contacts
        self.active["processed"] = True
        self.active["last_ping_time"] = None
        
        return contacts
        
    def get_contacts(self):
        """
        Get all current contacts
        
        Returns:
            dict: Contacts information
        """
        passive = self.passive.get("contacts", [])
        active = self.active.get("contacts", [])
        
        # Merge contacts and sort by distance
        contacts = passive + active
        contacts.sort(key=lambda c: c.get("distance", float("inf")))
        
        return {
            "contacts": contacts,
            "contact_count": len(contacts),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    def calculate_signature(self, ship):
        """
        Calculate this ship's sensor signature
        
        Args:
            ship (Ship): The ship to calculate signature for
            
        Returns:
            float: Signature strength
        """
        # Base signature
        signature = self.signature_base
        
        # Add signature from thrust
        if "propulsion" in ship.systems:
            propulsion = ship.systems["propulsion"]
            thrust = propulsion.get_thrust() if hasattr(propulsion, 'get_thrust') else {}
            
            # Calculate magnitude of thrust
            thrust_values = thrust.values() if thrust else [0, 0, 0]
            thrust_sum_squares = sum(v**2 for v in thrust_values if isinstance(v, (int, float)))
            thrust_signature = math.sqrt(thrust_sum_squares) if thrust_sum_squares > 0 else 0
            signature += thrust_signature
        
        # Add signature from mass
        signature += ship.mass * 0.001
        
        # Check for signature spike
        if self.spike_until:
            try:
                if datetime.utcnow() < datetime.fromisoformat(self.spike_until):
                    signature += 100.0
            except (ValueError, TypeError):
                logger.warning(f"Invalid spike_until format: {self.spike_until}")
                
        return signature
        
    def trigger_signature_spike(self, duration=3.0):
        """
        Trigger a temporary signature spike
        
        Args:
            duration (float): Duration of the spike in seconds
        """
        self.spike_until = (datetime.utcnow() + timedelta(seconds=duration)).isoformat()
        logger.debug(f"Signature spike triggered until {self.spike_until}")
        
    def get_state(self):
        """
        Get current sensor system state
        
        Returns:
            dict: Sensor system state
        """
        try:
            # Get base state from parent class
            state = super().get_state()
            
            # Add sensor mode
            state["mode"] = getattr(self, "mode", "passive")
            
            # Add passive sensors state (make a copy to avoid reference issues)
            state["passive"] = {
                "range": self.passive.get("range", 500.0),
                "contacts": list(self.passive.get("contacts", [])),
            }
            
            # Add active sensors state (make a copy to avoid reference issues)
            state["active"] = {
                "scan_range": self.active.get("scan_range", 5000.0),
                "scan_fov": self.active.get("scan_fov", 120.0),
                "cooldown": round(self.active.get("cooldown", 0.0), 1),
                "cooldown_time": self.active.get("cooldown_time", 10.0),
                "contact_count": len(self.active.get("contacts", [])),
                "last_ping_time": self.active.get("last_ping_time", 0),
                "scan_direction": self.active.get("scan_direction", 0.0)
            }
            
            # Add signature information
            state["signature_base"] = self.signature_base
            state["spike_until"] = self.spike_until
            
            # Add top-level contacts list
            state["contacts"] = list(self.config.get("contacts", []))
            
            return state
        except Exception as e:
            logger.error(f"Error generating sensor system state: {e}")
            # Return minimal valid state on error
            return {
                "enabled": self.enabled,
                "passive": {"contacts": []},
                "active": {"contacts": [], "last_ping_time": 0},
                "contacts": []
            }
