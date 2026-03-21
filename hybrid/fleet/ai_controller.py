"""AI Controller for autonomous ship behavior.

Provides basic AI decision-making for NPC ships. The AI controller
runs on a 2-second decision interval and follows a simple priority:
  1. If no threats: idle or hold position
  2. If threat detected: intercept to engagement range
  3. If in range: lock target and fire weapons
  4. If heavily damaged: evasive maneuvers

All system interactions use the real ship system APIs (targeting,
combat, navigation) rather than abstract command routing.
"""

import logging
from typing import Dict, Optional, List, Tuple
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
    """Assess threats and prioritize targets.

    Works with (contact_id, ContactData) tuples from the sensor
    contact tracker, not raw dicts.
    """

    @staticmethod
    def assess_threat(contact_id: str, contact, own_ship) -> float:
        """Assess threat level of a contact.

        Args:
            contact_id: Stable contact ID (e.g. "C001").
            contact: ContactData dataclass instance.
            own_ship: The ship being threatened.

        Returns:
            Threat score (0-10, higher is more threatening).
        """
        threat = 0.0

        # Distance factor (closer = more threatening)
        pos = getattr(contact, "position", {})
        contact_pos = np.array([pos.get("x", 0), pos.get("y", 0), pos.get("z", 0)])
        own_pos_dict = own_ship.position if hasattr(own_ship, "position") else {}
        own_pos = np.array([
            own_pos_dict.get("x", 0),
            own_pos_dict.get("y", 0),
            own_pos_dict.get("z", 0),
        ])
        distance = float(np.linalg.norm(contact_pos - own_pos))

        if distance < 10_000:       # Within 10km -- critical
            threat += 5.0
        elif distance < 50_000:     # Within 50km -- high
            threat += 3.0
        elif distance < 100_000:    # Within 100km -- moderate
            threat += 1.0

        # Closing velocity (approaching = more threatening)
        vel = getattr(contact, "velocity", {})
        contact_vel = np.array([vel.get("x", 0), vel.get("y", 0), vel.get("z", 0)])
        own_vel_dict = own_ship.velocity if hasattr(own_ship, "velocity") else {}
        own_vel = np.array([
            own_vel_dict.get("x", 0),
            own_vel_dict.get("y", 0),
            own_vel_dict.get("z", 0),
        ])
        relative_vel = contact_vel - own_vel

        if distance > 0:
            closing_velocity = -np.dot(relative_vel, (contact_pos - own_pos)) / distance
            if closing_velocity > 0:
                threat += min(closing_velocity / 100.0, 3.0)

        # Classification factor
        classification = (getattr(contact, "classification", None) or "unknown").lower()
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
    def prioritize_targets(
        contacts: List[Tuple[str, object]],
        own_ship,
    ) -> List[Tuple[str, object]]:
        """Sort contacts by threat level (highest first).

        Args:
            contacts: List of (contact_id, ContactData) tuples.
            own_ship: The ship assessing threats.

        Returns:
            Sorted list of (contact_id, ContactData) tuples.
        """
        scored = [
            (cid, contact, AIThreatAssessment.assess_threat(cid, contact, own_ship))
            for cid, contact in contacts
        ]
        scored.sort(key=lambda x: x[2], reverse=True)
        return [(cid, contact) for cid, contact, _score in scored]


