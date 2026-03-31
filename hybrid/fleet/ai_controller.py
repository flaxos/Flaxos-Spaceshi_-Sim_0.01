"""AI Controller for autonomous ship behavior.

Provides role-aware AI decision-making for NPC ships. The AI controller
runs on a 2-second decision interval and consults a BehaviorProfile to
determine how the ship reacts to threats.

Phase 1 (PR #236): all NPC ships fight.
Phase 2: role differentiation via BehaviorProfile:
  - combat:    aggressive pursuit and engagement
  - freighter: flee from threats, never fire, emit distress
  - escort:    interpose between threat and protected ship
  - patrol:    hold position, engage within range, return after
Phase 3: doctrine-level behaviors (ai_doctrine.py):
  - coordinated salvos: multi-ship fire timing
  - evasion jinking: heading changes keyed to railgun ToF
  - retreat conditions: subsystem-aware disengagement
  - smart target prioritization: spread fire across enemies

All system interactions use the real ship system APIs (targeting,
combat, navigation) rather than abstract command routing.
"""

import logging
from typing import Dict, Optional, List, Tuple
from enum import Enum
import numpy as np

from hybrid.fleet.npc_behavior import BehaviorProfile, get_profile, infer_role
from hybrid.fleet.threat_assessment import AIThreatAssessment
from hybrid.fleet.ai_doctrine import (
    SalvoCoordinator,
    EvasionState,
    RetreatAssessment,
    should_jink,
    assess_retreat,
)

logger = logging.getLogger(__name__)


class AIBehavior(Enum):
    """Available AI behaviors"""
    IDLE = "idle"                 # Do nothing, hold position
    PATROL = "patrol"             # Patrol between waypoints
    ESCORT = "escort"             # Follow and protect target
    INTERCEPT = "intercept"       # Pursue and close with target
    ATTACK = "attack"             # Engage hostile target
    EVADE = "evade"               # Evasive maneuvers
    FLEE = "flee"                 # Max thrust away from threats
    HOLD_POSITION = "hold"        # Station-keeping at position
    DEFEND_AREA = "defend"        # Defend a specific area
    FORMATION = "formation"       # Maintain fleet formation


