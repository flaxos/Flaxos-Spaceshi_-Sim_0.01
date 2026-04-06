# hybrid/systems/weapons/truth_weapons.py
"""Truth weapons - physics-based weapon implementations for realistic combat.

Sprint C: Railgun and PDC as the first two truth weapons.
These weapons have proper ballistics, range calculations, and damage models.
"""

import math
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Tuple
from hybrid.core.event_bus import EventBus
from hybrid.systems.combat.hit_location import compute_hit_location

logger = logging.getLogger(__name__)


class WeaponType(Enum):
    """Weapon classification types."""
    KINETIC = "kinetic"       # Railgun, PDC
    MISSILE = "missile"       # Torpedoes, missiles
    ENERGY = "energy"         # Future: lasers, plasma


class DamageType(Enum):
    """Damage classification for armor/subsystem interaction."""
    KINETIC_PENETRATOR = "kinetic_penetrator"  # Railgun - armor piercing
    KINETIC_FRAGMENTATION = "kinetic_fragmentation"  # PDC - area/surface
    EXPLOSIVE = "explosive"   # Missiles/torpedoes


class SlugType(Enum):
    """Railgun slug variants with different penetration/fragmentation trade-offs.

    STANDARD: Balanced tungsten penetrator — baseline damage and armor pen.
    SABOT: Discarding-sabot round with narrow dart core. Punches through
           heavier armor but the small cross-section fragments less inside
           the target, dealing reduced subsystem damage.
    FRAGMENTATION: Segmented slug that breaks apart on penetration. Poor
                   at defeating armor (segments deflect) but devastating
                   once inside — fragments spray across multiple subsystems.
    """
    STANDARD = "standard"
    SABOT = "sabot"
    FRAGMENTATION = "fragmentation"


# Slug type modifiers applied to base WeaponSpecs values.
# Keys: armor_penetration multiplier, subsystem_damage multiplier,
#       extra_subsystem_hits (additional subsystems hit beyond the primary).
SLUG_TYPE_MODIFIERS: Dict[str, Dict[str, float]] = {
    SlugType.STANDARD.value: {
        "armor_penetration_mult": 1.0,
        "subsystem_damage_mult": 1.0,
        "extra_subsystem_hits": 0,
    },
    SlugType.SABOT.value: {
        "armor_penetration_mult": 1.5,   # Narrow dart punches through
        "subsystem_damage_mult": 0.7,    # Less fragmentation inside target
        "extra_subsystem_hits": 0,
    },
    SlugType.FRAGMENTATION.value: {
        "armor_penetration_mult": 0.5,   # Segments deflect on armor
        "subsystem_damage_mult": 1.5,    # Devastating fragmentation
        "extra_subsystem_hits": 2,       # Sprays across 2 extra subsystems
    },
}


class ChargeState(Enum):
    """Railgun capacitor charge state.

    IDLE: capacitor discharged, weapon cold. Transitions to CHARGING
          when a valid firing solution exists and target is locked.
    CHARGING: capacitor energising toward full charge. Progress tracked
              as 0.0 -> 1.0 over specs.charge_time seconds.
    READY: capacitor at full charge, weapon may fire. Holds until
           fire command or lock is lost (resets to IDLE).
    """
    IDLE = "idle"
    CHARGING = "charging"
    READY = "ready"


@dataclass
class WeaponSpecs:
    """Physical specifications for a weapon."""
    name: str
    weapon_type: WeaponType
    damage_type: DamageType

    # Ballistics
    muzzle_velocity: float  # m/s - projectile speed
    effective_range: float  # m - max effective engagement range
    min_range: float = 0.0  # m - minimum arming/engagement distance

    # Damage
    base_damage: float = 10.0  # hull damage per hit
    subsystem_damage: float = 5.0  # damage to targeted subsystem
    armor_penetration: float = 1.0  # multiplier vs armored targets

    # Fire rate
    cycle_time: float = 1.0  # seconds between shots
    burst_count: int = 1  # shots per trigger pull
    burst_delay: float = 0.1  # seconds between burst shots

    # Ammunition
    ammo_capacity: Optional[int] = None  # None = unlimited
    mass_per_round: float = 0.0  # kg per round (affects ship mass via F=ma)
    reload_time: float = 0.0  # seconds to reload/cycle magazine (0 = no reload delay)

    # Power
    power_per_shot: float = 10.0  # power units consumed per shot
    charge_time: float = 0.0  # seconds to charge before firing

    # Accuracy
    base_accuracy: float = 0.95  # hit probability at point blank
    accuracy_falloff: float = 0.5  # accuracy loss at max range (0-1)
    tracking_speed: float = 30.0  # degrees/sec for turret tracking


# Pre-defined weapon specifications
RAILGUN_SPECS = WeaponSpecs(
    name="UNE-440 Railgun",
    weapon_type=WeaponType.KINETIC,
    damage_type=DamageType.KINETIC_PENETRATOR,
    muzzle_velocity=20000.0,  # 20 km/s - tungsten penetrator (design spec)
    effective_range=500000.0,  # 500 km effective range (design spec)
    min_range=500.0,  # Need some distance to track
    base_damage=55.0,  # Heavy hull damage — railgun is a high-skill penetrator, devastating on hit
    subsystem_damage=37.0,  # ~67% of hull damage — 1 subsystem per hit (design spec)
    armor_penetration=1.5,  # Good vs armor
    cycle_time=5.0,  # 5 seconds between shots
    burst_count=1,
    burst_delay=0.0,
    ammo_capacity=20,  # Limited heavy rounds
    mass_per_round=5.0,  # 5 kg tungsten penetrator
    reload_time=0.0,  # Railgun uses electromagnetic acceleration, no magazine reload
    power_per_shot=50.0,  # High power draw
    charge_time=2.0,  # 2 second charge
    base_accuracy=0.85,  # High accuracy
    accuracy_falloff=0.3,  # Maintains accuracy at range
    tracking_speed=15.0,  # Slower tracking (heavy weapon)
)

PDC_SPECS = WeaponSpecs(
    name="Narwhal-III PDC",
    weapon_type=WeaponType.KINETIC,
    damage_type=DamageType.KINETIC_FRAGMENTATION,
    muzzle_velocity=2000.0,  # 2 km/s - 40mm CIWS rounds (Expanse-style)
    effective_range=2000.0,  # 2 km - accuracy-limited, not physics-limited
    min_range=50.0,  # Very close engagement
    base_damage=5.0,  # Light damage per round (ablative, not penetrating)
    subsystem_damage=3.0,  # Can chip away at external subsystems
    armor_penetration=0.5,  # Poor vs heavy armor — strips plating, doesn't punch
    cycle_time=0.02,  # 50 rps = 3000 RPM per turret (Expanse CIWS fire rate)
    burst_count=10,  # Longer bursts — sustained fire strips armor
    burst_delay=0.02,  # Matches cycle time for continuous stream
    ammo_capacity=3000,  # High ammo count — bullet hose needs deep magazines
    mass_per_round=0.05,  # 50g 40mm autocannon rounds
    reload_time=3.0,  # 3 seconds to swap magazine (every 200 rounds)
    power_per_shot=2.0,  # Low power per shot — kinetic, not EM
    charge_time=0.0,  # No charge needed
    base_accuracy=0.95,  # Computer-controlled turret, very accurate at short range
    accuracy_falloff=0.9,  # Severe falloff — accuracy craters beyond 1km
    tracking_speed=180.0,  # Fast tracking — CIWS turret, must intercept missiles
)


