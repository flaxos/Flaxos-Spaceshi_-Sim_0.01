# hybrid/systems/combat/torpedo_manager.py
"""Torpedo manager for guided, self-propelled munitions.

Torpedoes are fundamentally different from railgun slugs:
- They have their own drive, fuel, and guidance system
- They accelerate toward the target using onboard guidance
- They can receive datalink updates from the launching ship
- They are interceptable by PDCs (the primary PDC role)
- Their warheads are explosive/fragmentation — area-effect damage

Torpedo effectiveness depends on:
- Launch geometry (closing speed matters — head-on is harder to intercept)
- Target PDC coverage and ammunition
- Torpedo fuel budget (limited delta-v for terminal maneuvers)
- Whether the target detects the launch (IR signature from drive)

Physics model:
- Mass: 250 kg (warhead 50kg, drive 80kg, fuel 60kg, structure 60kg)
- Thrust: 8 kN (gives ~32 m/s² at full mass, ~42 m/s² fuel-depleted)
- ISP: 2000s (lower than ship drives — compact thruster)
- Delta-v: ~4,600 m/s (enough for terminal maneuvers, not cross-system)
- Terminal velocity: inherited from launcher + own burn
- Warhead: 50 kg fragmentation — blast radius 100m, lethal within 30m
"""

import math
import logging
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum

from hybrid.core.event_bus import EventBus
from hybrid.utils.math_utils import (
    magnitude, subtract_vectors, calculate_distance,
    dot_product, normalize_vector, add_vectors, scale_vector,
)
from hybrid.systems.combat.hit_location import compute_hit_location

logger = logging.getLogger(__name__)


class TorpedoState(Enum):
    """Torpedo flight states."""
    BOOST = "boost"          # Initial acceleration phase after launch
    MIDCOURSE = "midcourse"  # Coasting / periodic corrections
    TERMINAL = "terminal"    # Final approach — max thrust, evasive
    DETONATED = "detonated"  # Warhead triggered (proximity or impact)
    INTERCEPTED = "intercepted"  # Destroyed by PDC fire
    EXPIRED = "expired"      # Fuel exhausted or lifetime exceeded


# --- Torpedo physical specifications ---

TORPEDO_MASS = 250.0          # kg total
TORPEDO_WARHEAD_MASS = 50.0   # kg explosive/fragmentation
TORPEDO_FUEL_MASS = 60.0      # kg propellant
TORPEDO_DRY_MASS = TORPEDO_MASS - TORPEDO_FUEL_MASS  # 190 kg without fuel
TORPEDO_THRUST = 8000.0       # Newtons
TORPEDO_ISP = 2000.0          # seconds (compact thruster)
TORPEDO_EXHAUST_VEL = TORPEDO_ISP * 9.81  # ~19,620 m/s
TORPEDO_MAX_DELTA_V = TORPEDO_EXHAUST_VEL * math.log(TORPEDO_MASS / TORPEDO_DRY_MASS)

# Engagement parameters
TORPEDO_ARM_DISTANCE = 500.0     # meters — minimum arming distance
TORPEDO_PROXIMITY_FUSE = 30.0    # meters — detonation radius
TORPEDO_BLAST_RADIUS = 100.0     # meters — fragmentation effective radius
TORPEDO_LETHAL_RADIUS = 30.0     # meters — heavy damage zone
TORPEDO_MAX_LIFETIME = 120.0     # seconds — fuel + guidance timeout
TORPEDO_TERMINAL_RANGE = 5000.0  # meters — switch to terminal phase
TORPEDO_HIT_RADIUS = 50.0       # meters — intercept detection (same as projectiles)

# IR signature when thrusting (visible to passive sensors)
TORPEDO_THRUST_IR = 500_000.0    # 500 kW — small but hot drive plume
TORPEDO_COAST_IR = 100.0         # 100 W — hull thermal only
TORPEDO_RCS_M2 = 0.1            # Radar cross-section — very small

