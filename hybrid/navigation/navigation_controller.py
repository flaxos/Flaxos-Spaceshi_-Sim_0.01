# hybrid/navigation/navigation_controller.py
"""Navigation controller managing manual vs autopilot control."""

import logging
from typing import Optional, Dict
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)

class NavigationController:
    """Manages navigation modes and autopilot programs."""

    def __init__(self, ship):
        """Initialize navigation controller.

        Args:
            ship: Ship object this controller manages
        """
        self.ship = ship
        self.mode = "manual"  # "manual", "manual_override", "autopilot"
        self.autopilot = None  # Current autopilot program instance
        self.manual_override_timeout = 5.0  # Seconds before autopilot resumes
        self.last_manual_input = 0.0
        self.autopilot_program_name = None
        self.target_id = None

    def set_manual_input(self, sim_time: float):
        """Record manual input from pilot.

        Args:
            sim_time: Current simulation time
        """
        self.last_manual_input = sim_time

        if self.mode == "autopilot":
            logger.info(f"Ship {self.ship.id}: Manual override engaged")
            self.mode = "manual_override"

    def engage_autopilot(self, program_name: str, target_id: Optional[str] = None, params: Dict = None) -> Dict:
        """Engage autopilot with specified program.

        Args:
            program_name: Name of autopilot program
            target_id: Target contact ID (if required)
            params: Additional parameters for autopilot

        Returns:
            dict: Success or error response
        """
        if params is None:
            params = {}

        # Import autopilot factory
        from hybrid.navigation.autopilot.factory import AutopilotFactory

        # Create autopilot instance
        try:
            self.autopilot = AutopilotFactory.create(
                program_name,
                self.ship,
                target_id,
                params
            )

            self.mode = "autopilot"
            self.autopilot_program_name = program_name
            self.target_id = target_id

            logger.info(f"Ship {self.ship.id}: Autopilot engaged - {program_name}")

            return success_dict(
                f"Autopilot engaged: {program_name}",
                program=program_name,
                target=target_id,
                mode=self.mode
            )

        except Exception as e:
            logger.error(f"Failed to engage autopilot {program_name}: {e}")
            return error_dict(
                "AUTOPILOT_ERROR",
                f"Failed to engage autopilot: {e}"
            )

    def disengage_autopilot(self) -> Dict:
        """Disengage autopilot and return to manual control.

        Returns:
            dict: Success response
        """
        if self.mode != "manual":
            logger.info(f"Ship {self.ship.id}: Autopilot disengaged")

        self.mode = "manual"
        self.autopilot = None
        self.autopilot_program_name = None

        return success_dict(
            "Autopilot disengaged",
            mode=self.mode
        )

    def update(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Update navigation controller and get thrust command.

        Args:
            dt: Time delta
            sim_time: Current simulation time

        Returns:
            dict: Thrust command {thrust, heading} or None for manual
        """
        # Manual mode - no autopilot control
        if self.mode == "manual":
            return None

        # Manual override - check timeout
        if self.mode == "manual_override":
            if sim_time - self.last_manual_input > self.manual_override_timeout:
                logger.info(f"Ship {self.ship.id}: Manual override timeout, resuming autopilot")
                self.mode = "autopilot"
            else:
                return None  # Still in manual override

        # Autopilot mode - execute program
        if self.autopilot:
            try:
                command = self.autopilot.compute(dt, sim_time)
                return command
            except Exception as e:
                logger.error(f"Autopilot error on {self.ship.id}: {e}", exc_info=True)
                # Disengage on error
                self.disengage_autopilot()
                return None

        return None

    def get_state(self) -> Dict:
        """Get current navigation state.

        Returns:
            dict: Navigation state
        """
        state = {
            "mode": self.mode,
            "autopilot_enabled": self.mode in ["autopilot", "manual_override"],
            "current_program": self.autopilot_program_name,
            "target_id": self.target_id
        }

        # Add autopilot state if active
        if self.autopilot and hasattr(self.autopilot, 'get_state'):
            state["autopilot_state"] = self.autopilot.get_state()

        # Add manual override info
        if self.mode == "manual_override":
            state["override_timeout_remaining"] = max(
                0,
                self.manual_override_timeout - (self.ship.sim_time - self.last_manual_input)
            ) if hasattr(self.ship, 'sim_time') else self.manual_override_timeout

        return state

    def calculate_intercept_solution(self, target_id: Optional[str] = None, target_position: Optional[Dict] = None) -> Optional[Dict]:
        """Calculate intercept solution for manual control assistance.
        
        Navigation computer provides calculations to assist manual piloting.
        This is assistance, not blocking - manual control always works.
        
        Args:
            target_id: Target contact ID
            target_position: Target position dict {x, y, z}
            
        Returns:
            dict: Intercept solution with suggested heading, burn, time, etc.
        """
        from hybrid.navigation.relative_motion import calculate_relative_motion, calculate_intercept_time, calculate_intercept_point
        
        # Get target
        target = None
        if target_id:
            # Try to find in sensor contacts
            sensor_system = self.ship.systems.get("sensors")
            if sensor_system and hasattr(sensor_system, "get_contact"):
                target = sensor_system.get_contact(target_id)
        
        if not target and target_position:
            # Use provided position
            class TargetObj:
                def __init__(self, pos):
                    self.position = pos
                    self.velocity = {"x": 0, "y": 0, "z": 0}
            target = TargetObj(target_position)
        
        if not target:
            return None
        
        # Calculate relative motion
        rel_motion = calculate_relative_motion(self.ship, target)
        
        # Calculate intercept solution
        intercept_time = calculate_intercept_time(self.ship, target)
        intercept_point = calculate_intercept_point(self.ship, target, intercept_time) if intercept_time else None
        
        # Calculate suggested heading
        from hybrid.utils.math_utils import calculate_bearing
        suggested_heading = calculate_bearing(self.ship.position, intercept_point if intercept_point else target.position if hasattr(target, 'position') else target_position)
        
        return {
            "target_id": target_id,
            "range": rel_motion.get("range", 0),
            "range_rate": rel_motion.get("range_rate", 0),
            "closing": rel_motion.get("closing", False),
            "intercept_time": intercept_time,
            "intercept_point": intercept_point,
            "suggested_heading": suggested_heading,
            "bearing": rel_motion.get("bearing", {})
        }

    def calculate_braking_solution(self, target_velocity: Optional[Dict] = None) -> Optional[Dict]:
        """Calculate braking solution (retrograde burn).
        
        Args:
            target_velocity: Target velocity to match (None = zero velocity)
            
        Returns:
            dict: Braking solution with suggested heading, burn duration, delta_v
        """
        from hybrid.navigation.relative_motion import calculate_required_burn, vector_to_heading
        
        current_vel = self.ship.velocity
        target_vel = target_velocity or {"x": 0, "y": 0, "z": 0}
        
        # Calculate required burn
        burn_info = calculate_required_burn(self.ship, target_vel)
        
        # Calculate retrograde heading (opposite of velocity)
        vel_mag = (current_vel["x"]**2 + current_vel["y"]**2 + current_vel["z"]**2)**0.5
        if vel_mag < 0.001:
            return None  # Already stopped
        
        retrograde_vec = {
            "x": -current_vel["x"] / vel_mag,
            "y": -current_vel["y"] / vel_mag,
            "z": -current_vel["z"] / vel_mag
        }
        suggested_heading = vector_to_heading(retrograde_vec)
        
        return {
            "suggested_heading": suggested_heading,
            "delta_v": burn_info.get("delta_v", 0),
            "burn_duration": burn_info.get("duration"),
            "current_velocity": current_vel,
            "target_velocity": target_vel
        }

    def get_nav_assistance(self) -> Dict:
        """Get current navigation computer assistance data.
        
        Returns calculations and suggestions for manual control.
        This makes manual control easier when nav computer is online.
        
        Returns:
            dict: Assistance data including intercept solutions, braking solutions, etc.
        """
        assistance = {
            "nav_computer_online": self.ship.systems.get("navigation", {}).enabled if hasattr(self.ship.systems.get("navigation", {}), "enabled") else False,
            "mode": self.mode,
            "autopilot_active": self.mode == "autopilot",
            "suggestions": []
        }
        
        # If we have a target, calculate intercept solution
        if self.target_id:
            intercept = self.calculate_intercept_solution(self.target_id)
            if intercept:
                assistance["intercept_solution"] = intercept
                assistance["suggestions"].append({
                    "type": "intercept",
                    "text": f"Intercept {self.target_id} in {intercept.get('intercept_time', 0):.1f}s",
                    "heading": intercept.get("suggested_heading")
                })
        
        # Always provide braking solution
        braking = self.calculate_braking_solution()
        if braking:
            assistance["braking_solution"] = braking
            assistance["suggestions"].append({
                "type": "brake",
                "text": f"Brake: {braking.get('delta_v', 0):.1f} m/s Δv required",
                "heading": braking.get("suggested_heading"),
                "duration": braking.get("burn_duration")
            })
        
        return assistance
