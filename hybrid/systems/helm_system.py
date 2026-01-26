# hybrid/systems/helm_system.py
"""Helm system implementation for ship simulation.

Expanse-style helm control:
- Attitude commands set targets for RCS (no instant teleportation)
- Throttle commands route to propulsion (scalar main drive)
- Manual override allows direct rate control
"""

from hybrid.core.base_system import BaseSystem
from hybrid.utils.math_utils import calculate_bearing
from hybrid.navigation.relative_motion import calculate_relative_motion
import math
import logging

logger = logging.getLogger(__name__)


class HelmSystem(BaseSystem):
    """Manages ship control interface for thrust and orientation."""

    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}

        # Manual control
        self.manual_override = config.get("manual_override", False)
        self.control_mode = config.get("control_mode", "standard")  # standard, precise, rapid
        self.dampening = config.get("dampening", 0.8)

        # Integration with other systems
        self.power_draw = config.get("power_draw", 2.0)
        self.mode = config.get("mode", "autopilot")  # autopilot or manual
        
        # Manual throttle (0..1 for scalar main drive)
        self.manual_throttle = config.get("manual_throttle", 0.0)
        
        # Attitude target (for RCS)
        self.attitude_target = None
        self.angular_velocity_target = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}

        self.status = "standby"

    def tick(self, dt, ship, event_bus):
        """Update helm system state."""
        if not self.enabled:
            self.status = "offline"
            return

        # Power request
        power_system = ship.systems.get("power")
        if power_system and not power_system.request_power(self.power_draw * dt, "helm"):
            return

        if self.manual_override or self.mode == "manual":
            self.status = "manual_control"
            
            # Apply manual throttle to propulsion
            propulsion = ship.systems.get("propulsion")
            if propulsion and hasattr(propulsion, 'set_throttle'):
                propulsion.set_throttle({"thrust": self.manual_throttle})
            
            # Apply attitude/rate targets to RCS
            rcs = ship.systems.get("rcs")
            if rcs:
                if self.attitude_target is not None:
                    rcs.set_attitude_target(self.attitude_target)
                else:
                    rcs.set_angular_velocity_target(self.angular_velocity_target)
        else:
            self.status = "standby"

        # Subscribe to navigation events (idempotent)
        event_bus.subscribe("navigation_autopilot_engaged", self._handle_autopilot_engaged)
        event_bus.subscribe("navigation_autopilot_disengaged", self._handle_autopilot_disengaged)

    def command(self, action, params):
        """Process helm system commands."""
        if action == "helm_override":
            return self._cmd_helm_override(params)
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
        if action == "status":
            return self.get_state()
        if action == "power_on":
            return self.power_on()
        if action == "power_off":
            return self.power_off()
        return super().command(action, params)

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
            
            pitch = float(params.get("pitch", current.get("pitch", 0)))
            yaw = float(params.get("yaw", current.get("yaw", 0)))
            roll = float(params.get("roll", current.get("roll", 0)))
            
            # Normalize angles
            pitch = max(-90, min(90, pitch))  # Pitch limited to -90 to 90
            yaw = yaw % 360  # Yaw wraps around
            if yaw > 180:
                yaw -= 360
            roll = max(-180, min(180, roll))  # Roll limited to -180 to 180
            
            self.attitude_target = {"pitch": pitch, "yaw": yaw, "roll": roll}
            
            # Record manual input for navigation system (if nav computer is online)
            if ship:
                nav_system = ship.systems.get("navigation")
                if nav_system and hasattr(nav_system, "controller") and nav_system.controller:
                    nav_system.controller.set_manual_input(getattr(ship, "sim_time", 0.0))
                
                # Route to RCS if available
                rcs = ship.systems.get("rcs")
                if rcs:
                    result = rcs.set_attitude_target(self.attitude_target)
                    return {
                        "status": "Attitude target set (RCS will maneuver)",
                        "target": self.attitude_target,
                        "rcs_response": result
                    }
            
            return {
                "status": "Attitude target set",
                "target": self.attitude_target,
                "note": "RCS not available - target stored for later"
            }
        except (ValueError, TypeError) as e:
            logger.error(f"Error setting orientation target: {e}")
            return {"error": f"Invalid orientation parameters: {e}"}

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
                "roll": float(params.get("roll", 0.0))
            }
            
            # Clear attitude target (rate mode)
            self.attitude_target = None
            
            # Record manual input for navigation system (if nav computer is online)
            if ship:
                nav_system = ship.systems.get("navigation")
                if nav_system and hasattr(nav_system, "controller") and nav_system.controller:
                    nav_system.controller.set_manual_input(getattr(ship, "sim_time", 0.0))
                
                # Route to RCS if available
                rcs = ship.systems.get("rcs")
                if rcs:
                    result = rcs.set_angular_velocity_target(self.angular_velocity_target)
                    return {
                        "status": "Angular velocity target set",
                        "target": self.angular_velocity_target,
                        "rcs_response": result
                    }
            
            return {
                "status": "Angular velocity target set",
                "target": self.angular_velocity_target
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
        Manual controls should always work when helm is enabled.
        """
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        if not ship:
            return {"error": "Ship reference required"}

        # Accept scalar 'thrust' or 'throttle'
        throttle = params.get("thrust", params.get("throttle"))
        
        if throttle is not None:
            self.manual_throttle = max(0.0, min(1.0, float(throttle)))
            
            # Record manual input for navigation system (if nav computer is online)
            nav_system = ship.systems.get("navigation")
            if nav_system and hasattr(nav_system, "controller") and nav_system.controller:
                nav_system.controller.set_manual_input(getattr(ship, "sim_time", 0.0))
            
            # Always allow manual control - route directly to propulsion
            propulsion = ship.systems.get("propulsion")
            if propulsion and hasattr(propulsion, "set_throttle"):
                result = propulsion.set_throttle({"thrust": self.manual_throttle, "_ship": ship, "ship": ship})
                return {
                    "status": "Throttle updated",
                    "throttle": self.manual_throttle,
                    "propulsion_response": result
                }
        
        return {"status": "Throttle updated", "throttle": self.manual_throttle}

    def _cmd_set_throttle(self, params):
        """Set throttle directly (0..1)."""
        if not self.enabled:
            return {"error": "Helm system is disabled"}
        
        throttle = params.get("thrust", params.get("throttle", 0.0))
        self.manual_throttle = max(0.0, min(1.0, float(throttle)))
        
        ship = params.get("_ship") or params.get("ship")
        if ship:
            propulsion = ship.systems.get("propulsion")
            if propulsion and hasattr(propulsion, "set_throttle"):
                propulsion.set_throttle({"thrust": self.manual_throttle})
        
        return {"status": "Throttle updated", "throttle": self.manual_throttle}

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
        self.mode = "autopilot"
        logger.info("Autopilot engaged, helm switching to autopilot mode")

    def _handle_autopilot_disengaged(self, event):
        logger.info("Autopilot disengaged")

    def get_state(self):
        state = super().get_state()
        state.update({
            "status": self.status,
            "manual_override": self.manual_override,
            "control_mode": self.control_mode,
            "dampening": self.dampening,
            "mode": self.mode,
            "manual_throttle": self.manual_throttle,
            "attitude_target": self.attitude_target,
            "angular_velocity_target": self.angular_velocity_target,
        })
        return state