# Warhead damage values
WARHEAD_BASE_DAMAGE = 60.0      # Hull damage at lethal radius
WARHEAD_SUBSYSTEM_DAMAGE = 20.0 # Per-subsystem damage at lethal radius
WARHEAD_ARMOR_PEN = 0.8         # Fragmentation — moderate vs armor


@dataclass
class Torpedo:
    """A self-propelled guided torpedo in flight."""
    id: str
    shooter_id: str
    target_id: str

    # Kinematics
    position: Dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0, "z": 0})
    velocity: Dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0, "z": 0})
    acceleration: Dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0, "z": 0})

    # Physical state
    mass: float = TORPEDO_MASS
    fuel: float = TORPEDO_FUEL_MASS
    thrust: float = TORPEDO_THRUST

    # Flight state
    state: TorpedoState = TorpedoState.BOOST
    spawn_time: float = 0.0
    alive: bool = True
    armed: bool = False  # Arms after travelling ARM_DISTANCE from launch

    # Guidance
    launch_position: Dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0, "z": 0})
    last_target_pos: Dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0, "z": 0})
    last_target_vel: Dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0, "z": 0})
    datalink_active: bool = True  # Can receive targeting updates from launcher

    # Launch profile
    profile: str = "direct"  # "direct" = straight at target, "evasive" = serpentine approach

    # Damage tracking (for PDC interception)
    hull_health: float = 100.0   # PDC hits degrade this
    max_hull_health: float = 100.0

    # Delta-v tracking
    delta_v_used: float = 0.0
    delta_v_budget: float = TORPEDO_MAX_DELTA_V


