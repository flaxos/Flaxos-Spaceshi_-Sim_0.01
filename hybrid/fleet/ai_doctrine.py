"""AI doctrine system for coordinated tactical behaviors.

Provides salvo coordination, evasion jinking, retreat conditions,
and ammo conservation.  Called from AIController -- the doctrine
layer makes DECISIONS, it does not issue commands directly.
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Railgun muzzle velocity in m/s (20 km/s per spec)
RAILGUN_VELOCITY = 20_000.0

# Window within which coordinated rounds should arrive (seconds)
SALVO_ARRIVAL_WINDOW = 2.0


# ── Coordinated Salvos ─────────────────────────────────────────────

@dataclass
class SalvoSlot:
    """Per-ship timing slot in a coordinated salvo."""
    ship_id: str
    time_of_flight: float
    scheduled_fire_time: float  # sim_time at which this ship should fire


@dataclass
class SalvoCoordination:
    """Active salvo coordination for a target."""
    target_id: str
    slots: List[SalvoSlot] = field(default_factory=list)
    created_at: float = 0.0
    # Stale after 10s -- if nobody fired, discard and re-plan
    expiry: float = 10.0


class SalvoCoordinator:
    """Coordinates railgun fire timing across friendly AI ships.

    The ship with the LONGEST time-of-flight fires first; others
    delay so rounds arrive within SALVO_ARRIVAL_WINDOW.
    """

    def __init__(self) -> None:
        # {target_id: SalvoCoordination}
        self._active: Dict[str, SalvoCoordination] = {}

    def plan_salvo(
        self,
        target_id: str,
        participants: List[Tuple[str, float]],
        sim_time: float,
    ) -> Optional[SalvoCoordination]:
        """Plan a coordinated salvo.

        Args:
            target_id: Contact ID of the shared target.
            participants: List of (ship_id, distance_to_target_m) tuples.
            sim_time: Current simulation time.

        Returns:
            SalvoCoordination if 2+ ships can participate, else None.
        """
        if len(participants) < 2:
            return None

        # Calculate time-of-flight for each ship's railgun round
        tof_list: List[Tuple[str, float]] = []
        for ship_id, distance in participants:
            tof = distance / RAILGUN_VELOCITY
            tof_list.append((ship_id, tof))

        # The longest ToF dictates the arrival time.  All ships
        # schedule their fire so rounds converge within the window.
        max_tof = max(tof for _, tof in tof_list)

        slots = []
        for ship_id, tof in tof_list:
            # Delay = max_tof - my_tof.  A closer ship waits longer
            # so its faster-arriving round hits at the same time.
            delay = max_tof - tof
            fire_time = sim_time + delay
            slots.append(SalvoSlot(
                ship_id=ship_id,
                time_of_flight=tof,
                scheduled_fire_time=fire_time,
            ))

        coord = SalvoCoordination(
            target_id=target_id,
            slots=slots,
            created_at=sim_time,
        )
        self._active[target_id] = coord

        logger.info(
            "Salvo planned: %d ships on %s, max_tof=%.1fs",
            len(slots), target_id, max_tof,
        )
        return coord

    def should_fire_now(
        self,
        ship_id: str,
        target_id: str,
        sim_time: float,
    ) -> bool:
        """Check if this ship should fire as part of an active salvo.

        Returns True if:
          - No salvo is planned (fire freely)
          - The ship's scheduled fire time has arrived

        Args:
            ship_id: This ship's ID.
            target_id: Contact ID being targeted.
            sim_time: Current simulation time.

        Returns:
            True if the ship should fire now.
        """
        coord = self._active.get(target_id)
        if not coord:
            return True  # No coordination -- fire at will

        # Expired salvo plan -- discard and allow fire
        if sim_time - coord.created_at > coord.expiry:
            del self._active[target_id]
            return True

        for slot in coord.slots:
            if slot.ship_id == ship_id:
                return sim_time >= slot.scheduled_fire_time

        # Ship not in the plan -- fire freely
        return True

    def clear_target(self, target_id: str) -> None:
        """Remove a salvo plan when target is destroyed or lost."""
        self._active.pop(target_id, None)

    def cleanup(self, sim_time: float) -> None:
        """Remove expired salvo plans."""
        expired = [
            tid for tid, coord in self._active.items()
            if sim_time - coord.created_at > coord.expiry
        ]
        for tid in expired:
            del self._active[tid]


# ── Evasion Doctrine ───────────────────────────────────────────────

@dataclass
class EvasionState:
    """Tracks jink pattern for a ship under fire."""
    last_jink_time: float = 0.0
    jink_clockwise: bool = True  # Alternates each jink
    jink_count: int = 0


def calculate_jink_interval(range_to_attacker_m: float) -> float:
    """Jink interval = railgun ToF at current range (clamped 1-15s).

    Change heading before the next round arrives.
    """
    tof = range_to_attacker_m / RAILGUN_VELOCITY
    return max(1.0, min(tof, 15.0))


def calculate_jink_angle(
    skill_level: float = 0.5,
    base_min: float = 10.0,
    base_max: float = 30.0,
) -> float:
    """Random heading change scaled by AI skill (higher = tighter jinks)."""
    # Skilled AI jinks just enough; unskilled over-corrects
    effective_max = base_max - (skill_level * (base_max - base_min))
    return random.uniform(base_min, effective_max)


def should_jink(
    evasion_state: EvasionState,
    range_to_attacker_m: float,
    sim_time: float,
) -> Optional[float]:
    """Determine if the ship should execute a jink maneuver now.

    Args:
        evasion_state: Current evasion tracking state.
        range_to_attacker_m: Distance to closest attacker in metres.
        sim_time: Current simulation time.

    Returns:
        Signed jink angle in degrees if a jink should happen, else None.
        Positive = clockwise, negative = counterclockwise.
    """
    interval = calculate_jink_interval(range_to_attacker_m)
    elapsed = sim_time - evasion_state.last_jink_time

    if elapsed < interval:
        return None

    # Time to jink -- calculate angle and alternate direction
    angle = calculate_jink_angle()
    if not evasion_state.jink_clockwise:
        angle = -angle

    # Update state
    evasion_state.last_jink_time = sim_time
    evasion_state.jink_clockwise = not evasion_state.jink_clockwise
    evasion_state.jink_count += 1

    return angle


# ── Retreat Conditions ─────────────────────────────────────────────

@dataclass
class RetreatAssessment:
    """Result of retreat condition evaluation."""
    should_retreat: bool = False
    reason: str = ""
    # If retreating, should we launch rearguard ordnance?
    launch_rearguard: bool = False
    # Conservative fire mode: only shoot high-confidence solutions
    conservative_fire: bool = False


def assess_retreat(
    ship,
    confidence_threshold: float = 0.8,
) -> RetreatAssessment:
    """Evaluate subsystem/ammo state for tactical retreat decisions.

    Goes beyond hull-fraction panic thresholds -- these are rational
    disengagement checks (propulsion crippled, weapons dead, ammo low).
    """
    result = RetreatAssessment()
    damage_model = getattr(ship, "damage_model", None)

    # 1. Propulsion < 50%: can't maneuver effectively
    if damage_model:
        prop_factor = damage_model.get_combined_factor("propulsion")
        if prop_factor < 0.5:
            result.should_retreat = True
            result.reason = f"propulsion_degraded ({prop_factor:.0%})"
            return result

    # 2. Weapons destroyed: no point continuing
    if damage_model:
        weapons_factor = damage_model.get_combined_factor("weapons")
        if weapons_factor <= 0.0:
            result.should_retreat = True
            result.reason = "weapons_destroyed"
            return result

    # 3. Ammo state: check total remaining across all weapons
    combat = ship.systems.get("combat")
    if combat:
        total_ammo, total_capacity = _get_ammo_fraction(combat)
        if total_capacity > 0:
            ammo_frac = total_ammo / total_capacity
            if ammo_frac < 0.20:
                result.conservative_fire = True
                result.reason = f"low_ammo ({ammo_frac:.0%})"

    return result


def _get_ammo_fraction(combat) -> Tuple[int, int]:
    """Get total remaining ammo and capacity across all weapons.

    Args:
        combat: CombatSystem instance.

    Returns:
        (remaining, capacity) tuple.
    """
    total = 0
    capacity = 0
    for weapon in combat.truth_weapons.values():
        if weapon.ammo is not None:
            total += weapon.ammo
            capacity += (weapon.specs.ammo_capacity or 0)
    # Include torpedoes and missiles
    total += combat.torpedoes_loaded + combat.missiles_loaded
    capacity += (
        combat.torpedo_tubes * combat.torpedo_capacity
        + combat.missile_launchers * combat.missile_capacity
    )
    return total, capacity