class AIController:
    """AI controller for autonomous ship behavior.

    Makes tactical decisions and issues commands through the real
    ship system APIs (NavigationSystem, TargetingSystem, CombatSystem).
    Uses a BehaviorProfile to differentiate between ship roles.
    """

    def __init__(self, ship):
        """Initialize AI controller.

        Automatically infers a role-based BehaviorProfile from the
        ship's class_type and faction.  The profile can be overridden
        later via scenario YAML or direct assignment.

        Args:
            ship: Ship to control.
        """
        self.ship = ship
        self.behavior = AIBehavior.IDLE
        self.behavior_params: Dict = {}

        # Role-based behavior profile -- drives thresholds and reactions
        role = infer_role(
            getattr(ship, "class_type", ""),
            getattr(ship, "faction", ""),
        )
        self.profile: BehaviorProfile = get_profile(role)

        # State tracking
        # current_target is a (contact_id, ContactData) tuple or None.
        self.current_target: Optional[Tuple[str, object]] = None
        self.waypoints: list = []
        self.current_waypoint_index = 0
        self.last_decision_time = 0.0
        self.decision_interval = 2.0  # seconds between AI decisions
        self._last_sim_time = 0.0

        # Combat parameters -- distances in metres.
        # engagement_range now comes from profile; weapon_range and
        # min_engagement_distance are combat-universal constants.
        self.engagement_range = self.profile.engagement_range
        self.weapon_range = 20_000.0       # 20km -- open fire
        self.min_engagement_distance = 2_000.0  # 2km -- too close

        # Track whether we already set autopilot this decision cycle
        # to avoid re-engaging every 2 seconds.
        self._autopilot_set_for_target: Optional[str] = None

        # Distress signal tracking -- don't spam every tick
        self._distress_emitted = False

        # Patrol home position -- captured when patrol behavior starts
        self._patrol_home: Optional[np.ndarray] = None

        # ── Doctrine state (Phase 3) ──────────────────────────────
        # Evasion jink tracking -- persists across decision cycles
        self._evasion_state = EvasionState()
        # Salvo coordinator -- shared instance, set externally by
        # the scenario or fleet manager.  If None, ships fire freely.
        self._salvo_coordinator: Optional[SalvoCoordinator] = None
        # Cached retreat assessment -- refreshed each decision cycle
        self._retreat: RetreatAssessment = RetreatAssessment()

        logger.info(
            "AI Controller initialized for %s (role=%s)",
            ship.id, self.profile.role,
        )

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

        # Check hull damage before normal behavior -- profile thresholds
        # can override the current behavior (flee/evade).
        if self._check_damage_reaction():
            return  # Damage reaction took priority

        # Check fuel state -- low fuel overrides aggressive behaviors.
        # Fuel check runs after damage check because damage is more
        # immediately life-threatening.
        if self._check_fuel_reaction():
            return  # Fuel conservation took priority

        # Doctrine: subsystem-aware retreat conditions (propulsion
        # degraded, weapons destroyed, low ammo).  These are rational
        # tactical decisions vs the panic reactions above.
        if self._check_retreat_conditions():
            return  # Retreat doctrine took priority

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
        elif self.behavior == AIBehavior.FLEE:
            self._behavior_flee()
        elif self.behavior == AIBehavior.DEFEND_AREA:
            self._behavior_defend_area()

    # ── Damage & fuel reactions ──────────────────────────────────────

    def _get_hull_fraction(self) -> float:
        """Current hull integrity as a 0-1 fraction."""
        max_hull = getattr(self.ship, "max_hull_integrity", 0)
        if max_hull <= 0:
            return 1.0
        return getattr(self.ship, "hull_integrity", max_hull) / max_hull

    def _get_fuel_fraction(self) -> float:
        """Current fuel level as a 0-1 fraction.

        Returns:
            Fuel fraction (0.0 = empty, 1.0 = full). Returns 1.0 if
            no propulsion system exists (assume unlimited fuel).
        """
        propulsion = self.ship.systems.get("propulsion")
        if not propulsion:
            return 1.0
        max_fuel = getattr(propulsion, "max_fuel", 0.0)
        if max_fuel <= 0:
            return 1.0
        return getattr(propulsion, "fuel_level", 0.0) / max_fuel

    def _get_delta_v_margin(self) -> float:
        """Ratio of remaining delta-v to delta-v needed to stop.

        A margin > 1.0 means the ship can still brake to zero.
        A margin < 1.0 means the ship is past the point of no return.
        Returns float('inf') when stationary (no braking needed).

        Returns:
            Delta-v margin ratio, or inf if speed is negligible.
        """
        from hybrid.utils.units import calculate_delta_v
        from hybrid.utils.math_utils import magnitude

        propulsion = self.ship.systems.get("propulsion")
        if not propulsion:
            return float("inf")

        fuel = getattr(propulsion, "fuel_level", 0.0)
        isp = getattr(propulsion, "isp", 3000.0)
        dry_mass = getattr(self.ship, "dry_mass", self.ship.mass)
        remaining_dv = calculate_delta_v(dry_mass, fuel, isp)

        speed = magnitude(self.ship.velocity)
        if speed < 1.0:
            return float("inf") if remaining_dv > 0 else 0.0
        return remaining_dv / speed

    def _check_fuel_reaction(self) -> bool:
        """Check fuel state and switch to conservative behavior if low.

        Thresholds:
          - fuel_fraction < 10%: switch to FLEE (disengage from combat)
          - fuel_fraction < 25%: switch to EVADE (stop aggressive burns)
          - delta-v margin < 1.2: emergency brake -- switch to HOLD

        Does not interrupt if already in a fuel-conservation behavior.

        Returns:
            True if a fuel reaction overrode normal behavior.
        """
        fuel_frac = self._get_fuel_fraction()
        dv_margin = self._get_delta_v_margin()

        # Emergency: delta-v margin is too thin to stop safely
        if dv_margin < 1.2 and dv_margin != float("inf"):
            if self.behavior not in (AIBehavior.HOLD_POSITION, AIBehavior.FLEE):
                logger.warning(
                    "AI %s: EMERGENCY -- delta-v margin %.2f, "
                    "switching to HOLD to conserve fuel",
                    self.ship.id, dv_margin,
                )
                self.set_behavior(AIBehavior.HOLD_POSITION)
            return True

        # Low fuel: disengage from combat
        if fuel_frac < 0.10:
            if self.behavior not in (AIBehavior.FLEE, AIBehavior.HOLD_POSITION):
                logger.info(
                    "AI %s: Fuel at %.0f%%, fleeing to conserve",
                    self.ship.id, fuel_frac * 100,
                )
                self.set_behavior(AIBehavior.FLEE)
            return True

        # Moderate fuel: stop aggressive pursuit
        if fuel_frac < 0.25:
            if self.behavior in (AIBehavior.ATTACK, AIBehavior.INTERCEPT):
                logger.info(
                    "AI %s: Fuel at %.0f%%, switching to evasive",
                    self.ship.id, fuel_frac * 100,
                )
                self.set_behavior(AIBehavior.EVADE)
                return True

        return False

    def _check_damage_reaction(self) -> bool:
        """Check hull damage against profile thresholds.

        If hull falls below flee_threshold, switch to FLEE.
        If hull falls below evade_threshold, switch to EVADE.
        Does not interrupt if already in the correct damage-reaction
        behavior.

        Returns:
            True if a damage reaction overrode normal behavior.
        """
        hull = self._get_hull_fraction()

        if hull < self.profile.flee_threshold:
            if self.behavior != AIBehavior.FLEE:
                logger.info(
                    "AI %s: Hull at %.0f%%, fleeing (threshold %.0f%%)",
                    self.ship.id, hull * 100, self.profile.flee_threshold * 100,
                )
                self.set_behavior(AIBehavior.FLEE)
                self._emit_distress()
            # Still execute flee behavior this tick
            self._behavior_flee()
            return True

        if hull < self.profile.evade_threshold:
            if self.behavior != AIBehavior.EVADE:
                logger.info(
                    "AI %s: Hull at %.0f%%, evading (threshold %.0f%%)",
                    self.ship.id, hull * 100, self.profile.evade_threshold * 100,
                )
                self.set_behavior(AIBehavior.EVADE)
            self._behavior_evade()
            return True

        return False

    def _check_retreat_conditions(self) -> bool:
        """Check doctrine-level retreat conditions.

        Evaluates subsystem health and ammo state.  Unlike the hull-
        fraction thresholds in _check_damage_reaction, these are
        tactical retreat decisions (e.g. weapons destroyed, propulsion
        crippled, ammo depleted).

        Returns:
            True if a retreat condition overrode normal behavior.
        """
        self._retreat = assess_retreat(self.ship)

        if self._retreat.should_retreat:
            if self.behavior not in (AIBehavior.FLEE, AIBehavior.HOLD_POSITION):
                logger.info(
                    "AI %s: Retreat doctrine — %s, disengaging",
                    self.ship.id, self._retreat.reason,
                )
                self.set_behavior(AIBehavior.HOLD_POSITION)
                self._ensure_autopilot("hold")
            return True

        return False

    # ── Behavior implementations ──────────────────────────────────

    def _behavior_idle(self):
        """Idle behavior -- check for threats and react based on role.

        Combat/escort ships switch to ATTACK.  Freighters switch to
        FLEE.  Patrol ships switch to ATTACK only within engagement
        range.
        """
        threats = self._get_hostile_contacts()
        if not threats:
            return

        role = self.profile.role

        if role == "freighter":
            # Freighters never fight -- flee immediately
            logger.info("AI %s: Threat detected, fleeing (freighter)", self.ship.id)
            self.set_behavior(AIBehavior.FLEE)
            self._emit_distress()
            return

        if role == "patrol":
            # Patrol only engages threats within engagement_range
            contact_id, contact = threats[0]
            distance = self._distance_to(contact)
            if distance <= self.engagement_range:
                logger.info("AI %s: Threat in range, attacking (patrol)", self.ship.id)
                self.current_target = threats[0]
                self.set_behavior(AIBehavior.ATTACK)
            return

        if role == "escort":
            # Escort checks if threat is near the protected ship first
            protect_id = self.profile.protect_target
            if protect_id and self._is_threat_near_ward(threats[0], protect_id):
                logger.info(
                    "AI %s: Threat near ward %s, intercepting (escort)",
                    self.ship.id, protect_id,
                )
            else:
                logger.info("AI %s: Threat detected, attacking (escort)", self.ship.id)
            self.current_target = threats[0]
            self.set_behavior(AIBehavior.ATTACK)
            return

        # Default (combat): engage immediately
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
        """Patrol: hold position, engage threats within range, return after.

        Uses profile.patrol_position as the home anchor point.
        If no patrol_position is set, captures current position as home
        on first entry.
        """
        # Establish home position
        if self._patrol_home is None:
            if self.profile.patrol_position:
                pp = self.profile.patrol_position
                self._patrol_home = np.array([
                    pp.get("x", 0), pp.get("y", 0), pp.get("z", 0),
                ])
            else:
                self._patrol_home = self._get_position(self.ship)

        # Check for threats within engagement range
        threats = self._get_hostile_contacts()
        if threats:
            contact_id, contact = threats[0]
            distance = self._distance_to(contact)
            if distance <= self.engagement_range:
                logger.info("AI %s: Threat in patrol range, attacking", self.ship.id)
                self.current_target = threats[0]
                self.set_behavior(AIBehavior.ATTACK)
                return

        # Check waypoints from behavior_params (legacy support)
        waypoints = self.behavior_params.get("waypoints", [])
        if waypoints:
            if self.current_waypoint_index >= len(waypoints):
                self.current_waypoint_index = 0
            waypoint = waypoints[self.current_waypoint_index]
            wp_pos = np.array(waypoint)
            own_pos = self._get_position(self.ship)
            distance = float(np.linalg.norm(wp_pos - own_pos))
            if distance < 1000:
                self.current_waypoint_index = (
                    (self.current_waypoint_index + 1) % len(waypoints)
                )
            return

        # No threats, no waypoints -- hold at patrol home
        own_pos = self._get_position(self.ship)
        dist_from_home = float(np.linalg.norm(own_pos - self._patrol_home))
        if dist_from_home > 5_000:
            # Drifted too far from home -- navigate back
            self._ensure_autopilot("hold")
        else:
            self._ensure_autopilot("hold")

    def _behavior_escort(self):
        """Escort: protect a target ship by interposing against threats.

        Reads protect_target from the profile.  Falls back to
        behavior_params["escort_target"] for Phase 1 compatibility.
        When threats are detected, intercepts the highest-priority
        threat.  When no threats exist, matches velocity with the ward.
        """
        protect_id = (
            self.profile.protect_target
            or self.behavior_params.get("escort_target")
        )
        if not protect_id:
            self.set_behavior(AIBehavior.IDLE)
            return

        threats = self._get_hostile_contacts()
        if threats:
            # Prioritize threats near the protected ship
            threat_near_ward = None
            for threat_tuple in threats:
                if self._is_threat_near_ward(threat_tuple, protect_id):
                    threat_near_ward = threat_tuple
                    break

            target = threat_near_ward or threats[0]
            contact_id, contact = target

            # Intercept the threat
            distance = self._distance_to(contact)
            if distance > self.weapon_range:
                self._ensure_autopilot("intercept", target_id=contact_id)
            else:
                self._ensure_autopilot("match", target_id=contact_id)
            self._engage_target(contact_id, contact)
        else:
            # No threats -- stay near the protected ship
            self._ensure_autopilot("match", target_id=protect_id)

    def _behavior_attack(self):
        """Attack hostile targets -- the core combat loop.

        Priority:
          1. Acquire target if none (with tactical prioritization)
          2. Close to engagement range
          3. Evasion jinking while in weapon range
          4. Lock and fire (with salvo coordination + ammo conservation)
        """
        # Acquire target using tactical prioritization when possible
        if not self.current_target:
            threats = self._get_hostile_contacts_tactical()
            if not threats:
                logger.info("AI %s: No threats, returning to idle", self.ship.id)
                self._return_to_role_behavior()
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
                if self._salvo_coordinator:
                    self._salvo_coordinator.clear_target(contact_id)
                return

        # Get distance to target
        distance = self._distance_to(contact)

        # Doctrine: evasion jinking when in weapon range.
        # Change heading at intervals tuned to enemy railgun ToF
        # to degrade their firing solution accuracy.
        if distance <= self.engagement_range:
            self._apply_evasion_jink(distance)

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
            distance = self._distance_to(target)

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
            self._return_to_role_behavior()
            return

        # Engage evasive autopilot (random jink pattern)
        self._ensure_autopilot("evasive")

    def _behavior_flee(self):
        """Flee: max thrust directly away from the nearest threat.

        Used by freighters and heavily-damaged ships.  Emits a
        distress signal on the event bus so escort AI can react.
        Doctrine: launches rearguard torpedoes/missiles if available
        to discourage pursuit.
        """
        threats = self._get_hostile_contacts()
        if not threats:
            logger.info("AI %s: No threats, ending flee", self.ship.id)
            self._distress_emitted = False
            self._return_to_role_behavior()
            return

        # Emit distress if we haven't yet
        self._emit_distress()

        # Doctrine: launch rearguard ordnance while fleeing.
        # Torpedoes/missiles fired during retreat force the pursuer
        # to divert PDC attention or break off.
        self._launch_rearguard(threats[0])

        # Engage evasive autopilot -- the best flee option available.
        # A dedicated "flee" autopilot would thrust directly away from
        # the threat vector, but evasive is the closest we have.
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

    # ── Role-aware transitions ─────────────────────────────────────

    def _return_to_role_behavior(self):
        """Return to the natural resting behavior for this ship's role.

        Called when threats disappear so the AI goes back to its
        role-appropriate default instead of always reverting to IDLE.
        """
        role = self.profile.role

        if role == "patrol":
            self.set_behavior(AIBehavior.PATROL)
        elif role == "escort":
            self.set_behavior(AIBehavior.ESCORT, {
                "escort_target": self.profile.protect_target,
            })
        else:
            # combat and freighter both rest at IDLE
            self.set_behavior(AIBehavior.IDLE)

    # ── System interaction helpers ────────────────────────────────

    def _get_hostile_contacts(self) -> List[Tuple[str, object]]:
        """Get hostile contacts from sensor system using diplomatic state.

        Only contacts whose faction is HOSTILE to ours are considered
        threats.  UNKNOWN contacts are NOT treated as hostile — they
        must be hailed or scanned first.

        Returns:
            List of (contact_id, ContactData) tuples sorted by threat.
        """
        from hybrid.fleet.faction_rules import get_diplomatic_state, DiplomaticState

        sensors = self.ship.systems.get("sensors")
        if not sensors or not hasattr(sensors, "contact_tracker"):
            return []

        sim_time = getattr(sensors, "sim_time", self._last_sim_time)
        contacts = sensors.contact_tracker.get_all_contacts(sim_time)

        hostile = []
        for contact_id, contact in contacts.items():
            contact_faction = getattr(contact, "faction", None)
            if not contact_faction:
                continue
            diplo = get_diplomatic_state(self.ship.faction, contact_faction)
            if diplo == DiplomaticState.HOSTILE:
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

        Respects profile.weapon_confidence_threshold -- if set to 1.0
        (freighter), this method effectively never fires because the
        confidence check can never pass.

        Doctrine integrations:
          - Salvo coordination: delays fire if coordinator says wait
          - Conservative fire: only fires high-confidence solutions
            when ammo is low

        Args:
            contact_id: Stable contact ID.
            contact: ContactData instance.
        """
        # Freighter-class ships never fire (threshold 1.0 is unreachable)
        if self.profile.weapon_confidence_threshold >= 1.0:
            return

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

        # Doctrine: salvo coordination -- wait if coordinator says
        # it's not our turn yet.
        if self._salvo_coordinator:
            if not self._salvo_coordinator.should_fire_now(
                self.ship.id, contact_id, self._last_sim_time,
            ):
                return  # Hold fire for coordinated salvo

        # Doctrine: conservative fire mode -- when ammo is low,
        # only fire when the firing solution confidence is high
        # enough to be worth the round.
        if self._retreat.conservative_fire:
            combat = self.ship.systems.get("combat")
            if combat:
                # Check if any weapon has a high-confidence solution
                has_good_solution = False
                for weapon in combat.truth_weapons.values():
                    sol = weapon.current_solution
                    if sol and sol.confidence >= 0.8:
                        has_good_solution = True
                        break
                if not has_good_solution:
                    return  # Save ammo for a better shot

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

    def _emit_distress(self):
        """Publish a distress_signal event so escort AI can react.

        Only emits once per flee episode to avoid spamming the bus.
        """
        if self._distress_emitted:
            return
        self._distress_emitted = True

        if hasattr(self.ship, "event_bus"):
            self.ship.event_bus.publish("distress_signal", {
                "ship_id": self.ship.id,
                "position": self.ship.position,
                "faction": getattr(self.ship, "faction", "unknown"),
            })
            logger.info("AI %s: Distress signal emitted", self.ship.id)

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

    # ── Doctrine helpers ────────────────────────────────────────────

    def _get_hostile_contacts_tactical(self) -> List[Tuple[str, object]]:
        """Get hostile contacts with tactical prioritization.

        Uses the spread-fire logic to avoid all AI ships dogpiling
        the same target.  Falls back to the base prioritization if
        _all_ships_ref is not available.

        Returns:
            List of (contact_id, ContactData) sorted by tactical score.
        """
        from hybrid.fleet.faction_rules import get_diplomatic_state, DiplomaticState

        sensors = self.ship.systems.get("sensors")
        if not sensors or not hasattr(sensors, "contact_tracker"):
            return []

        sim_time = getattr(sensors, "sim_time", self._last_sim_time)
        contacts = sensors.contact_tracker.get_all_contacts(sim_time)

        hostile = []
        for contact_id, contact in contacts.items():
            contact_faction = getattr(contact, "faction", None)
            if not contact_faction:
                continue
            diplo = get_diplomatic_state(self.ship.faction, contact_faction)
            if diplo == DiplomaticState.HOSTILE:
                hostile.append((contact_id, contact))

        if not hostile:
            return []

        # Build friendly_targets map: how many friendly AI ships
        # are already targeting each contact.
        friendly_targets = self._build_friendly_target_map()

        return AIThreatAssessment.prioritize_targets_tactical(
            hostile, self.ship, friendly_targets,
        )

    def _build_friendly_target_map(self) -> Dict[str, int]:
        """Count how many friendly AI ships target each contact.

        Scans _all_ships_ref for same-faction AI ships and checks
        their current_target.

        Returns:
            Dict of {contact_id: count_of_friendly_engagements}.
        """
        from hybrid.fleet.faction_rules import are_allied

        counts: Dict[str, int] = {}
        all_ships = getattr(self.ship, "_all_ships_ref", None) or []

        for other in all_ships:
            if other.id == self.ship.id:
                continue
            if not getattr(other, "ai_enabled", False):
                continue
            if not are_allied(
                getattr(self.ship, "faction", ""),
                getattr(other, "faction", ""),
            ):
                continue

            ai = getattr(other, "ai_controller", None)
            if ai and ai.current_target:
                target_cid = ai.current_target[0]
                counts[target_cid] = counts.get(target_cid, 0) + 1

        return counts

    def _apply_evasion_jink(self, range_to_target: float) -> None:
        """Apply evasion doctrine heading change if due.

        Calculates whether a jink is needed based on railgun ToF
        at current range, and if so applies a random heading offset
        through the navigation system.

        Args:
            range_to_target: Distance to closest threat in metres.
        """
        jink_angle = should_jink(
            self._evasion_state, range_to_target, self._last_sim_time,
        )
        if jink_angle is None:
            return

        # Apply heading change through navigation system
        nav = self.ship.systems.get("navigation")
        if not nav or not hasattr(nav, "command"):
            return

        # Get current heading and offset it by jink_angle degrees.
        # This uses the same heading command as manual flight.
        current_heading = getattr(self.ship, "heading", 0.0)
        new_heading = (current_heading + jink_angle) % 360.0

        try:
            nav.command("set_heading", {
                "heading": new_heading,
                "ship": self.ship,
                "_ship": self.ship,
                "_from_autopilot": True,
            })
            logger.debug(
                "AI %s: Evasion jink %.0f° (heading %.0f → %.0f)",
                self.ship.id, jink_angle, current_heading, new_heading,
            )
        except Exception as e:
            logger.warning("AI %s: Jink command failed: %s", self.ship.id, e)

    def _launch_rearguard(self, threat_tuple: Tuple[str, object]) -> None:
        """Launch torpedoes or missiles as rearguard during retreat.

        Only fires if the ship has ordnance loaded and the launcher
        is not on cooldown.  Freighters skip this (no weapons).

        Args:
            threat_tuple: (contact_id, ContactData) of the pursuer.
        """
        if self.profile.weapon_confidence_threshold >= 1.0:
            return  # Freighters don't fire

        combat = self.ship.systems.get("combat")
        if not combat:
            return

        contact_id, _ = threat_tuple

        # Build ships dict for target resolution
        all_ships = getattr(self.ship, "_all_ships_ref", None) or []
        ships_dict = {s.id: s for s in all_ships}

        # Prefer torpedoes (heavier ordnance, better deterrent)
        if combat.torpedoes_loaded > 0 and combat._torpedo_cooldown <= 0:
            combat.launch_torpedo(contact_id, "direct", ships_dict)
            logger.info("AI %s: Rearguard torpedo launched at %s", self.ship.id, contact_id)
        elif combat.missiles_loaded > 0 and combat._missile_cooldown <= 0:
            combat.launch_missile(contact_id, "evasive", ships_dict)
            logger.info("AI %s: Rearguard missile launched at %s", self.ship.id, contact_id)

    def set_salvo_coordinator(self, coordinator: SalvoCoordinator) -> None:
        """Attach a shared salvo coordinator for multi-ship fire timing.

        Called by FleetManager or scenario setup to enable coordinated
        salvos among AI ships on the same faction.

        Args:
            coordinator: Shared SalvoCoordinator instance.
        """
        self._salvo_coordinator = coordinator

    # ── Utility helpers ───────────────────────────────────────────

    def _distance_to(self, obj) -> float:
        """Distance in metres from own ship to another object.

        Args:
            obj: Object with a position attribute (Ship or ContactData).

        Returns:
            Distance in metres.
        """
        target_pos = self._get_position(obj)
        own_pos = self._get_position(self.ship)
        return float(np.linalg.norm(target_pos - own_pos))

    def _is_threat_near_ward(
        self,
        threat_tuple: Tuple[str, object],
        ward_id: str,
        proximity: float = 50_000.0,
    ) -> bool:
        """Check if a threat is within proximity of the protected ship.

        Args:
            threat_tuple: (contact_id, ContactData) of the threat.
            ward_id: Ship ID of the protected ship.
            proximity: Distance threshold in metres (default 50km).

        Returns:
            True if the threat is within proximity of the ward.
        """
        ward = self._get_ship_or_contact(ward_id)
        if not ward:
            return False
        _, contact = threat_tuple
        threat_pos = self._get_position(contact)
        ward_pos = self._get_position(ward)
        return float(np.linalg.norm(threat_pos - ward_pos)) < proximity

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
            dict: Current AI state including role and profile info.
        """
        target_id = None
        if self.current_target:
            target_id = self.current_target[0]

        return {
            "behavior": self.behavior.value,
            "current_target": target_id,
            "waypoint_index": self.current_waypoint_index,
            "total_waypoints": len(self.waypoints),
            "role": self.profile.role,
            "hull_fraction": round(self._get_hull_fraction(), 2),
            "fuel_fraction": round(self._get_fuel_fraction(), 2),
            "dv_margin": round(self._get_delta_v_margin(), 2)
                         if self._get_delta_v_margin() != float("inf")
                         else None,
            # Doctrine state (Phase 3)
            "doctrine": {
                "conservative_fire": self._retreat.conservative_fire,
                "retreat_reason": self._retreat.reason or None,
                "jink_count": self._evasion_state.jink_count,
                "salvo_coordinated": self._salvo_coordinator is not None,
            },
        }