class TorpedoManager:
    """Manages in-flight torpedoes with guidance, fuel, and interception.

    Each tick:
    1. Update torpedo guidance (compute thrust vector toward target)
    2. Apply thrust and consume fuel (Tsiolkovsky-consistent)
    3. Advance positions
    4. Check proximity detonation against target
    5. Check PDC interception (torpedoes are valid PDC targets)
    6. Apply warhead damage on detonation
    """

    def __init__(self):
        self._torpedoes: List[Torpedo] = []
        self._next_id = 1
        self._event_bus = EventBus.get_instance()

    @property
    def active_count(self) -> int:
        """Number of torpedoes currently in flight."""
        return len(self._torpedoes)

    def spawn(
        self,
        shooter_id: str,
        target_id: str,
        position: Dict[str, float],
        velocity: Dict[str, float],
        sim_time: float,
        target_pos: Dict[str, float],
        target_vel: Dict[str, float],
        profile: str = "direct",
    ) -> Torpedo:
        """Launch a new torpedo.

        Args:
            shooter_id: Ship ID that launched
            target_id: Target ship ID
            position: Launch position {x, y, z}
            velocity: Initial velocity (inherited from launcher) {x, y, z}
            sim_time: Current simulation time
            target_pos: Target position at launch
            target_vel: Target velocity at launch
            profile: Attack profile ("direct" or "evasive")

        Returns:
            The spawned Torpedo
        """
        torpedo = Torpedo(
            id=f"torp_{self._next_id}",
            shooter_id=shooter_id,
            target_id=target_id,
            position=dict(position),
            velocity=dict(velocity),
            mass=TORPEDO_MASS,
            fuel=TORPEDO_FUEL_MASS,
            thrust=TORPEDO_THRUST,
            state=TorpedoState.BOOST,
            spawn_time=sim_time,
            launch_position=dict(position),
            last_target_pos=dict(target_pos),
            last_target_vel=dict(target_vel),
            profile=profile,
        )
        self._next_id += 1
        self._torpedoes.append(torpedo)

        self._event_bus.publish("torpedo_launched", {
            "torpedo_id": torpedo.id,
            "shooter": shooter_id,
            "target": target_id,
            "position": torpedo.position,
            "profile": profile,
        })

        return torpedo

    def tick(self, dt: float, sim_time: float, ships: dict) -> List[dict]:
        """Advance all torpedoes and check for detonation/interception.

        Args:
            dt: Time step in seconds
            sim_time: Current simulation time
            ships: Dict of ship_id -> Ship objects

        Returns:
            List of detonation/interception event dicts
        """
        events = []
        surviving = []

        for torpedo in self._torpedoes:
            if not torpedo.alive:
                continue

            age = sim_time - torpedo.spawn_time
            if age > TORPEDO_MAX_LIFETIME:
                torpedo.alive = False
                torpedo.state = TorpedoState.EXPIRED
                self._event_bus.publish("torpedo_expired", {
                    "torpedo_id": torpedo.id,
                    "shooter": torpedo.shooter_id,
                    "target": torpedo.target_id,
                    "flight_time": age,
                })
                continue

            # Update datalink — get fresh target data from launching ship
            self._update_datalink(torpedo, ships)

            # Get target ship
            target_ship = ships.get(torpedo.target_id)

            # Update guidance and apply thrust
            self._update_guidance(torpedo, target_ship, dt, sim_time)

            # Advance position (Euler integration — fine for guided munitions)
            old_pos = dict(torpedo.position)
            torpedo.position["x"] += torpedo.velocity["x"] * dt
            torpedo.position["y"] += torpedo.velocity["y"] * dt
            torpedo.position["z"] += torpedo.velocity["z"] * dt

            # Check arming distance
            if not torpedo.armed:
                dist_from_launch = calculate_distance(torpedo.position, torpedo.launch_position)
                if dist_from_launch >= TORPEDO_ARM_DISTANCE:
                    torpedo.armed = True

            # Check proximity detonation against target.
            # Two checks are needed:
            # 1) Swept-line test — did the torpedo pass through the fuse
            #    zone during this tick's position advance?
            # 2) Predictive closest-approach — will the torpedo reach the
            #    fuse zone on its current trajectory?  Real proximity fuses
            #    fire when they detect minimum range is imminent and within
            #    lethal distance.  Without this, a fast torpedo can be many
            #    ticks away from the target at each check but still clearly
            #    on a collision course.
            if target_ship and torpedo.armed:
                # --- Swept-line check (handles pass-through in one tick) ---
                closest_dist, closest_point = self._swept_closest_approach(
                    old_pos, torpedo.position, target_ship.position
                )
                if closest_dist <= TORPEDO_PROXIMITY_FUSE:
                    torpedo.position = closest_point
                    event = self._detonate(torpedo, target_ship, sim_time, closest_dist, ships)
                    events.append(event)
                    continue

                # --- Predictive proximity fuse ---
                # A real proximity fuse triggers when it detects that the
                # torpedo has reached (or is about to reach) its closest
                # approach to the target and that distance is within the
                # fuse radius.  We model this by computing the time of
                # closest approach (TCA) from current relative kinematics.
                # If the predicted miss distance is within fuse range, we
                # detonate at that point — the fuse has done its job.
                pred_dist, pred_point, tca = self._predict_closest_approach(
                    torpedo, target_ship
                )
                if pred_dist <= TORPEDO_PROXIMITY_FUSE and tca > 0:
                    # Advance torpedo to the detonation point
                    torpedo.position = pred_point
                    event = self._detonate(torpedo, target_ship, sim_time + tca, pred_dist, ships)
                    events.append(event)
                    continue

            # Check if torpedo is out of fuel and past target
            if torpedo.fuel <= 0 and target_ship:
                dist = calculate_distance(torpedo.position, target_ship.position)
                # If torpedo is moving away from target and out of fuel, expire
                rel_vel = subtract_vectors(torpedo.velocity, target_ship.velocity)
                rel_pos = subtract_vectors(torpedo.position, target_ship.position)
                closing = -(dot_product(rel_vel, rel_pos) / max(1.0, magnitude(rel_pos)))
                if closing < 0 and dist > TORPEDO_BLAST_RADIUS:
                    torpedo.alive = False
                    torpedo.state = TorpedoState.EXPIRED
                    self._event_bus.publish("torpedo_expired", {
                        "torpedo_id": torpedo.id,
                        "shooter": torpedo.shooter_id,
                        "target": torpedo.target_id,
                        "reason": "fuel_exhausted_past_target",
                        "flight_time": age,
                    })
                    continue

            surviving.append(torpedo)

        self._torpedoes = surviving
        return events

    def _update_datalink(self, torpedo: Torpedo, ships: dict):
        """Update torpedo guidance data via datalink from launching ship.

        If the launching ship still exists and has a sensor lock on the
        target, the torpedo receives updated target position/velocity.
        """
        if not torpedo.datalink_active:
            return

        launcher = ships.get(torpedo.shooter_id)
        if not launcher:
            torpedo.datalink_active = False
            return

        # Check if launcher still has sensor data on target.
        # targeting.locked_target is a contact ID (e.g. "C001") while
        # torpedo.target_id is a real ship ID (e.g. "pirate01").  Resolve
        # via the contact tracker's id_mapping for comparison.
        targeting = launcher.systems.get("targeting") if hasattr(launcher, "systems") else None
        if targeting and hasattr(targeting, "target_data") and targeting.target_data:
            locked = targeting.locked_target
            # Direct match (both are same format) or contact-ID match
            is_match = locked == torpedo.target_id
            if not is_match:
                sensors = launcher.systems.get("sensors") if hasattr(launcher, "systems") else None
                if sensors and hasattr(sensors, "contact_tracker"):
                    stable_id = sensors.contact_tracker.id_mapping.get(torpedo.target_id)
                    is_match = (stable_id is not None and stable_id == locked)
            if is_match:
                torpedo.last_target_pos = dict(targeting.target_data.get("position", torpedo.last_target_pos))
                torpedo.last_target_vel = dict(targeting.target_data.get("velocity", torpedo.last_target_vel))
                return

        # Fallback: check sensor contacts
        sensors = launcher.systems.get("sensors") if hasattr(launcher, "systems") else None
        if sensors and hasattr(sensors, "contact_tracker"):
            # Reverse-lookup: find the stable contact ID for the torpedo's target ship ID
            tracker = sensors.contact_tracker
            stable_id = tracker.id_mapping.get(torpedo.target_id)
            if stable_id:
                contact = tracker.contacts.get(stable_id)
                if contact:
                    pos = getattr(contact, "position", None)
                    vel = getattr(contact, "velocity", None)
                    if pos:
                        torpedo.last_target_pos = dict(pos)
                    if vel:
                        torpedo.last_target_vel = dict(vel)
                    return

    def _update_guidance(self, torpedo: Torpedo, target_ship, dt: float, sim_time: float):
        """Compute and apply thrust vector for torpedo guidance.

        Guidance modes:
        - BOOST: Full thrust toward intercept point
        - MIDCOURSE: Periodic corrections, may coast to save fuel
        - TERMINAL: Max thrust, potential evasive maneuvers
        """
        if torpedo.fuel <= 0:
            torpedo.acceleration = {"x": 0, "y": 0, "z": 0}
            torpedo.state = TorpedoState.MIDCOURSE  # Coasting, no fuel
            return

        # Use actual target position if available, otherwise last known
        if target_ship:
            target_pos = target_ship.position
            target_vel = target_ship.velocity
        else:
            target_pos = torpedo.last_target_pos
            target_vel = torpedo.last_target_vel

        # Calculate intercept vector
        rel_pos = subtract_vectors(target_pos, torpedo.position)
        dist = magnitude(rel_pos)

        # State transitions
        if dist <= TORPEDO_TERMINAL_RANGE:
            torpedo.state = TorpedoState.TERMINAL
        elif torpedo.state == TorpedoState.BOOST and (sim_time - torpedo.spawn_time) > 5.0:
            torpedo.state = TorpedoState.MIDCOURSE

        # Proportional navigation — lead the target
        rel_vel = subtract_vectors(target_vel, torpedo.velocity)
        closing_speed = -dot_product(rel_vel, normalize_vector(rel_pos)) if dist > 1.0 else 0
        tgo = dist / max(1.0, abs(closing_speed)) if closing_speed > 0 else dist / max(1.0, magnitude(torpedo.velocity))

        # Predicted intercept point
        intercept = {
            "x": target_pos["x"] + target_vel["x"] * tgo,
            "y": target_pos["y"] + target_vel["y"] * tgo,
            "z": target_pos["z"] + target_vel["z"] * tgo,
        }

        # Aim vector toward intercept point
        aim_vec = subtract_vectors(intercept, torpedo.position)
        aim_dist = magnitude(aim_vec)
        if aim_dist < 1.0:
            aim_dir = normalize_vector(rel_pos) if dist > 1.0 else {"x": 1, "y": 0, "z": 0}
        else:
            aim_dir = normalize_vector(aim_vec)

        # Apply thrust based on state
        if torpedo.state == TorpedoState.TERMINAL:
            # Full thrust, no fuel conservation
            thrust_fraction = 1.0
        elif torpedo.state == TorpedoState.MIDCOURSE:
            # Save fuel — only thrust when correction needed
            # Coast if roughly on course (aim angle < 5 degrees from velocity)
            vel_dir = normalize_vector(torpedo.velocity) if magnitude(torpedo.velocity) > 1.0 else aim_dir
            cos_angle = dot_product(vel_dir, aim_dir)
            if cos_angle > 0.996:  # ~5 degrees
                thrust_fraction = 0.0  # On course, coast
            else:
                thrust_fraction = 0.5  # Correction burn
        else:
            # BOOST — full thrust
            thrust_fraction = 1.0

        # Apply thrust and consume fuel
        if thrust_fraction > 0:
            actual_thrust = torpedo.thrust * thrust_fraction
            accel_mag = actual_thrust / torpedo.mass

            torpedo.acceleration = {
                "x": aim_dir["x"] * accel_mag,
                "y": aim_dir["y"] * accel_mag,
                "z": aim_dir["z"] * accel_mag,
            }

            # Apply acceleration to velocity
            torpedo.velocity["x"] += torpedo.acceleration["x"] * dt
            torpedo.velocity["y"] += torpedo.acceleration["y"] * dt
            torpedo.velocity["z"] += torpedo.acceleration["z"] * dt

            # Consume fuel (Tsiolkovsky-consistent)
            mass_flow = actual_thrust / TORPEDO_EXHAUST_VEL
            fuel_consumed = mass_flow * dt
            fuel_consumed = min(fuel_consumed, torpedo.fuel)
            torpedo.fuel -= fuel_consumed
            torpedo.mass -= fuel_consumed
            torpedo.delta_v_used += accel_mag * dt
        else:
            torpedo.acceleration = {"x": 0, "y": 0, "z": 0}

    def _detonate(
        self, torpedo: Torpedo, target_ship, sim_time: float,
        impact_distance: float, ships: dict,
    ) -> dict:
        """Detonate torpedo warhead with area-effect damage.

        Fragmentation warhead damages multiple subsystems based on
        proximity. Closer detonation = more damage. Subsystems near
        the impact face take extra damage.

        Args:
            torpedo: Detonating torpedo
            target_ship: Primary target ship
            sim_time: Current simulation time
            impact_distance: Distance from target at detonation
            ships: All ships (for area-effect on nearby ships)

        Returns:
            Detonation event dict
        """
        torpedo.alive = False
        torpedo.state = TorpedoState.DETONATED

        flight_time = sim_time - torpedo.spawn_time

        # Damage scales with proximity (inverse square, capped)
        # At lethal radius (30m): full damage
        # At blast radius (100m): ~10% damage
        # Beyond blast radius: no damage
        damage_results = []

        # Check all ships within blast radius
        for ship_id, ship in ships.items():
            if ship_id == torpedo.shooter_id:
                continue  # Don't damage own ship

            dist = calculate_distance(torpedo.position, ship.position)
            if dist > TORPEDO_BLAST_RADIUS:
                continue

            # Damage falloff: inverse-square from lethal radius
            if dist <= TORPEDO_LETHAL_RADIUS:
                damage_factor = 1.0
            else:
                damage_factor = (TORPEDO_LETHAL_RADIUS / dist) ** 2
                damage_factor = max(0.1, min(1.0, damage_factor))

            hull_damage = WARHEAD_BASE_DAMAGE * damage_factor
            sub_damage = WARHEAD_SUBSYSTEM_DAMAGE * damage_factor

            # Area-effect: damage multiple subsystems
            # Fragmentation hits everything on the facing side
            subsystems_hit = self._determine_blast_subsystems(torpedo, ship)

            result = {"ship_id": ship_id, "distance": dist, "damage_factor": damage_factor}

            if hasattr(ship, "take_damage"):
                dmg_result = ship.take_damage(
                    hull_damage,
                    source=f"{torpedo.shooter_id}:torpedo",
                )
                result["hull_damage"] = hull_damage
                result["damage_result"] = dmg_result

            # Apply subsystem damage to each affected subsystem
            result["subsystems_hit"] = []
            if hasattr(ship, "damage_model"):
                for subsystem in subsystems_hit:
                    ship.damage_model.apply_damage(subsystem, sub_damage)
                    result["subsystems_hit"].append({
                        "subsystem": subsystem,
                        "damage": sub_damage,
                    })

            damage_results.append(result)

        # Build event
        event = {
            "type": "torpedo_detonation",
            "torpedo_id": torpedo.id,
            "shooter": torpedo.shooter_id,
            "target": torpedo.target_id,
            "position": torpedo.position,
            "impact_distance": impact_distance,
            "flight_time": flight_time,
            "damage_results": damage_results,
            "feedback": self._generate_detonation_feedback(
                torpedo, target_ship, impact_distance, flight_time, damage_results
            ),
        }

        self._event_bus.publish("torpedo_detonation", event)
        return event

    @staticmethod
    def _swept_closest_approach(
        seg_start: Dict[str, float],
        seg_end: Dict[str, float],
        point: Dict[str, float],
    ) -> Tuple[float, Dict[str, float]]:
        """Find closest approach of a line segment to a point.

        Used for proximity-fuse checks so that a fast torpedo cannot
        skip over the detonation zone between ticks.  Projects the
        target point onto the segment [seg_start, seg_end] and clamps
        to the segment endpoints.

        Returns:
            (distance, closest_point_on_segment)
        """
        dx = seg_end["x"] - seg_start["x"]
        dy = seg_end["y"] - seg_start["y"]
        dz = seg_end["z"] - seg_start["z"]
        seg_len_sq = dx * dx + dy * dy + dz * dz

        if seg_len_sq < 1e-12:
            # Torpedo barely moved this tick — just use endpoint
            return calculate_distance(seg_end, point), dict(seg_end)

        # Parameter t: projection of (point - seg_start) onto segment
        t = (
            (point["x"] - seg_start["x"]) * dx
            + (point["y"] - seg_start["y"]) * dy
            + (point["z"] - seg_start["z"]) * dz
        ) / seg_len_sq
        t = max(0.0, min(1.0, t))

        closest = {
            "x": seg_start["x"] + t * dx,
            "y": seg_start["y"] + t * dy,
            "z": seg_start["z"] + t * dz,
        }
        return calculate_distance(closest, point), closest

    @staticmethod
    def _predict_closest_approach(
        torpedo: "Torpedo", target_ship,
    ) -> Tuple[float, Dict[str, float], float]:
        """Predict closest approach using current relative kinematics.

        Models the proximity fuse's onboard computer: given current
        positions and velocities, compute when the torpedo will be
        closest to the target (time of closest approach) and the miss
        distance at that moment.  This lets the fuse fire even when
        discrete tick checks would otherwise miss the detonation window.

        Assumes constant velocity over the prediction horizon (thrust
        changes are small relative to closing speed).

        Returns:
            (predicted_distance, predicted_torpedo_position, time_to_closest_approach)
        """
        rel_pos = subtract_vectors(torpedo.position, target_ship.position)
        rel_vel = subtract_vectors(torpedo.velocity, target_ship.velocity)

        vel_sq = dot_product(rel_vel, rel_vel)
        if vel_sq < 1e-12:
            # Not closing — return current distance
            dist = magnitude(rel_pos)
            return dist, dict(torpedo.position), 0.0

        # TCA: t = -dot(rel_pos, rel_vel) / dot(rel_vel, rel_vel)
        tca = -dot_product(rel_pos, rel_vel) / vel_sq
        if tca <= 0:
            # Closest approach was in the past — already diverging
            dist = magnitude(rel_pos)
            return dist, dict(torpedo.position), 0.0

        # Position at TCA
        pred_pos = {
            "x": torpedo.position["x"] + torpedo.velocity["x"] * tca,
            "y": torpedo.position["y"] + torpedo.velocity["y"] * tca,
            "z": torpedo.position["z"] + torpedo.velocity["z"] * tca,
        }
        target_at_tca = {
            "x": target_ship.position["x"] + target_ship.velocity["x"] * tca,
            "y": target_ship.position["y"] + target_ship.velocity["y"] * tca,
            "z": target_ship.position["z"] + target_ship.velocity["z"] * tca,
        }
        pred_dist = calculate_distance(pred_pos, target_at_tca)
        return pred_dist, pred_pos, tca

    def _determine_blast_subsystems(self, torpedo: Torpedo, ship) -> List[str]:
        """Determine which subsystems are affected by torpedo blast.

        Fragmentation warheads damage multiple systems on the facing side.
        Uses approach vector to determine which section of the ship faces
        the torpedo, then selects subsystems in that region.

        Args:
            torpedo: Detonating torpedo
            ship: Ship being damaged

        Returns:
            List of subsystem names affected by blast
        """
        # Approach direction: torpedo position -> ship position
        approach = subtract_vectors(ship.position, torpedo.position)
        dist = magnitude(approach)
        if dist < 1.0:
            # Point-blank — hits everything
            subsystems = ["propulsion", "sensors", "weapons", "rcs", "reactor"]
            return subsystems[:3]  # Cap at 3 for balance

        approach_dir = normalize_vector(approach)

        # Determine facing section based on approach direction
        # This is simplified — we pick 2-3 subsystems based on where
        # the blast wave hits
        ax, ay, az = abs(approach_dir["x"]), abs(approach_dir["y"]), abs(approach_dir["z"])

        affected = []
        if approach_dir["x"] > 0.3:
            # Coming from fore — hits sensors, weapons (forward-mounted)
            affected.extend(["sensors", "weapons"])
        elif approach_dir["x"] < -0.3:
            # Coming from aft — hits propulsion, reactor
            affected.extend(["propulsion", "reactor"])

        if ay > 0.3:
            # Broadside — hits weapons, rcs
            affected.extend(["weapons", "rcs"])

        if az > 0.3:
            # Dorsal/ventral — hits radiators, rcs
            affected.extend(["radiators", "rcs"])

        # De-duplicate and cap at 3
        seen = set()
        unique = []
        for s in affected:
            if s not in seen:
                seen.add(s)
                unique.append(s)
        if not unique:
            unique = ["weapons", "sensors"]  # Default if geometry unclear

        return unique[:3]

    def _generate_detonation_feedback(
        self, torpedo: Torpedo, target_ship, impact_distance: float,
        flight_time: float, damage_results: List[dict],
    ) -> str:
        """Generate human-readable feedback for torpedo detonation.

        Args:
            torpedo: Detonating torpedo
            target_ship: Primary target
            impact_distance: Distance at detonation
            flight_time: Total flight time
            damage_results: List of ships damaged

        Returns:
            Human-readable feedback string
        """
        target_name = getattr(target_ship, "name", torpedo.target_id) if target_ship else torpedo.target_id

        if impact_distance <= TORPEDO_LETHAL_RADIUS:
            proximity = "point-blank detonation"
        elif impact_distance <= TORPEDO_PROXIMITY_FUSE:
            proximity = f"proximity detonation at {impact_distance:.0f}m"
        else:
            proximity = f"blast at {impact_distance:.0f}m range"

        ships_hit = len(damage_results)
        subsystems_total = sum(len(r.get("subsystems_hit", [])) for r in damage_results)

        feedback = f"Torpedo impact — {proximity} on {target_name}"
        feedback += f", {flight_time:.1f}s flight time"
        if subsystems_total > 0:
            feedback += f", {subsystems_total} subsystems damaged"
        if ships_hit > 1:
            feedback += f", {ships_hit} ships in blast radius"

        return feedback

    def apply_pdc_damage(self, torpedo_id: str, damage: float, source: str = "") -> dict:
        """Apply PDC hit damage to a torpedo.

        PDCs can intercept torpedoes — this is their primary role.
        Each PDC hit degrades torpedo hull health. When health reaches
        zero, the torpedo is destroyed (intercepted).

        Args:
            torpedo_id: ID of torpedo to damage
            damage: PDC damage amount
            source: Source ship/weapon for events

        Returns:
            dict with result
        """
        for torpedo in self._torpedoes:
            if torpedo.id == torpedo_id and torpedo.alive:
                torpedo.hull_health -= damage
                if torpedo.hull_health <= 0:
                    torpedo.alive = False
                    torpedo.state = TorpedoState.INTERCEPTED
                    self._event_bus.publish("torpedo_intercepted", {
                        "torpedo_id": torpedo.id,
                        "shooter": torpedo.shooter_id,
                        "target": torpedo.target_id,
                        "intercepted_by": source,
                        "position": torpedo.position,
                    })
                    return {"ok": True, "destroyed": True, "torpedo_id": torpedo_id}
                return {
                    "ok": True,
                    "destroyed": False,
                    "torpedo_id": torpedo_id,
                    "hull_remaining": torpedo.hull_health,
                }
        return {"ok": False, "reason": "torpedo_not_found"}

    def get_torpedoes_targeting(self, ship_id: str) -> List[Torpedo]:
        """Get all torpedoes targeting a specific ship.

        Used by PDC auto-targeting to prioritize incoming torpedoes.

        Args:
            ship_id: Ship being targeted

        Returns:
            List of torpedoes targeting this ship
        """
        return [t for t in self._torpedoes if t.alive and t.target_id == ship_id]

    def get_state(self) -> List[dict]:
        """Get state of all active torpedoes for telemetry.

        Returns:
            List of torpedo state dicts with distance and ETA to target
        """
        result = []
        for t in self._torpedoes:
            if not t.alive:
                continue

            # Distance to last known target position
            dist = calculate_distance(t.position, t.last_target_pos)

            # Estimated time to impact: uses closing speed from relative
            # velocity projected onto the line-of-sight vector.
            # Negative closing speed means torpedo is diverging.
            eta = None
            rel_pos = subtract_vectors(t.last_target_pos, t.position)
            rel_vel = subtract_vectors(t.velocity, t.last_target_vel)
            dist_mag = magnitude(rel_pos)
            if dist_mag > 1.0:
                los = normalize_vector(rel_pos)
                closing_speed = dot_product(rel_vel, los)
                if closing_speed > 1.0:
                    eta = round(dist_mag / closing_speed, 1)

            result.append({
                "id": t.id,
                "shooter": t.shooter_id,
                "target": t.target_id,
                "position": t.position,
                "velocity": t.velocity,
                "state": t.state.value,
                "fuel_percent": round((t.fuel / TORPEDO_FUEL_MASS * 100) if TORPEDO_FUEL_MASS > 0 else 0, 1),
                "armed": t.armed,
                "hull_health": t.hull_health,
                "profile": t.profile,
                "alive": t.alive,
                "age": 0.0,  # Filled by caller if needed
                "distance": round(dist, 1),
                "eta": eta,
                "is_thrusting": t.fuel > 0 and t.state in (TorpedoState.BOOST, TorpedoState.TERMINAL),
                "ir_signature": TORPEDO_THRUST_IR if (t.fuel > 0 and t.state != TorpedoState.MIDCOURSE) else TORPEDO_COAST_IR,
                "rcs_m2": TORPEDO_RCS_M2,
            })
        return result

    def get_all_torpedoes(self) -> List[Torpedo]:
        """Get all active torpedo objects (for PDC targeting).

        Returns:
            List of active Torpedo objects
        """
        return [t for t in self._torpedoes if t.alive]

    def clear(self):
        """Remove all torpedoes."""
        self._torpedoes.clear()
