# hybrid/systems/weapons/truth_weapons.py
"""Truth weapons - physics-based weapon implementations for realistic combat.

Sprint C: Railgun and PDC as the first two truth weapons.
These weapons have proper ballistics, range calculations, and damage models.
"""

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Tuple
from hybrid.core.event_bus import EventBus


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

    # Power
    power_per_shot: float = 10.0  # power units consumed per shot
    charge_time: float = 0.0  # seconds to charge before firing

    # Accuracy
    base_accuracy: float = 0.95  # hit probability at point blank
    accuracy_falloff: float = 0.5  # accuracy loss at max range (0-1)
    tracking_speed: float = 30.0  # degrees/sec for turret tracking


# Pre-defined weapon specifications
RAILGUN_SPECS = WeaponSpecs(
    name="Railgun",
    weapon_type=WeaponType.KINETIC,
    damage_type=DamageType.KINETIC_PENETRATOR,
    muzzle_velocity=5000.0,  # 5 km/s - tungsten penetrator
    effective_range=75000.0,  # 75 km effective range
    min_range=500.0,  # Need some distance to track
    base_damage=35.0,  # Heavy hull damage
    subsystem_damage=25.0,  # Significant subsystem damage
    armor_penetration=1.5,  # Good vs armor
    cycle_time=5.0,  # 5 seconds between shots
    burst_count=1,
    burst_delay=0.0,
    ammo_capacity=20,  # Limited heavy rounds
    power_per_shot=50.0,  # High power draw
    charge_time=2.0,  # 2 second charge
    base_accuracy=0.85,  # High accuracy
    accuracy_falloff=0.3,  # Maintains accuracy at range
    tracking_speed=15.0,  # Slower tracking (heavy weapon)
)

