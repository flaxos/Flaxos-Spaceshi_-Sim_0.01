# hybrid/navigation/autopilot/formation.py
"""Formation autopilot for fleet coordination."""

import logging
from typing import Dict, Optional
import numpy as np
from hybrid.navigation.autopilot.base import BaseAutopilot
from hybrid.utils.math_utils import magnitude, subtract_vectors
from hybrid.navigation.relative_motion import vector_to_heading

logger = logging.getLogger(__name__)


class FormationAutopilot(BaseAutopilot):
    """
    Autopilot to maintain position in fleet formation.

    Continuously tracks flagship and maintains relative position
    according to formation parameters.
    """

    def __init__(self, ship, target_id: Optional[str] = None, params: Dict = None):
        """Initialize formation autopilot.

        Args:
            ship: Ship under control
            target_id: Flagship ID to follow
            params: Additional parameters:
                - formation_position: Relative position [x, y, z] in meters
                - tolerance: Position hold tolerance (m), default 50.0
                - max_thrust: Maximum thrust to use (0-1), default 0.8
                - match_velocity: Whether to match flagship velocity, default True
                - aggressive: Use more aggressive station-keeping, default False
        """
        super().__init__(ship, target_id, params)

        # Formation parameters
        self.flagship_id = target_id
        self.relative_position = np.array(params.get("formation_position", [0, 0, 0]))
        self.tolerance = params.get("tolerance", 50.0)
        self.max_thrust = params.get("max_thrust", 0.8)
        self.match_velocity = params.get("match_velocity", True)
        self.aggressive = params.get("aggressive", False)

        # Control parameters
        self.position_gain = 0.02 if not self.aggressive else 0.05
        self.velocity_gain = 0.1 if not self.aggressive else 0.2
        self.damping = 0.95

        # State tracking
        self.target_position = None
        self.target_velocity = None
        self.last_error = 0.0

        self.status = "seeking"
        logger.info(f"Formation autopilot engaged: Following {flagship_id}, offset {self.relative_position}")

    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute thrust to maintain formation position.

        Args:
            dt: Time delta
            sim_time: Current simulation time

        Returns:
            dict: Thrust command or None
        """
        # Get flagship
        flagship = self._get_flagship()
        if not flagship:
            self.status = "no_flagship"
            self.error_message = f"Flagship {self.flagship_id} not found"
            logger.warning(f"Formation: Flagship {self.flagship_id} not found")
            return None

        # Calculate target position (flagship position + relative offset)
        flagship_pos = np.array([flagship.x, flagship.y, flagship.z])
        self.target_position = flagship_pos + self.relative_position

        # Calculate current position error
        current_pos = np.array([self.ship.x, self.ship.y, self.ship.z])
        position_error = self.target_position - current_pos
        error_magnitude = np.linalg.norm(position_error)

        # Get flagship velocity for matching
        flagship_vel = np.array([flagship.vx, flagship.vy, flagship.vz])
        self.target_velocity = flagship_vel

        # Calculate current velocity error (if matching velocity)
        current_vel = np.array([self.ship.vx, self.ship.vy, self.ship.vz])
        velocity_error = flagship_vel - current_vel
        velocity_error_magnitude = np.linalg.norm(velocity_error)

        # Update status based on error
        if error_magnitude < self.tolerance and velocity_error_magnitude < 1.0:
            self.status = "in_formation"
        elif error_magnitude < self.tolerance * 2:
            self.status = "adjusting"
        else:
            self.status = "seeking"

        # Calculate desired acceleration using PD control
        # P term: proportional to position error
        p_term = position_error * self.position_gain

        # D term: velocity error (damping)
        if self.match_velocity:
            d_term = velocity_error * self.velocity_gain
        else:
            # Just damp our own velocity when close
            if error_magnitude < self.tolerance * 2:
                d_term = -current_vel * 0.1
            else:
                d_term = np.array([0.0, 0.0, 0.0])

        # Combine terms
        desired_acceleration = p_term + d_term

        # Convert acceleration to thrust vector
        accel_magnitude = np.linalg.norm(desired_acceleration)

        if accel_magnitude < 0.01:
            # Already in position and velocity matched
            logger.debug(f"Formation: In position (error={error_magnitude:.1f}m)")
            return {
                "thrust": 0.0,
                "heading": self.ship.orientation
            }

        # Normalize to get direction
        accel_direction = desired_acceleration / accel_magnitude

        # Calculate required thrust
        # thrust = desired_acceleration / max_acceleration
        propulsion = self.ship.systems.get("propulsion")
        if propulsion and hasattr(propulsion, "max_acceleration"):
            max_accel = propulsion.max_acceleration
        else:
            max_accel = 10.0  # Default 10 m/s²

        thrust = min(accel_magnitude / max_accel, self.max_thrust)

        # Convert acceleration direction to heading
        heading_vector = {
            "x": accel_direction[0],
            "y": accel_direction[1],
            "z": accel_direction[2]
        }
        desired_heading = vector_to_heading(heading_vector)

        # Log detailed info periodically
        if int(sim_time) % 10 == 0:  # Every 10 seconds
            logger.debug(
                f"Formation: pos_err={error_magnitude:.1f}m, "
                f"vel_err={velocity_error_magnitude:.1f}m/s, "
                f"thrust={thrust:.2f}, status={self.status}"
            )

        self.last_error = error_magnitude

        return {
            "thrust": self._clamp_thrust(thrust),
            "heading": desired_heading
        }

    def update_formation_position(self, new_position: np.ndarray):
        """
        Update the relative formation position.

        Args:
            new_position: New relative position [x, y, z]
        """
        self.relative_position = new_position
        logger.info(f"Formation position updated to {new_position}")

    def _get_flagship(self):
        """Get flagship ship object from simulator."""
        # Try to get from ship's simulator reference
        if hasattr(self.ship, 'simulator') and self.ship.simulator:
            simulator = self.ship.simulator
            if self.flagship_id in simulator.ships:
                return simulator.ships[self.flagship_id]

        # Try to get from sensors as fallback
        sensors = self.ship.systems.get("sensors")
        if sensors and hasattr(sensors, "get_contact"):
            contact = sensors.get_contact(self.flagship_id)
            if contact:
                # Create a mock object with position/velocity
                class FlagshipContact:
                    def __init__(self, contact_data):
                        pos = contact_data.get("position", {})
                        vel = contact_data.get("velocity", {})
                        self.x = pos.get("x", 0)
                        self.y = pos.get("y", 0)
                        self.z = pos.get("z", 0)
                        self.vx = vel.get("x", 0)
                        self.vy = vel.get("y", 0)
                        self.vz = vel.get("z", 0)

                return FlagshipContact(contact)

        return None

    def get_state(self) -> Dict:
        """Get formation autopilot state.

        Returns:
            dict: State with formation info
        """
        state = super().get_state()
        state["flagship_id"] = self.flagship_id
        state["formation_position"] = self.relative_position.tolist()
        state["tolerance"] = self.tolerance

        if self.target_position is not None:
            current_pos = np.array([self.ship.x, self.ship.y, self.ship.z])
            position_error = self.target_position - current_pos
            state["position_error"] = float(np.linalg.norm(position_error))
        else:
            state["position_error"] = None

        if self.target_velocity is not None and self.match_velocity:
            current_vel = np.array([self.ship.vx, self.ship.vy, self.ship.vz])
            velocity_error = self.target_velocity - current_vel
            state["velocity_error"] = float(np.linalg.norm(velocity_error))
        else:
            state["velocity_error"] = None

        return state


class EchelonFormationAutopilot(FormationAutopilot):
    """
    Specialized formation autopilot for echelon formations.

    Provides additional awareness of adjacent ships to maintain proper spacing.
    """

    def __init__(self, ship, target_id: Optional[str] = None, params: Dict = None):
        """Initialize echelon formation autopilot.

        Args:
            ship: Ship under control
            target_id: Flagship ID to follow
            params: Formation parameters plus:
                - adjacent_ships: List of adjacent ship IDs
                - min_separation: Minimum distance to adjacent ships (m), default 500.0
        """
        super().__init__(ship, target_id, params)

        self.adjacent_ships = params.get("adjacent_ships", [])
        self.min_separation = params.get("min_separation", 500.0)

    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute thrust with collision avoidance for adjacent ships."""
        # Get base formation command
        base_command = super().compute(dt, sim_time)

        if not base_command:
            return None

        # Check for nearby ships and adjust if needed
        avoidance_vector = self._compute_collision_avoidance()

        if np.linalg.norm(avoidance_vector) > 0.1:
            # Add avoidance to base command
            current_heading_dict = base_command["heading"]
            current_heading = np.array([
                current_heading_dict["x"],
                current_heading_dict["y"],
                current_heading_dict["z"]
            ])

            # Blend avoidance with desired heading (weighted)
            blended = current_heading * 0.7 + avoidance_vector * 0.3
            blended = blended / np.linalg.norm(blended)

            base_command["heading"] = {
                "x": blended[0],
                "y": blended[1],
                "z": blended[2]
            }

            logger.debug(f"Formation: Collision avoidance active")

        return base_command

    def _compute_collision_avoidance(self) -> np.ndarray:
        """Compute avoidance vector for nearby ships."""
        avoidance = np.array([0.0, 0.0, 0.0])

        current_pos = np.array([self.ship.x, self.ship.y, self.ship.z])

        for ship_id in self.adjacent_ships:
            # Get adjacent ship
            if hasattr(self.ship, 'simulator') and self.ship.simulator:
                adjacent = self.ship.simulator.ships.get(ship_id)
                if adjacent:
                    adjacent_pos = np.array([adjacent.x, adjacent.y, adjacent.z])

                    # Calculate separation
                    separation = current_pos - adjacent_pos
                    distance = np.linalg.norm(separation)

                    # If too close, push away
                    if distance < self.min_separation and distance > 0:
                        # Repulsion force inversely proportional to distance
                        force = (self.min_separation - distance) / self.min_separation
                        avoidance += (separation / distance) * force

        # Normalize if non-zero
        avoidance_magnitude = np.linalg.norm(avoidance)
        if avoidance_magnitude > 0:
            avoidance = avoidance / avoidance_magnitude

        return avoidance
