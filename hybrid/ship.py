# hybrid/ship.py

"""
Ship implementation that manages systems and handles physics.
"""
from hybrid.core.event_bus import EventBus
from hybrid.utils.math_utils import (
    sanitize_physics_state, is_valid_number, clamp, magnitude,
    normalize_angle as normalize_angle_util
)
from hybrid.utils.quaternion import Quaternion, quaternion_identity
import math
import time
import copy
import logging
from collections import deque

logger = logging.getLogger(__name__)

class Ship:
    """Class representing a ship with multiple systems"""
    
    def __init__(self, ship_id, config=None):
        """
        Initialize a ship with the given configuration

        Args:
            ship_id (str): Unique identifier for the ship
            config (dict): Configuration dictionary for the ship
        """
        self.id = ship_id
        config = config or {}

        # Initialize ship properties with defaults
        self.name = config.get("name", ship_id)
        self.class_type = config.get("class", "shuttle")
        self.faction = config.get("faction", "neutral")

        # Ship class metadata (from ship class definitions)
        self.dimensions = config.get("dimensions", None)
        self.armor = config.get("armor", None)
        self.crew_complement = config.get("crew_complement", None)
        self.weapon_mounts = config.get("weapon_mounts", None)

        # Dynamic mass model: total mass = dry_mass + fuel + ammo
        # When dry_mass is explicitly set, mass updates each tick as
        # consumables are spent. When omitted, mass stays fixed for
        # backward compatibility with existing ship configs.
        total_mass = config.get("mass", 1000.0)
        self._dynamic_mass = "dry_mass" in config
        self.dry_mass = float(config.get("dry_mass", total_mass))  # structural mass
        self.mass = total_mass  # kg, current total mass

        # Rotational inertia (kg⋅m²)
        # For S3: moment of inertia for rotational dynamics (torque = I * angular_acceleration)
        # Currently scalar (spherical approximation), can be extended to 3x3 tensor for complex shapes
        # Default: I ≈ (1/6) * m * L² where L ≈ ∛(m) (rough estimate for spacecraft)
        self._base_moment_of_inertia = config.get("moment_of_inertia", None)
        self.moment_of_inertia = self._base_moment_of_inertia or self._calculate_moment_of_inertia(self.mass)

        # D6: Hull integrity for damage model
        # Base hull on mass: roughly 1 hull point per 10 kg of mass
        self.max_hull_integrity = config.get("max_hull_integrity", self.mass / 10.0)
        self.hull_integrity = config.get("hull_integrity", self.max_hull_integrity)

        # Initialize physical state
        self.position = self._get_vector3_config(config.get("position", {}))
        self.velocity = self._get_vector3_config(config.get("velocity", {}))
        self.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}

        # Orientation: Euler angles for backward compatibility, quaternion for physics
        self.orientation = self._get_vector3_config(config.get("orientation", {}), "pitch", "yaw", "roll")

        # S3: Quaternion-based attitude (eliminates gimbal lock)
        # Initialize from Euler angles
        self.quaternion = Quaternion.from_euler(
            self.orientation["pitch"],
            self.orientation["yaw"],
            self.orientation["roll"]
        )

        self.angular_velocity = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        self.angular_acceleration = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}  # For S3: RCS torque integration
        self.thrust = {"x": 0.0, "y": 0.0, "z": 0.0}

        # Previous acceleration for Velocity Verlet integration
        self._prev_acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}

        # Flight path logging (for minimap trails)
        # Records position history: 600 samples @ 0.5s = 5 minutes of history
        self._flight_path_max_samples = 600
        self._flight_path_sample_interval = 0.5  # seconds (simulation time)
        self._flight_path_history = deque(maxlen=self._flight_path_max_samples)
        self._last_flight_path_sample_time = 0.0  # Simulation time, not real time

        # Create the event bus for system communication
        self.event_bus = EventBus()

        # Docking state
        self.docked_to = config.get("docked_to")

        # Initialize damage model
        from hybrid.systems.damage_model import DamageModel
        from hybrid.systems_schema import get_subsystem_health_schema
        self.damage_model = DamageModel(
            config.get("damage_model", {}),
            schema=get_subsystem_health_schema(),
            systems_config=config.get("systems", {}),
        )

        # Initialize armor model — tracks per-section armor thickness and ablation.
        # Uses the same armor config that hit_location.py reads for static thickness,
        # but now the thickness is mutable state that degrades under fire.
        from hybrid.combat.armor import ArmorModel
        self.armor_model = ArmorModel(self.armor)

        # Initialize cascade manager for damage propagation effects
        from hybrid.systems.cascade_manager import CascadeManager
        self.cascade_manager = CascadeManager()

        # Initialize systems
        self.systems = {}
        self._systems_config = config.get("systems", {})  # Raw config for hit-location placement data
        self._load_systems(self._systems_config)

        # Infer dynamic mass model when dry_mass wasn't explicitly provided
        # but propulsion fuel is present.  Without this, ships defined with
        # just ``mass: 5000`` and ``fuel_level: 10000`` would never update
        # their mass as fuel burns -- giving them infinite effective range.
        #
        # Scenario convention: ``mass`` is the structural hull mass, and fuel
        # is configured separately under systems.propulsion.fuel_level.
        # The ship class registry sets ``dry_mass`` explicitly, but raw
        # scenario definitions do not -- so we treat ``mass`` as the dry mass
        # and compute total mass = mass + fuel.
        if not self._dynamic_mass:
            propulsion = self.systems.get("propulsion")
            if propulsion and hasattr(propulsion, "fuel_level") and propulsion.fuel_level > 0:
                fuel = propulsion.fuel_level
                # Treat the configured ``mass`` as the structural dry mass
                self.dry_mass = float(config.get("mass", self.mass))
                self.mass = self.dry_mass + fuel
                self._dynamic_mass = True
                logger.info(
                    f"Ship {self.id}: inferred dry_mass={self.dry_mass:.1f} kg "
                    f"(from config mass), fuel={fuel:.1f} kg, "
                    f"total={self.mass:.1f} kg"
                )

        # Fleet and AI control
        self.fleet_id = None  # Fleet this ship belongs to
        self.ai_controller = None  # AI controller (if AI-controlled)
        self.ai_enabled = config.get("ai_enabled", False)

        # Auto-initialize AI controller if ai_enabled is set in config.
        # Without this, ai_enabled=True ships would never get an ai_controller
        # and would sit inert in the simulation.
        if self.ai_enabled:
            self.enable_ai()

            # Apply role-based behavior profile from scenario YAML.
            # The ai_behavior block lets scenarios override the auto-
            # inferred role (e.g. force a corvette to escort a freighter).
            ai_config = config.get("ai_behavior", {})
            if ai_config and self.ai_controller:
                from hybrid.fleet.npc_behavior import get_profile
                role = ai_config.get("role", self.ai_controller.profile.role)
                self.ai_controller.profile = get_profile(role, ai_config)
                # Sync engagement_range from the new profile
                self.ai_controller.engagement_range = (
                    self.ai_controller.profile.engagement_range
                )

        # Initialize command handler
        self.command_handlers = {
            "get_state": self._cmd_get_state,
            "get_position": self._cmd_get_position,
            "get_velocity": self._cmd_get_velocity,
            "get_orientation": self._cmd_get_orientation,
            "set_thrust": self._cmd_set_thrust,
            "set_course": self._cmd_set_course,
            "rotate": self._cmd_rotate,
            "get_system_state": self._cmd_get_system_state,
            "request_power": self._cmd_request_power,
            "reroute_power": self._cmd_reroute_power,
            "get_power_state": self._cmd_get_power_state,
            "set_power_allocation": self._cmd_set_power_allocation,
            "set_power_profile": self._cmd_set_power_profile,
            "get_power_profiles": self._cmd_get_power_profiles,
            "set_overdrive_limits": self._cmd_set_overdrive_limits,
            "get_subsystem_health": self._cmd_get_subsystem_health,
            "repair_subsystem": self._cmd_repair_subsystem,
        }
        
    def _get_vector3_config(self, config, x_key="x", y_key="y", z_key="z"):
        """Extract a vector3 from config with defaults"""
        return {
            x_key: float(config.get(x_key, 0.0)),
            y_key: float(config.get(y_key, 0.0)),
            z_key: float(config.get(z_key, 0.0))
        }

    @staticmethod
    def _calculate_moment_of_inertia(mass: float) -> float:
        """Calculate moment of inertia from mass using spherical approximation.

        I = (1/6) * m * L^2 where L = m^(1/3) (rough spacecraft estimate).
        """
        return mass * (mass ** (1.0 / 3.0)) / 6.0

    def _update_mass(self):
        """Recalculate total mass from dry mass plus consumables (fuel, ammo).

        Only active when ``dry_mass`` was explicitly set in the ship config
        (``_dynamic_mass`` flag).  Updates moment_of_inertia when mass
        changes significantly so that F=ma and torque calculations stay
        correct as fuel is burned.
        """
        if not self._dynamic_mass:
            return

        old_mass = self.mass

        fuel_mass = 0.0
        propulsion = self.systems.get("propulsion")
        if propulsion and hasattr(propulsion, "fuel_level"):
            fuel_mass = propulsion.fuel_level

        ammo_mass = 0.0
        # Truth weapons (railguns, PDCs) live in the combat system
        combat = self.systems.get("combat")
        if combat and hasattr(combat, "get_total_ammo_mass"):
            ammo_mass += combat.get_total_ammo_mass()
        # Legacy weapons may also contribute ammo mass
        weapons = self.systems.get("weapons")
        if weapons and hasattr(weapons, "get_total_ammo_mass"):
            ammo_mass += weapons.get_total_ammo_mass()

        self.mass = self.dry_mass + fuel_mass + ammo_mass

        # Recalculate moment of inertia if mass changed by >1%
        if self._base_moment_of_inertia is None and abs(self.mass - old_mass) > old_mass * 0.01:
            self.moment_of_inertia = self._calculate_moment_of_inertia(self.mass)

    def _load_systems(self, systems_config):
        """
        Load ship systems from configuration

        Args:
            systems_config (dict): Dictionary of system configurations
        """
        from hybrid.systems import get_system_class

        # Ensure essential systems are always present with defaults
        # These systems are required for Expanse-style flight model
        essential_systems = {
            "helm": {},      # Helm for manual control interface
            "rcs": {},       # RCS for attitude control (torque-based rotation)
            "flight_computer": {},  # Flight computer for high-level manoeuvre commands
            "ops": {},       # Ops for power allocation and damage control
            "engineering": {},  # Engineering for reactor, drive, radiators, fuel
            "crew_fatigue": {},  # Crew fatigue and g-load performance model
            "science": {},   # Science for sensor analysis and contact classification
        }

        # Merge config with defaults (config takes precedence)
        merged_config = {**essential_systems, **systems_config}

        # Inject weapon_mounts into combat config for firing arc enforcement
        if "combat" in merged_config and self.weapon_mounts:
            combat_cfg = merged_config["combat"]
            if isinstance(combat_cfg, dict) and "weapon_mounts" not in combat_cfg:
                combat_cfg["weapon_mounts"] = self.weapon_mounts

        # Load each system type
        for system_type, config in merged_config.items():
            # Skip systems with None config
            if config is None:
                continue
                
            try:
                # Get the appropriate class for this system type
                system_class = get_system_class(system_type)
                
                # Create an instance of the system
                if system_class:
                    system = system_class(config)
                    self.systems[system_type] = system
                    logger.debug(f"Loaded system: {system_type}")
                else:
                    logger.warning(f"Unknown system type: {system_type}")
            except Exception as e:
                logger.error(f"Error loading system {system_type}: {e}")
                # Create a basic dictionary for failed systems
                self.systems[system_type] = {
                    "status": "error",
                    "error": str(e)
                }
    
    def tick(self, dt, all_ships=None, sim_time=0.0):
        """
        Update ship state for the current time step

        Args:
            dt (float): Time delta in seconds
            all_ships (list, optional): List of all ships in simulation
            sim_time (float): Current simulation time
        """
        if all_ships is None:
            resolved_all_ships = [self]
        elif isinstance(all_ships, dict):
            resolved_all_ships = list(all_ships.values())
        else:
            resolved_all_ships = all_ships
        self._all_ships_ref = resolved_all_ships
        self.sim_time = sim_time

        # Update AI controller if enabled
        if self.ai_enabled and self.ai_controller:
            try:
                self.ai_controller.update(dt, sim_time)
            except Exception as e:
                logger.error(f"Error in AI controller for {self.id}: {e}")

        # First pass: update all systems
        for system_type, system in self.systems.items():
            if hasattr(system, "tick") and callable(system.tick):
                try:
                    system.tick(dt, self, self.event_bus)
                except Exception as e:
                    logger.error(f"Error in system {system_type} tick: {e}")
            if hasattr(system, "report_heat") and callable(system.report_heat):
                try:
                    system.report_heat(self, self.event_bus)
                except Exception as e:
                    logger.error(f"Error reporting heat for system {system_type}: {e}")

        # v0.7.0: Evaluate cascade effects (reactor→all, sensors→targeting, etc.)
        self.cascade_manager.tick(self.damage_model, self.event_bus, self.id)

        # v0.6.0: Dissipate heat from all subsystems
        self.damage_model.dissipate_heat(dt, self.event_bus, self.id)

        # Update mass from consumables (fuel burned, ammo expended)
        self._update_mass()

        # Update physics after systems have updated
        self._update_physics(dt, sim_time=sim_time)
    
    def _update_physics(self, dt, force=None, sim_time=0.0):
        """Update ship physics using Velocity Verlet integration.

        Velocity Verlet provides better energy conservation than Euler
        integration while remaining simple and efficient. The update is:

            x(t+dt) = x(t) + v(t)*dt + 0.5*a(t)*dt^2
            v(t+dt) = v(t) + 0.5*(a(t) + a(t+dt))*dt

        Since acceleration changes are set by systems *before* this method
        runs, ``self.acceleration`` already holds the new value ``a(t+dt)``.
        We cache the previous acceleration to complete the Verlet step.

        Args:
            dt (float): Time delta in seconds
            force (dict, optional): Net force vector acting on the ship. If not
                provided, the existing acceleration is used.
            sim_time (float, optional): Current simulation time for flight path recording
        """
        # No physics integration while docked — position is locked by docking system
        if self.docked_to:
            return

        # Guard against invalid dt
        if not is_valid_number(dt) or dt <= 0:
            logger.warning(f"Ship {self.id}: Invalid dt={dt}, skipping physics update")
            return

        # Guard against zero or invalid mass
        if not is_valid_number(self.mass) or self.mass <= 0:
            logger.error(f"Ship {self.id}: Invalid mass={self.mass}, resetting to default")
            self.mass = 1000.0

        # Store previous acceleration for Verlet integration
        prev_accel = {
            "x": self._prev_acceleration.get("x", 0.0),
            "y": self._prev_acceleration.get("y", 0.0),
            "z": self._prev_acceleration.get("z", 0.0),
        }

        if force is not None:
            # Calculate new acceleration from force
            self.acceleration = {
                "x": force.get("x", 0.0) / self.mass,
                "y": force.get("y", 0.0) / self.mass,
                "z": force.get("z", 0.0) / self.mass,
            }

        # Velocity Verlet: position update uses previous velocity + 0.5*a_prev*dt^2
        half_dt_sq = 0.5 * dt * dt
        self.position["x"] += self.velocity["x"] * dt + prev_accel["x"] * half_dt_sq
        self.position["y"] += self.velocity["y"] * dt + prev_accel["y"] * half_dt_sq
        self.position["z"] += self.velocity["z"] * dt + prev_accel["z"] * half_dt_sq

        # Velocity Verlet: velocity update uses average of old and new acceleration
        half_dt = 0.5 * dt
        self.velocity["x"] += (prev_accel["x"] + self.acceleration["x"]) * half_dt
        self.velocity["y"] += (prev_accel["y"] + self.acceleration["y"]) * half_dt
        self.velocity["z"] += (prev_accel["z"] + self.acceleration["z"]) * half_dt

        # Cache current acceleration for next tick's Verlet step
        self._prev_acceleration = {
            "x": self.acceleration["x"],
            "y": self.acceleration["y"],
            "z": self.acceleration["z"],
        }

        # Record position in flight path history (use simulation time)
        self._record_flight_path(sim_time)

        # Sanitize physics state (check for NaN/Inf and clamp to reasonable bounds)
        self.position, self.velocity, self.acceleration, recovered = sanitize_physics_state(
            self.position, self.velocity, self.acceleration, self.id
        )

        if recovered:
            logger.warning(f"Ship {self.id}: Physics state recovered from invalid values")
            # Publish event for monitoring/debugging
            self.event_bus.publish("physics_recovery", {
                "ship_id": self.id,
                "position": self.position,
                "velocity": self.velocity,
                "acceleration": self.acceleration
            })

        # S3: Update orientation using quaternion integration (no gimbal lock!)
        # Quaternion derivative: dq/dt = 0.5 * q * ω
        # where ω is represented as pure quaternion (0, ωx, ωy, ωz)

        # Convert angular velocity from degrees/s to radians/s
        # Axis mapping: aerospace convention (pitch=Y, yaw=Z, roll=X)
        omega_x = math.radians(self.angular_velocity.get("roll", 0.0))   # Roll = rotation around X
        omega_y = math.radians(self.angular_velocity.get("pitch", 0.0))  # Pitch = rotation around Y
        omega_z = math.radians(self.angular_velocity.get("yaw", 0.0))    # Yaw = rotation around Z

        # Create pure quaternion from angular velocity
        omega_quat = Quaternion(0.0, omega_x, omega_y, omega_z)

        # Compute quaternion derivative
        q_dot = (self.quaternion * omega_quat).scale(0.5)

        # Integrate quaternion (Euler integration)
        self.quaternion = self.quaternion + q_dot.scale(dt)

        # Normalize quaternion to prevent drift
        self.quaternion.normalize()

        # Sync Euler angles from quaternion for backward compatibility and telemetry
        pitch, yaw, roll = self.quaternion.to_euler()
        self.orientation["pitch"] = pitch
        self.orientation["yaw"] = yaw
        self.orientation["roll"] = roll

        # Guard against NaN in Euler angles (shouldn't happen with quaternions, but safety check)
        for key in self.orientation:
            if not is_valid_number(self.orientation[key]):
                logger.error(f"Ship {self.id}: Invalid orientation {key}={self.orientation[key]}, resetting quaternion")
                self.quaternion = quaternion_identity()
                self.orientation[key] = 0.0

        # S3: No more gimbal lock warnings! Quaternions handle all orientations perfectly.
        # The old gimbal lock warning has been removed - quaternions eliminate this issue entirely.

    def _record_flight_path(self, sim_time):
        """Record position in flight path history at regular intervals.
        
        Args:
            sim_time (float): Current simulation time
        """
        # Sample at regular intervals (using simulation time)
        if sim_time - self._last_flight_path_sample_time >= self._flight_path_sample_interval:
            self._flight_path_history.append({
                "pos": {
                    "x": self.position["x"],
                    "y": self.position["y"],
                    "z": self.position["z"]
                },
                "t": sim_time
            })
            self._last_flight_path_sample_time = sim_time

    def get_flight_path(self, max_age_seconds=60, current_sim_time=None):
        """Get flight path positions from last N seconds.
        
        Args:
            max_age_seconds: Maximum age of positions to include (simulation seconds)
            current_sim_time: Current simulation time (if None, uses last recorded time + sample_interval)
            
        Returns:
            list: List of position dicts {x, y, z} from last N seconds
        """
        if not self._flight_path_history:
            return []
        
        # Use provided sim_time or estimate from last sample + interval
        if current_sim_time is None:
            if self._flight_path_history:
                # Estimate current time as last sample + one interval
                current_sim_time = self._flight_path_history[-1]["t"] + self._flight_path_sample_interval
            else:
                return []
        
        cutoff_time = max(0, current_sim_time - max_age_seconds)
        
        return [
            entry["pos"] for entry in self._flight_path_history
            if entry["t"] >= cutoff_time
        ]

    def command(self, command_type, params=None):
        """
        Process a command
        
        Args:
            command_type (str): The type of command
            params (dict): Parameters for the command
            
        Returns:
            dict: Response containing the result or error
        """
        if params is None:
            params = {}
            
        # Check if this is a system-specific command
        if "system" in params:
            system_type = params["system"]
            if system_type in self.systems:
                system = self.systems[system_type]
                # Check if this is a direct system command
                if "command" in params:
                    system_cmd = params["command"]
                    system_params = params.get("params", {})
                    
                    if hasattr(system, "command") and callable(system.command):
                        return system.command(system_cmd, system_params)
                    else:
                        return {"error": f"System {system_type} does not support commands"}
                        
                # Otherwise, pass the command to the system's command handler
                elif hasattr(system, "command") and callable(system.command):
                    return system.command(command_type, params)
        
        # Check ship's command handlers
        if command_type in self.command_handlers:
            return self.command_handlers[command_type](params)
            
        # Try to find a system that can handle this command
        for system_type, system in self.systems.items():
            if hasattr(system, "command") and callable(system.command):
                try:
                    result = system.command(command_type, params)
                    if result and "error" not in result:
                        return result
                except Exception:
                    pass  # Ignore exceptions, try next system
        
        return {"error": f"Command '{command_type}' not recognized"}
    
    def get_state(self):
        """
        Get the current state of the ship and all systems
        
        Returns:
            dict: Complete ship state
        """
        # Calculate navigation awareness metrics
        nav_awareness = self._calculate_navigation_awareness()
        
        # Determine engine/drift state
        accel_mag = magnitude(self.acceleration)
        vel_mag = magnitude(self.velocity)
        is_drifting = accel_mag < 0.001 and vel_mag > 0.01

        # Start with the ship's physical state
        state = {
            "id": self.id,
            "name": self.name,
            "class": self.class_type,
            "faction": self.faction,
            "mass": self.mass,
            "dry_mass": self.dry_mass,
            "moment_of_inertia": self.moment_of_inertia,
            "hull_integrity": self.hull_integrity,
            "max_hull_integrity": self.max_hull_integrity,
            "hull_percent": (self.hull_integrity / self.max_hull_integrity * 100) if self.max_hull_integrity > 0 else 0,
            "position": self.position,
            "velocity": self.velocity,
            "acceleration": self.acceleration,
            "orientation": self.orientation,
            "angular_velocity": self.angular_velocity,
            "thrust": self.thrust,
            "is_drifting": is_drifting,
            "navigation": nav_awareness,  # Add navigation awareness metrics
            "flight_path": self.get_flight_path(60) if self._flight_path_history else [],  # Last 60 seconds of flight path
            "systems": {},
            "damage_model": self.damage_model.get_report(),
            "cascade_effects": self.cascade_manager.get_report(),
        }

        # Include ship class metadata when available
        if self.dimensions:
            state["dimensions"] = self.dimensions
        if self.armor:
            state["armor"] = self.armor
        if self.crew_complement:
            state["crew_complement"] = self.crew_complement
        if self.weapon_mounts:
            state["weapon_mounts"] = self.weapon_mounts
        
        # Add systems state
        for system_type, system in self.systems.items():
            if hasattr(system, "get_state") and callable(system.get_state):
                try:
                    state["systems"][system_type] = system.get_state()
                except Exception as e:
                    state["systems"][system_type] = {
                        "status": "error",
                        "error": str(e)
                    }
            elif isinstance(system, dict):
                # If it's a plain dictionary, include it directly
                state["systems"][system_type] = copy.deepcopy(system)
        
        return state
    
    def _calculate_navigation_awareness(self):
        """Calculate navigation awareness metrics: drift angle, velocity heading, etc.
        
        Returns:
            dict: Navigation awareness data
        """
        from hybrid.utils.math_utils import magnitude, normalize_vector, dot_product
        from hybrid.navigation.relative_motion import vector_to_heading
        
        # Calculate velocity magnitude
        vel_mag = magnitude(self.velocity)
        
        # Calculate velocity heading (direction of velocity vector)
        velocity_heading = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        if vel_mag > 0.001:
            velocity_heading = vector_to_heading(self.velocity)
        
        # Calculate drift angle (angle between ship heading and velocity direction)
        # Use quaternion to get ship's forward direction in world frame
        drift_angle = 0.0
        if vel_mag > 0.001 and hasattr(self, 'quaternion'):
            # Ship's forward axis in ship frame is +X
            ship_forward_ship_frame = (1.0, 0.0, 0.0)
            # Rotate to world frame
            ship_forward_world = self.quaternion.rotate_vector(ship_forward_ship_frame)
            
            # Normalize velocity vector
            vel_normalized = normalize_vector(self.velocity)
            
            # Calculate angle between ship forward and velocity
            # dot product gives cos(angle)
            dot = (ship_forward_world[0] * vel_normalized["x"] + 
                   ship_forward_world[1] * vel_normalized["y"] + 
                   ship_forward_world[2] * vel_normalized["z"])
            
            # Clamp to valid range for acos
            dot = max(-1.0, min(1.0, dot))
            drift_angle = math.degrees(math.acos(dot))
        
        return {
            "velocity_heading": velocity_heading,
            "velocity_magnitude": vel_mag,
            "drift_angle": drift_angle,
            "heading": self.orientation.copy()  # Current heading (nose direction)
        }

    def take_damage(self, amount, source=None, target_subsystem=None):
        """
        Apply damage to the ship's hull and optionally to a specific subsystem.

        v0.6.0: Enhanced with subsystem targeting.

        Args:
            amount (float): Amount of damage to apply
            source (str, optional): ID of ship/weapon that caused damage
            target_subsystem (str, optional): Specific subsystem to damage

        Returns:
            dict: Damage result with current hull status
        """
        if amount <= 0:
            return {"ok": False, "error": "Invalid damage amount"}

        previous_hull = self.hull_integrity
        self.hull_integrity = max(0.0, self.hull_integrity - amount)

        # v0.6.0: Apply subsystem damage if targeted
        subsystem_result = None
        if target_subsystem:
            subsystem_result = self.apply_subsystem_damage(
                target_subsystem, amount * 0.5, source  # 50% of damage goes to subsystem
            )
        else:
            # Random subsystem damage on hull hits (propagation)
            subsystem_result = self._propagate_damage_to_subsystems(amount, source)

        # Publish damage event
        self.event_bus.publish("ship_damaged", {
            "ship_id": self.id,
            "damage": amount,
            "hull_before": previous_hull,
            "hull_after": self.hull_integrity,
            "source": source,
            "destroyed": self.is_destroyed(),
            "target_subsystem": target_subsystem,
            "subsystem_result": subsystem_result,
        })

        if self.is_destroyed():
            logger.warning(f"Ship {self.id} destroyed! Hull integrity: {self.hull_integrity:.1f}")
            self.event_bus.publish("ship_destroyed", {
                "ship_id": self.id,
                "source": source
            })

        return {
            "ok": True,
            "damage_applied": amount,
            "hull_integrity": self.hull_integrity,
            "max_hull_integrity": self.max_hull_integrity,
            "hull_percent": (self.hull_integrity / self.max_hull_integrity * 100) if self.max_hull_integrity > 0 else 0,
            "destroyed": self.is_destroyed(),
            "subsystem_damage": subsystem_result,
        }

    def apply_subsystem_damage(self, subsystem: str, amount: float, source=None) -> dict:
        """
        Apply damage directly to a specific subsystem.

        v0.6.0: Sub-targeting support.

        Args:
            subsystem (str): Name of the subsystem to damage
            amount (float): Amount of damage to apply
            source (str, optional): ID of ship/weapon that caused damage

        Returns:
            dict: Damage result with subsystem status
        """
        if amount <= 0:
            return {"ok": False, "error": "Invalid damage amount"}

        result = self.damage_model.apply_damage(
            subsystem,
            amount,
            source=source,
            event_bus=self.event_bus,
            ship_id=self.id
        )

        return result

    def _propagate_damage_to_subsystems(self, hull_damage: float, source=None) -> dict:
        """
        Propagate hull damage to random subsystems.

        v0.6.0: Damage propagation model. Significant hull hits have a chance
        to damage internal subsystems.

        Args:
            hull_damage (float): Amount of damage to the hull
            source (str, optional): Damage source

        Returns:
            dict: Summary of subsystem damage applied
        """
        import random

        # Only propagate if damage is significant (>5% of max hull)
        if hull_damage < (self.max_hull_integrity * 0.05):
            return {"propagated": False, "reason": "damage_too_small"}

        # Probability of subsystem damage increases with damage amount
        damage_ratio = min(1.0, hull_damage / self.max_hull_integrity)
        propagation_chance = 0.3 + (damage_ratio * 0.5)  # 30-80% chance

        if random.random() > propagation_chance:
            return {"propagated": False, "reason": "chance_roll"}

        # Select a random subsystem weighted by criticality
        subsystems = list(self.damage_model.subsystems.keys())
        if not subsystems:
            return {"propagated": False, "reason": "no_subsystems"}

        # Weight by inverse of remaining health (damaged systems more vulnerable)
        weights = []
        for name in subsystems:
            sub = self.damage_model.subsystems[name]
            # Lower health = higher weight (more vulnerable)
            health_weight = 2.0 - (sub.health / sub.max_health)
            # Higher criticality = higher weight
            crit_weight = sub.criticality / 5.0
            weights.append(health_weight * crit_weight)

        total_weight = sum(weights)
        if total_weight <= 0:
            weights = [1.0] * len(subsystems)
            total_weight = len(subsystems)

        # Weighted random selection
        r = random.random() * total_weight
        cumulative = 0
        selected_subsystem = subsystems[0]
        for i, weight in enumerate(weights):
            cumulative += weight
            if r <= cumulative:
                selected_subsystem = subsystems[i]
                break

        # Apply 20-40% of hull damage to the selected subsystem
        subsystem_damage = hull_damage * (0.2 + random.random() * 0.2)
        result = self.apply_subsystem_damage(selected_subsystem, subsystem_damage, source)

        return {
            "propagated": True,
            "subsystem": selected_subsystem,
            "damage": subsystem_damage,
            "result": result,
        }

    def get_effective_factor(self, subsystem: str) -> float:
        """Get the effective performance factor for a subsystem, including cascades.

        Combines damage degradation, heat penalty, cascade effects from
        upstream subsystem failures, and crew fatigue impairment.

        Args:
            subsystem: Subsystem name

        Returns:
            float: Combined factor (0.0-1.0)
        """
        cascade_factor = self.cascade_manager.get_cascade_factor(subsystem)
        base_factor = self.damage_model.get_combined_factor(subsystem, cascade_factor)

        # Crew fatigue degrades operator-dependent subsystems
        crew_fatigue = self.systems.get("crew_fatigue")
        if crew_fatigue and hasattr(crew_fatigue, "get_performance_factor"):
            crew_factor = crew_fatigue.get_performance_factor()
            # Automated systems (reactor) less affected than manual systems
            automated_systems = {"reactor", "life_support", "radiators"}
            if subsystem in automated_systems:
                # Automated systems only mildly affected (10% of crew degradation)
                crew_factor = 1.0 - (1.0 - crew_factor) * 0.1
            base_factor *= crew_factor

        return base_factor

    def is_destroyed(self):
        """
        Check if the ship is destroyed (hull integrity <= 0).

        Returns:
            bool: True if ship is destroyed
        """
        return self.hull_integrity <= 0

    def _cmd_get_state(self, params):
        """Command handler for get_state"""
        return self.get_state()

    def _cmd_get_subsystem_health(self, params):
        subsystem = params.get("subsystem")
        if subsystem:
            return self.damage_model.get_subsystem_report(subsystem)
        return self.damage_model.get_report()

    def _cmd_repair_subsystem(self, params):
        subsystem = params.get("subsystem")
        amount = float(params.get("amount", 0))
        if not subsystem:
            return {"ok": False, "error": "Missing subsystem"}
        if amount <= 0:
            return {"ok": False, "error": "Repair amount must be positive"}
        return self.damage_model.repair_subsystem(subsystem, amount)

    def _cmd_get_position(self, params):
        """Return current ship position"""
        return dict(self.position)

    def _cmd_get_velocity(self, params):
        """Return current ship velocity"""
        return dict(self.velocity)

    def _cmd_get_orientation(self, params):
        """Return current ship orientation"""
        return dict(self.orientation)
    
    def _cmd_set_thrust(self, params):
        """Command handler for set_thrust"""
        # Check for override by helm system
        helm_system = self.systems.get("helm", None)
        if helm_system and hasattr(helm_system, "get_state"):
            helm_state = helm_system.get_state()
            if helm_state.get("manual_override", False):
                return {"error": "Cannot set thrust while helm has manual control"}
        
        # Check for override by navigation system
        nav_system = self.systems.get("navigation", None)
        if nav_system and hasattr(nav_system, "get_state"):
            nav_state = nav_system.get_state()
            if nav_state.get("autopilot_enabled", False):
                return {"error": "Cannot set thrust while autopilot is engaged"}
        
        # Update thrust
        for axis in ["x", "y", "z"]:
            if axis in params:
                try:
                    self.thrust[axis] = float(params[axis])
                except (ValueError, TypeError):
                    return {"error": f"Invalid thrust value for {axis}: {params[axis]}"}
        
        return {"status": "Thrust updated", "thrust": self.thrust}
    
    def _cmd_set_course(self, params):
        """Command handler for set_course"""
        # Pass to navigation system if available
        if "navigation" in self.systems:
            nav_system = self.systems["navigation"]
            if hasattr(nav_system, "command") and callable(nav_system.command):
                return nav_system.command("set_course", params)
        
        return {"error": "Navigation system not available"}
    
    def _cmd_rotate(self, params):
        """Command handler for rotate"""
        axis = params.get("axis", "yaw")
        if axis not in ["pitch", "yaw", "roll"]:
            return {"error": f"Invalid rotation axis: {axis}"}
        
        try:
            value = float(params.get("value", 0))
            self.orientation[axis] += value
            
            # Normalize to [-180, 180)
            while self.orientation[axis] >= 180:
                self.orientation[axis] -= 360
            while self.orientation[axis] < -180:
                self.orientation[axis] += 360
                
            return {"status": "Rotation applied", "orientation": self.orientation}
        except (ValueError, TypeError):
            return {"error": f"Invalid rotation value: {params.get('value')}"}
    
    def _cmd_get_system_state(self, params):
        """Command handler for get_system_state"""
        system_type = params.get("system")
        if not system_type:
            return {"error": "System type not specified"}
            
        if system_type in self.systems:
            system = self.systems[system_type]
            
            if hasattr(system, "get_state") and callable(system.get_state):
                return system.get_state()
            elif isinstance(system, dict):
                return copy.deepcopy(system)
            else:
                return {"status": "System found but state not available"}
        else:
            return {"error": f"System '{system_type}' not found"}

    def _cmd_request_power(self, params):
        """Request power via the power management system"""
        pm = self.systems.get("power_management")
        if not pm:
            return {"error": "Power management system not available"}
        amount = float(params.get("amount", 0))
        system = params.get("system", "")
        # Note: layer parameter is accepted but not used - request_power uses priority-based allocation
        success = pm.request_power(amount, system)
        return {"success": success, "state": pm.get_state()}

    def _cmd_reroute_power(self, params):
        """Reroute power between layers"""
        pm = self.systems.get("power_management")
        if not pm:
            return {"error": "Power management system not available"}
        amount = float(params.get("amount", 0))
        from_layer = params.get("from_layer", "primary")
        to_layer = params.get("to_layer", "secondary")
        moved = pm.reroute_power(amount, from_layer, to_layer)
        return {"moved": moved, "state": pm.get_state()}

    def _cmd_get_power_state(self, params):
        """Return power management system state"""
        pm = self.systems.get("power_management")
        if not pm:
            return {"error": "Power management system not available"}
        return pm.get_state()

    def _cmd_set_power_allocation(self, params):
        """Set power allocation ratios for the power management system."""
        pm = self.systems.get("power_management")
        if not pm:
            return {"error": "Power management system not available"}
        allocation = params.get("allocation", {})
        if not allocation:
            allocation = {
                key: params.get(key)
                for key in ("primary", "secondary", "tertiary")
                if params.get(key) is not None
            }
        if not allocation:
            return {"error": "Missing allocation values"}
        return pm.set_power_allocation(allocation)

    def _cmd_set_power_profile(self, params):
        """Apply a named power profile."""
        pm = self.systems.get("power_management")
        if not pm:
            return {"error": "Power management system not available"}
        profile = params.get("profile") or params.get("mode")
        if not profile:
            return {"error": "Missing profile parameter"}
        return pm.apply_profile(profile, ship=self)

    def _cmd_get_power_profiles(self, params):
        """Return available power profiles."""
        pm = self.systems.get("power_management")
        if not pm:
            return {"error": "Power management system not available"}
        return pm.get_profiles()

    def _cmd_set_overdrive_limits(self, params):
        """Set overdrive limits for power buses."""
        pm = self.systems.get("power_management")
        if not pm:
            return {"error": "Power management system not available"}
        limits = params.get("limits", params)
        if not limits:
            return {"error": "Missing limits"}
        return pm.set_overdrive_limits(limits)

    def enable_ai(self, behavior=None, params=None):
        """
        Enable AI control for this ship.

        Args:
            behavior (AIBehavior, optional): Initial AI behavior
            params (dict, optional): Behavior parameters

        Returns:
            bool: True if AI was enabled successfully
        """
        try:
            from hybrid.fleet.ai_controller import AIController, AIBehavior

            # Create AI controller if it doesn't exist
            if not self.ai_controller:
                self.ai_controller = AIController(self)

            # Set behavior if specified
            if behavior:
                self.ai_controller.set_behavior(behavior, params)

            self.ai_enabled = True
            logger.info(f"AI enabled for {self.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to enable AI for {self.id}: {e}")
            return False

    def disable_ai(self):
        """
        Disable AI control for this ship.

        Returns:
            bool: True if AI was disabled successfully
        """
        self.ai_enabled = False
        logger.info(f"AI disabled for {self.id}")
        return True

    def set_ai_behavior(self, behavior, params=None):
        """
        Set AI behavior (AI must be enabled first).

        Args:
            behavior (AIBehavior): Behavior to set
            params (dict, optional): Behavior parameters

        Returns:
            bool: True if behavior was set successfully
        """
        if not self.ai_controller:
            logger.warning(f"Cannot set AI behavior for {self.id}: AI not initialized")
            return False

        try:
            self.ai_controller.set_behavior(behavior, params)
            return True
        except Exception as e:
            logger.error(f"Failed to set AI behavior for {self.id}: {e}")
            return False
