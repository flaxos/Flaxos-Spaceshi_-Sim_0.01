# hybrid/systems/combat/torpedo_manager.py
"""Guided munition manager for torpedoes and missiles.

Both torpedoes and missiles are self-propelled guided munitions that share
launcher hardpoints. They differ in mass, acceleration, warhead, and
guidance philosophy:

Torpedoes — heavy ordnance for slow/large targets:
- Mass: 250 kg (warhead 50kg, drive 80kg, fuel 60kg, structure 60kg)
- Thrust: 8 kN (~32 m/s² at full mass)
- Burn time: ~120s. Delta-v: ~4,600 m/s
- Warhead: 50 kg fragmentation — blast radius 100m, lethal within 30m
- Guidance: proportional navigation

Missiles — light ordnance for fast maneuvering ships:
- Mass: 95 kg (warhead 10kg, drive 25kg, fuel 30kg, structure 30kg)
- Thrust: 10 kN (~105 m/s² at full mass — high-G interceptor)
- Burn time: ~53s. Delta-v: ~5,200 m/s (enough for boost + terminal at 80km)
- Warhead: 10 kg shaped charge — blast radius 30m, lethal within 10m
- Guidance: augmented PN with terminal lead correction
- Flight profiles: direct, evasive, terminal_pop, bracket

Shared traits:
- Both fire from the same launcher bays (switchable ordnance)
- Both have onboard drive, fuel, and guidance
- Both can receive datalink updates from the launching ship
- Both are interceptable by PDCs
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
    cross_product,
)
from hybrid.systems.combat.hit_location import compute_hit_location

logger = logging.getLogger(__name__)


class MunitionType(Enum):
    """Distinguishes torpedo vs missile ordnance sharing the same launcher."""
    TORPEDO = "torpedo"
    MISSILE = "missile"


class WarheadType(Enum):
    """Warhead variants for torpedoes and missiles.

    FRAGMENTATION (default): Area-effect shrapnel — wide blast, multiple
        subsystem hits. Current baseline stats for both torpedo and missile.
    SHAPED_CHARGE: Focused penetrating jet — high hull damage but tiny
        blast radius. Needs a near-direct hit but punches through armor.
    EMP: Electromagnetic pulse — minimal hull damage but temporarily
        disables subsystems (recoverable, not destroyed).
    """
    FRAGMENTATION = "fragmentation"
    SHAPED_CHARGE = "shaped_charge"
    EMP = "emp"


class GuidanceMode(Enum):
    """Guidance CPU levels for torpedoes and missiles.

    DUMB: Fire-and-forget on initial aim vector. No course corrections.
        Cheapest ordnance, immune to ECM jamming, but only hits targets
        on predictable trajectories.
    GUIDED (default): Proportional navigation with datalink updates.
        Standard guidance — effective against non-evading or slow targets.
    SMART: Enhanced terminal guidance with evasion prediction. The onboard
        CPU models target acceleration history and predicts jinking patterns.
        Harder to defeat with ECM but still defeated by chaff at close range.
    """
    DUMB = "dumb"
    GUIDED = "guided"
    SMART = "smart"


# Per-warhead-type damage specs for torpedoes.
# Keys: hull_damage, subsystem_damage, lethal_radius, blast_radius,
#       subsystem_disable_duration (seconds, EMP only), max_subsystems_disabled.
TORPEDO_WARHEAD_SPECS: Dict[str, Dict[str, float]] = {
    WarheadType.FRAGMENTATION.value: {
        "hull_damage": 60.0,
        "subsystem_damage": 20.0,
        "lethal_radius": 30.0,
        "blast_radius": 100.0,
        "subsystem_disable_duration": 0.0,
        "max_subsystems_disabled": 0,
    },
    WarheadType.SHAPED_CHARGE.value: {
        "hull_damage": 80.0,
        "subsystem_damage": 20.0,
        "lethal_radius": 10.0,
        "blast_radius": 20.0,
        "subsystem_disable_duration": 0.0,
        "max_subsystems_disabled": 0,
    },
    WarheadType.EMP.value: {
        "hull_damage": 20.0,
        "subsystem_damage": 5.0,
        "lethal_radius": 30.0,
        "blast_radius": 100.0,
        "subsystem_disable_duration": 30.0,
        "max_subsystems_disabled": 2,
    },
}

# Per-warhead-type damage specs for missiles.
MISSILE_WARHEAD_SPECS: Dict[str, Dict[str, float]] = {
    WarheadType.FRAGMENTATION.value: {
        "hull_damage": 25.0,
        "subsystem_damage": 15.0,
        "lethal_radius": 10.0,
        "blast_radius": 30.0,
        "subsystem_disable_duration": 0.0,
        "max_subsystems_disabled": 0,
    },
    WarheadType.SHAPED_CHARGE.value: {
        "hull_damage": 40.0,
        "subsystem_damage": 15.0,
        "lethal_radius": 5.0,
        "blast_radius": 10.0,
        "subsystem_disable_duration": 0.0,
        "max_subsystems_disabled": 0,
    },
    WarheadType.EMP.value: {
        "hull_damage": 10.0,
        "subsystem_damage": 5.0,
        "lethal_radius": 10.0,
        "blast_radius": 30.0,
        "subsystem_disable_duration": 20.0,
        "max_subsystems_disabled": 1,
    },
}


class TorpedoState(Enum):
    """Flight states for both torpedoes and missiles."""
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


# --- Missile physical specifications ---
# Missiles are lighter, higher-G, shorter burn, smaller warhead.
# Designed to chase fast maneuvering ships that torpedoes cannot catch.
# The high thrust-to-mass ratio (150 m/s^2) lets them match corvette
# evasive maneuvers, but the small fuel load means they burn out fast.

MISSILE_MASS = 95.0              # kg total (heavier fuel load for 40-80km engagements)
MISSILE_WARHEAD_MASS = 10.0      # kg shaped charge
MISSILE_FUEL_MASS = 30.0         # kg propellant — doubled from 15 to sustain boost+terminal
MISSILE_DRY_MASS = MISSILE_MASS - MISSILE_FUEL_MASS  # 65 kg without fuel
MISSILE_THRUST = 10000.0         # Newtons — high-G motor (reduced from 12kN to extend burn)
MISSILE_ISP = 1800.0             # seconds (optimised for impulse, not efficiency)
MISSILE_EXHAUST_VEL = MISSILE_ISP * 9.81  # ~17,658 m/s
MISSILE_MAX_DELTA_V = MISSILE_EXHAUST_VEL * math.log(MISSILE_MASS / MISSILE_DRY_MASS)

# Engagement parameters — tighter fuse, smaller blast, shorter life
MISSILE_ARM_DISTANCE = 300.0     # meters — arms faster than torpedoes
MISSILE_PROXIMITY_FUSE = 10.0    # meters — smaller fuse radius (direct-hit weapon)
MISSILE_BLAST_RADIUS = 30.0      # meters — shaped charge, not area-effect
MISSILE_LETHAL_RADIUS = 10.0     # meters — tight kill zone
MISSILE_MAX_LIFETIME = 90.0      # seconds — extended to match larger fuel load
MISSILE_TERMINAL_RANGE = 3000.0  # meters — enters terminal phase closer
MISSILE_G_LIMIT = 80.0           # G tolerance — structural limit on guidance corrections

# IR/RCS — smaller, cooler, harder to see
MISSILE_THRUST_IR = 300_000.0    # 300 kW — smaller plume than torpedo
MISSILE_COAST_IR = 50.0          # 50 W — tiny thermal signature
MISSILE_RCS_M2 = 0.03            # Very small radar cross-section

# Warhead damage — less raw damage, but focused on direct hits
MISSILE_WARHEAD_BASE_DAMAGE = 25.0     # Hull damage at lethal radius
MISSILE_WARHEAD_SUB_DAMAGE = 15.0      # Per-subsystem damage at lethal radius
MISSILE_WARHEAD_ARMOR_PEN = 0.6        # Shaped charge — moderate penetration

# Flight profiles determine midcourse behaviour.
# "direct" is shared with torpedoes; the rest are missile-only.
MISSILE_FLIGHT_PROFILES = {"direct", "evasive", "terminal_pop", "bracket"}


@dataclass
class Torpedo:
    """A self-propelled guided munition in flight (torpedo or missile).

    Both torpedoes and missiles share this dataclass.  The munition_type
    field controls which physical specs and guidance law apply.
    """
    id: str
    shooter_id: str
    target_id: str

    # What kind of ordnance this is — determines specs and guidance
    munition_type: MunitionType = MunitionType.TORPEDO

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

    # Launch profile — missiles support: direct, evasive, terminal_pop, bracket
    profile: str = "direct"

    # Per-missile profile state initialised at spawn time.
    # evasive: {"period": float}  — weave period (randomised 2-4s)
    # terminal_pop: {"offset_dir": {x,y,z}, "offset_mag": float, "popped": bool}
    # bracket: {"quadrant_angle": float}  — radians around approach axis
    profile_data: Dict[str, object] = field(default_factory=dict)

    # Warhead and guidance configuration
    warhead_type: str = WarheadType.FRAGMENTATION.value
    guidance_mode: str = GuidanceMode.GUIDED.value

    # Player-programmable overrides (set via program_munition command).
    # When None, the guidance code uses the default constant for this
    # munition type.  These let MANUAL-tier players tune PN gain, fuse
    # sensitivity, terminal transition range, boost duration, and
    # datalink behavior per-munition.
    pn_gain_override: Optional[float] = None
    fuse_distance_override: Optional[float] = None
    terminal_range_override: Optional[float] = None
    boost_duration_override: Optional[float] = None

    # Damage tracking (for PDC interception)
    # Missiles are frailer: 40 HP vs 100 HP for torpedoes
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
        munition_type: MunitionType = MunitionType.TORPEDO,
        warhead_type: Optional[str] = None,
        guidance_mode: Optional[str] = None,
        pn_gain: Optional[float] = None,
        fuse_distance: Optional[float] = None,
        terminal_range: Optional[float] = None,
        boost_duration: Optional[float] = None,
        datalink: Optional[bool] = None,
    ) -> Torpedo:
        """Launch a new torpedo or missile.

        Physical specs (mass, fuel, thrust, hull HP, engagement params)
        are selected from the appropriate constant block based on
        munition_type so both ordnance types share the same flight and
        detonation pipeline.

        Args:
            shooter_id: Ship ID that launched
            target_id: Target ship ID
            position: Launch position {x, y, z}
            velocity: Initial velocity (inherited from launcher) {x, y, z}
            sim_time: Current simulation time
            target_pos: Target position at launch
            target_vel: Target velocity at launch
            profile: Attack profile (torpedoes: "direct"/"evasive";
                     missiles: "direct"/"evasive"/"terminal_pop"/"bracket")
            munition_type: TORPEDO or MISSILE
            warhead_type: Warhead variant (fragmentation/shaped_charge/emp).
                None defaults to fragmentation.
            guidance_mode: CPU assist level (dumb/guided/smart).
                None defaults to guided.
            pn_gain: Override PN gain (1.0-8.0). None uses guidance mode default.
            fuse_distance: Override proximity fuse radius in meters. None uses default.
            terminal_range: Override terminal phase transition range in meters.
            boost_duration: Override boost phase duration in seconds.
            datalink: Override datalink enabled state. None defaults to True.

        Returns:
            The spawned Torpedo (also used for missiles)
        """
        if munition_type == MunitionType.MISSILE:
            mass = MISSILE_MASS
            fuel = MISSILE_FUEL_MASS
            thrust = MISSILE_THRUST
            dv_budget = MISSILE_MAX_DELTA_V
            # Missiles are frailer — smaller airframe, less shielding
            hull_hp = 40.0
            prefix = "msl"
        else:
            mass = TORPEDO_MASS
            fuel = TORPEDO_FUEL_MASS
            thrust = TORPEDO_THRUST
            dv_budget = TORPEDO_MAX_DELTA_V
            hull_hp = 100.0
            prefix = "torp"

        # Resolve warhead and guidance defaults
        resolved_warhead = warhead_type or WarheadType.FRAGMENTATION.value
        resolved_guidance = guidance_mode or GuidanceMode.GUIDED.value

        torpedo = Torpedo(
            id=f"{prefix}_{self._next_id}",
            shooter_id=shooter_id,
            target_id=target_id,
            munition_type=munition_type,
            position=dict(position),
            velocity=dict(velocity),
            mass=mass,
            fuel=fuel,
            thrust=thrust,
            state=TorpedoState.BOOST,
            spawn_time=sim_time,
            launch_position=dict(position),
            last_target_pos=dict(target_pos),
            last_target_vel=dict(target_vel),
            profile=profile,
            warhead_type=resolved_warhead,
            guidance_mode=resolved_guidance,
            hull_health=hull_hp,
            max_hull_health=hull_hp,
            delta_v_budget=dv_budget,
            # Player-programmed overrides — None means "use default"
            pn_gain_override=pn_gain,
            fuse_distance_override=fuse_distance,
            terminal_range_override=terminal_range,
            boost_duration_override=boost_duration,
            datalink_active=datalink if datalink is not None else True,
        )
        # Initialise per-missile profile state with randomised parameters.
        # Each profile needs different data seeded at launch so that
        # missiles in the same salvo behave distinctly.
        if munition_type == MunitionType.MISSILE:
            torpedo.profile_data = self._init_profile_data(
                profile, torpedo.id, target_pos, position,
            )

        self._next_id += 1
        self._torpedoes.append(torpedo)

        event_name = ("missile_launched" if munition_type == MunitionType.MISSILE
                       else "torpedo_launched")
        self._event_bus.publish(event_name, {
            "torpedo_id": torpedo.id,
            "munition_type": munition_type.value,
            "shooter": shooter_id,
            "target": target_id,
            "position": torpedo.position,
            "profile": profile,
            "warhead_type": resolved_warhead,
            "guidance_mode": resolved_guidance,
        })

        return torpedo

    def tick(
        self, dt: float, sim_time: float, ships: dict,
        environment_manager=None,
    ) -> List[dict]:
        """Advance all torpedoes and check for detonation/interception.

        Args:
            dt: Time step in seconds
            sim_time: Current simulation time
            ships: Dict of ship_id -> Ship objects
            environment_manager: Optional EnvironmentManager for debris
                damage and nebula datalink loss

        Returns:
            List of detonation/interception event dicts
        """
        events = []
        surviving = []

        for torpedo in self._torpedoes:
            if not torpedo.alive:
                continue

            # Lifetime depends on munition type — missiles burn out faster
            max_lifetime = (MISSILE_MAX_LIFETIME
                            if torpedo.munition_type == MunitionType.MISSILE
                            else TORPEDO_MAX_LIFETIME)
            age = sim_time - torpedo.spawn_time
            if age > max_lifetime:
                torpedo.alive = False
                torpedo.state = TorpedoState.EXPIRED
                dist = calculate_distance(torpedo.position, torpedo.last_target_pos)
                speed = magnitude(torpedo.velocity)
                label = torpedo.munition_type.value.capitalize()
                logger.warning(
                    "%s %s expired: %.1fs flight, %.1f km from target, "
                    "speed %.0f m/s, fuel %.1f kg remaining",
                    label, torpedo.id, age, dist / 1000, speed, torpedo.fuel,
                )
                self._event_bus.publish("torpedo_expired", {
                    "torpedo_id": torpedo.id,
                    "munition_type": torpedo.munition_type.value,
                    "shooter": torpedo.shooter_id,
                    "target": torpedo.target_id,
                    "flight_time": age,
                })
                continue

            # Environment: debris degrades hull, nebula severs datalink.
            # Applied BEFORE guidance update so datalink loss takes effect
            # on the same tick the munition enters the nebula.
            if environment_manager is not None:
                env_damage, datalink_blocked = (
                    environment_manager.check_torpedo_degradation(
                        torpedo.position, dt,
                    )
                )
                if env_damage > 0:
                    torpedo.hull_health -= env_damage
                    if torpedo.hull_health <= 0:
                        torpedo.alive = False
                        torpedo.state = TorpedoState.INTERCEPTED
                        label = torpedo.munition_type.value.capitalize()
                        logger.info(
                            "%s %s destroyed by debris field", label, torpedo.id,
                        )
                        self._event_bus.publish("torpedo_debris_destroyed", {
                            "torpedo_id": torpedo.id,
                            "munition_type": torpedo.munition_type.value,
                            "shooter": torpedo.shooter_id,
                            "target": torpedo.target_id,
                        })
                        continue
                if datalink_blocked:
                    torpedo.datalink_active = False

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

            # Arming distance — missiles arm sooner (lighter, less backblast risk)
            if not torpedo.armed:
                arm_dist = (MISSILE_ARM_DISTANCE
                            if torpedo.munition_type == MunitionType.MISSILE
                            else TORPEDO_ARM_DISTANCE)
                dist_from_launch = calculate_distance(torpedo.position, torpedo.launch_position)
                if dist_from_launch >= arm_dist:
                    torpedo.armed = True

            # Proximity fuse radius depends on warhead type:
            # Torpedoes have a wider fuse (area-effect fragmentation)
            # Missiles have a tighter fuse (shaped-charge, needs near-hit)
            # Player can override via program_munition for manual control.
            if torpedo.fuse_distance_override is not None:
                prox_fuse = torpedo.fuse_distance_override
            else:
                prox_fuse = (MISSILE_PROXIMITY_FUSE
                             if torpedo.munition_type == MunitionType.MISSILE
                             else TORPEDO_PROXIMITY_FUSE)

            # Check proximity detonation against target.
            # Two checks are needed:
            # 1) Swept-line test — did the munition pass through the fuse
            #    zone during this tick's position advance?
            # 2) Predictive closest-approach — will the munition reach the
            #    fuse zone on its current trajectory?  Real proximity fuses
            #    fire when they detect minimum range is imminent and within
            #    lethal distance.  Without this, a fast munition can be many
            #    ticks away from the target at each check but still clearly
            #    on a collision course.
            if target_ship and torpedo.armed:
                # --- Swept-line check (handles pass-through in one tick) ---
                closest_dist, closest_point = self._swept_closest_approach(
                    old_pos, torpedo.position, target_ship.position
                )
                if closest_dist <= prox_fuse:
                    torpedo.position = closest_point
                    event = self._detonate(torpedo, target_ship, sim_time, closest_dist, ships)
                    events.append(event)
                    continue

                # --- Predictive proximity fuse ---
                pred_dist, pred_point, tca = self._predict_closest_approach(
                    torpedo, target_ship
                )
                if pred_dist <= prox_fuse and tca > 0:
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
        """Compute and apply thrust vector for guided munition.

        Guidance mode determines how much course correction the onboard
        CPU performs:
        - DUMB: No guidance — fires thrust along launch vector only during
          boost phase, then coasts on ballistic trajectory.
        - GUIDED (default): Proportional navigation with datalink updates.
        - SMART: Enhanced PN with higher gain and terminal evasion
          prediction — models target acceleration history to anticipate jinks.

        Guidance phases:
        - BOOST: Full thrust toward intercept point
        - MIDCOURSE: Periodic corrections, may coast to save fuel
        - TERMINAL: Max thrust, tight corrections to hit
        """
        if torpedo.fuel <= 0:
            torpedo.acceleration = {"x": 0, "y": 0, "z": 0}
            torpedo.state = TorpedoState.MIDCOURSE  # Coasting, no fuel
            return

        # DUMB guidance: fire straight ahead during boost, then coast.
        # No course corrections, no PN, no terminal maneuver.
        # Advantage: immune to ECM jamming, cheap ordnance.
        # Disadvantage: only hits non-maneuvering targets.
        if torpedo.guidance_mode == GuidanceMode.DUMB.value:
            self._update_dumb_guidance(torpedo, dt, sim_time)
            return

        is_missile = torpedo.munition_type == MunitionType.MISSILE

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

        # Per-type engagement parameters, with player override support
        if torpedo.terminal_range_override is not None:
            terminal_range = torpedo.terminal_range_override
        else:
            terminal_range = (MISSILE_TERMINAL_RANGE if is_missile
                              else TORPEDO_TERMINAL_RANGE)
        max_lifetime = (MISSILE_MAX_LIFETIME if is_missile
                        else TORPEDO_MAX_LIFETIME)

        # State transitions
        if dist <= terminal_range:
            torpedo.state = TorpedoState.TERMINAL
        elif torpedo.state == TorpedoState.BOOST:
            age = sim_time - torpedo.spawn_time
            remaining_time = max_lifetime - age
            rel_vel = subtract_vectors(torpedo.velocity, target_vel)
            if dist > 1.0:
                los = normalize_vector(rel_pos)
                current_closing = dot_product(rel_vel, los)
            else:
                current_closing = magnitude(torpedo.velocity)
            required_speed = dist / max(1.0, remaining_time) * 1.2
            # Missiles have shorter boost: 2s min (fast motor) vs 5s torpedoes
            min_boost = 2.0 if is_missile else 5.0
            if age > min_boost and current_closing > required_speed:
                torpedo.state = TorpedoState.MIDCOURSE
                label = torpedo.munition_type.value.capitalize()
                logger.info(
                    "%s %s BOOST->MIDCOURSE at %.1fs: closing %.0f m/s "
                    "(required %.0f), dist %.1f km, fuel %.1f kg",
                    label, torpedo.id, age, current_closing, required_speed,
                    dist / 1000, torpedo.fuel,
                )

        # --- Proportional Navigation (PN) guidance ---
        # PN gain selection:
        # - SMART guidance uses higher gain (N=6) for tighter intercepts
        #   and better correction against maneuvering targets.
        # - Missiles use augmented PN (N=5) for tighter intercepts.
        # - Standard torpedoes use PN (N=4).
        # Player can override via program_munition for fine-tuned control.
        is_smart = torpedo.guidance_mode == GuidanceMode.SMART.value
        if torpedo.pn_gain_override is not None:
            pn_gain = torpedo.pn_gain_override
        elif is_smart:
            pn_gain = 6.0  # Enhanced CPU predicts evasion patterns
        elif is_missile:
            pn_gain = 5.0
        else:
            pn_gain = 4.0

        # Relative velocity: munition - target (positive = closing)
        rel_vel_to_target = subtract_vectors(torpedo.velocity, target_vel)
        los_dir = normalize_vector(rel_pos) if dist > 1.0 else {"x": 1, "y": 0, "z": 0}
        closing_speed = dot_product(rel_vel_to_target, los_dir)

        # LOS rotation rate: omega = (V_perp) / R
        v_along = scale_vector(los_dir, dot_product(rel_vel_to_target, los_dir))
        v_perp = subtract_vectors(rel_vel_to_target, v_along)
        omega_los = magnitude(v_perp) / max(1.0, dist)

        # PN acceleration perpendicular to LOS, opposing rotation
        pn_accel_mag = pn_gain * abs(closing_speed) * omega_los
        if magnitude(v_perp) > 0.01:
            pn_dir = normalize_vector(v_perp)
            pn_dir = scale_vector(pn_dir, -1.0)
        else:
            pn_dir = {"x": 0, "y": 0, "z": 0}

        # Predicted intercept point (aim bias)
        tgo = dist / max(1.0, abs(closing_speed)) if closing_speed > 1.0 else dist / max(1.0, magnitude(torpedo.velocity))
        intercept = {
            "x": target_pos["x"] + target_vel["x"] * tgo,
            "y": target_pos["y"] + target_vel["y"] * tgo,
            "z": target_pos["z"] + target_vel["z"] * tgo,
        }
        aim_vec = subtract_vectors(intercept, torpedo.position)
        aim_dist = magnitude(aim_vec)
        if aim_dist < 1.0:
            aim_dir = los_dir
        else:
            aim_dir = normalize_vector(aim_vec)

        # SMART guidance: include target acceleration in intercept prediction.
        # The onboard CPU extrapolates the target's current acceleration into
        # the predicted intercept point (second-order prediction).  This makes
        # SMART munitions much harder to evade with constant-thrust maneuvers,
        # but can be defeated by erratic jinking (frequent accel changes).
        if is_smart and target_ship and hasattr(target_ship, "acceleration"):
            target_accel = target_ship.acceleration
            if target_accel:
                intercept = {
                    "x": intercept["x"] + 0.5 * target_accel.get("x", 0) * tgo * tgo,
                    "y": intercept["y"] + 0.5 * target_accel.get("y", 0) * tgo * tgo,
                    "z": intercept["z"] + 0.5 * target_accel.get("z", 0) * tgo * tgo,
                }
                aim_vec = subtract_vectors(intercept, torpedo.position)
                aim_dist = magnitude(aim_vec)
                if aim_dist >= 1.0:
                    aim_dir = normalize_vector(aim_vec)

        # Missiles (and SMART torpedoes in terminal) add a terminal
        # lead-pursuit bias: in the last 3s of predicted flight, blend
        # toward pure pursuit of current position rather than predicted
        # intercept.  This corrects for last-second target jinking.
        use_terminal_pursuit = (
            (is_missile or is_smart) and torpedo.state == TorpedoState.TERMINAL and tgo < 3.0
        )
        if use_terminal_pursuit:
            pursuit_dir = los_dir
            # Blend: as tgo->0, pure pursuit dominates
            blend = max(0.0, min(1.0, 1.0 - tgo / 3.0))
            aim_dir = normalize_vector(add_vectors(
                scale_vector(aim_dir, 1.0 - blend),
                scale_vector(pursuit_dir, blend),
            ))

        # Blend PN correction into aim direction
        if pn_accel_mag > 0.01:
            accel_max = torpedo.thrust / torpedo.mass if torpedo.mass > 0 else 32.0
            if torpedo.state == TorpedoState.TERMINAL:
                pn_weight = min(pn_accel_mag, accel_max * 0.8)
            else:
                pn_weight = min(pn_accel_mag, accel_max * 0.4)
            los_weight = max(0.1, accel_max - pn_weight)
            blended = add_vectors(
                scale_vector(aim_dir, los_weight),
                scale_vector(pn_dir, pn_weight),
            )
            dir_mag = magnitude(blended)
            if dir_mag > 0.01:
                aim_dir = normalize_vector(blended)

        # Missile flight profile modifiers.
        # Most profiles apply during MIDCOURSE only, but terminal_pop
        # must also steer during BOOST so the missile builds lateral
        # velocity toward the offset line before it starts coasting.
        if is_missile and torpedo.state in (TorpedoState.MIDCOURSE, TorpedoState.BOOST):
            aim_dir = self._apply_missile_profile(torpedo, aim_dir, dt, sim_time, dist)

        # Determine thrust fraction based on flight phase
        if torpedo.state == TorpedoState.TERMINAL:
            thrust_fraction = 1.0
        elif torpedo.state == TorpedoState.MIDCOURSE:
            # Missiles with terminal_pop profile coast cold during the
            # offset approach (far from target) to minimise IR signature.
            # Once inside 2x terminal range they re-engage thrust to
            # execute the pop-up climb maneuver before terminal dive.
            if is_missile and torpedo.profile == "terminal_pop":
                _tr = torpedo.terminal_range_override if torpedo.terminal_range_override is not None else MISSILE_TERMINAL_RANGE
                pop_range = 2.0 * _tr
                if dist > pop_range:
                    thrust_fraction = 0.0
                else:
                    thrust_fraction = 1.0  # Full thrust for pop maneuver
            else:
                vel_dir = normalize_vector(torpedo.velocity) if magnitude(torpedo.velocity) > 1.0 else aim_dir
                cos_angle = dot_product(vel_dir, aim_dir)
                age = sim_time - torpedo.spawn_time
                remaining = max_lifetime - age
                required_closing = dist / max(1.0, remaining) * 1.3

                if cos_angle > 0.996 and closing_speed > required_closing:
                    thrust_fraction = 0.0
                elif cos_angle > 0.99:
                    thrust_fraction = 0.5
                else:
                    thrust_fraction = 1.0
        else:
            thrust_fraction = 1.0

        # Apply thrust and consume fuel
        if thrust_fraction > 0:
            actual_thrust = torpedo.thrust * thrust_fraction
            accel_mag = actual_thrust / torpedo.mass

            # Missiles have a structural G-limit — clamp commanded accel
            if is_missile:
                max_accel = MISSILE_G_LIMIT * 9.81  # Convert G to m/s^2
                accel_mag = min(accel_mag, max_accel)

            torpedo.acceleration = {
                "x": aim_dir["x"] * accel_mag,
                "y": aim_dir["y"] * accel_mag,
                "z": aim_dir["z"] * accel_mag,
            }

            torpedo.velocity["x"] += torpedo.acceleration["x"] * dt
            torpedo.velocity["y"] += torpedo.acceleration["y"] * dt
            torpedo.velocity["z"] += torpedo.acceleration["z"] * dt

            # Consume fuel (Tsiolkovsky-consistent)
            exhaust_vel = (MISSILE_EXHAUST_VEL if is_missile
                           else TORPEDO_EXHAUST_VEL)
            mass_flow = actual_thrust / exhaust_vel
            fuel_consumed = mass_flow * dt
            fuel_consumed = min(fuel_consumed, torpedo.fuel)
            torpedo.fuel -= fuel_consumed
            torpedo.mass -= fuel_consumed
            torpedo.delta_v_used += accel_mag * dt
        else:
            torpedo.acceleration = {"x": 0, "y": 0, "z": 0}

    def _update_dumb_guidance(self, torpedo: Torpedo, dt: float, sim_time: float):
        """Guidance for DUMB munitions: boost-phase-only thrust, then coast.

        DUMB munitions fire along their initial velocity vector during the
        boost phase. After boost ends (by time or fuel), they coast on a
        ballistic trajectory with no course corrections. This makes them
        immune to ECM jamming but useless against maneuvering targets.

        Args:
            torpedo: Munition in flight
            dt: Time step in seconds
            sim_time: Current simulation time
        """
        is_missile = torpedo.munition_type == MunitionType.MISSILE

        # Boost for a fixed duration, then coast.
        # Player can override boost duration via program_munition.
        age = sim_time - torpedo.spawn_time
        if torpedo.boost_duration_override is not None:
            boost_duration = torpedo.boost_duration_override
        else:
            boost_duration = 3.0 if is_missile else 8.0

        if age > boost_duration or torpedo.fuel <= 0:
            # Coast phase — no thrust, no corrections
            torpedo.acceleration = {"x": 0, "y": 0, "z": 0}
            torpedo.state = TorpedoState.MIDCOURSE
            return

        # Boost phase: thrust along current velocity direction
        # (set at launch from the firing solution's aim vector)
        vel_mag = magnitude(torpedo.velocity)
        if vel_mag > 1.0:
            thrust_dir = normalize_vector(torpedo.velocity)
        else:
            # Fallback: aim toward last known target position
            aim_vec = subtract_vectors(torpedo.last_target_pos, torpedo.position)
            aim_mag = magnitude(aim_vec)
            if aim_mag > 1.0:
                thrust_dir = normalize_vector(aim_vec)
            else:
                thrust_dir = {"x": 1, "y": 0, "z": 0}

        accel_mag = torpedo.thrust / torpedo.mass
        if is_missile:
            max_accel = MISSILE_G_LIMIT * 9.81
            accel_mag = min(accel_mag, max_accel)

        torpedo.acceleration = {
            "x": thrust_dir["x"] * accel_mag,
            "y": thrust_dir["y"] * accel_mag,
            "z": thrust_dir["z"] * accel_mag,
        }
        torpedo.velocity["x"] += torpedo.acceleration["x"] * dt
        torpedo.velocity["y"] += torpedo.acceleration["y"] * dt
        torpedo.velocity["z"] += torpedo.acceleration["z"] * dt

        # Consume fuel
        exhaust_vel = (MISSILE_EXHAUST_VEL if is_missile else TORPEDO_EXHAUST_VEL)
        mass_flow = torpedo.thrust / exhaust_vel
        fuel_consumed = min(mass_flow * dt, torpedo.fuel)
        torpedo.fuel -= fuel_consumed
        torpedo.mass -= fuel_consumed
        torpedo.delta_v_used += accel_mag * dt

    @staticmethod
    def _init_profile_data(
        profile: str, missile_id: str,
        target_pos: Dict[str, float], launch_pos: Dict[str, float],
    ) -> Dict[str, object]:
        """Build per-missile profile state at spawn time.

        Each profile needs stable random parameters so that missiles
        in the same salvo diverge deterministically:
        - evasive:  weave period (2-4s), randomised per missile
        - terminal_pop:  offset direction perpendicular to approach,
                         magnitude 500-1000m
        - bracket:  quadrant angle around approach axis (assigned later
                    when sibling count is known; seed stored here)

        Args:
            profile: Flight profile name
            missile_id: Unique missile ID (used as RNG seed)
            target_pos: Target position at launch
            launch_pos: Missile launch position

        Returns:
            Dict of profile-specific state
        """
        if profile == "direct":
            return {}

        # Deterministic RNG per missile so salvos diverge repeatably
        rng = random.Random(hash(missile_id))

        if profile == "evasive":
            return {"period": rng.uniform(2.0, 4.0)}

        if profile == "terminal_pop":
            # Compute a stable perpendicular to the approach vector.
            # The missile will fly offset below/beside the direct line,
            # then "pop" up into a terminal dive at close range.
            approach = subtract_vectors(target_pos, launch_pos)
            a_mag = magnitude(approach)
            if a_mag < 1.0:
                approach = {"x": 1, "y": 0, "z": 0}
            else:
                approach = normalize_vector(approach)

            # Pick an arbitrary non-parallel reference to cross with approach
            ref = {"x": 0, "y": 1, "z": 0}
            if abs(dot_product(approach, ref)) > 0.95:
                ref = {"x": 0, "y": 0, "z": 1}

            perp = cross_product(approach, ref)
            pmag = magnitude(perp)
            if pmag > 0.01:
                perp = normalize_vector(perp)
            else:
                perp = {"x": 0, "y": 1, "z": 0}

            offset_mag = rng.uniform(500.0, 1000.0)
            return {
                "offset_dir": perp,
                "offset_mag": offset_mag,
                "popped": False,
            }

        if profile == "bracket":
            # Store a seed angle; actual quadrant is assigned during
            # _apply_missile_profile once we know how many siblings
            # share the same target, so we can space them evenly.
            return {"seed_angle": rng.uniform(0, 2 * math.pi)}

        return {}

    def _apply_missile_profile(
        self, missile: Torpedo, aim_dir: Dict[str, float],
        dt: float, sim_time: float, dist: float,
    ) -> Dict[str, float]:
        """Apply missile flight profile modifiers during midcourse.

        Each profile physically alters the thrust vector to create
        distinct approach geometries that complicate PDC intercept:

        - direct: Pure PN, no modification.
        - evasive: Sinusoidal lateral weave perpendicular to approach.
          Amplitude scales with closing velocity so faster missiles
          weave harder.  Period is randomised per missile (2-4s) to
          prevent PDCs from predicting the pattern.
        - terminal_pop: Fly offset from the direct line (below/beside
          the target plane) during midcourse, coasting cold to reduce
          IR signature.  At 2x terminal_range, "pop" perpendicular
          to approach then dive onto target in TERMINAL.
        - bracket: When 2+ missiles target the same ship, space them
          evenly around the approach axis (quadrant offsets).  Forces
          PDCs to slew between widely separated threats.  Single
          missiles default to direct behaviour.

        Args:
            missile: The missile munition
            aim_dir: Current aim direction from PN guidance
            dt: Time step
            sim_time: Current sim time
            dist: Distance to target

        Returns:
            Modified aim direction
        """
        profile = missile.profile
        pd = missile.profile_data

        if profile == "direct":
            return aim_dir

        # --- EVASIVE: sinusoidal lateral weave ---
        # Physics: add oscillating acceleration perpendicular to the
        # approach vector.  This makes the missile's trajectory a helix
        # around the PN line, defeating PDC linear-extrapolation aim.
        # The weave amplitude is proportional to closing speed because
        # faster missiles need larger displacement to force the same
        # angular tracking error on the defender's fire-control.
        if profile == "evasive":
            period = pd.get("period", 3.0)
            # Build a perpendicular frame from aim_dir
            ref = {"x": 0, "y": 1, "z": 0}
            if abs(dot_product(aim_dir, ref)) > 0.95:
                ref = {"x": 0, "y": 0, "z": 1}
            perp1 = cross_product(aim_dir, ref)
            p1_mag = magnitude(perp1)
            if p1_mag < 0.01:
                return aim_dir
            perp1 = normalize_vector(perp1)

            # Sinusoidal weave: the perpendicular offset oscillates
            # with sim_time.  Amplitude is 40% of max accel -- enough
            # to force PDC re-acquisition each half-cycle without
            # spending excessive delta-v on lateral burns.
            phase = 2.0 * math.pi * sim_time / period
            weave_strength = 0.40 * math.sin(phase)
            result = add_vectors(
                scale_vector(aim_dir, 1.0 - abs(weave_strength)),
                scale_vector(perp1, weave_strength),
            )
            rmag = magnitude(result)
            if rmag > 0.01:
                return normalize_vector(result)
            return aim_dir

        # --- TERMINAL POP: offset approach then rapid climb + dive ---
        # Physics: during midcourse, the missile flies parallel to the
        # direct line but displaced by 500-1000m in a perpendicular
        # direction (typically "below").  This keeps it outside the
        # defender's most likely PDC scan cone.  At 2x terminal_range
        # it executes a rapid climb perpendicular to approach, then
        # the TERMINAL phase dives onto the target from the offset
        # direction -- a harder intercept geometry for PDCs because
        # the angular rate spikes during the pop maneuver.
        if profile == "terminal_pop":
            offset_dir = pd.get("offset_dir", {"x": 0, "y": 1, "z": 0})
            offset_mag = pd.get("offset_mag", 750.0)
            _tr = missile.terminal_range_override if missile.terminal_range_override is not None else MISSILE_TERMINAL_RANGE
            pop_range = 2.0 * _tr  # Pop at 2x terminal range

            if dist > pop_range:
                # Midcourse: steer toward offset line (parallel to
                # direct approach but displaced by offset_mag).
                # Blend a lateral component into aim_dir to maintain
                # the offset without diverging from the intercept course.
                offset_blend = min(0.35, offset_mag / max(1.0, dist))
                result = add_vectors(
                    scale_vector(aim_dir, 1.0 - offset_blend),
                    scale_vector(offset_dir, offset_blend),
                )
                rmag = magnitude(result)
                if rmag > 0.01:
                    return normalize_vector(result)
            else:
                # Pop maneuver: inside 2x terminal range, steer
                # sharply opposite to the offset (climb away from
                # the offset plane) to create a crossing trajectory.
                # The TERMINAL phase guidance will then pull back
                # toward the target for the final dive.
                if not pd.get("popped", False):
                    pd["popped"] = True
                    logger.info(
                        "Missile %s executing terminal pop at %.0f m",
                        missile.id, dist,
                    )
                anti_offset = scale_vector(offset_dir, -1.0)
                pop_blend = 0.5
                result = add_vectors(
                    scale_vector(aim_dir, 1.0 - pop_blend),
                    scale_vector(anti_offset, pop_blend),
                )
                rmag = magnitude(result)
                if rmag > 0.01:
                    return normalize_vector(result)
            return aim_dir

        # --- BRACKET: quadrant-spread for multi-missile salvos ---
        # Physics: if N missiles target the same ship, they space
        # evenly around the approach axis so the defender's PDCs must
        # slew across 360 degrees instead of tracking a single bearing.
        # Each missile maintains a fixed angular offset in the plane
        # perpendicular to the line-of-sight, decaying to zero as it
        # enters terminal range (all converge for simultaneous impact).
        if profile == "bracket":
            # Find sibling bracket missiles targeting the same ship
            siblings = [
                t for t in self._torpedoes
                if t.alive
                and t.target_id == missile.target_id
                and t.profile == "bracket"
                and t.munition_type == MunitionType.MISSILE
            ]
            if len(siblings) < 2:
                # Solo bracket missile -- no spread benefit, fly direct
                return aim_dir

            # Assign evenly-spaced quadrant angles.  Sort siblings by
            # ID for deterministic ordering across ticks.
            siblings.sort(key=lambda t: t.id)
            idx = next(
                (i for i, t in enumerate(siblings) if t.id == missile.id), 0
            )
            quadrant_angle = (2.0 * math.pi * idx) / len(siblings)

            # Build two perpendicular axes in the plane normal to aim_dir
            ref = {"x": 0, "y": 1, "z": 0}
            if abs(dot_product(aim_dir, ref)) > 0.95:
                ref = {"x": 0, "y": 0, "z": 1}

            perp1 = cross_product(aim_dir, ref)
            p1_mag = magnitude(perp1)
            if p1_mag < 0.01:
                return aim_dir
            perp1 = normalize_vector(perp1)

            perp2 = cross_product(aim_dir, perp1)
            p2_mag = magnitude(perp2)
            if p2_mag < 0.01:
                return aim_dir
            perp2 = normalize_vector(perp2)

            # Offset decays linearly as missile approaches terminal range
            # so all missiles converge for simultaneous impact
            _tr = missile.terminal_range_override if missile.terminal_range_override is not None else MISSILE_TERMINAL_RANGE
            offset_strength = min(1.0, dist / max(1.0, _tr))
            bracket_factor = 0.30 * offset_strength

            offset_dir = add_vectors(
                scale_vector(perp1, math.cos(quadrant_angle)),
                scale_vector(perp2, math.sin(quadrant_angle)),
            )
            result = add_vectors(
                scale_vector(aim_dir, 1.0 - bracket_factor),
                scale_vector(offset_dir, bracket_factor),
            )
            rmag = magnitude(result)
            if rmag > 0.01:
                return normalize_vector(result)
            return aim_dir

        return aim_dir

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

        # Select warhead specs from the per-type tables.
        # Warhead type determines hull damage, blast radii, and subsystem effects.
        # Falls back to legacy constants when the warhead type is not in the table
        # (shouldn't happen, but defensive coding).
        is_missile = torpedo.munition_type == MunitionType.MISSILE
        warhead = torpedo.warhead_type

        if is_missile:
            wh_specs = MISSILE_WARHEAD_SPECS.get(warhead, MISSILE_WARHEAD_SPECS[WarheadType.FRAGMENTATION.value])
        else:
            wh_specs = TORPEDO_WARHEAD_SPECS.get(warhead, TORPEDO_WARHEAD_SPECS[WarheadType.FRAGMENTATION.value])

        blast_radius = wh_specs["blast_radius"]
        lethal_radius = wh_specs["lethal_radius"]
        base_damage = wh_specs["hull_damage"]
        sub_damage_base = wh_specs["subsystem_damage"]
        # EMP fields (zero for non-EMP warheads)
        emp_disable_duration = wh_specs.get("subsystem_disable_duration", 0.0)
        emp_max_disabled = int(wh_specs.get("max_subsystems_disabled", 0))

        damage_results = []
        munition_label = torpedo.munition_type.value

        # Check all ships within blast radius
        for ship_id, ship in ships.items():
            if ship_id == torpedo.shooter_id:
                continue  # Don't damage own ship

            dist = calculate_distance(torpedo.position, ship.position)
            if dist > blast_radius:
                continue

            # Damage falloff: inverse-square from lethal radius
            if dist <= lethal_radius:
                damage_factor = 1.0
            else:
                damage_factor = (lethal_radius / dist) ** 2
                damage_factor = max(0.1, min(1.0, damage_factor))

            hull_damage = base_damage * damage_factor
            sub_damage = sub_damage_base * damage_factor

            # Subsystem targeting varies by warhead type:
            # FRAGMENTATION: 2-3 subsystems (area shrapnel)
            # SHAPED_CHARGE: 1-2 subsystems (focused jet)
            # EMP: subsystem disable (temporary, not permanent)
            subsystems_hit = self._determine_blast_subsystems(torpedo, ship)
            if warhead == WarheadType.SHAPED_CHARGE.value:
                # Focused penetrating jet — only affects 1-2 subsystems
                subsystems_hit = subsystems_hit[:2] if is_missile else subsystems_hit[:2]
            elif is_missile:
                subsystems_hit = subsystems_hit[:2]

            result = {"ship_id": ship_id, "distance": dist, "damage_factor": damage_factor,
                      "warhead_type": warhead}

            if hasattr(ship, "take_damage"):
                dmg_result = ship.take_damage(
                    hull_damage,
                    source=f"{torpedo.shooter_id}:{munition_label}",
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

            # EMP warhead: temporarily disable subsystems instead of
            # permanent destruction.  The disable is recoverable — subsystems
            # regain function after the duration expires.  This uses the
            # damage model's disable_temporarily() if available, otherwise
            # falls back to regular damage (graceful degradation for older
            # damage models that lack the method).
            result["subsystems_disabled"] = []
            if emp_disable_duration > 0 and emp_max_disabled > 0:
                disable_targets = subsystems_hit[:emp_max_disabled]
                if hasattr(ship, "damage_model"):
                    for subsystem in disable_targets:
                        if hasattr(ship.damage_model, "disable_temporarily"):
                            ship.damage_model.disable_temporarily(
                                subsystem, emp_disable_duration
                            )
                        else:
                            # Fallback: apply heavy damage to simulate disable
                            ship.damage_model.apply_damage(subsystem, 50.0)
                        result["subsystems_disabled"].append({
                            "subsystem": subsystem,
                            "duration": emp_disable_duration,
                        })

            damage_results.append(result)

        # Build event
        event_type = ("missile_detonation" if is_missile
                       else "torpedo_detonation")
        event = {
            "type": event_type,
            "munition_type": munition_label,
            "torpedo_id": torpedo.id,
            "shooter": torpedo.shooter_id,
            "target": torpedo.target_id,
            "position": torpedo.position,
            "impact_distance": impact_distance,
            "flight_time": flight_time,
            "warhead_type": warhead,
            "damage_results": damage_results,
            "feedback": self._generate_detonation_feedback(
                torpedo, target_ship, impact_distance, flight_time, damage_results
            ),
        }

        self._event_bus.publish(event_type, event)
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
        """Generate human-readable feedback for munition detonation.

        Args:
            torpedo: Detonating munition (torpedo or missile)
            target_ship: Primary target
            impact_distance: Distance at detonation
            flight_time: Total flight time
            damage_results: List of ships damaged

        Returns:
            Human-readable feedback string
        """
        is_missile = torpedo.munition_type == MunitionType.MISSILE
        label = "Missile" if is_missile else "Torpedo"

        # Use warhead-specific radii for feedback accuracy
        warhead = torpedo.warhead_type
        if is_missile:
            wh = MISSILE_WARHEAD_SPECS.get(warhead, MISSILE_WARHEAD_SPECS[WarheadType.FRAGMENTATION.value])
        else:
            wh = TORPEDO_WARHEAD_SPECS.get(warhead, TORPEDO_WARHEAD_SPECS[WarheadType.FRAGMENTATION.value])
        lethal_r = wh["lethal_radius"]
        if torpedo.fuse_distance_override is not None:
            prox_r = torpedo.fuse_distance_override
        else:
            prox_r = MISSILE_PROXIMITY_FUSE if is_missile else TORPEDO_PROXIMITY_FUSE

        # Include warhead type in label for non-default warheads
        warhead_label = ""
        if warhead != WarheadType.FRAGMENTATION.value:
            warhead_label = f" ({warhead.replace('_', ' ')})"

        target_name = getattr(target_ship, "name", torpedo.target_id) if target_ship else torpedo.target_id

        if impact_distance <= lethal_r:
            proximity = "direct hit" if is_missile else "point-blank detonation"
        elif impact_distance <= prox_r:
            proximity = f"proximity detonation at {impact_distance:.0f}m"
        else:
            proximity = f"blast at {impact_distance:.0f}m range"

        ships_hit = len(damage_results)
        subsystems_total = sum(len(r.get("subsystems_hit", [])) for r in damage_results)
        subsystems_disabled = sum(len(r.get("subsystems_disabled", [])) for r in damage_results)

        feedback = f"{label}{warhead_label} impact — {proximity} on {target_name}"
        feedback += f", {flight_time:.1f}s flight time"
        if subsystems_total > 0:
            feedback += f", {subsystems_total} subsystems damaged"
        if subsystems_disabled > 0:
            feedback += f", {subsystems_disabled} subsystems disabled"
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
        """Get state of all active munitions (torpedoes and missiles) for telemetry.

        Returns:
            List of munition state dicts with distance and ETA to target
        """
        result = []
        for t in self._torpedoes:
            if not t.alive:
                continue

            is_missile = t.munition_type == MunitionType.MISSILE
            fuel_max = MISSILE_FUEL_MASS if is_missile else TORPEDO_FUEL_MASS
            thrust_ir = MISSILE_THRUST_IR if is_missile else TORPEDO_THRUST_IR
            coast_ir = MISSILE_COAST_IR if is_missile else TORPEDO_COAST_IR
            rcs = MISSILE_RCS_M2 if is_missile else TORPEDO_RCS_M2

            # Distance to last known target position
            dist = calculate_distance(t.position, t.last_target_pos)

            # Estimated time to impact
            eta = None
            closing_speed = 0.0
            rel_pos = subtract_vectors(t.last_target_pos, t.position)
            rel_vel = subtract_vectors(t.velocity, t.last_target_vel)
            dist_mag = magnitude(rel_pos)
            if dist_mag > 1.0:
                los = normalize_vector(rel_pos)
                closing_speed = dot_product(rel_vel, los)
                if closing_speed > 1.0:
                    eta = round(dist_mag / closing_speed, 1)

            # Compute delta-v remaining for this munition
            munition_mass = t.mass
            dry_mass = munition_mass - t.fuel
            exhaust_vel = t.exhaust_velocity if hasattr(t, "exhaust_velocity") else 2943.0
            dv_remaining = exhaust_vel * math.log(munition_mass / max(dry_mass, 0.1)) if t.fuel > 0 else 0.0

            result.append({
                "id": t.id,
                "munition_type": t.munition_type.value,
                "shooter": t.shooter_id,
                "target": t.target_id,
                "position": t.position,
                "velocity": t.velocity,
                "state": t.state.value,
                "fuel_percent": round((t.fuel / fuel_max * 100) if fuel_max > 0 else 0, 1),
                "armed": t.armed,
                "hull_health": t.hull_health,
                "profile": t.profile,
                "warhead_type": t.warhead_type,
                "guidance_mode": t.guidance_mode,
                "alive": t.alive,
                "age": 0.0,  # Filled by caller if needed
                "distance": round(dist, 1),
                "eta": eta,
                "is_thrusting": t.fuel > 0 and t.state in (TorpedoState.BOOST, TorpedoState.TERMINAL),
                "ir_signature": thrust_ir if (t.fuel > 0 and t.state != TorpedoState.MIDCOURSE) else coast_ir,
                "rcs_m2": rcs,
                # MANUAL-tier guidance diagnostics
                "pn_gain": getattr(t, "pn_gain", 4.0),
                "fuse_distance": getattr(t, "fuse_distance", 50.0),
                "datalink_active": getattr(t, "datalink_active", True),
                "dv_remaining": round(dv_remaining, 1),
                "closing_speed": round(closing_speed, 1) if closing_speed is not None else None,
                "thrust": getattr(t, "thrust", 0.0),
                "mass": round(munition_mass, 1),
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
