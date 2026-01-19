"""
AI Controller for autonomous ship behavior.
Provides basic AI for ships operating without human control.
"""

import logging
import time
from typing import Dict, Optional, List
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class AIBehavior(Enum):
    """Available AI behaviors"""
    IDLE = "idle"                 # Do nothing, hold position
    PATROL = "patrol"             # Patrol between waypoints
    ESCORT = "escort"             # Follow and protect target
    INTERCEPT = "intercept"       # Pursue and close with target
    ATTACK = "attack"             # Engage hostile target
    EVADE = "evade"               # Evasive maneuvers
    HOLD_POSITION = "hold"        # Station-keeping at position
    DEFEND_AREA = "defend"        # Defend a specific area
    FORMATION = "formation"       # Maintain fleet formation


class AIThreatAssessment:
    """Assess threats and prioritize targets"""

    @staticmethod
    def assess_threat(contact: Dict, own_ship) -> float:
        """
        Assess threat level of a contact.

        Args:
            contact: Contact information dict
            own_ship: The ship being threatened

        Returns:
            Threat score (0-10, higher is more threatening)
        """
        threat = 0.0

        # Check if hostile
        if not contact.get("is_hostile", False):
            return 0.0

        # Distance factor (closer = more threatening)
        pos = contact.get("position", {})
        contact_pos = np.array([pos.get("x", 0), pos.get("y", 0), pos.get("z", 0)])
        own_pos_dict = own_ship.position if hasattr(own_ship, 'position') else {}
        own_pos = np.array([own_pos_dict.get("x", 0), own_pos_dict.get("y", 0), own_pos_dict.get("z", 0)])
        distance = np.linalg.norm(contact_pos - own_pos)

        if distance < 10000:  # Within 10km - critical
            threat += 5.0
        elif distance < 50000:  # Within 50km - high
            threat += 3.0
        elif distance < 100000:  # Within 100km - moderate
            threat += 1.0

        # Closing velocity (approaching = more threatening)
        vel = contact.get("velocity", {})
        contact_vel = np.array([vel.get("x", 0), vel.get("y", 0), vel.get("z", 0)])
        own_vel_dict = own_ship.velocity if hasattr(own_ship, 'velocity') else {}
        own_vel = np.array([own_vel_dict.get("x", 0), own_vel_dict.get("y", 0), own_vel_dict.get("z", 0)])
        relative_vel = contact_vel - own_vel

        # Check if approaching
        if distance > 0:
            closing_velocity = -np.dot(relative_vel, (contact_pos - own_pos)) / distance
            if closing_velocity > 0:  # Approaching
                threat += min(closing_velocity / 100, 3.0)  # Up to +3 for fast approach

        # Classification factor
        classification = contact.get("classification", "unknown").lower()
        if "fighter" in classification:
            threat += 1.0
        elif "frigate" in classification or "destroyer" in classification:
            threat += 2.0
        elif "cruiser" in classification:
            threat += 3.0
        elif "battleship" in classification or "carrier" in classification:
            threat += 4.0

        return min(threat, 10.0)

    @staticmethod
    def prioritize_targets(contacts: List[Dict], own_ship) -> List[Dict]:
        """
        Sort contacts by threat level.

        Args:
            contacts: List of contact dicts
            own_ship: The ship assessing threats

        Returns:
            List of contacts sorted by threat (highest first)
        """
        scored = [
            (contact, AIThreatAssessment.assess_threat(contact, own_ship))
            for contact in contacts
        ]

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        return [contact for contact, score in scored]


