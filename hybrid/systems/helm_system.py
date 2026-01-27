# hybrid/systems/helm_system.py
"""Helm system implementation for ship simulation.

Expanse-style helm control:
- Attitude commands set targets for RCS (no instant teleportation)
- Throttle commands route to propulsion (scalar main drive)
- Manual override allows direct rate control

Control Authority Model:
- NAV_AUTOPILOT: Navigation computer controls thrust/heading via autopilot
- MANUAL: Pilot has direct control via helm inputs
- QUEUE: Helm command queue is executing a sequence
- When pilot inputs occur during autopilot, switches to manual with optional timeout
"""

from hybrid.core.base_system import BaseSystem
from hybrid.utils.math_utils import calculate_bearing
from hybrid.navigation.relative_motion import calculate_relative_motion
import math
import logging

logger = logging.getLogger(__name__)


# Control authority modes
CONTROL_AUTHORITY_MANUAL = "manual"
CONTROL_AUTHORITY_AUTOPILOT = "nav_autopilot"
CONTROL_AUTHORITY_QUEUE = "queue"


class HelmSystem(BaseSystem):
    """Manages ship control interface for thrust and orientation.

    The helm system is the execution layer for ship control:
    - Navigation computes desired thrust/heading
    - Helm executes commands and tracks control authority
    - Manual inputs from pilot always take precedence
    """

    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}

        # Control authority tracking - who is currently controlling the ship
        self.control_authority = config.get("control_authority", CONTROL_AUTHORITY_MANUAL)
        self.manual_override = config.get("manual_override", False)
        self.control_mode = config.get("control_mode", "standard")  # standard, precise, rapid
        self.dampening = config.get("dampening", 0.8)

        # Manual override timeout (seconds before resuming autopilot if enabled)
        self.manual_override_timeout = config.get("manual_override_timeout", 5.0)
        self.last_manual_input_time = 0.0
        self.resume_autopilot_after_override = config.get("resume_autopilot", True)

        # Integration with other systems
        self.power_draw = config.get("power_draw", 2.0)
        self.mode = config.get("mode", "autopilot")  # autopilot or manual (legacy)

        # Manual throttle (0..1 for scalar main drive)
        self.manual_throttle = config.get("manual_throttle", 0.0)

        # Attitude target (for RCS)
        self.attitude_target = None
        self.angular_velocity_target = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}

        # Command queue (server-side helm sequencing)
        self.command_queue = []
        self.active_command = None
        self._queue_sequence = 0
        self._queue_tolerance = config.get("queue_tolerance_deg", 1.0)

        self.status = "standby"

        # Track what autopilot program is active (for display)
        self._autopilot_program = None
        self._autopilot_phase = None

    def tick(self, dt, ship, event_bus):
        """Update helm system state and control authority."""
        if not self.enabled:
            self.status = "offline"
            self.control_authority = CONTROL_AUTHORITY_MANUAL
            return

        # Power request
        power_system = ship.systems.get("power")
        if power_system and not power_system.request_power(self.power_draw * dt, "helm"):
            return

        # Get current simulation time
        sim_time = getattr(ship, "sim_time", 0.0)

        # Update control authority based on state
        queue_active = self._process_command_queue(dt, ship)

        if queue_active:
            self.control_authority = CONTROL_AUTHORITY_QUEUE
            self.status = "executing_queue"
        elif self.manual_override or self.mode == "manual":
            self.control_authority = CONTROL_AUTHORITY_MANUAL
            self.status = "manual_control"

            # Apply manual throttle to propulsion
            propulsion = ship.systems.get("propulsion")
            if propulsion and hasattr(propulsion, "set_throttle"):
                propulsion.set_throttle({"thrust": self.manual_throttle})

            # Apply attitude/rate targets to RCS
            rcs = ship.systems.get("rcs")
            if rcs:
                if self.attitude_target is not None:
                    rcs.set_attitude_target(self.attitude_target)
                else:
                    rcs.set_angular_velocity_target(self.angular_velocity_target)

            # Check if manual override should timeout and resume autopilot
            if self.manual_override and self.resume_autopilot_after_override:
                if sim_time - self.last_manual_input_time > self.manual_override_timeout:
                    self._resume_autopilot(ship)
        else:
            # In autopilot mode - navigation system controls
            self.control_authority = CONTROL_AUTHORITY_AUTOPILOT
            self.status = "autopilot"

        # Update autopilot info from navigation system
        self._update_autopilot_info(ship)

        # Subscribe to navigation events (idempotent)
        event_bus.subscribe("navigation_autopilot_engaged", self._handle_autopilot_engaged)
        event_bus.subscribe("navigation_autopilot_disengaged", self._handle_autopilot_disengaged)
        event_bus.subscribe("autopilot_phase_change", self._handle_autopilot_phase_change)

    def _update_autopilot_info(self, ship):
        """Update cached autopilot information from navigation system."""
        nav = ship.systems.get("navigation")
        if nav and hasattr(nav, "controller") and nav.controller:
            controller = nav.controller
            self._autopilot_program = controller.autopilot_program_name
            if controller.autopilot and hasattr(controller.autopilot, "phase"):
                self._autopilot_phase = controller.autopilot.phase
            elif controller.autopilot and hasattr(controller.autopilot, "get_state"):
                state = controller.autopilot.get_state()
                self._autopilot_phase = state.get("phase")
            else:
                self._autopilot_phase = None
        else:
            self._autopilot_program = None
            self._autopilot_phase = None

    def _resume_autopilot(self, ship):
        """Resume autopilot control after manual override timeout."""
        logger.info(f"Manual override timeout on {ship.id}, resuming autopilot")
        self.manual_override = False
        self.mode = "autopilot"
        self.control_authority = CONTROL_AUTHORITY_AUTOPILOT

    def _record_manual_input(self, ship, sim_time=None):
        """Record that pilot made a manual input - triggers manual override."""
        if sim_time is None:
            sim_time = getattr(ship, "sim_time", 0.0) if ship else 0.0

        self.last_manual_input_time = sim_time
        old_authority = self.control_authority

        # Switch to manual control
        if self.control_authority == CONTROL_AUTHORITY_AUTOPILOT:
            self.manual_override = True
            self.control_authority = CONTROL_AUTHORITY_MANUAL
            logger.info(f"Manual override engaged on {ship.id if ship else 'unknown'}")

        # Also notify navigation controller
        if ship:
            nav = ship.systems.get("navigation")
            if nav and hasattr(nav, "controller") and nav.controller:
                nav.controller.set_manual_input(sim_time)

    def command(self, action, params):
        """Process helm system commands."""
        if action == "helm_override":
            return self._cmd_helm_override(params)
        if action == "take_manual_control":
            return self._cmd_take_manual_control(params)
        if action == "release_to_autopilot":
            return self._cmd_release_to_autopilot(params)
        if action == "set_thrust":
            return self._cmd_set_thrust(params, params.get("_ship"))
        if action == "set_orientation":
            # Legacy - route to RCS target
            return self._cmd_set_orientation_target(params)
        if action == "set_orientation_target":
            return self._cmd_set_orientation_target(params)
        if action == "set_angular_velocity":
            return self._cmd_set_angular_velocity(params)
        if action == "rotate":
            return self._cmd_rotate(params)
        if action == "point_at":
            return self._cmd_point_at(params)
        if action == "maneuver":
            return self._cmd_maneuver(params)
        if action == "set_dampening":
            return self._cmd_set_dampening(params)
        if action == "set_mode":
            return self._cmd_set_mode(params)
        if action == "set_throttle":
            return self._cmd_set_throttle(params)
        if action == "queue_command":
            return self._cmd_queue_command(params)
        if action == "queue_commands":
            return self._cmd_queue_commands(params)
        if action == "clear_queue":
            return self._cmd_clear_queue(params)
        if action == "interrupt_queue":
            return self._cmd_interrupt_queue(params)
        if action == "queue_status":
            return self._cmd_queue_status(params)
        if action == "status":
            return self.get_state()
        if action == "power_on":
            return self.power_on()
        if action == "power_off":
            return self.power_off()
        return super().command(action, params)

    def _cmd_take_manual_control(self, params):
        """Explicitly take manual control from autopilot.

        This is the pilot saying "I've got the stick" - immediately transfers
        control authority to manual and disables autopilot resume timeout.
        """
        if not self.enabled:
            return {"error": "Helm system is disabled"}

        ship = params.get("_ship") or params.get("ship")

        # Disable autopilot resume
        self.resume_autopilot_after_override = False
        self.manual_override = True
        self.mode = "manual"
        self.control_authority = CONTROL_AUTHORITY_MANUAL

        # Disengage navigation autopilot
        if ship:
            nav = ship.systems.get("navigation")
            if nav and hasattr(nav, "controller") and nav.controller:
                nav.controller.disengage_autopilot()

        logger.info(f"Manual control taken on {ship.id if ship else 'unknown'}")

        return {
            "status": "Manual control engaged",
            "control_authority": self.control_authority,
            "autopilot_disabled": True,
        }

    def _cmd_release_to_autopilot(self, params):
        """Release manual control and allow autopilot to resume.

        This doesn't engage autopilot directly - it just allows it to take over
        if/when navigation commands set_course or autopilot.
        """
        if not self.enabled:
            return {"error": "Helm system is disabled"}

        ship = params.get("_ship") or params.get("ship")

        self.manual_override = False
        self.resume_autopilot_after_override = True
        self.mode = "autopilot"

        # Check if navigation has an active autopilot
        if ship:
            nav = ship.systems.get("navigation")
            if nav and hasattr(nav, "controller") and nav.controller:
                if nav.controller.autopilot:
                    self.control_authority = CONTROL_AUTHORITY_AUTOPILOT
                else:
                    self.control_authority = CONTROL_AUTHORITY_MANUAL
            else:
                self.control_authority = CONTROL_AUTHORITY_MANUAL
        else:
            self.control_authority = CONTROL_AUTHORITY_MANUAL

        logger.info(f"Released to autopilot on {ship.id if ship else 'unknown'}")

        return {
            "status": "Released to autopilot",
            "control_authority": self.control_authority,
        }

    def _cmd_set_orientation_target(self, params):
        """Set attitude target for RCS (ship will rotate to reach it).
        
        This is the Expanse-style realistic behavior - orientation changes
        take time as RCS thrusters fire to produce torque.
        
        Manual controls should always work when helm is enabled.
        Navigation computer can assist but doesn't block.
        
        Args:
            params: Dictionary with pitch, yaw, roll values (degrees)
            
        Returns:
            dict: Result status
        """
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        
        ship = params.get("_ship") or params.get("ship")
        
        try:
            # Get current orientation as defaults
            current = ship.orientation if ship else {"pitch": 0, "yaw": 0, "roll": 0}

            def _coerce_angle(value, fallback):
                if isinstance(value, dict):
                    if "value" in value:
                        value = value["value"]
                    else:
                        return fallback
                if value is None:
                    return fallback
                return float(value)

            heading = params.get("heading") if isinstance(params.get("heading"), dict) else None
            if not heading and isinstance(params.get("orientation"), dict):
                heading = params.get("orientation")
            if not heading:
                for key in ("pitch", "yaw", "roll"):
                    value = params.get(key)
                    if isinstance(value, dict) and any(k in value for k in ("pitch", "yaw", "roll")):
                        heading = value
                        break

            source = heading or params
            pitch = _coerce_angle(source.get("pitch"), current.get("pitch", 0))
            yaw = _coerce_angle(source.get("yaw"), current.get("yaw", 0))
            roll = _coerce_angle(source.get("roll"), current.get("roll", 0))
            
            # Normalize angles
            pitch = max(-90, min(90, pitch))  # Pitch limited to -90 to 90
            yaw = yaw % 360  # Yaw wraps around
            if yaw > 180:
                yaw -= 360
            roll = max(-180, min(180, roll))  # Roll limited to -180 to 180
            
            self.attitude_target = {"pitch": pitch, "yaw": yaw, "roll": roll}

            # Record manual input - triggers manual override if autopilot active
            if ship:
                self._record_manual_input(ship, getattr(ship, "sim_time", 0.0))

                # Route to RCS if available
                rcs = ship.systems.get("rcs")
                if rcs:
                    result = rcs.set_attitude_target(self.attitude_target)
                    return {
                        "status": "Attitude target set (RCS will maneuver)",
                        "target": self.attitude_target,
                        "control_authority": self.control_authority,
                        "rcs_response": result,
                    }

            return {
                "status": "Attitude target set",
                "target": self.attitude_target,
                "control_authority": self.control_authority,
                "note": "RCS not available - target stored for later",
            }
        except (ValueError, TypeError) as e:
            logger.error(f"Error setting orientation target: {e}")
            return {"error": f"Invalid orientation parameters: {e}"}

    def _cmd_queue_command(self, params):
        """Queue a single helm command for sequential execution."""
        command = params.get("command") or params.get("action")
        if not command:
            return {"error": "Missing command for queue"}

        if isinstance(params.get("params"), dict):
            command_params = dict(params["params"])
        else:
            command_params = {
                key: value
                for key, value in params.items()
                if key not in {"command", "action", "params", "_ship", "ship"}
            }

        normalized = self._normalize_queue_command(command, command_params)
        if "error" in normalized:
            return normalized

        entry = self._enqueue_command(normalized["command"], normalized["params"])
        return {
            "status": "Command queued",
            "queued": entry,
            "queue_depth": len(self.command_queue)
        }

    def _cmd_queue_commands(self, params):
        """Queue multiple helm commands in order."""
        commands = params.get("commands")
        if not isinstance(commands, list) or not commands:
            return {"error": "commands must be a non-empty list"}

        queued = []
        for command in commands:
            if not isinstance(command, dict):
                return {"error": "Each queued command must be an object"}
            action = command.get("command") or command.get("action")
            if not action:
                return {"error": "Queued command missing 'command' field"}
            command_params = {
                key: value
                for key, value in command.items()
                if key not in {"command", "action", "params"}
            }
            if isinstance(command.get("params"), dict):
                command_params.update(command["params"])
            normalized = self._normalize_queue_command(action, command_params)
            if "error" in normalized:
                return normalized
            queued.append(self._enqueue_command(normalized["command"], normalized["params"]))

        return {
            "status": "Commands queued",
            "queued_count": len(queued),
            "queue_depth": len(self.command_queue)
        }

    def _cmd_clear_queue(self, params):
        """Clear pending queue commands."""
        cleared = len(self.command_queue)
        self.command_queue.clear()
        return {"status": "Queue cleared", "cleared": cleared}

    def _cmd_interrupt_queue(self, params):
        """Interrupt current command and clear queue."""
        cleared = len(self.command_queue)
        self.command_queue.clear()
        active = self.active_command
        self.active_command = None
        ship = params.get("_ship") or params.get("ship")
        self._stop_active_command(active, ship)
        return {
            "status": "Queue interrupted",
            "cleared": cleared,
            "active_command": self._format_queue_entry(active)
        }

    def _cmd_queue_status(self, params):
        """Return queue status snapshot."""
        return {
            "status": "Queue status",
            "queue": self.get_queue_state()
        }

    def _cmd_set_angular_velocity(self, params):
        """Set angular velocity target (rate command for RCS).
        
        Manual controls should always work when helm is enabled.
        
        Args:
            params: Dictionary with pitch, yaw, roll rates (degrees/second)
            
        Returns:
            dict: Result status
        """
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        
        ship = params.get("_ship") or params.get("ship")
        
        try:
            self.angular_velocity_target = {
                "pitch": float(params.get("pitch", 0.0)),
                "yaw": float(params.get("yaw", 0.0)),
                "roll": float(params.get("roll", 0.0)),
            }

            # Clear attitude target (rate mode)
            self.attitude_target = None

            # Record manual input - triggers manual override if autopilot active
            if ship:
                self._record_manual_input(ship, getattr(ship, "sim_time", 0.0))

                # Route to RCS if available
                rcs = ship.systems.get("rcs")
                if rcs:
                    result = rcs.set_angular_velocity_target(self.angular_velocity_target)
                    return {
                        "status": "Angular velocity target set",
                        "target": self.angular_velocity_target,
                        "control_authority": self.control_authority,
                        "rcs_response": result,
                    }

            return {
                "status": "Angular velocity target set",
                "target": self.angular_velocity_target,
                "control_authority": self.control_authority,
            }
        except (ValueError, TypeError) as e:
            logger.error(f"Error setting angular velocity: {e}")
            return {"error": f"Invalid angular velocity parameters: {e}"}

    def _cmd_rotate(self, params):
        """Apply rotation command (adds to current attitude target).
        
        Args:
            params: Dictionary with axis (pitch/yaw/roll) and amount (degrees)
            
        Returns:
            dict: Result status
        """
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        
        ship = params.get("_ship") or params.get("ship")
        axis = params.get("axis", "yaw")
        amount = float(params.get("amount", 0.0))
        
        if axis not in ["pitch", "yaw", "roll"]:
            return {"error": f"Invalid axis: {axis}"}
        
        # Get current orientation
        current = ship.orientation if ship else {"pitch": 0, "yaw": 0, "roll": 0}
        
        # Compute new target
        new_target = dict(current)
        new_target[axis] = current.get(axis, 0) + amount
        
        # Normalize
        if axis == "yaw":
            while new_target[axis] >= 180:
                new_target[axis] -= 360
            while new_target[axis] < -180:
                new_target[axis] += 360
        elif axis == "pitch":
            new_target[axis] = max(-90, min(90, new_target[axis]))
        else:  # roll
            new_target[axis] = max(-180, min(180, new_target[axis]))
        
        self.attitude_target = new_target
        
        # Route to RCS
        if ship:
            rcs = ship.systems.get("rcs")
            if rcs:
                rcs.set_attitude_target(self.attitude_target)
        
        return {
            "status": f"Rotate {amount}° on {axis} commanded",
            "target": self.attitude_target
        }

    def _cmd_point_at(self, params):
        """Point ship at a target contact or position.
        
        Uses RCS to rotate ship to face the target. This is the Expanse-style
        "point at target" command - rotation only, no translation.
        
        Args:
            params: Dictionary with either:
                - 'target': Contact ID or ship ID to point at
                - 'position': Dict {x, y, z} absolute position to point at
                - 'contact_id': Alternative to 'target' for contact ID
                
        Returns:
            dict: Result status with calculated bearing
        """
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        
        ship = params.get("_ship") or params.get("ship")
        if not ship:
            return {"error": "Ship reference required"}
        
        # Get target position
        target_pos = None
        target_id = None
        
        # Check for position parameter (absolute coordinates)
        if "position" in params:
            pos = params["position"]
            if isinstance(pos, dict):
                target_pos = pos
            elif isinstance(pos, (list, tuple)) and len(pos) >= 3:
                target_pos = {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2])}
            else:
                return {"error": "Invalid position format. Expected {x, y, z} or [x, y, z]"}
        
        # Check for target/contact_id parameter (look up in all_ships or contacts)
        elif "target" in params or "contact_id" in params:
            target_id = params.get("target") or params.get("contact_id")
            all_ships = params.get("all_ships", {})
            
            # Try to find target in ships
            if target_id in all_ships:
                target_ship = all_ships[target_id]
                if hasattr(target_ship, "position"):
                    target_pos = target_ship.position
                elif isinstance(target_ship, dict) and "position" in target_ship:
                    target_pos = target_ship["position"]
            
            # If not found, try to get from sensor contacts (would need sensor system)
            if target_pos is None:
                sensor_system = ship.systems.get("sensors")
                if sensor_system and hasattr(sensor_system, "get_contact"):
                    contact = sensor_system.get_contact(target_id)
                    if contact:
                        if hasattr(contact, "position"):
                            target_pos = contact.position
                        elif isinstance(contact, dict) and "position" in contact:
                            target_pos = contact["position"]
        
        if target_pos is None:
            return {"error": f"Target '{target_id}' not found or position not provided"}
        
        # Calculate bearing to target
        try:
            bearing = calculate_bearing(ship.position, target_pos, ship.orientation)
            
            # Set attitude target (RCS will rotate ship to this heading)
            self.attitude_target = {
                "pitch": bearing.get("pitch", 0),
                "yaw": bearing.get("yaw", 0),
                "roll": ship.orientation.get("roll", 0)  # Keep current roll
            }
            
            # Route to RCS
            rcs = ship.systems.get("rcs")
            if rcs:
                rcs.set_attitude_target(self.attitude_target)
            
            return {
                "status": f"Pointing at target" + (f" '{target_id}'" if target_id else ""),
                "target": self.attitude_target,
                "bearing": bearing,
                "target_position": target_pos
            }
        except Exception as e:
            logger.error(f"Error calculating bearing to target: {e}")
            return {"error": f"Failed to calculate bearing: {e}"}

    def _cmd_maneuver(self, params):
        """Execute pre-programmed maneuver.
        
        Supported maneuvers:
        - flip_burn: Rotate 180° and burn (deceleration maneuver)
        - retrograde: Point opposite to velocity and burn
        - prograde: Point along velocity and burn
        
        Args:
            params: Dictionary with:
                - 'type': Maneuver type ('flip_burn', 'retrograde', 'prograde')
                - 'g': Optional G-force for burn (default: current throttle)
                - 'duration': Optional duration in seconds (None = until stopped)
                
        Returns:
            dict: Result status
        """
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        
        ship = params.get("_ship") or params.get("ship")
        if not ship:
            return {"error": "Ship reference required"}
        
        maneuver_type = params.get("type")
        if not maneuver_type:
            return {"error": "Missing maneuver type"}
        
        maneuver_type = maneuver_type.lower()
        
        if maneuver_type == "flip_burn":
            # Flip-and-burn: rotate 180° then burn
            current = ship.orientation
            new_target = {
                "pitch": current.get("pitch", 0),
                "yaw": (current.get("yaw", 0) + 180) % 360,
                "roll": current.get("roll", 0)
            }
            # Normalize yaw to [-180, 180]
            if new_target["yaw"] > 180:
                new_target["yaw"] -= 360
            
            self.attitude_target = new_target
            
            # Route to RCS
            rcs = ship.systems.get("rcs")
            if rcs:
                rcs.set_attitude_target(self.attitude_target)
            
            return {
                "status": "Flip-and-burn initiated (rotating 180°)",
                "target": self.attitude_target,
                "note": "Set thrust after rotation completes"
            }
        
        elif maneuver_type == "retrograde" or maneuver_type == "brake":
            # Retrograde burn: point opposite to velocity vector
            # Use nav computer if available for better calculations
            nav_system = ship.systems.get("navigation")
            braking_solution = None
            
            if nav_system and hasattr(nav_system, "controller") and nav_system.controller:
                braking_solution = nav_system.controller.calculate_braking_solution()
            
            if braking_solution:
                # Use nav computer's calculation
                retrograde_heading = braking_solution.get("suggested_heading")
                delta_v = braking_solution.get("delta_v", 0)
                burn_duration = braking_solution.get("burn_duration")
            else:
                # Fallback: manual calculation
                vel_mag = math.sqrt(
                    ship.velocity["x"]**2 + 
                    ship.velocity["y"]**2 + 
                    ship.velocity["z"]**2
                )
                
                if vel_mag < 0.001:
                    return {"error": "Ship has no velocity - cannot determine retrograde"}
                
                # Calculate retrograde direction (opposite of velocity)
                retrograde_vec = {
                    "x": -ship.velocity["x"] / vel_mag,
                    "y": -ship.velocity["y"] / vel_mag,
                    "z": -ship.velocity["z"] / vel_mag
                }
                
                # Convert to heading
                from hybrid.navigation.relative_motion import vector_to_heading
                retrograde_heading = vector_to_heading(retrograde_vec)
                delta_v = vel_mag
                burn_duration = None
            
            self.attitude_target = {
                "pitch": retrograde_heading.get("pitch", 0),
                "yaw": retrograde_heading.get("yaw", 0),
                "roll": ship.orientation.get("roll", 0)
            }
            
            # Route to RCS
            rcs = ship.systems.get("rcs")
            if rcs:
                rcs.set_attitude_target(self.attitude_target)
            
            # Optionally set thrust if G-force specified
            g_force = params.get("g")
            if g_force is not None:
                propulsion = ship.systems.get("propulsion")
                if propulsion:
                    propulsion.set_throttle({"g": float(g_force), "_ship": ship, "ship": ship})
            
            return {
                "status": "Retrograde burn initiated",
                "target": self.attitude_target,
                "thrust_g": g_force,
                "delta_v_required": delta_v,
                "estimated_duration": burn_duration,
                "nav_assisted": braking_solution is not None
            }
        
        elif maneuver_type == "prograde":
            # Prograde burn: point along velocity vector
            vel_mag = math.sqrt(
                ship.velocity["x"]**2 + 
                ship.velocity["y"]**2 + 
                ship.velocity["z"]**2
            )
            
            if vel_mag < 0.001:
                return {"error": "Ship has no velocity - cannot determine prograde"}
            
            # Calculate prograde direction (same as velocity)
            prograde_vec = {
                "x": ship.velocity["x"] / vel_mag,
                "y": ship.velocity["y"] / vel_mag,
                "z": ship.velocity["z"] / vel_mag
            }
            
            # Convert to heading
            from hybrid.navigation.relative_motion import vector_to_heading
            prograde_heading = vector_to_heading(prograde_vec)
            
            self.attitude_target = {
                "pitch": prograde_heading.get("pitch", 0),
                "yaw": prograde_heading.get("yaw", 0),
                "roll": ship.orientation.get("roll", 0)
            }
            
            # Route to RCS
            rcs = ship.systems.get("rcs")
            if rcs:
                rcs.set_attitude_target(self.attitude_target)
            
            # Optionally set thrust if G-force specified
            g_force = params.get("g")
            if g_force is not None:
                propulsion = ship.systems.get("propulsion")
                if propulsion:
                    propulsion.set_throttle({"g": float(g_force), "_ship": ship, "ship": ship})
            
            return {
                "status": "Prograde burn initiated",
                "target": self.attitude_target,
                "thrust_g": g_force
            }
        
        elif maneuver_type == "intercept":
            # Intercept maneuver: use nav computer to calculate solution
            target_id = params.get("target")
            nav_system = ship.systems.get("navigation")
            
            if not target_id:
                return {"error": "Intercept maneuver requires target ID"}
            
            if nav_system and hasattr(nav_system, "controller") and nav_system.controller:
                intercept_solution = nav_system.controller.calculate_intercept_solution(target_id)
                if intercept_solution:
                    suggested_heading = intercept_solution.get("suggested_heading", {})
                    self.attitude_target = {
                        "pitch": suggested_heading.get("pitch", ship.orientation.get("pitch", 0)),
                        "yaw": suggested_heading.get("yaw", ship.orientation.get("yaw", 0)),
                        "roll": ship.orientation.get("roll", 0)
                    }
                    
                    # Route to RCS
                    rcs = ship.systems.get("rcs")
                    if rcs:
                        rcs.set_attitude_target(self.attitude_target)
                    
                    # Optionally set thrust if G-force specified
                    g_force = params.get("g")
                    if g_force is not None:
                        propulsion = ship.systems.get("propulsion")
                        if propulsion:
                            propulsion.set_throttle({"g": float(g_force), "_ship": ship, "ship": ship})
                    
                    return {
                        "status": f"Intercept maneuver initiated (target: {target_id})",
                        "target": self.attitude_target,
                        "thrust_g": g_force,
                        "intercept_time": intercept_solution.get("intercept_time"),
                        "range": intercept_solution.get("range"),
                        "nav_assisted": True
                    }
            
            # Fallback: use point_at
            return self._cmd_point_at({"target": target_id, "_ship": ship, "ship": ship})
        
        else:
            return {"error": f"Unknown maneuver type: {maneuver_type}"}

    def _cmd_helm_override(self, params):
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        if "enabled" not in params:
            return {"error": "Missing 'enabled' parameter"}
        try:
            self.manual_override = bool(params["enabled"])
            ship = params.get("_ship")
            if self.manual_override and ship and "navigation" in ship.systems:
                nav_system = ship.systems["navigation"]
                if hasattr(nav_system, "command") and callable(nav_system.command):
                    nav_system.command("autopilot", {"enabled": False})
            return {"status": f"Manual helm control {'enabled' if self.manual_override else 'disabled'}"}
        except (ValueError, TypeError):
            return {"error": f"Invalid value for 'enabled': {params['enabled']}"}

    def _cmd_set_thrust(self, params, ship):
        """Set thrust - routes to propulsion with scalar throttle.

        NOTE: This handler is for helm-specific set_thrust calls.
        Direct set_thrust commands route to propulsion system.
        Manual controls ALWAYS work when helm is enabled - pilot authority is paramount.
        """
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        if not ship:
            return {"error": "Ship reference required"}

        # Accept scalar 'thrust' or 'throttle'
        throttle = params.get("thrust", params.get("throttle"))

        if throttle is not None:
            self.manual_throttle = max(0.0, min(1.0, float(throttle)))

            # Record manual input - this triggers manual override if autopilot is active
            self._record_manual_input(ship, getattr(ship, "sim_time", 0.0))

            # Always allow manual control - route directly to propulsion
            propulsion = ship.systems.get("propulsion")
            if propulsion and hasattr(propulsion, "set_throttle"):
                result = propulsion.set_throttle({"thrust": self.manual_throttle, "_ship": ship, "ship": ship})
                return {
                    "status": "Throttle updated",
                    "throttle": self.manual_throttle,
                    "control_authority": self.control_authority,
                    "propulsion_response": result,
                }

        return {
            "status": "Throttle updated",
            "throttle": self.manual_throttle,
            "control_authority": self.control_authority,
        }

    def _cmd_set_throttle(self, params):
        """Set throttle directly (0..1)."""
        if not self.enabled:
            return {"error": "Helm system is disabled"}

        throttle = params.get("thrust", params.get("throttle", 0.0))
        self.manual_throttle = max(0.0, min(1.0, float(throttle)))

        ship = params.get("_ship") or params.get("ship")
        if ship:
            # Record manual input - triggers manual override if autopilot active
            self._record_manual_input(ship, getattr(ship, "sim_time", 0.0))

            propulsion = ship.systems.get("propulsion")
            if propulsion and hasattr(propulsion, "set_throttle"):
                propulsion.set_throttle({"thrust": self.manual_throttle})

        return {
            "status": "Throttle updated",
            "throttle": self.manual_throttle,
            "control_authority": self.control_authority,
        }

    def _cmd_set_dampening(self, params):
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        if "value" not in params:
            return {"error": "Missing 'value' parameter"}
        try:
            value = float(params["value"])
            if 0 <= value <= 1:
                self.dampening = value
                return {"status": "Dampening set", "value": self.dampening}
            return {"error": "Dampening value must be between 0 and 1"}
        except (ValueError, TypeError):
            return {"error": f"Invalid dampening value: {params['value']}"}

    def _cmd_set_mode(self, params):
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        mode = params.get("mode")
        if mode in ["standard", "precise", "rapid"]:
            self.control_mode = mode
            return {"status": "Control mode set", "mode": self.control_mode}
        return {"error": f"Invalid mode: {mode}. Must be 'standard', 'precise', or 'rapid'"}

    def set_mode(self, params):
        if "enabled" in params:
            manual_enabled = bool(params["enabled"])
            self.mode = "manual" if manual_enabled else "autopilot"
        elif "mode" in params and params["mode"] in ["manual", "autopilot"]:
            self.mode = params["mode"]
        else:
            return {"error": "Invalid or missing mode"}
        return {"status": f"Helm mode set to {self.mode}", "mode": self.mode}

    def _handle_autopilot_engaged(self, event):
        """Handle navigation autopilot engagement."""
        self.mode = "autopilot"
        self.manual_override = False
        self.control_authority = CONTROL_AUTHORITY_AUTOPILOT
        self._autopilot_program = event.get("program")
        logger.info(f"Autopilot engaged: {self._autopilot_program}, helm deferring to nav")

    def _handle_autopilot_disengaged(self, event):
        """Handle navigation autopilot disengagement."""
        self.control_authority = CONTROL_AUTHORITY_MANUAL
        self._autopilot_program = None
        self._autopilot_phase = None
        logger.info("Autopilot disengaged, helm taking manual control")

    def _handle_autopilot_phase_change(self, event):
        """Handle autopilot phase changes for status display."""
        self._autopilot_phase = event.get("phase")
        logger.debug(f"Autopilot phase changed to: {self._autopilot_phase}")

    def _normalize_queue_command(self, command, params):
        command = str(command).lower()
        params = dict(params or {})

        if command == "rotate":
            axis = params.get("axis", "yaw")
            amount = params.get("amount")
            if amount is None:
                return {"error": "Rotate command requires 'amount'"}
            if axis not in ["pitch", "yaw", "roll"]:
                return {"error": f"Invalid axis: {axis}"}
            return {
                "command": "rotate",
                "params": {"axis": axis, "amount": float(amount)}
            }

        if command == "wait":
            duration = params.get("duration", params.get("seconds"))
            if duration is None:
                return {"error": "Wait command requires 'duration'"}
            duration = float(duration)
            if duration < 0:
                return {"error": "Wait duration must be non-negative"}
            return {
                "command": "wait",
                "params": {"duration": duration}
            }

        if command in ["thrust", "set_thrust", "set_throttle"]:
            duration = params.get("duration", params.get("seconds"))
            if duration is None:
                return {"error": "Thrust command requires 'duration'"}
            duration = float(duration)
            if duration < 0:
                return {"error": "Thrust duration must be non-negative"}
            if "g" in params:
                g_force = float(params["g"])
                return {
                    "command": "thrust",
                    "params": {"g": g_force, "duration": duration}
                }
            throttle = params.get("thrust", params.get("throttle"))
            if throttle is None:
                return {"error": "Thrust command requires 'thrust' or 'g'"}
            return {
                "command": "thrust",
                "params": {"thrust": float(throttle), "duration": duration}
            }

        return {"error": f"Unsupported queued command: {command}"}

    def _enqueue_command(self, command, params):
        self._queue_sequence += 1
        entry = {
            "id": self._queue_sequence,
            "command": command,
            "params": params,
            "status": "queued",
            "elapsed": 0.0
        }
        self.command_queue.append(entry)
        return self._format_queue_entry(entry)

    def _process_command_queue(self, dt, ship):
        if self.manual_override or self.mode == "manual":
            return False

        if self.active_command is None and self.command_queue:
            self.active_command = self.command_queue.pop(0)
            self.active_command["status"] = "active"
            self.active_command["elapsed"] = 0.0
            self._start_command(self.active_command, ship)

        if not self.active_command:
            return False

        self.active_command["elapsed"] += dt
        if self._update_active_command(self.active_command, dt, ship):
            self.active_command["status"] = "complete"
            self._complete_command(self.active_command, ship)
            self.active_command = None
        return True

    def _start_command(self, command, ship):
        action = command["command"]
        params = command.get("params", {})

        if action == "rotate":
            current = ship.orientation if ship else {"pitch": 0, "yaw": 0, "roll": 0}
            axis = params["axis"]
            amount = params["amount"]
            target = dict(current)
            target[axis] = current.get(axis, 0) + amount
            target = self._normalize_attitude_target(target)
            command["target"] = target
            self.attitude_target = target
            if ship:
                rcs = ship.systems.get("rcs")
                if rcs:
                    rcs.set_attitude_target(target)

        elif action == "thrust":
            self._apply_thrust_command(command, ship)

    def _update_active_command(self, command, dt, ship):
        action = command["command"]
        params = command.get("params", {})

        if action == "rotate":
            target = command.get("target")
            if not ship or not target:
                return True
            return self._attitude_within_tolerance(ship.orientation, target)

        if action == "wait":
            duration = params.get("duration", 0.0)
            return command.get("elapsed", 0.0) >= duration

        if action == "thrust":
            self._apply_thrust_command(command, ship)
            duration = params.get("duration", 0.0)
            return command.get("elapsed", 0.0) >= duration

        return True

    def _complete_command(self, command, ship):
        if command["command"] == "thrust":
            propulsion = ship.systems.get("propulsion") if ship else None
            if propulsion:
                propulsion.set_throttle({"thrust": 0.0, "_ship": ship, "ship": ship})
            self.manual_throttle = 0.0

    def _stop_active_command(self, command, ship):
        if not command:
            return
        if command.get("command") == "thrust":
            propulsion = ship.systems.get("propulsion") if ship else None
            if propulsion:
                propulsion.set_throttle({"thrust": 0.0, "_ship": ship, "ship": ship})
            self.manual_throttle = 0.0

    def _apply_thrust_command(self, command, ship):
        if not ship:
            return
        propulsion = ship.systems.get("propulsion")
        if not propulsion:
            return
        params = command.get("params", {})
        if "g" in params:
            result = propulsion.set_throttle({"g": params["g"], "_ship": ship, "ship": ship})
            command["throttle_result"] = result
        else:
            throttle = max(0.0, min(1.0, float(params.get("thrust", 0.0))))
            self.manual_throttle = throttle
            result = propulsion.set_throttle({"thrust": throttle, "_ship": ship, "ship": ship})
            command["throttle_result"] = result

    def _normalize_attitude_target(self, target):
        pitch = max(-90, min(90, target.get("pitch", 0)))
        yaw = target.get("yaw", 0) % 360
        if yaw > 180:
            yaw -= 360
        roll = max(-180, min(180, target.get("roll", 0)))
        return {"pitch": pitch, "yaw": yaw, "roll": roll}

    def _attitude_within_tolerance(self, current, target):
        def _angle_delta(a, b):
            delta = (a - b + 180) % 360 - 180
            return abs(delta)

        pitch_error = abs(current.get("pitch", 0) - target.get("pitch", 0))
        yaw_error = _angle_delta(current.get("yaw", 0), target.get("yaw", 0))
        roll_error = _angle_delta(current.get("roll", 0), target.get("roll", 0))
        tol = self._queue_tolerance
        return pitch_error <= tol and yaw_error <= tol and roll_error <= tol

    def _format_queue_entry(self, entry):
        if not entry:
            return None
        return {
            "id": entry.get("id"),
            "command": entry.get("command"),
            "params": entry.get("params"),
            "status": entry.get("status"),
            "elapsed": entry.get("elapsed"),
            "target": entry.get("target")
        }

    def get_queue_state(self):
        return {
            "active": self._format_queue_entry(self.active_command),
            "pending": [self._format_queue_entry(entry) for entry in self.command_queue]
        }

    def get_state(self):
        state = super().get_state()
        state.update({
            "status": self.status,
            # Control authority - who is controlling the ship
            "control_authority": self.control_authority,
            "manual_override": self.manual_override,
            "control_mode": self.control_mode,
            "dampening": self.dampening,
            "mode": self.mode,
            "manual_throttle": self.manual_throttle,
            "attitude_target": self.attitude_target,
            "angular_velocity_target": self.angular_velocity_target,
            "command_queue": self.get_queue_state(),
            # Autopilot info (cached from navigation)
            "autopilot_program": self._autopilot_program,
            "autopilot_phase": self._autopilot_phase,
        })
        return state