def _range_accuracy(specs: WeaponSpecs, range_m: float) -> float:
    """Compute range-dependent accuracy for a weapon.

    PDCs (KINETIC_FRAGMENTATION) use a steep exponential falloff curve
    modeled on Expanse-style CIWS turrets: computer-controlled and
    near-perfect at knife-fight range, but 40mm rounds disperse fast
    and lose predictability beyond 1km.

    The curve is tuned to match Expanse combat doctrine:
        500m  -> ~0.95  (point-blank, computer-controlled)
        1000m -> ~0.70  (effective engagement range)
        2000m -> ~0.30  (edge of effective range, mostly suppression)
        3000m -> ~0.05  (desperation fire, near-zero hit chance)

    All other weapons use the original linear falloff:
        accuracy = base_accuracy - accuracy_falloff * (range / effective_range)

    Args:
        specs: Weapon specifications.
        range_m: Distance to target in meters.

    Returns:
        float: Hit probability from range alone (before lateral vel, etc.).
    """
    if specs.damage_type == DamageType.KINETIC_FRAGMENTATION:
        # Exponential decay: accuracy = base * exp(-k * range)
        # Tuned so that at 1km accuracy is ~0.70 and at 2km ~0.30.
        # k = -ln(0.70 / 0.95) / 1000 ≈ 0.000305
        # Verification: 0.95 * exp(-0.000305 * 2000) ≈ 0.52 — slightly
        # generous. Use k=0.00058 for sharper falloff matching the spec:
        # 0.95 * exp(-0.00058 * 500)  = 0.71 — too low at 500m.
        # Instead use a piecewise approach that exactly matches doctrine:
        #   [0, 500m]:     0.95 (flat, computer-controlled)
        #   [500m, 2000m]: cubic falloff from 0.95 -> 0.05
        #   [2000m+]:      0.05 floor (desperation fire)
        if range_m <= 500.0:
            return specs.base_accuracy  # ~0.95 at knife-fight range
        elif range_m >= specs.effective_range:
            return 0.05  # Beyond effective range, near-zero
        else:
            # Cubic falloff from 500m to effective_range (2000m)
            # t=0 at 500m, t=1 at effective_range
            t = (range_m - 500.0) / (specs.effective_range - 500.0)
            # Smoothstep-like: starts high, drops sharply past midpoint
            # At t=0: 0.95, at t=0.33 (~1000m): ~0.70, at t=1: 0.05
            return specs.base_accuracy - (specs.base_accuracy - 0.05) * (3 * t**2 - 2 * t**3)
    else:
        # Railgun and other weapons: linear falloff (original model)
        range_factor = range_m / specs.effective_range
        return specs.base_accuracy - specs.accuracy_falloff * range_factor


def pdc_range_accuracy(range_m: float) -> float:
    """Public helper for PDC accuracy at a given range.

    Convenience wrapper used by simulator.py for torpedo intercept
    calculations. Returns the same curve as the internal model.

    Args:
        range_m: Distance to target in meters.

    Returns:
        float: PDC hit probability from range alone.
    """
    return _range_accuracy(PDC_SPECS, range_m)


@dataclass
class FiringSolution:
    """Calculated firing solution for engaging a target."""
    valid: bool = False
    target_id: Optional[str] = None

    # Geometry
    range_to_target: float = 0.0  # Current range (m)
    lead_angle: Dict[str, float] = field(default_factory=lambda: {"pitch": 0.0, "yaw": 0.0})
    intercept_point: Dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    time_of_flight: float = 0.0  # Projectile flight time (s)

    # Engagement quality
    confidence: float = 0.0  # 0-1 overall solution confidence (design spec)
    hit_probability: float = 0.0  # 0-1 chance to hit
    in_range: bool = False  # Within weapon effective range
    in_arc: bool = False  # Within weapon firing arc
    target_closing: bool = False  # Target is closing
    closing_speed: float = 0.0  # Relative closing velocity (m/s)

    # Confidence breakdown — each physical factor that feeds into confidence
    confidence_factors: Dict[str, float] = field(default_factory=lambda: {
        "track_quality": 0.0,     # Sensor data freshness/accuracy (0-1)
        "range_factor": 0.0,      # Range degradation (0-1, lower = further)
        "target_accel": 0.0,      # Target maneuver penalty (0-1, lower = harder)
        "own_rotation": 0.0,      # Own ship rotation/vibration penalty (0-1)
        "weapon_health": 0.0,     # Weapon system damage factor (0-1)
        "time_of_flight": 0.0,    # Long-flight uncertainty penalty (0-1)
    })

    # Confidence cone — dispersion area at target range
    cone_radius_m: float = 0.0   # Radius of impact cone at target range (m)
    cone_angle_deg: float = 0.0  # Half-angle of cone (degrees)

    # Snapshot of conditions at solution time (for causal feedback after impact)
    target_accel_magnitude: float = 0.0  # Target acceleration when fired (m/s²)
    lateral_velocity: float = 0.0  # Target lateral velocity (m/s)

    # Status
    tracking: bool = False  # Turret is tracking target
    ready_to_fire: bool = False  # All conditions met
    reason: str = ""  # Explanation if not ready