class AIController:
    """
    AI controller for autonomous ship behavior.
    Makes tactical decisions and issues commands.
    """

    def __init__(self, ship):
        """
        Initialize AI controller.

        Args:
            ship: Ship to control
        """
        self.ship = ship
        self.behavior = AIBehavior.IDLE
        self.behavior_params = {}

        # State tracking
        self.current_target = None
        self.waypoints = []
        self.current_waypoint_index = 0
        self.last_decision_time = 0.0
        self.decision_interval = 2.0  # Make decisions every 2 seconds

        # Combat parameters
        self.engagement_range = 50000.0  # 50km
        self.weapon_range = 20000.0  # 20km
        self.min_engagement_distance = 5000.0  # 5km
        self.evasion_threshold = 0.7  # Evade if threat > 7/10

        logger.info(f"AI Controller initialized for {ship.id}")

    def set_behavior(self, behavior: AIBehavior, params: Optional[Dict] = None):
        """
        Set AI behavior.

        Args:
            behavior: Behavior to activate
            params: Behavior-specific parameters
        """
        self.behavior = behavior
        self.behavior_params = params or {}
        logger.info(f"AI behavior set to {behavior.value} for {self.ship.id}")

    def update(self, dt: float, sim_time: float):
        """
        Update AI controller and make decisions.

        Args:
            dt: Time delta
            sim_time: Current simulation time
        """
        # Only make decisions at intervals to reduce overhead
        if sim_time - self.last_decision_time < self.decision_interval:
            return

        self.last_decision_time = sim_time

        # Execute current behavior
        if self.behavior == AIBehavior.IDLE:
            self._behavior_idle()
        elif self.behavior == AIBehavior.HOLD_POSITION:
            self._behavior_hold_position()
        elif self.behavior == AIBehavior.PATROL:
            self._behavior_patrol()
        elif self.behavior == AIBehavior.ESCORT:
            self._behavior_escort()
        elif self.behavior == AIBehavior.ATTACK:
            self._behavior_attack()
        elif self.behavior == AIBehavior.INTERCEPT:
            self._behavior_intercept()
        elif self.behavior == AIBehavior.EVADE:
            self._behavior_evade()
        elif self.behavior == AIBehavior.DEFEND_AREA:
            self._behavior_defend_area()

    def _behavior_idle(self):
        """Idle behavior - do nothing."""
        # Check for threats and switch to defend if needed
        threats = self._get_hostile_contacts()
        if threats:
            logger.info(f"AI {self.ship.id}: Threats detected, switching to attack")
            self.set_behavior(AIBehavior.ATTACK)

    def _behavior_hold_position(self):
        """Hold current position."""
        # Engage autopilot if not already active
        nav_system = self.ship.systems.get("navigation")
        if nav_system and not nav_system.autopilot:
            self._command_autopilot("hold")

        # Check for threats
        threats = self._get_hostile_contacts()
        if threats:
            # Stay in position but engage targets
            self._engage_target(threats[0])

    def _behavior_patrol(self):
        """Patrol between waypoints."""
        waypoints = self.behavior_params.get("waypoints", [])
        if not waypoints:
            logger.warning(f"AI {self.ship.id}: No waypoints for patrol, switching to idle")
            self.set_behavior(AIBehavior.IDLE)
            return

        # Get current waypoint
        if self.current_waypoint_index >= len(waypoints):
            self.current_waypoint_index = 0

        waypoint = waypoints[self.current_waypoint_index]

        # Check if reached waypoint
        wp_pos = np.array(waypoint)
        own_pos = self._get_position(self.ship)
        distance = np.linalg.norm(wp_pos - own_pos)

        if distance < 1000:  # Within 1km
            # Move to next waypoint
            self.current_waypoint_index = (self.current_waypoint_index + 1) % len(waypoints)
            logger.info(f"AI {self.ship.id}: Reached waypoint {self.current_waypoint_index}")

        # Navigate to current waypoint
        self._command_autopilot("intercept", target_position=waypoint)

        # Check for threats while patrolling
        threats = self._get_hostile_contacts()
        if threats:
            logger.info(f"AI {self.ship.id}: Threats detected during patrol, engaging")
            self.current_target = threats[0]
            self.set_behavior(AIBehavior.ATTACK)

    def _behavior_escort(self):
        """Escort and protect target ship."""
        escort_target = self.behavior_params.get("escort_target")
        if not escort_target:
            logger.warning(f"AI {self.ship.id}: No escort target, switching to idle")
            self.set_behavior(AIBehavior.IDLE)
            return

        # Get escort target ship
        target_ship = self._get_ship_or_contact(escort_target)
        if not target_ship:
            logger.warning(f"AI {self.ship.id}: Escort target lost")
            self.set_behavior(AIBehavior.IDLE)
            return

        # Maintain escort position (offset from target)
        offset = self.behavior_params.get("offset", [0, -2000, 0])  # 2km behind
        self._command_autopilot("formation", flagship_id=escort_target, formation_position=offset)

        # Check for threats to escort target
        threats = self._get_hostile_contacts()
        if threats:
            # Prioritize threats close to escort target
            for threat in threats:
                self._engage_target(threat)
                break  # Engage first threat

    def _behavior_attack(self):
        """Attack hostile targets."""
        # Get current target or find new one
        if not self.current_target:
            threats = self._get_hostile_contacts()
            if not threats:
                logger.info(f"AI {self.ship.id}: No threats, returning to idle")
                self.set_behavior(AIBehavior.IDLE)
                return
            self.current_target = threats[0]

        # Check if target still valid
        target = self._get_ship_or_contact(self.current_target.get("id"))
        if not target:
            logger.info(f"AI {self.ship.id}: Target lost, acquiring new target")
            self.current_target = None
            return

        # Get distance to target
        target_pos = self._get_position(target)
        own_pos = self._get_position(self.ship)
        distance = np.linalg.norm(target_pos - own_pos)

        # Decide on maneuver based on range
        if distance > self.engagement_range:
            # Too far, close in
            self._command_autopilot("intercept", target_id=self.current_target.get("id"))
        elif distance < self.min_engagement_distance:
            # Too close, create distance
            self._command_autopilot("match", target_id=self.current_target.get("id"))
        else:
            # In engagement range, match velocity and fire
            self._command_autopilot("match", target_id=self.current_target.get("id"))
            self._engage_target(self.current_target)

    def _behavior_intercept(self):
        """Pursue and intercept target."""
        intercept_target = self.behavior_params.get("intercept_target")
        if not intercept_target:
            logger.warning(f"AI {self.ship.id}: No intercept target")
            self.set_behavior(AIBehavior.IDLE)
            return

        # Intercept target
        self._command_autopilot("intercept", target_id=intercept_target)

        # Check if close enough to switch to attack
        target = self._get_ship_or_contact(intercept_target)
        if target:
            target_pos = self._get_position(target)
            own_pos = self._get_position(self.ship)
            distance = np.linalg.norm(target_pos - own_pos)

            if distance < self.engagement_range:
                logger.info(f"AI {self.ship.id}: In range, switching to attack")
                self.current_target = target if isinstance(target, dict) else {"id": intercept_target}
                self.set_behavior(AIBehavior.ATTACK)

    def _behavior_evade(self):
        """Evasive maneuvers."""
        # Find threat direction
        threats = self._get_hostile_contacts()
        if not threats:
            logger.info(f"AI {self.ship.id}: No threats, ending evasion")
            self.set_behavior(AIBehavior.IDLE)
            return

        # Calculate evasion vector (away from threats)
        own_pos = self._get_position(self.ship)
        evasion_vector = np.array([0.0, 0.0, 0.0])

        for threat in threats:
            threat_pos = self._get_position(threat)
            to_threat = threat_pos - own_pos
            distance = np.linalg.norm(to_threat)
            if distance > 0:
                # Push away from threat (weighted by proximity)
                weight = 1.0 / (distance / 1000 + 1)  # Closer threats have more weight
                evasion_vector -= (to_threat / distance) * weight

        # Normalize and create evasion point
        if np.linalg.norm(evasion_vector) > 0:
            evasion_vector = evasion_vector / np.linalg.norm(evasion_vector)
            evasion_point = own_pos + evasion_vector * 10000  # 10km away

            self._command_autopilot("intercept", target_position=evasion_point.tolist())

    def _behavior_defend_area(self):
        """Defend a specific area."""
        defend_position = self.behavior_params.get("position")
        defend_radius = self.behavior_params.get("radius", 5000)

        if not defend_position:
            logger.warning(f"AI {self.ship.id}: No defend position")
            self.set_behavior(AIBehavior.IDLE)
            return

        # Check if in defend area
        own_pos = self._get_position(self.ship)
        defend_pos = np.array(defend_position)
        distance_from_center = np.linalg.norm(own_pos - defend_pos)

        if distance_from_center > defend_radius:
            # Return to defend position
            self._command_autopilot("intercept", target_position=defend_position)
        else:
            # In area, look for threats
            threats = self._get_hostile_contacts()
            if threats:
                # Engage closest threat
                self._engage_target(threats[0])
            else:
                # Hold position
                self._command_autopilot("hold")

    def _get_hostile_contacts(self) -> List[Dict]:
        """Get list of hostile contacts, sorted by threat."""
        sensors = self.ship.systems.get("sensors")
        if not sensors:
            return []

        # Get all contacts
        all_contacts = []
        if hasattr(sensors, "contacts"):
            all_contacts = [
                contact for contact in sensors.contacts.values()
                if contact.get("is_hostile", False)
            ]

        # Prioritize by threat
        return AIThreatAssessment.prioritize_targets(all_contacts, self.ship)

    def _engage_target(self, target: Dict):
        """Engage a target with weapons."""
        target_id = target.get("id")
        if not target_id:
            return

        # Target the contact
        targeting = self.ship.systems.get("targeting")
        if targeting:
            if not hasattr(targeting, "current_target") or targeting.current_target != target_id:
                # Lock target
                self._command("target", [target_id])

        # Fire weapons if in range
        target_pos = self._get_position(target)
        own_pos = self._get_position(self.ship)
        distance = np.linalg.norm(target_pos - own_pos)

        if distance < self.weapon_range:
            weapons = self.ship.systems.get("weapons")
            if weapons and hasattr(weapons, "can_fire") and weapons.can_fire():
                self._command("fire", [])

    def _command_autopilot(self, program: str, **params):
        """Issue autopilot command."""
        try:
            nav = self.ship.systems.get("navigation")
            if nav:
                # Build params dict
                ap_params = {}
                if "target_id" in params:
                    ap_params["target_id"] = params["target_id"]
                if "target_position" in params:
                    ap_params["target_position"] = params["target_position"]
                if "flagship_id" in params:
                    ap_params["target_id"] = params["flagship_id"]
                if "formation_position" in params:
                    ap_params["formation_position"] = params["formation_position"]

                # Engage autopilot
                if hasattr(nav, "engage_autopilot"):
                    nav.engage_autopilot(program, **ap_params)
        except Exception as e:
            logger.error(f"AI autopilot command failed: {e}")

    def _command(self, command: str, args: List):
        """Issue command to ship."""
        try:
            if hasattr(self.ship, "execute_command"):
                self.ship.execute_command(command, args)
        except Exception as e:
            logger.error(f"AI command failed: {command} - {e}")

    def _get_ship_or_contact(self, identifier: str):
        """Get ship object or sensor contact by ID."""
        # Try to get from simulator
        if hasattr(self.ship, "simulator") and self.ship.simulator:
            if identifier in self.ship.simulator.ships:
                return self.ship.simulator.ships[identifier]

        # Try to get from sensors
        sensors = self.ship.systems.get("sensors")
        if sensors and hasattr(sensors, "get_contact"):
            return sensors.get_contact(identifier)

        return None

    def _get_position(self, obj) -> np.ndarray:
        """Get position from ship or contact."""
        if isinstance(obj, dict):
            pos = obj.get("position", {})
            return np.array([pos.get("x", 0), pos.get("y", 0), pos.get("z", 0)])
        else:
            # Ship object with position dict
            pos = obj.position if hasattr(obj, 'position') else {}
            return np.array([pos.get("x", 0), pos.get("y", 0), pos.get("z", 0)])

    def _get_velocity(self, obj) -> np.ndarray:
        """Get velocity from ship or contact."""
        if isinstance(obj, dict):
            vel = obj.get("velocity", {})
            return np.array([vel.get("x", 0), vel.get("y", 0), vel.get("z", 0)])
        else:
            # Ship object with velocity dict
            vel = obj.velocity if hasattr(obj, 'velocity') else {}
            return np.array([vel.get("x", 0), vel.get("y", 0), vel.get("z", 0)])

    def get_state(self) -> Dict:
        """Get AI controller state."""
        return {
            "behavior": self.behavior.value,
            "current_target": self.current_target.get("id") if self.current_target else None,
            "waypoint_index": self.current_waypoint_index,
            "total_waypoints": len(self.waypoints),
        }