PDC_SPECS = WeaponSpecs(
    name="PDC",
    weapon_type=WeaponType.KINETIC,
    damage_type=DamageType.KINETIC_FRAGMENTATION,
    muzzle_velocity=1200.0,  # 1.2 km/s - fast autocannon
    effective_range=5000.0,  # 5 km effective range
    min_range=50.0,  # Very close engagement
    base_damage=5.0,  # Light damage per round
    subsystem_damage=3.0,  # Can chip away at subsystems
    armor_penetration=0.5,  # Poor vs heavy armor
    cycle_time=0.1,  # 10 rounds/second
    burst_count=5,  # 5-round bursts
    burst_delay=0.05,  # Fast burst
    ammo_capacity=2000,  # Large ammo supply
    power_per_shot=2.0,  # Low power per shot
    charge_time=0.0,  # No charge needed
    base_accuracy=0.7,  # Moderate accuracy
    accuracy_falloff=0.6,  # Accuracy drops at range
    tracking_speed=120.0,  # Fast tracking (point defense)
)


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
    hit_probability: float = 0.0  # 0-1 chance to hit
    in_range: bool = False  # Within weapon effective range
    in_arc: bool = False  # Within weapon firing arc
    target_closing: bool = False  # Target is closing
    closing_speed: float = 0.0  # Relative closing velocity (m/s)

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
        self.charge_start = None
        self.charging = False

        # Tracking
        self.current_solution: Optional[FiringSolution] = None
        self.turret_bearing = {"pitch": 0.0, "yaw": 0.0}
        self.target_bearing = {"pitch": 0.0, "yaw": 0.0}

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

        # Turret tracking
        if self.current_solution and self.current_solution.valid:
            self._update_turret_tracking(dt)

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

    def calculate_solution(
        self,
        shooter_pos: Dict[str, float],
        shooter_vel: Dict[str, float],
        target_pos: Dict[str, float],
        target_vel: Dict[str, float],
        target_id: str,
        sim_time: float
    ) -> FiringSolution:
        """Calculate firing solution for a target.

        Uses lead prediction to calculate where to aim to hit a moving target.

        Args:
            shooter_pos: Shooter position {x, y, z}
            shooter_vel: Shooter velocity {x, y, z}
            target_pos: Target position {x, y, z}
            target_vel: Target velocity {x, y, z}
            target_id: Target identifier
            sim_time: Current simulation time

        Returns:
            FiringSolution with engagement data
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
        # Accuracy degrades with range
        range_factor = solution.range_to_target / self.specs.effective_range
        range_accuracy = self.specs.base_accuracy - (
            self.specs.accuracy_falloff * range_factor
        )

        # Lateral velocity reduces accuracy
        lateral_vel_sq = (
            (rel_vel["x"] - solution.closing_speed * range_direction["x"])**2 +
            (rel_vel["y"] - solution.closing_speed * range_direction["y"])**2 +
            (rel_vel["z"] - solution.closing_speed * range_direction["z"])**2
        )
        lateral_vel = math.sqrt(lateral_vel_sq)
        lateral_factor = max(0.5, 1.0 - lateral_vel / 500.0)  # 500 m/s = 50% reduction

        solution.hit_probability = max(0.05, min(0.95, range_accuracy * lateral_factor))

        # Check turret tracking
        turret_error = math.sqrt(
            (self.turret_bearing["pitch"] - solution.lead_angle["pitch"])**2 +
            (self.turret_bearing["yaw"] - solution.lead_angle["yaw"])**2
        )
        solution.tracking = turret_error < 5.0  # Within 5 degrees
        solution.in_arc = True  # TODO: implement firing arcs

        # Ready to fire check
        time_since_fired = sim_time - self.last_fired
        cooldown_ready = time_since_fired >= self.specs.cycle_time
        ammo_ok = self.ammo is None or self.ammo > 0
        heat_ok = self.heat < self.max_heat * 0.9

        solution.ready_to_fire = (
            self.enabled and
            solution.in_range and
            solution.in_arc and
            solution.tracking and
            cooldown_ready and
            ammo_ok and
            heat_ok
        )

        if not solution.ready_to_fire:
            if not self.enabled:
                solution.reason = "Weapon disabled"
            elif not solution.in_range:
                if solution.range_to_target < self.specs.min_range:
                    solution.reason = f"Target too close ({solution.range_to_target:.0f}m < {self.specs.min_range:.0f}m)"
                else:
                    solution.reason = f"Target out of range ({solution.range_to_target:.0f}m > {self.specs.effective_range:.0f}m)"
            elif not solution.tracking:
                solution.reason = f"Turret tracking ({turret_error:.1f} deg error)"
            elif not cooldown_ready:
                remaining = self.specs.cycle_time - time_since_fired
                solution.reason = f"Cycling ({remaining:.1f}s remaining)"
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
    ) -> Dict:
        """Attempt to fire the weapon.

        Args:
            sim_time: Current simulation time
            power_manager: Power system for power draw
            target_ship: Target ship object for damage application
            ship_id: Firing ship ID for events
            damage_factor: Weapon system damage degradation factor

        Returns:
            dict: Fire result
        """
        # Check basic requirements
        if not self.enabled:
            return {"ok": False, "reason": "disabled"}

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

        # Fire!
        self.last_fired = sim_time
        if self.ammo is not None:
            self.ammo -= 1

        self.heat += 10.0 * (1.0 / max(0.5, damage_factor))
        if damage_model is not None:
            heat_scale = self.specs.subsystem_damage / max(1.0, self.specs.base_damage)
            heat_amount = self.specs.power_per_shot * (1.0 + heat_scale)
            if heat_amount > 0:
                damage_model.add_heat("weapons", heat_amount, event_bus, ship_id)

        # Determine hit
        import random
        hit_roll = random.random()
        hit = hit_roll < self.current_solution.hit_probability

        # Calculate damage
        damage_result = None
        effective_damage = 0.0

        if hit and target_ship:
            # Apply damage
            effective_damage = self.specs.base_damage * damage_factor
            subsystem_damage = self.specs.subsystem_damage * damage_factor

            # Apply to target
            if hasattr(target_ship, 'take_damage'):
                damage_result = target_ship.take_damage(
                    effective_damage,
                    source=f"{ship_id}:{self.specs.name}"
                )

            # Apply subsystem damage
            if hasattr(target_ship, 'damage_model'):
                subsystem_target = self._select_subsystem_target()
                target_ship.damage_model.apply_damage(
                    subsystem_target, subsystem_damage
                )
                if damage_result:
                    damage_result["subsystem_hit"] = subsystem_target
                    damage_result["subsystem_damage"] = subsystem_damage

        # Publish event
        target_id = getattr(target_ship, 'id', None) if target_ship else None
        self.event_bus.publish("weapon_fired", {
            "weapon": self.specs.name,
            "mount_id": self.mount_id,
            "ship_id": ship_id,
            "target": target_id,
            "hit": hit,
            "hit_probability": self.current_solution.hit_probability,
            "range": self.current_solution.range_to_target,
            "damage": effective_damage if hit else 0,
            "damage_result": damage_result,
        })

        return {
            "ok": True,
            "hit": hit,
            "damage": effective_damage if hit else 0,
            "target": target_id,
            "range": self.current_solution.range_to_target,
            "time_of_flight": self.current_solution.time_of_flight,
            "hit_probability": self.current_solution.hit_probability,
            "ammo_remaining": self.ammo,
            "heat": self.heat,
            "damage_result": damage_result,
        }

    def _select_subsystem_target(self) -> str:
        """Select which subsystem to damage based on weapon type."""
        import random

        # Weights based on damage type
        if self.specs.damage_type == DamageType.KINETIC_PENETRATOR:
            # Railgun: tends to hit deep systems
            weights = {
                "propulsion": 0.35,
                "power": 0.25,
                "weapons": 0.25,
                "sensors": 0.15,
            }
        else:
            # PDC/fragmentation: tends to hit external systems
            weights = {
                "sensors": 0.35,
                "rcs": 0.30,
                "weapons": 0.25,
                "propulsion": 0.10,
            }

        roll = random.random()
        cumulative = 0.0
        for subsystem, weight in weights.items():
            cumulative += weight
            if roll < cumulative:
                return subsystem
        return "weapons"  # fallback

    def can_fire(self, sim_time: float) -> bool:
        """Quick check if weapon can fire."""
        if not self.enabled:
            return False
        if self.ammo is not None and self.ammo <= 0:
            return False
        if sim_time - self.last_fired < self.specs.cycle_time:
            return False
        if self.heat >= self.max_heat * 0.95:
            return False
        return True

    def get_state(self) -> Dict:
        """Get weapon state for telemetry."""
        return {
            "name": self.specs.name,
            "mount_id": self.mount_id,
            "enabled": self.enabled,
            "ammo": self.ammo,
            "ammo_capacity": self.specs.ammo_capacity,
            "heat": self.heat,
            "max_heat": self.max_heat,
            "cycle_time": self.specs.cycle_time,
            "effective_range": self.specs.effective_range,
            "turret_bearing": self.turret_bearing,
            "solution": {
                "valid": self.current_solution.valid if self.current_solution else False,
                "target_id": self.current_solution.target_id if self.current_solution else None,
                "range": self.current_solution.range_to_target if self.current_solution else 0,
                "hit_probability": self.current_solution.hit_probability if self.current_solution else 0,
                "ready_to_fire": self.current_solution.ready_to_fire if self.current_solution else False,
                "reason": self.current_solution.reason if self.current_solution else "",
            } if self.current_solution else None,
        }


def create_railgun(mount_id: str = "railgun_1") -> TruthWeapon:
    """Factory function for railgun weapon."""
    return TruthWeapon(RAILGUN_SPECS, mount_id)


def create_pdc(mount_id: str = "pdc_1") -> TruthWeapon:
    """Factory function for PDC weapon."""
    return TruthWeapon(PDC_SPECS, mount_id)