class TruthWeapon:
    """Physics-based weapon with realistic ballistics and engagement."""

    def __init__(self, specs: WeaponSpecs, mount_id: str = "default"):
        """Initialize weapon with specifications.

        Args:
            specs: Weapon physical specifications
            mount_id: Unique identifier for this weapon mount
        """
        self.specs = specs
        self.mount_id = mount_id

        # State
        self.enabled = True
        self.ammo = specs.ammo_capacity
        self.heat = 0.0
        self.max_heat = 100.0

        # Timing
        self.last_fired = -specs.cycle_time  # Ready to fire immediately

        # Charge state machine — only active when specs.charge_time > 0
        # (railgun capacitor bank needs time to energise before firing).
        # PDCs have charge_time=0 so these fields are inert for them.
        self._charge_state: ChargeState = ChargeState.IDLE
        self._charge_progress: float = 0.0
        self._charge_target_id: Optional[str] = None  # target the charge is coupled to

        # Reload state (magazine-based for PDCs, per-round for railguns)
        self.reloading = False
        self.reload_progress = 0.0  # 0.0 to 1.0
        self._reload_timer = 0.0
        # PDC magazine: reload triggers every N rounds
        self._magazine_size = 200 if specs.reload_time > 0 else 0
        self._rounds_since_reload = 0

        # Firing arc constraints (set from ship_class weapon_mounts config)
        self.firing_arc: Optional[Dict[str, float]] = None  # {azimuth_min, azimuth_max, elevation_min, elevation_max}

        # PDC operating mode (auto=point defense, manual=fire on command, hold_fire=cease)
        self.pdc_mode: str = "auto" if mount_id.startswith("pdc") else "manual"

        # Tracking
        self.current_solution: Optional[FiringSolution] = None
        self.turret_bearing = {"pitch": 0.0, "yaw": 0.0}
        self.target_bearing = {"pitch": 0.0, "yaw": 0.0}

        # Gimbal state: independent turret tracking within arc limits.
        # When gimbal_enabled is True, the weapon slews its own azimuth
        # and elevation toward the desired lead angle at max_rotation_rate,
        # clamped to the hardpoint's arc limits. The weapon only reports
        # "tracking" when gimbal error drops below a weapon-specific
        # threshold (tight for railguns, loose for PDCs).
        self.gimbal_enabled: bool = False
        self.current_azimuth: float = 0.0   # Current gimbal azimuth (deg, ship-relative)
        self.current_elevation: float = 0.0  # Current gimbal elevation (deg, ship-relative)
        self._gimbal_az_limits: tuple = (-180.0, 180.0)
        self._gimbal_el_limits: tuple = (-90.0, 90.0)
        self._gimbal_max_rate: float = 0.0  # deg/s, copied from hardpoint config
        self._gimbal_error: float = 0.0     # RSS error to desired angles (deg)

        # Events
        self.event_bus = EventBus.get_instance()

    def tick(self, dt: float, sim_time: float):
        """Update weapon state each tick.

        Args:
            dt: Time delta
            sim_time: Current simulation time
        """
        # Passive heat dissipation
        if self.heat > 0:
            self.heat = max(0.0, self.heat - dt * 5.0)

        # Reload timer
        if self.reloading:
            self._reload_timer -= dt
            if self._reload_timer <= 0:
                self.reloading = False
                self._reload_timer = 0.0
                self.reload_progress = 1.0
                self._rounds_since_reload = 0
                self.event_bus.publish("weapon_reloaded", {
                    "weapon": self.specs.name,
                    "mount_id": self.mount_id,
                })
            else:
                self.reload_progress = 1.0 - (self._reload_timer / self.specs.reload_time)

        # Turret tracking (legacy bearing-based)
        if self.current_solution and self.current_solution.valid:
            self._update_turret_tracking(dt)

        # Gimbal tracking — independent turret slew toward lead angle.
        # Runs every tick regardless of solution validity so the gimbal
        # holds its last commanded position when the solution drops.
        if self.gimbal_enabled:
            self._update_gimbal(dt)

        # Charge state machine — advances capacitor toward READY when a
        # valid solution exists on a locked target. Resets to IDLE if
        # the lock is lost or the solution drops. PDCs (charge_time=0)
        # skip this entirely.
        self._update_charge_state(dt)

    def _update_charge_state(self, dt: float) -> None:
        """Advance the capacitor charge state machine.

        Weapons with charge_time <= 0 (e.g. PDCs) are always implicitly
        READY and this method is a no-op for them.

        Charging begins when a valid firing solution exists (target is
        locked and in range). If the solution is lost mid-charge the
        capacitor dumps and progress resets to zero — the weapon must
        start charging from scratch once a new lock is established.
        """
        if self.specs.charge_time <= 0:
            return  # No charge required (PDC, etc.)

        has_valid_solution = (
            self.current_solution is not None
            and self.current_solution.valid
            and self.current_solution.target_id is not None
        )

        if not has_valid_solution:
            # Lock lost or solution dropped — dump capacitor
            if self._charge_state != ChargeState.IDLE:
                self._charge_state = ChargeState.IDLE
                self._charge_progress = 0.0
                self._charge_target_id = None
            return

        current_target = self.current_solution.target_id

        # Target changed mid-charge — capacitor is coupled to the old
        # firing solution geometry, so dump and restart.
        if self._charge_target_id is not None and current_target != self._charge_target_id:
            self._charge_state = ChargeState.IDLE
            self._charge_progress = 0.0
            self._charge_target_id = None

        if self._charge_state == ChargeState.IDLE:
            # Begin charging for this target
            self._charge_state = ChargeState.CHARGING
            self._charge_progress = 0.0
            self._charge_target_id = current_target

        if self._charge_state == ChargeState.CHARGING:
            self._charge_progress = min(
                1.0, self._charge_progress + dt / self.specs.charge_time
            )
            if self._charge_progress >= 1.0:
                self._charge_state = ChargeState.READY

        # READY state holds until fire() consumes it or lock is lost
        # (handled by the has_valid_solution check above).

    def _update_turret_tracking(self, dt: float):
        """Update turret position to track target."""
        target = self.current_solution.lead_angle
        max_move = self.specs.tracking_speed * dt

        for axis in ["pitch", "yaw"]:
            diff = target[axis] - self.turret_bearing[axis]
            # Normalize angle difference
            while diff > 180:
                diff -= 360
            while diff < -180:
                diff += 360

            # Move turret toward target
            if abs(diff) <= max_move:
                self.turret_bearing[axis] = target[axis]
            else:
                self.turret_bearing[axis] += max_move if diff > 0 else -max_move

    def _update_gimbal(self, dt: float) -> None:
        """Slew gimbal azimuth/elevation toward the desired lead angle.

        The gimbal tracks the firing solution's lead angle in the ship-
        relative frame. It slews at _gimbal_max_rate deg/s and clamps to
        the hardpoint's arc limits. When no valid solution exists the
        gimbal holds its current position (does not snap to boresight).

        Gimbal error is the RSS of azimuth and elevation deltas. The
        weapon reports ``tracking = True`` only when error falls below a
        threshold that depends on weapon type:
          - Railgun: 1 deg (tight, needs precise aim for a single slug)
          - PDC: 5 deg (loose, sustained burst covers the spread)
        """
        if self._gimbal_max_rate <= 0.0:
            return

        # Determine desired angles from the firing solution.
        # If no valid solution, hold position (gimbal error stays stale).
        if self.current_solution and self.current_solution.valid:
            desired_az = self.current_solution.lead_angle.get("yaw", 0.0)
            desired_el = self.current_solution.lead_angle.get("pitch", 0.0)
        else:
            # No solution -- hold current position, report large error
            self._gimbal_error = 999.0
            return

        max_move = self._gimbal_max_rate * dt

        # Slew azimuth
        az_diff = desired_az - self.current_azimuth
        # Normalise to [-180, 180]
        while az_diff > 180.0:
            az_diff -= 360.0
        while az_diff < -180.0:
            az_diff += 360.0
        if abs(az_diff) <= max_move:
            new_az = desired_az
        else:
            new_az = self.current_azimuth + (max_move if az_diff > 0 else -max_move)

        # Slew elevation
        el_diff = desired_el - self.current_elevation
        while el_diff > 180.0:
            el_diff -= 360.0
        while el_diff < -180.0:
            el_diff += 360.0
        if abs(el_diff) <= max_move:
            new_el = desired_el
        else:
            new_el = self.current_elevation + (max_move if el_diff > 0 else -max_move)

        # Clamp to arc limits.
        # Azimuth limits may wrap (e.g. aft-facing: 90..270). Clamping
        # in that case is non-trivial, so for simplicity we clamp to
        # the nearest limit if the new value falls outside the arc.
        az_lo, az_hi = self._gimbal_az_limits
        if az_lo <= az_hi:
            new_az = max(az_lo, min(az_hi, new_az))
        else:
            # Wrapping arc: valid if new_az >= az_lo OR new_az <= az_hi.
            # If outside, snap to whichever limit is closer.
            norm_az = new_az
            while norm_az > 180.0:
                norm_az -= 360.0
            while norm_az < -180.0:
                norm_az += 360.0
            if not (norm_az >= az_lo or norm_az <= az_hi):
                dist_lo = abs(norm_az - az_lo)
                dist_hi = abs(norm_az - az_hi)
                new_az = az_lo if dist_lo < dist_hi else az_hi

        el_lo, el_hi = self._gimbal_el_limits
        new_el = max(el_lo, min(el_hi, new_el))

        self.current_azimuth = new_az
        self.current_elevation = new_el

        # Compute residual error (how far gimbal is from desired aim)
        final_az_diff = desired_az - self.current_azimuth
        while final_az_diff > 180.0:
            final_az_diff -= 360.0
        while final_az_diff < -180.0:
            final_az_diff += 360.0
        final_el_diff = desired_el - self.current_elevation
        self._gimbal_error = math.sqrt(final_az_diff ** 2 + final_el_diff ** 2)

    def calculate_solution(
        self,
        shooter_pos: Dict[str, float],
        shooter_vel: Dict[str, float],
        target_pos: Dict[str, float],
        target_vel: Dict[str, float],
        target_id: str,
        sim_time: float,
        track_quality: float = 1.0,
        shooter_angular_vel: Optional[Dict[str, float]] = None,
        weapon_damage_factor: float = 1.0,
        target_accel: Optional[Dict[str, float]] = None,
        shooter_heading: Optional[Dict[str, float]] = None,
    ) -> FiringSolution:
        """Calculate firing solution for a target.

        Uses lead prediction to calculate where to aim to hit a moving target.
        Computes a physics-derived confidence score from five factors:
        track quality, range, target acceleration, own ship rotation, and
        weapon system health.

        Args:
            shooter_pos: Shooter position {x, y, z}
            shooter_vel: Shooter velocity {x, y, z}
            target_pos: Target position {x, y, z}
            target_vel: Target velocity {x, y, z}
            target_id: Target identifier
            sim_time: Current simulation time
            track_quality: Track quality from targeting system (0-1).
                Degrades with range and target acceleration. Defaults to 1.0.
            shooter_angular_vel: Own ship angular velocity {pitch, yaw, roll}
                in deg/s. Ship rotation degrades aim stability.
            weapon_damage_factor: Weapon system health factor (0-1).
                Damaged weapons have degraded firing solutions.
            target_accel: Target acceleration vector {x, y, z} in m/s².
                Maneuvering targets are harder to predict during slug flight.
            shooter_heading: Ship orientation {pitch, yaw, roll} in degrees.
                Required for firing arc checks — arcs are defined relative
                to the ship's nose, so world-space aim angles must be
                converted to ship-relative bearings for comparison.

        Returns:
            FiringSolution with engagement data including confidence score.
        """
        solution = FiringSolution(target_id=target_id)

        # Calculate relative position and velocity
        rel_pos = {
            "x": target_pos["x"] - shooter_pos["x"],
            "y": target_pos["y"] - shooter_pos["y"],
            "z": target_pos["z"] - shooter_pos["z"],
        }
        rel_vel = {
            "x": target_vel["x"] - shooter_vel["x"],
            "y": target_vel["y"] - shooter_vel["y"],
            "z": target_vel["z"] - shooter_vel["z"],
        }

        # Current range
        range_sq = rel_pos["x"]**2 + rel_pos["y"]**2 + rel_pos["z"]**2
        solution.range_to_target = math.sqrt(range_sq) if range_sq > 0 else 0.001

        # Range check
        solution.in_range = (
            self.specs.min_range <= solution.range_to_target <= self.specs.effective_range
        )

        # Closing speed (negative rel_vel dot range_direction = closing)
        range_direction = {
            k: rel_pos[k] / solution.range_to_target for k in ["x", "y", "z"]
        }
        solution.closing_speed = -(
            rel_vel["x"] * range_direction["x"] +
            rel_vel["y"] * range_direction["y"] +
            rel_vel["z"] * range_direction["z"]
        )
        solution.target_closing = solution.closing_speed > 0

        # Calculate lead angle using quadratic solution
        # We need to find time t such that:
        # |target_pos + target_vel * t - shooter_pos| = muzzle_velocity * t

        # Coefficients for quadratic: a*t^2 + b*t + c = 0
        projectile_speed = self.specs.muzzle_velocity

        a = (rel_vel["x"]**2 + rel_vel["y"]**2 + rel_vel["z"]**2) - projectile_speed**2
        b = 2 * (rel_pos["x"] * rel_vel["x"] +
                 rel_pos["y"] * rel_vel["y"] +
                 rel_pos["z"] * rel_vel["z"])
        c = range_sq

        # Solve quadratic
        discriminant = b**2 - 4 * a * c

        if discriminant < 0 or abs(a) < 0.001:
            # No solution or nearly stationary - aim directly
            solution.time_of_flight = solution.range_to_target / projectile_speed
            solution.intercept_point = dict(target_pos)
        else:
            # Two solutions - take the positive one
            sqrt_disc = math.sqrt(discriminant)
            t1 = (-b + sqrt_disc) / (2 * a)
            t2 = (-b - sqrt_disc) / (2 * a)

            # Choose smallest positive time
            if t1 > 0 and t2 > 0:
                solution.time_of_flight = min(t1, t2)
            elif t1 > 0:
                solution.time_of_flight = t1
            elif t2 > 0:
                solution.time_of_flight = t2
            else:
                # No valid solution
                solution.time_of_flight = solution.range_to_target / projectile_speed
                solution.intercept_point = dict(target_pos)
                solution.valid = False
                solution.reason = "No intercept solution"
                self.current_solution = solution
                return solution

            # Calculate intercept point
            solution.intercept_point = {
                "x": target_pos["x"] + target_vel["x"] * solution.time_of_flight,
                "y": target_pos["y"] + target_vel["y"] * solution.time_of_flight,
                "z": target_pos["z"] + target_vel["z"] * solution.time_of_flight,
            }

        # Calculate lead angle (direction to intercept point)
        aim_vector = {
            "x": solution.intercept_point["x"] - shooter_pos["x"],
            "y": solution.intercept_point["y"] - shooter_pos["y"],
            "z": solution.intercept_point["z"] - shooter_pos["z"],
        }
        aim_dist = math.sqrt(aim_vector["x"]**2 + aim_vector["y"]**2 + aim_vector["z"]**2)

        if aim_dist > 0.001:
            # Calculate yaw (horizontal angle) and pitch (vertical angle)
            solution.lead_angle["yaw"] = math.degrees(
                math.atan2(aim_vector["y"], aim_vector["x"])
            )
            horiz_dist = math.sqrt(aim_vector["x"]**2 + aim_vector["y"]**2)
            if horiz_dist > 0.001:
                solution.lead_angle["pitch"] = math.degrees(
                    math.atan2(aim_vector["z"], horiz_dist)
                )

        # Calculate hit probability
        # Accuracy degrades with range — PDCs use a steep exponential curve
        # because 40mm rounds spread and lose predictability fast, while
        # railgun slugs maintain accuracy through superior muzzle velocity.
        range_accuracy = _range_accuracy(
            self.specs, solution.range_to_target
        )

        # Closing speed penalty for PDC against fast targets (missiles, torpedoes).
        # A target approaching at a significant fraction of the PDC's muzzle
        # velocity shortens the engagement window and reduces the number of
        # rounds that can be walked onto target before it arrives. At 50% of
        # muzzle velocity the effective accuracy drops by 25%; at 100% by 50%.
        if self.specs.damage_type == DamageType.KINETIC_FRAGMENTATION:
            closing_speed = getattr(solution, 'closing_speed', 0.0)
            if closing_speed > 0 and self.specs.muzzle_velocity > 0:
                speed_ratio = closing_speed / self.specs.muzzle_velocity
                speed_penalty = max(0.5, 1.0 - speed_ratio * 0.5)
                range_accuracy *= speed_penalty

        # Lateral velocity reduces accuracy
        lateral_vel_sq = (
            (rel_vel["x"] - solution.closing_speed * range_direction["x"])**2 +
            (rel_vel["y"] - solution.closing_speed * range_direction["y"])**2 +
            (rel_vel["z"] - solution.closing_speed * range_direction["z"])**2
        )
        lateral_vel = math.sqrt(lateral_vel_sq)
        # Scale lateral penalty by muzzle velocity: slow bullets (PDC) are much more
        # sensitive to lateral movement than fast slugs (railgun). The 0.025 factor
        # means lateral vel at 2.5% of muzzle velocity halves hit probability.
        lateral_factor = max(0.3, 1.0 - lateral_vel / max(100.0, self.specs.muzzle_velocity * 0.025))

        # Weapon-specific hit probability bounds reflect engagement doctrine:
        # Railgun: precision weapon with a single slug — can thread the needle
        #   at optimal range but has no volume-of-fire to compensate for errors,
        #   so both floor and ceiling are lower than spray weapons.
        # PDC: 3000 RPM suppression fire — high baseline at close range because
        #   sheer volume compensates for individual round dispersion, but the
        #   ceiling is capped because no amount of bullets fixes bad geometry.
        if self.specs.damage_type == DamageType.KINETIC_PENETRATOR:
            hp_floor, hp_ceil = 0.02, 0.85
        elif self.specs.damage_type == DamageType.KINETIC_FRAGMENTATION:
            hp_floor, hp_ceil = 0.15, 0.95
        else:
            hp_floor, hp_ceil = 0.05, 0.90

        solution.hit_probability = max(hp_floor, min(hp_ceil, range_accuracy * lateral_factor))

        # --- Confidence from five physical factors (design spec) ---
        # 1. Track quality: sensor data freshness and accuracy (from targeting system)
        cf_track = max(0.0, min(1.0, track_quality))

        # 2. Range factor: longer range = more time for target to maneuver
        #    during slug flight. Normalised as accuracy at range.
        cf_range = max(0.1, min(1.0, range_accuracy))

        # 3. Target acceleration: maneuvering targets are unpredictable
        #    during the slug's flight time. Even moderate burns during
        #    a 25-second flight invalidate the ballistic assumption.
        target_accel_mag = 0.0
        if target_accel:
            target_accel_mag = math.sqrt(
                target_accel.get("x", 0)**2 +
                target_accel.get("y", 0)**2 +
                target_accel.get("z", 0)**2
            )
        # 1G (10 m/s²) = no penalty; 5G (50 m/s²) = 50% penalty; 10G+ = severe
        cf_accel = max(0.2, 1.0 - target_accel_mag / 100.0)
        solution.target_accel_magnitude = target_accel_mag
        solution.lateral_velocity = lateral_vel

        # 4. Own ship rotation/vibration: angular velocity degrades aim
        #    stability. Turret gimbals can compensate for slow rotations
        #    but fast spins blur the aim.
        rotation_magnitude = 0.0
        if shooter_angular_vel:
            rotation_magnitude = math.sqrt(
                shooter_angular_vel.get("pitch", 0)**2 +
                shooter_angular_vel.get("yaw", 0)**2 +
                shooter_angular_vel.get("roll", 0)**2
            )
        # 5 deg/s = no penalty; 30 deg/s = ~50% penalty; 60+ deg/s = severe
        cf_rotation = max(0.3, 1.0 - rotation_magnitude / 60.0)

        # 5. Weapon system health: damaged weapons have degraded fire control
        cf_weapon = max(0.1, min(1.0, weapon_damage_factor))

        # 6. Time-of-flight degradation
        # Longer flights accumulate uncertainty from target maneuvers
        # that weren't predicted at fire time. Even a gentle 1G burn
        # over 25s displaces the target ~3km from the ballistic prediction.
        # At 0s: 1.0, at 10s: 0.8, at 25s: 0.5, at 50s: floor of 0.1
        tof = getattr(solution, 'time_of_flight', 0.0)
        cf_tof = max(0.1, 1.0 - tof / 50.0)

        # Store individual factors for telemetry/GUI breakdown
        solution.confidence_factors = {
            "track_quality": round(cf_track, 3),
            "range_factor": round(cf_range, 3),
            "target_accel": round(cf_accel, 3),
            "own_rotation": round(cf_rotation, 3),
            "weapon_health": round(cf_weapon, 3),
            "time_of_flight": round(cf_tof, 3),
        }

        # Overall confidence is the product of all factors
        solution.confidence = max(0.0, min(1.0,
            cf_track * cf_range * cf_accel * cf_rotation * cf_weapon * cf_tof
        ))

        # --- Confidence cone calculation ---
        # The cone represents the dispersion area at target range.
        # Lower confidence = wider cone = larger possible miss area.
        # At confidence=1.0, cone angle is minimal (weapon base spread).
        # Base angular spread from weapon accuracy at this range
        base_spread_rad = math.asin(max(0.001, min(0.999,
            1.0 - solution.hit_probability
        )))
        # Confidence scales the cone: low confidence widens dispersion
        effective_spread = base_spread_rad / max(0.1, solution.confidence)
        effective_spread = min(effective_spread, math.radians(15.0))  # Cap at 15 degrees

        solution.cone_angle_deg = round(math.degrees(effective_spread), 2)
        solution.cone_radius_m = round(
            solution.range_to_target * math.tan(effective_spread), 1
        )

        # Check turret tracking.
        # Gimballed weapons use their own slewed azimuth/elevation error
        # against weapon-specific thresholds:
        #   Railgun: 1 deg — tight, single slug needs precise aim
        #   PDC: 5 deg — loose, sustained burst covers the cone
        # Non-gimballed weapons use the legacy turret bearing check.
        if self.gimbal_enabled:
            turret_error = self._gimbal_error
            if self.specs.damage_type == DamageType.KINETIC_PENETRATOR:
                tracking_threshold = 1.0  # Railgun: precise
            else:
                tracking_threshold = 5.0  # PDC: permissive burst cone
        else:
            turret_error = math.sqrt(
                (self.turret_bearing["pitch"] - solution.lead_angle["pitch"])**2 +
                (self.turret_bearing["yaw"] - solution.lead_angle["yaw"])**2
            )
            tracking_threshold = 5.0
        solution.tracking = turret_error < tracking_threshold

        # Check firing arc constraints from weapon mount config.
        # Arcs are defined in ship-relative coordinates (0 azimuth = nose),
        # so the world-space aim direction must be converted to a bearing
        # relative to the ship's heading before comparison.
        if self.firing_arc:
            az_min = self.firing_arc.get("azimuth_min", -180)
            az_max = self.firing_arc.get("azimuth_max", 180)
            el_min = self.firing_arc.get("elevation_min", -90)
            el_max = self.firing_arc.get("elevation_max", 90)

            if shooter_heading is not None:
                # Convert intercept-point bearing to ship-relative frame.
                # We use the same quaternion-based calculate_bearing that
                # the sensor system uses, giving us a proper 3D rotation
                # from world space into the ship body frame.
                from hybrid.utils.math_utils import calculate_bearing
                rel_bearing = calculate_bearing(
                    shooter_pos, solution.intercept_point, shooter_heading
                )
                yaw = rel_bearing["yaw"]
                pitch = rel_bearing["pitch"]
            else:
                # Fallback: no heading provided, use world-space angles.
                # Only correct if the ship faces along +X (yaw=0, pitch=0).
                yaw = solution.lead_angle["yaw"]
                pitch = solution.lead_angle["pitch"]

            # Normalize yaw to [-180, 180] for comparison
            while yaw > 180:
                yaw -= 360
            while yaw < -180:
                yaw += 360
            # Azimuth check handles arcs that wrap past +/-180
            # (e.g. rear-facing arc: az_min=170, az_max=-170)
            if az_min <= az_max:
                az_ok = az_min <= yaw <= az_max
            else:
                # Wrapping arc: valid if yaw >= min OR yaw <= max
                az_ok = yaw >= az_min or yaw <= az_max
            el_ok = el_min <= pitch <= el_max
            solution.in_arc = az_ok and el_ok
        else:
            solution.in_arc = True  # No arc constraints defined

        # Ready to fire check
        time_since_fired = sim_time - self.last_fired
        cooldown_ready = time_since_fired >= self.specs.cycle_time
        ammo_ok = self.ammo is None or self.ammo > 0
        heat_ok = self.heat < self.max_heat * 0.9
        # Charge gate: weapons with charge_time>0 must be fully charged.
        # PDCs (charge_time=0) are always considered charged.
        charge_ready = (
            self.specs.charge_time <= 0
            or self._charge_state == ChargeState.READY
        )

        solution.ready_to_fire = (
            self.enabled and
            not self.reloading and
            solution.in_range and
            solution.in_arc and
            solution.tracking and
            cooldown_ready and
            ammo_ok and
            heat_ok and
            charge_ready
        )

        if not solution.ready_to_fire:
            if not self.enabled:
                solution.reason = "Weapon disabled"
            elif self.reloading:
                solution.reason = f"Reloading ({self.reload_progress * 100:.0f}%)"
            elif not solution.in_range:
                if solution.range_to_target < self.specs.min_range:
                    solution.reason = f"Target too close ({solution.range_to_target:.0f}m < {self.specs.min_range:.0f}m)"
                else:
                    solution.reason = f"Target out of range ({solution.range_to_target:.0f}m > {self.specs.effective_range:.0f}m)"
            elif not solution.in_arc:
                solution.reason = "Target outside firing arc"
            elif not solution.tracking:
                solution.reason = f"Turret tracking ({turret_error:.1f} deg error)"
            elif not cooldown_ready:
                remaining = self.specs.cycle_time - time_since_fired
                solution.reason = f"Cycling ({remaining:.1f}s remaining)"
            elif not charge_ready:
                pct = self._charge_progress * 100
                solution.reason = f"Charging ({pct:.0f}%)"
            elif not ammo_ok:
                solution.reason = "No ammunition"
            elif not heat_ok:
                solution.reason = "Overheating"

        solution.valid = solution.in_range
        self.current_solution = solution
        return solution

    def fire(
        self,
        sim_time: float,
        power_manager,
        target_ship=None,
        ship_id: str = None,
        damage_factor: float = 1.0,
        damage_model=None,
        event_bus=None,
        target_subsystem: str = None,
        projectile_manager=None,
        shooter_pos: Dict = None,
        shooter_vel: Dict = None,
        slug_type: Optional[str] = None,
    ) -> Dict:
        """Attempt to fire the weapon.

        For railguns (KINETIC_PENETRATOR), spawns a Newtonian projectile via
        projectile_manager instead of resolving hits instantly. The slug
        travels at muzzle_velocity along the firing solution's intercept
        vector and hit/miss is determined when it reaches the target.

        For PDCs and other weapons, hits are resolved instantly (short range).

        Args:
            sim_time: Current simulation time
            power_manager: Power system for power draw
            target_ship: Target ship object for damage application
            ship_id: Firing ship ID for events
            damage_factor: Weapon system damage degradation factor
            damage_model: Shooter's damage model for heat tracking
            event_bus: Ship event bus for publishing events
            target_subsystem: Specific subsystem to target
            projectile_manager: ProjectileManager for spawning ballistic slugs
            shooter_pos: Shooter position {x,y,z} for projectile spawn
            shooter_vel: Shooter velocity {x,y,z} for projectile velocity calc
            slug_type: Railgun slug variant (standard/sabot/fragmentation).
                None defaults to STANDARD. Only applies to railguns.

        Returns:
            dict: Fire result
        """
        # Check basic requirements
        if not self.enabled:
            return {"ok": False, "reason": "disabled"}

        if self.reloading:
            return {
                "ok": False,
                "reason": "reloading",
                "reload_remaining": self._reload_timer,
            }

        if damage_factor <= 0.0:
            return {"ok": False, "reason": "weapon_damaged"}

        if self.ammo is not None and self.ammo <= 0:
            return {"ok": False, "reason": "no_ammo"}

        time_since_fired = sim_time - self.last_fired
        if time_since_fired < self.specs.cycle_time:
            return {
                "ok": False,
                "reason": "cycling",
                "cooldown_remaining": self.specs.cycle_time - time_since_fired
            }

        if self.heat >= self.max_heat * 0.95:
            return {"ok": False, "reason": "overheated"}

        # Charge gate — railgun capacitor must be fully charged before
        # the weapon can fire. PDCs (charge_time=0) skip this.
        if self.specs.charge_time > 0 and self._charge_state != ChargeState.READY:
            return {
                "ok": False,
                "reason": "charging",
                "charge_state": self._charge_state.value,
                "charge_progress": round(self._charge_progress, 3),
            }

        # Check power
        if power_manager and not power_manager.request_power(
            self.specs.power_per_shot, "weapon"
        ):
            return {"ok": False, "reason": "insufficient_power"}

        # Check firing solution
        if not self.current_solution or not self.current_solution.valid:
            return {"ok": False, "reason": "no_solution"}

        if not self.current_solution.ready_to_fire:
            return {"ok": False, "reason": self.current_solution.reason}

        # Discharge capacitor — fire() has passed the charge gate so the
        # weapon is committed to firing. Reset so the next shot requires
        # a full charge cycle. tick() will begin charging again if a
        # valid solution persists.
        if self.specs.charge_time > 0:
            self._charge_state = ChargeState.IDLE
            self._charge_progress = 0.0

        # Railgun ballistic path: spawn projectile instead of instant hit
        is_railgun = self.specs.damage_type == DamageType.KINETIC_PENETRATOR
        if is_railgun and projectile_manager and shooter_pos:
            return self._fire_ballistic(
                sim_time=sim_time,
                damage_factor=damage_factor,
                damage_model=damage_model,
                event_bus=event_bus,
                target_subsystem=target_subsystem,
                projectile_manager=projectile_manager,
                shooter_pos=shooter_pos,
                shooter_vel=shooter_vel or {"x": 0, "y": 0, "z": 0},
                ship_id=ship_id,
                target_ship=target_ship,
                slug_type=slug_type,
            )

        # PDC / instant-hit path (short range weapons)
        return self._fire_instant(
            sim_time=sim_time,
            damage_factor=damage_factor,
            damage_model=damage_model,
            event_bus=event_bus,
            target_subsystem=target_subsystem,
            ship_id=ship_id,
            target_ship=target_ship,
        )

    def _fire_ballistic(
        self,
        sim_time: float,
        damage_factor: float,
        damage_model,
        event_bus,
        target_subsystem: str,
        projectile_manager,
        shooter_pos: Dict,
        shooter_vel: Dict,
        ship_id: str,
        target_ship,
        slug_type: Optional[str] = None,
    ) -> Dict:
        """Fire a railgun slug as a Newtonian projectile.

        The slug is unguided after launch — it follows a straight-line
        trajectory at muzzle_velocity toward the computed intercept point.
        Hit/miss is determined by the ProjectileManager when the slug
        reaches the target's vicinity.

        Slug type modifiers scale armor penetration, subsystem damage,
        and extra subsystem hits at impact time. STANDARD is the default
        when no slug_type is specified.

        Args:
            sim_time: Current simulation time
            damage_factor: Weapon degradation factor
            damage_model: Shooter damage model (for heat)
            event_bus: Ship event bus
            target_subsystem: Subsystem to target
            projectile_manager: ProjectileManager to spawn into
            shooter_pos: Shooter world position
            shooter_vel: Shooter world velocity
            ship_id: Firing ship ID
            target_ship: Target ship object
            slug_type: Slug variant (standard/sabot/fragmentation).
                None defaults to standard.

        Returns:
            dict: Fire result with projectile info
        """
        self.last_fired = sim_time
        target_id = getattr(target_ship, 'id', None) if target_ship else None

        # Resolve slug type modifiers — default to standard if unspecified
        resolved_slug = slug_type or SlugType.STANDARD.value
        slug_mods = SLUG_TYPE_MODIFIERS.get(resolved_slug, SLUG_TYPE_MODIFIERS[SlugType.STANDARD.value])

        # Consume ammo
        if self.ammo is not None:
            self.ammo -= 1

        # Heat generation (capacitor discharge)
        self.heat += 10.0 * (1.0 / max(0.5, damage_factor))
        if damage_model is not None:
            heat_scale = self.specs.subsystem_damage / max(1.0, self.specs.base_damage)
            heat_amount = self.specs.power_per_shot * (1.0 + heat_scale)
            if heat_amount > 0:
                damage_model.add_heat("weapons", heat_amount, event_bus, ship_id)

        # Calculate projectile velocity in world frame
        # Direction: toward the intercept point computed by the firing solution
        solution = self.current_solution
        aim_vec = {
            "x": solution.intercept_point["x"] - shooter_pos["x"],
            "y": solution.intercept_point["y"] - shooter_pos["y"],
            "z": solution.intercept_point["z"] - shooter_pos["z"],
        }
        aim_dist = math.sqrt(aim_vec["x"]**2 + aim_vec["y"]**2 + aim_vec["z"]**2)

        if aim_dist > 0.001:
            aim_dir = {k: aim_vec[k] / aim_dist for k in ["x", "y", "z"]}
        else:
            aim_dir = {"x": 1.0, "y": 0.0, "z": 0.0}

        # Slug velocity = shooter velocity + muzzle velocity in aim direction
        proj_vel = {
            "x": shooter_vel["x"] + aim_dir["x"] * self.specs.muzzle_velocity,
            "y": shooter_vel["y"] + aim_dir["y"] * self.specs.muzzle_velocity,
            "z": shooter_vel["z"] + aim_dir["z"] * self.specs.muzzle_velocity,
        }

        # Hit-location physics handles armor penetration at impact time,
        # so we pass base damage scaled only by weapon degradation.
        # The projectile carries mass and armor_pen for penetration calc on hit.
        # Slug type modifiers scale subsystem damage and armor pen —
        # sabot punches through armor but fragments less, frag does the opposite.
        effective_damage = self.specs.base_damage * damage_factor
        subsystem_dmg = self.specs.subsystem_damage * damage_factor * slug_mods["subsystem_damage_mult"]
        effective_armor_pen = self.specs.armor_penetration * slug_mods["armor_penetration_mult"]
        # No subsystem pre-selection — hit-location physics determines
        # which subsystem is hit based on intercept geometry
        subsystem_target = target_subsystem  # Only use explicit target, not random

        # Spawn projectile with firing conditions snapshot for causal feedback
        target_pos = solution.intercept_point  # predicted intercept
        target_vel_snapshot = {}
        if hasattr(self, '_last_target_vel'):
            target_vel_snapshot = self._last_target_vel
        # Get target data from the solution's target_data if available
        targeting = None
        if target_ship and hasattr(target_ship, 'systems'):
            # We're the shooter — get target pos/vel from our targeting system
            pass
        # Use the target_ship's current state for the snapshot
        if target_ship:
            target_vel_snapshot = getattr(target_ship, 'velocity', {"x": 0, "y": 0, "z": 0})
            target_pos = getattr(target_ship, 'position', solution.intercept_point)

        proj = projectile_manager.spawn(
            weapon_name=self.specs.name,
            weapon_mount=self.mount_id,
            shooter_id=ship_id,
            position=dict(shooter_pos),
            velocity=proj_vel,
            damage=effective_damage,
            subsystem_damage=subsystem_dmg,
            hit_probability=solution.hit_probability,
            sim_time=sim_time,
            target_id=target_id,
            target_subsystem=subsystem_target,
            hit_radius=50.0,
            mass=self.specs.mass_per_round,
            armor_penetration=effective_armor_pen,
            confidence=solution.confidence,
            confidence_factors=dict(solution.confidence_factors),
            target_vel_at_fire=dict(target_vel_snapshot) if target_vel_snapshot else {"x": 0, "y": 0, "z": 0},
            target_pos_at_fire=dict(target_pos) if target_pos else {"x": 0, "y": 0, "z": 0},
            target_accel_at_fire=solution.target_accel_magnitude,
            intercept_point=dict(solution.intercept_point),
        )

        # Publish weapon_fired event (slug launched, not yet hit)
        self.event_bus.publish("weapon_fired", {
            "weapon": self.specs.name,
            "mount_id": self.mount_id,
            "ship_id": ship_id,
            "target": target_id,
            "hit": None,  # Unknown — slug in flight
            "hits": 0,
            "rounds_fired": 1,
            "hit_probability": solution.hit_probability,
            "confidence": solution.confidence,
            "confidence_factors": solution.confidence_factors,
            "cone_radius_m": solution.cone_radius_m,
            "range": solution.range_to_target,
            "damage": 0,  # No damage yet — slug in flight
            "projectile_id": proj.id,
            "time_of_flight": solution.time_of_flight,
            "ballistic": True,
            "slug_type": resolved_slug,
        })

        return {
            "ok": True,
            "ballistic": True,
            "projectile_id": proj.id,
            "hit": None,  # Unknown — slug in flight
            "rounds_fired": 1,
            "damage": 0,
            "target": target_id,
            "range": solution.range_to_target,
            "time_of_flight": solution.time_of_flight,
            "hit_probability": solution.hit_probability,
            "confidence": solution.confidence,
            "confidence_factors": solution.confidence_factors,
            "cone_radius_m": solution.cone_radius_m,
            "ammo_remaining": self.ammo,
            "heat": self.heat,
            "slug_type": resolved_slug,
        }

    def _fire_instant(
        self,
        sim_time: float,
        damage_factor: float,
        damage_model,
        event_bus,
        target_subsystem: str,
        ship_id: str,
        target_ship,
    ) -> Dict:
        """Fire with instant hit resolution (PDC and short-range weapons).

        Args:
            sim_time: Current simulation time
            damage_factor: Weapon degradation factor
            damage_model: Shooter damage model (for heat)
            event_bus: Ship event bus
            target_subsystem: Subsystem to target
            ship_id: Firing ship ID
            target_ship: Target ship object

        Returns:
            dict: Fire result
        """
        import random

        self.last_fired = sim_time
        target_id = getattr(target_ship, 'id', None) if target_ship else None

        burst_hits = 0
        burst_damage = 0.0
        burst_rounds = 0
        burst_results = []

        # Consume one ammo unit per trigger pull (covers the entire burst)
        if self.ammo is not None:
            if self.ammo <= 0:
                return {"ok": False, "reason": "no_ammo"}
            self.ammo -= 1

        for shot_i in range(self.specs.burst_count):
            burst_rounds += 1

            # Magazine reload check per round (> 0: only count live rounds)
            if self._magazine_size > 0 and self.ammo is not None and self.ammo > 0:
                self._rounds_since_reload += 1
                if self._rounds_since_reload >= self._magazine_size:
                    self.reloading = True
                    self._reload_timer = self.specs.reload_time
                    self.reload_progress = 0.0
                    self.event_bus.publish("weapon_reloading", {
                        "weapon": self.specs.name,
                        "mount_id": self.mount_id,
                        "reload_time": self.specs.reload_time,
                    })
                    break  # Stop burst on reload

            # Heat per round
            self.heat += 10.0 * (1.0 / max(0.5, damage_factor))
            if damage_model is not None:
                heat_scale = self.specs.subsystem_damage / max(1.0, self.specs.base_damage)
                heat_amount = self.specs.power_per_shot * (1.0 + heat_scale)
                if heat_amount > 0:
                    damage_model.add_heat("weapons", heat_amount, event_bus, ship_id)

            # Hit roll per round
            hit = random.random() < self.current_solution.hit_probability

            shot_damage = 0.0
            damage_result = None

            if hit and target_ship:
                # Use hit-location physics for PDC hits
                hit_loc = self._compute_instant_hit_location(target_ship)
                pen_factor = hit_loc.penetration_factor if hit_loc else 1.0
                is_ricochet = hit_loc.is_ricochet if hit_loc else False

                if is_ricochet:
                    effective_damage = self.specs.base_damage * damage_factor * 0.1
                    subsystem_dmg = 0.0
                    subsystem_target = hit_loc.nearest_subsystem if hit_loc else (target_subsystem or self._select_subsystem_target())
                else:
                    effective_damage = self.specs.base_damage * damage_factor * pen_factor
                    subsystem_dmg = self.specs.subsystem_damage * damage_factor * pen_factor
                    subsystem_target = hit_loc.nearest_subsystem if hit_loc else (target_subsystem or self._select_subsystem_target())

                if hasattr(target_ship, 'take_damage'):
                    damage_result = target_ship.take_damage(
                        effective_damage,
                        source=f"{ship_id}:{self.specs.name}",
                        target_subsystem=subsystem_target if subsystem_dmg > 0 else None,
                    )

                if subsystem_dmg > 0 and hasattr(target_ship, 'damage_model'):
                    target_ship.damage_model.apply_damage(
                        subsystem_target, subsystem_dmg
                    )
                    if damage_result:
                        damage_result["subsystem_hit"] = subsystem_target
                        damage_result["subsystem_damage"] = subsystem_dmg

                shot_damage = effective_damage
                burst_hits += 1
                burst_damage += shot_damage

            burst_results.append({
                "hit": hit,
                "damage": shot_damage,
                "damage_result": damage_result,
            })

            # Stop burst if overheating
            if self.heat >= self.max_heat * 0.95:
                break

        # Publish single event summarizing the burst
        self.event_bus.publish("weapon_fired", {
            "weapon": self.specs.name,
            "mount_id": self.mount_id,
            "ship_id": ship_id,
            "target": target_id,
            "hit": burst_hits > 0,
            "hits": burst_hits,
            "rounds_fired": burst_rounds,
            "hit_probability": self.current_solution.hit_probability,
            "range": self.current_solution.range_to_target,
            "damage": burst_damage,
        })

        return {
            "ok": True,
            "hit": burst_hits > 0,
            "hits": burst_hits,
            "rounds_fired": burst_rounds,
            "damage": burst_damage,
            "target": target_id,
            "range": self.current_solution.range_to_target,
            "time_of_flight": self.current_solution.time_of_flight,
            "hit_probability": self.current_solution.hit_probability,
            "ammo_remaining": self.ammo,
            "heat": self.heat,
            "burst_results": burst_results,
        }

    def _select_subsystem_target(self) -> str:
        """Select which subsystem to damage based on weapon type.

        Subsystem targets match design spec: drive (propulsion), RCS,
        sensors, weapons, reactor (power).

        Returns:
            str: Name of the subsystem hit.
        """
        import random

        # Weights based on damage type — all five spec subsystems represented
        if self.specs.damage_type == DamageType.KINETIC_PENETRATOR:
            # Railgun: penetrator reaches deep systems
            weights = {
                "propulsion": 0.30,
                "power": 0.20,
                "weapons": 0.20,
                "rcs": 0.15,
                "sensors": 0.15,
            }
        else:
            # PDC/fragmentation: tends to hit external systems
            weights = {
                "sensors": 0.30,
                "rcs": 0.25,
                "weapons": 0.20,
                "propulsion": 0.15,
                "power": 0.10,
            }

        roll = random.random()
        cumulative = 0.0
        for subsystem, weight in weights.items():
            cumulative += weight
            if roll < cumulative:
                return subsystem
        return "weapons"  # fallback

    def _calculate_armor_factor(self, armor: Dict) -> float:
        """Calculate damage multiplier based on armor vs weapon penetration.

        Armor sections have thickness_cm. Thicker armor reduces damage
        more, but high armor_penetration weapons bypass it.

        PDC (0.5 pen) vs 3cm armor → ~0.5x damage (struggles)
        Railgun (1.5 pen) vs 3cm armor → ~1.0x damage (punches through)

        Args:
            armor: Ship armor dict with sections {fore, aft, ...} each
                having thickness_cm.

        Returns:
            float: Damage multiplier (0.2 to 1.0).
        """
        # Average armor thickness across all sections
        thicknesses = []
        for section_data in armor.values():
            if isinstance(section_data, dict):
                thicknesses.append(section_data.get("thickness_cm", 0.0))
        if not thicknesses:
            return 1.0

        avg_thickness = sum(thicknesses) / len(thicknesses)
        # Armor resistance scales with thickness: 1cm = 0.1 resistance
        armor_resistance = avg_thickness * 0.1
        # Effective factor: penetration / (penetration + resistance)
        pen = self.specs.armor_penetration
        factor = pen / (pen + armor_resistance)
        return max(0.2, min(1.0, factor))

    def _compute_instant_hit_location(self, target_ship):
        """Compute hit location for instant-hit weapons (PDC).

        Uses the firing solution's intercept geometry to determine
        which part of the target ship is hit.

        Args:
            target_ship: Target ship object

        Returns:
            HitLocation or None if ship lacks required data
        """
        if not target_ship or not hasattr(target_ship, 'position'):
            return None

        # Construct a synthetic projectile velocity from weapon → target
        solution = self.current_solution
        if not solution or not solution.valid:
            return None

        # PDC projectile velocity toward intercept point
        intercept = solution.intercept_point
        target_pos = target_ship.position
        aim_vec = {
            "x": intercept["x"] - target_pos["x"],
            "y": intercept["y"] - target_pos["y"],
            "z": intercept["z"] - target_pos["z"],
        }
        # Normalize and scale to muzzle velocity
        aim_mag = math.sqrt(aim_vec["x"]**2 + aim_vec["y"]**2 + aim_vec["z"]**2)
        if aim_mag < 1e-10:
            proj_vel = {"x": self.specs.muzzle_velocity, "y": 0.0, "z": 0.0}
        else:
            proj_vel = {
                "x": (aim_vec["x"] / aim_mag) * self.specs.muzzle_velocity,
                "y": (aim_vec["y"] / aim_mag) * self.specs.muzzle_velocity,
                "z": (aim_vec["z"] / aim_mag) * self.specs.muzzle_velocity,
            }

        ship_quat = getattr(target_ship, "quaternion", None)
        ship_dims = getattr(target_ship, "dimensions", None)
        ship_armor = getattr(target_ship, "armor", None)
        ship_weapon_mounts = getattr(target_ship, "weapon_mounts", None)
        # Use raw systems config for placement data, not loaded system objects
        ship_systems = getattr(target_ship, "_systems_config", None)

        subsystem_names = None
        if hasattr(target_ship, "damage_model") and hasattr(target_ship.damage_model, "subsystems"):
            subsystem_names = list(target_ship.damage_model.subsystems.keys())

        try:
            return compute_hit_location(
                projectile_velocity=proj_vel,
                projectile_mass=self.specs.mass_per_round,
                projectile_armor_pen=self.specs.armor_penetration,
                ship_position=target_ship.position,
                ship_quaternion=ship_quat,
                ship_dimensions=ship_dims,
                ship_armor=ship_armor,
                ship_systems=ship_systems,
                ship_weapon_mounts=ship_weapon_mounts,
                ship_subsystems=subsystem_names,
            )
        except Exception as e:
            logger.warning(f"Hit location calc failed for PDC: {e}")
            return None

    def get_ammo_mass(self) -> float:
        """Get total mass of remaining ammunition in kg.

        Returns:
            float: Mass of all remaining rounds.
        """
        if self.ammo is None:
            return 0.0
        return self.ammo * self.specs.mass_per_round

    def can_fire(self, sim_time: float) -> bool:
        """Quick check if weapon can fire."""
        if not self.enabled:
            return False
        if self.reloading:
            return False
        if self.ammo is not None and self.ammo <= 0:
            return False
        if sim_time - self.last_fired < self.specs.cycle_time:
            return False
        if self.heat >= self.max_heat * 0.95:
            return False
        if self.specs.charge_time > 0 and self._charge_state != ChargeState.READY:
            return False
        return True

    def _solution_telemetry(self) -> Optional[Dict]:
        """Full firing solution telemetry including MANUAL-tier diagnostics."""
        s = self.current_solution
        if not s:
            return None
        return {
            "valid": s.valid,
            "target_id": s.target_id,
            "range": s.range_to_target,
            "confidence": s.confidence,
            "confidence_factors": dict(s.confidence_factors),
            "cone_radius_m": s.cone_radius_m,
            "cone_angle_deg": s.cone_angle_deg,
            "hit_probability": s.hit_probability,
            "in_arc": s.in_arc,
            "ready_to_fire": s.ready_to_fire,
            "reason": s.reason,
            "time_of_flight": s.time_of_flight,
            # MANUAL-tier diagnostics (previously hidden)
            "lead_angle": dict(s.lead_angle),
            "intercept_point": dict(s.intercept_point),
            "closing_speed": s.closing_speed,
            "target_closing": s.target_closing,
            "target_accel_magnitude": s.target_accel_magnitude,
            "lateral_velocity": s.lateral_velocity,
            "tracking": s.tracking,
            "in_range": s.in_range,
        }

    def get_state(self) -> Dict:
        """Get weapon state for telemetry."""
        return {
            "name": self.specs.name,
            "mount_id": self.mount_id,
            "weapon_type": self.specs.weapon_type.value,
            "enabled": self.enabled,
            "ammo": self.ammo,
            "ammo_capacity": self.specs.ammo_capacity,
            "ammo_mass": self.get_ammo_mass(),
            "mass_per_round": self.specs.mass_per_round,
            "reloading": self.reloading,
            "reload_progress": round(self.reload_progress, 2),
            "reload_time": self.specs.reload_time,
            "heat": self.heat,
            "max_heat": self.max_heat,
            "cycle_time": self.specs.cycle_time,
            "charge_time": self.specs.charge_time,
            "charge_state": self._charge_state.value,
            "charge_progress": round(self._charge_progress, 3),
            "effective_range": self.specs.effective_range,
            "turret_bearing": self.turret_bearing,
            "pdc_mode": self.pdc_mode,
            # Gimbal state — independent turret tracking
            "gimbal_enabled": self.gimbal_enabled,
            "gimbal_azimuth": round(self.current_azimuth, 2),
            "gimbal_elevation": round(self.current_elevation, 2),
            "gimbal_error": round(self._gimbal_error, 2),
            "solution": self._solution_telemetry(),
        }


def create_railgun(mount_id: str = "railgun_1") -> TruthWeapon:
    """Factory function for railgun weapon."""
    return TruthWeapon(RAILGUN_SPECS, mount_id)


def create_pdc(mount_id: str = "pdc_1") -> TruthWeapon:
    """Factory function for PDC weapon."""
    return TruthWeapon(PDC_SPECS, mount_id)