class AIController:
    """AI controller for autonomous ship behavior.

    Makes tactical decisions and issues commands through the real
    ship system APIs (NavigationSystem, TargetingSystem, CombatSystem).
    """

    def __init__(self, ship):
        """Initialize AI controller.

        Args:
            ship: Ship to control.
        """
        self.ship = ship
        self.behavior = AIBehavior.IDLE
        self.behavior_params: Dict = {}

        # State tracking
        # current_target is a (contact_id, ContactData) tuple or None.
        self.current_target: Optional[Tuple[str, object]] = None
        self.waypoints: list = []
        self.current_waypoint_index = 0
        self.last_decision_time = 0.0
        self.decision_interval = 2.0  # seconds between AI decisions
        self._last_sim_time = 0.0

        # Combat parameters -- distances in metres
        self.engagement_range = 50_000.0   # 50km -- start closing
        self.weapon_range = 20_000.0       # 20km -- open fire
        self.min_engagement_distance = 2_000.0  # 2km -- too close, match velocity

        # Track whether we already set autopilot this decision cycle
        # to avoid re-engaging every 2 seconds.
        self._autopilot_set_for_target: Optional[str] = None

        logger.info("AI Controller initialized for %s", ship.id)

    def set_behavior(self, behavior: AIBehavior, params: Optional[Dict] = None):
        """Set AI behavior.

        Args:
            behavior: Behavior to activate.
            params: Behavior-specific parameters.
        """
        self.behavior = behavior
        self.behavior_params = params or {}
        # Reset target tracking when switching behaviors
        if behavior != AIBehavior.ATTACK:
            self.current_target = None
        self._autopilot_set_for_target = None
        logger.info("AI behavior set to %s for %s", behavior.value, self.ship.id)

    def update(self, dt: float, sim_time: float):
        """Update AI controller and make decisions.

        Called every tick from Ship.tick(). Respects decision_interval
        to avoid thrashing autopilot commands.

        Args:
            dt: Time delta in seconds.
            sim_time: Current simulation time.
        """
        self._last_sim_time = sim_time

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

    # ── Behavior implementations ──────────────────────────────────

    def _behavior_idle(self):
        """Idle behavior -- check for threats and react."""
        threats = self._get_hostile_contacts()
        if threats:
            logger.info("AI %s: Threats detected, switching to attack", self.ship.id)
            self.current_target = threats[0]
            self.set_behavior(AIBehavior.ATTACK)

    def _behavior_hold_position(self):
        """Hold current position, engage threats if detected."""
        self._ensure_autopilot("hold")

        threats = self._get_hostile_contacts()
        if threats:
            self._engage_target(threats[0][0], threats[0][1])

    def _behavior_patrol(self):
        """Patrol between waypoints."""
        waypoints = self.behavior_params.get("waypoints", [])
        if not waypoints:
            self.set_behavior(AIBehavior.IDLE)
            return

        if self.current_waypoint_index >= len(waypoints):
            self.current_waypoint_index = 0

        waypoint = waypoints[self.current_waypoint_index]
        wp_pos = np.array(waypoint)
        own_pos = self._get_position(self.ship)
        distance = float(np.linalg.norm(wp_pos - own_pos))

        if distance < 1000:
            self.current_waypoint_index = (self.current_waypoint_index + 1) % len(waypoints)

        # Check for threats while patrolling
        threats = self._get_hostile_contacts()
        if threats:
            logger.info("AI %s: Threats detected during patrol", self.ship.id)
            self.current_target = threats[0]
            self.set_behavior(AIBehavior.ATTACK)

    def _behavior_escort(self):
        """Escort and protect target ship."""
        escort_target = self.behavior_params.get("escort_target")
        if not escort_target:
            self.set_behavior(AIBehavior.IDLE)
            return

        threats = self._get_hostile_contacts()
        if threats:
            self._engage_target(threats[0][0], threats[0][1])

    def _behavior_attack(self):
        """Attack hostile targets -- the core combat loop.

        Priority:
          1. Acquire target if none
          2. Close to engagement range
          3. Lock and fire
        """
        # Acquire target
        if not self.current_target:
            threats = self._get_hostile_contacts()
            if not threats:
                logger.info("AI %s: No threats, returning to idle", self.ship.id)
                self.set_behavior(AIBehavior.IDLE)
                return
            self.current_target = threats[0]

        contact_id, contact = self.current_target

        # Refresh contact data from sensors (might have updated)
        sensors = self.ship.systems.get("sensors")
        if sensors and hasattr(sensors, "contact_tracker"):
            fresh = sensors.contact_tracker.get_contact(contact_id)
            if fresh:
                contact = fresh
                self.current_target = (contact_id, contact)
            else:
                # Contact lost
                logger.info("AI %s: Target %s lost", self.ship.id, contact_id)
                self.current_target = None
                return

        # Get distance to target
        target_pos = self._get_position(contact)
        own_pos = self._get_position(self.ship)
        distance = float(np.linalg.norm(target_pos - own_pos))

        # Range-based decision
        if distance > self.engagement_range:
            # Too far -- close in with intercept autopilot
            self._ensure_autopilot("intercept", target_id=contact_id)
        elif distance > self.weapon_range:
            # Closing -- keep intercepting
            self._ensure_autopilot("intercept", target_id=contact_id)
            # Start locking target while closing
            self._lock_target(contact_id)
        else:
            # In weapon range -- match velocity and fire
            self._ensure_autopilot("match", target_id=contact_id)
            self._engage_target(contact_id, contact)

    def _behavior_intercept(self):
        """Pursue and intercept a specific target."""
        intercept_target = self.behavior_params.get("intercept_target")
        if not intercept_target:
            self.set_behavior(AIBehavior.IDLE)
            return

        self._ensure_autopilot("intercept", target_id=intercept_target)

        # Check if close enough to switch to attack
        target = self._get_ship_or_contact(intercept_target)
        if target:
            target_pos = self._get_position(target)
            own_pos = self._get_position(self.ship)
            distance = float(np.linalg.norm(target_pos - own_pos))

            if distance < self.engagement_range:
                logger.info("AI %s: In range, switching to attack", self.ship.id)
                # Build a proper (contact_id, ContactData) tuple
                sensors = self.ship.systems.get("sensors")
                if sensors and hasattr(sensors, "contact_tracker"):
                    contact = sensors.contact_tracker.get_contact(intercept_target)
                    if contact:
                        self.current_target = (intercept_target, contact)
                self.set_behavior(AIBehavior.ATTACK)

    def _behavior_evade(self):
        """Evasive maneuvers -- flee from threats."""
        threats = self._get_hostile_contacts()
        if not threats:
            logger.info("AI %s: No threats, ending evasion", self.ship.id)
            self.set_behavior(AIBehavior.IDLE)
            return

        # Engage evasive autopilot (random jink pattern)
        self._ensure_autopilot("evasive")

    def _behavior_defend_area(self):
        """Defend a specific area."""
        defend_position = self.behavior_params.get("position")
        defend_radius = self.behavior_params.get("radius", 5000)

        if not defend_position:
            self.set_behavior(AIBehavior.IDLE)
            return

        own_pos = self._get_position(self.ship)
        defend_pos = np.array(defend_position)
        distance_from_center = float(np.linalg.norm(own_pos - defend_pos))

        if distance_from_center > defend_radius:
            self._ensure_autopilot("hold")
        else:
            threats = self._get_hostile_contacts()
            if threats:
                self._engage_target(threats[0][0], threats[0][1])
            else:
                self._ensure_autopilot("hold")

    # ── System interaction helpers ────────────────────────────────

    def _get_hostile_contacts(self) -> List[Tuple[str, object]]:
        """Get hostile contacts from sensor system using faction rules.

        Returns:
            List of (contact_id, ContactData) tuples sorted by threat.
        """
        from hybrid.fleet.faction_rules import are_hostile

        sensors = self.ship.systems.get("sensors")
        if not sensors or not hasattr(sensors, "contact_tracker"):
            return []

        sim_time = getattr(sensors, "sim_time", self._last_sim_time)
        contacts = sensors.contact_tracker.get_all_contacts(sim_time)

        hostile = []
        for contact_id, contact in contacts.items():
            contact_faction = getattr(contact, "faction", None)
            if contact_faction and are_hostile(self.ship.faction, contact_faction):
                hostile.append((contact_id, contact))

        return AIThreatAssessment.prioritize_targets(hostile, self.ship)

    def _lock_target(self, contact_id: str):
        """Lock the targeting system onto a contact.

        Args:
            contact_id: Stable contact ID (e.g. "C001").
        """
        targeting = self.ship.systems.get("targeting")
        if not targeting:
            return

        # Don't re-lock if already locked on same target
        if (hasattr(targeting, "locked_target")
                and targeting.locked_target == contact_id):
            return

        if hasattr(targeting, "lock_target"):
            targeting.lock_target(contact_id, self._last_sim_time)
        elif hasattr(targeting, "command"):
            targeting.command("lock", {"target_id": contact_id})

    def _engage_target(self, contact_id: str, contact):
        """Lock target and fire weapons when ready.

        Args:
            contact_id: Stable contact ID.
            contact: ContactData instance.
        """
        # Step 1: Lock target
        self._lock_target(contact_id)

        # Step 2: Check if we have a lock
        targeting = self.ship.systems.get("targeting")
        if not targeting or not hasattr(targeting, "lock_state"):
            return

        lock_val = targeting.lock_state
        # LockState is an enum -- get its string value
        if hasattr(lock_val, "value"):
            lock_val = lock_val.value

        if lock_val != "locked":
            return  # Not locked yet, wait for targeting pipeline

        # Step 3: Fire all ready weapons
        combat = self.ship.systems.get("combat")
        if not combat or not hasattr(combat, "fire_all_ready"):
            return

        # Resolve the actual Ship object for the target
        target_ship = self._resolve_target_ship(contact_id)
        if target_ship:
            result = combat.fire_all_ready(target_ship)
            if result.get("weapons_fired", 0) > 0:
                logger.info(
                    "AI %s: Fired %d weapons at %s",
                    self.ship.id, result["weapons_fired"], contact_id,
                )

    def _resolve_target_ship(self, contact_id: str):
        """Resolve a contact ID to the actual Ship object.

        The contact tracker maps stable contact IDs ("C001") to
        original ship IDs via id_mapping. We then look up the ship
        in _all_ships_ref (set by Ship.tick each frame).

        Args:
            contact_id: Stable contact ID.

        Returns:
            Ship object or None.
        """
        sensors = self.ship.systems.get("sensors")
        if sensors and hasattr(sensors, "contact_tracker"):
            tracker = sensors.contact_tracker
            # id_mapping is real_ship_id -> stable_contact_id
            # We need the reverse: stable_contact_id -> real_ship_id
            ship_id = None
            for real_id, stable_id in tracker.id_mapping.items():
                if stable_id == contact_id:
                    ship_id = real_id
                    break

            if ship_id and hasattr(self.ship, "_all_ships_ref"):
                for s in self.ship._all_ships_ref:
                    if s.id == ship_id:
                        return s

        # Fallback: contact_id might be the raw ship ID
        if hasattr(self.ship, "_all_ships_ref"):
            for s in self.ship._all_ships_ref:
                if s.id == contact_id:
                    return s

        return None

    def _ensure_autopilot(self, program: str, target_id: str = None):
        """Engage autopilot if not already set for this target.

        Avoids re-engaging the same program every decision cycle.
        Routes through NavigationSystem.command("set_autopilot", ...)
        which is the canonical API.

        Args:
            program: Autopilot program name (e.g. "intercept", "match").
            target_id: Target contact ID (optional).
        """
        # Build a cache key to avoid re-engaging same program/target
        cache_key = f"{program}:{target_id}"
        if self._autopilot_set_for_target == cache_key:
            return

        nav = self.ship.systems.get("navigation")
        if not nav or not hasattr(nav, "command"):
            return

        try:
            params = {
                "program": program,
                "target": target_id,
                "ship": self.ship,
                "_ship": self.ship,
                "event_bus": self.ship.event_bus,
                "_from_autopilot": True,
            }
            result = nav.command("set_autopilot", params)
            if result and not result.get("error"):
                self._autopilot_set_for_target = cache_key
                logger.debug(
                    "AI %s: Autopilot set to %s (target=%s)",
                    self.ship.id, program, target_id,
                )
        except Exception as e:
            logger.warning("AI %s: Autopilot command failed: %s", self.ship.id, e)

    # ── Utility helpers ───────────────────────────────────────────

    def _get_ship_or_contact(self, identifier: str):
        """Get ship object or sensor contact by ID.

        Args:
            identifier: Ship ID or contact ID.

        Returns:
            Ship object, ContactData, or None.
        """
        # Try sensor contacts first (stable IDs)
        sensors = self.ship.systems.get("sensors")
        if sensors and hasattr(sensors, "get_contact"):
            contact = sensors.get_contact(identifier)
            if contact:
                return contact

        # Try direct ship lookup from _all_ships_ref
        if hasattr(self.ship, "_all_ships_ref"):
            for s in self.ship._all_ships_ref:
                if s.id == identifier:
                    return s

        return None

    def _get_position(self, obj) -> np.ndarray:
        """Get position from ship, contact, or ContactData.

        Args:
            obj: Object with a position attribute or dict.

        Returns:
            numpy array [x, y, z].
        """
        pos = getattr(obj, "position", {})
        if isinstance(pos, dict):
            return np.array([pos.get("x", 0), pos.get("y", 0), pos.get("z", 0)])
        return np.array([0.0, 0.0, 0.0])

    def _get_velocity(self, obj) -> np.ndarray:
        """Get velocity from ship, contact, or ContactData.

        Args:
            obj: Object with a velocity attribute or dict.

        Returns:
            numpy array [x, y, z].
        """
        vel = getattr(obj, "velocity", {})
        if isinstance(vel, dict):
            return np.array([vel.get("x", 0), vel.get("y", 0), vel.get("z", 0)])
        return np.array([0.0, 0.0, 0.0])

    def get_state(self) -> Dict:
        """Get AI controller state for telemetry.

        Returns:
            dict: Current AI state.
        """
        target_id = None
        if self.current_target:
            target_id = self.current_target[0]

        return {
            "behavior": self.behavior.value,
            "current_target": target_id,
            "waypoint_index": self.current_waypoint_index,
            "total_waypoints": len(self.waypoints),
        }
