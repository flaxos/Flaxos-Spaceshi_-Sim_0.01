# tests/systems/combat/test_missile_system.py
"""Tests for the missile weapon subtype — light, high-G guided munitions.

Missiles share the TorpedoManager flight/detonation pipeline but differ in:
- Physical specs (80 kg, 12 kN thrust, 150 m/s^2 accel, 15 kg fuel)
- Warhead (25 hull damage, 10m lethal, 30m blast)
- Guidance (augmented PN with N=5, terminal lead pursuit, G-limited)
- Flight profiles (direct, evasive, terminal_pop, bracket)
- Magazine tracking (separate from torpedoes in CombatSystem)
"""

import pytest
import math


class TestMissileSpecs:
    """Verify missile physical constants match the design spec."""

    def test_missile_mass(self):
        from hybrid.systems.combat.torpedo_manager import MISSILE_MASS
        assert MISSILE_MASS == 80.0

    def test_missile_thrust(self):
        from hybrid.systems.combat.torpedo_manager import MISSILE_THRUST
        assert MISSILE_THRUST == 12000.0

    def test_missile_max_accel(self):
        """Initial acceleration should be ~150 m/s^2 at full mass."""
        from hybrid.systems.combat.torpedo_manager import MISSILE_MASS, MISSILE_THRUST
        accel = MISSILE_THRUST / MISSILE_MASS
        assert accel == 150.0

    def test_missile_fuel(self):
        from hybrid.systems.combat.torpedo_manager import MISSILE_FUEL_MASS
        assert MISSILE_FUEL_MASS == 15.0

    def test_missile_warhead_damage(self):
        from hybrid.systems.combat.torpedo_manager import (
            MISSILE_WARHEAD_BASE_DAMAGE, MISSILE_WARHEAD_SUB_DAMAGE,
        )
        assert MISSILE_WARHEAD_BASE_DAMAGE == 25.0
        assert MISSILE_WARHEAD_SUB_DAMAGE == 15.0

    def test_missile_blast_radii(self):
        from hybrid.systems.combat.torpedo_manager import (
            MISSILE_BLAST_RADIUS, MISSILE_LETHAL_RADIUS,
        )
        assert MISSILE_BLAST_RADIUS == 30.0
        assert MISSILE_LETHAL_RADIUS == 10.0

    def test_missile_lifetime_shorter_than_torpedo(self):
        from hybrid.systems.combat.torpedo_manager import (
            MISSILE_MAX_LIFETIME, TORPEDO_MAX_LIFETIME,
        )
        assert MISSILE_MAX_LIFETIME < TORPEDO_MAX_LIFETIME
        assert MISSILE_MAX_LIFETIME == 60.0

    def test_missile_g_limit(self):
        from hybrid.systems.combat.torpedo_manager import MISSILE_G_LIMIT
        assert MISSILE_G_LIMIT == 80.0

    def test_flight_profiles_set(self):
        from hybrid.systems.combat.torpedo_manager import MISSILE_FLIGHT_PROFILES
        assert MISSILE_FLIGHT_PROFILES == {"direct", "evasive", "terminal_pop", "bracket"}


class TestMunitionType:
    """Test MunitionType enum and its integration with Torpedo dataclass."""

    def test_munition_type_enum(self):
        from hybrid.systems.combat.torpedo_manager import MunitionType
        assert MunitionType.TORPEDO.value == "torpedo"
        assert MunitionType.MISSILE.value == "missile"

    def test_torpedo_default_munition_type(self):
        from hybrid.systems.combat.torpedo_manager import Torpedo, MunitionType
        t = Torpedo(id="t1", shooter_id="s1", target_id="s2")
        assert t.munition_type == MunitionType.TORPEDO

    def test_missile_munition_type(self):
        from hybrid.systems.combat.torpedo_manager import Torpedo, MunitionType
        m = Torpedo(id="m1", shooter_id="s1", target_id="s2",
                    munition_type=MunitionType.MISSILE)
        assert m.munition_type == MunitionType.MISSILE


class TestMissileSpawn:
    """Test spawning missiles through TorpedoManager."""

    def test_missile_spawn_uses_missile_specs(self):
        """Spawned missile should have missile mass, fuel, thrust, not torpedo."""
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, MunitionType,
            MISSILE_MASS, MISSILE_FUEL_MASS, MISSILE_THRUST, MISSILE_MAX_DELTA_V,
        )

        manager = TorpedoManager()
        msl = manager.spawn(
            shooter_id="ship_1",
            target_id="ship_2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            munition_type=MunitionType.MISSILE,
        )

        assert msl.munition_type == MunitionType.MISSILE
        assert msl.mass == MISSILE_MASS
        assert msl.fuel == MISSILE_FUEL_MASS
        assert msl.thrust == MISSILE_THRUST
        assert msl.delta_v_budget == MISSILE_MAX_DELTA_V

    def test_missile_id_prefix(self):
        """Missile IDs should start with 'msl_', not 'torp_'."""
        from hybrid.systems.combat.torpedo_manager import TorpedoManager, MunitionType

        manager = TorpedoManager()
        msl = manager.spawn(
            shooter_id="s1", target_id="s2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 1000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            munition_type=MunitionType.MISSILE,
        )
        assert msl.id.startswith("msl_")

    def test_torpedo_id_prefix_unchanged(self):
        """Torpedoes should still use 'torp_' prefix."""
        from hybrid.systems.combat.torpedo_manager import TorpedoManager, MunitionType

        manager = TorpedoManager()
        torp = manager.spawn(
            shooter_id="s1", target_id="s2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 1000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            munition_type=MunitionType.TORPEDO,
        )
        assert torp.id.startswith("torp_")

    def test_missile_hull_health_lower_than_torpedo(self):
        """Missiles are frailer: 40 HP vs 100 HP for torpedoes."""
        from hybrid.systems.combat.torpedo_manager import TorpedoManager, MunitionType

        manager = TorpedoManager()
        msl = manager.spawn(
            shooter_id="s1", target_id="s2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 1000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            munition_type=MunitionType.MISSILE,
        )
        torp = manager.spawn(
            shooter_id="s1", target_id="s2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 1000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            munition_type=MunitionType.TORPEDO,
        )
        assert msl.hull_health == 40.0
        assert torp.hull_health == 100.0

    def test_mixed_spawn_counting(self):
        """Manager active_count includes both torpedoes and missiles."""
        from hybrid.systems.combat.torpedo_manager import TorpedoManager, MunitionType

        manager = TorpedoManager()
        base_args = dict(
            shooter_id="s1", target_id="s2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 1000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
        )
        manager.spawn(**base_args, munition_type=MunitionType.TORPEDO)
        manager.spawn(**base_args, munition_type=MunitionType.MISSILE)
        manager.spawn(**base_args, munition_type=MunitionType.MISSILE)

        assert manager.active_count == 3


class TestMissileGuidance:
    """Test missile-specific guidance behaviour."""

    def test_missile_higher_acceleration(self):
        """Missile should accelerate faster than torpedo from same position."""
        from hybrid.systems.combat.torpedo_manager import TorpedoManager, MunitionType
        from hybrid.utils.math_utils import magnitude

        manager = TorpedoManager()
        base_args = dict(
            shooter_id="s1", target_id="s2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
        )

        # Spawn torpedo and missile in separate managers to avoid interference
        mgr_torp = TorpedoManager()
        mgr_msl = TorpedoManager()
        torp = mgr_torp.spawn(**base_args, munition_type=MunitionType.TORPEDO)
        msl = mgr_msl.spawn(**base_args, munition_type=MunitionType.MISSILE)

        # One tick
        mgr_torp.tick(dt=0.1, sim_time=0.1, ships={})
        mgr_msl.tick(dt=0.1, sim_time=0.1, ships={})

        # Missile velocity should be higher (higher thrust-to-mass ratio)
        torp_speed = magnitude(torp.velocity)
        msl_speed = magnitude(msl.velocity)
        assert msl_speed > torp_speed, (
            f"Missile speed {msl_speed:.1f} should exceed torpedo {torp_speed:.1f}"
        )

    def test_missile_expires_at_missile_lifetime(self):
        """Missiles expire at MISSILE_MAX_LIFETIME (60s), not torpedo's 120s."""
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, TorpedoState, MunitionType, MISSILE_MAX_LIFETIME,
        )

        manager = TorpedoManager()
        msl = manager.spawn(
            shooter_id="s1", target_id="s2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 100000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            munition_type=MunitionType.MISSILE,
        )

        # Tick past missile lifetime but before torpedo lifetime
        manager.tick(dt=0.1, sim_time=MISSILE_MAX_LIFETIME + 1, ships={})
        assert not msl.alive
        assert msl.state == TorpedoState.EXPIRED

    def test_missile_arms_at_missile_distance(self):
        """Missiles arm at 300m, not torpedo's 500m."""
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, MunitionType, MISSILE_ARM_DISTANCE,
        )

        manager = TorpedoManager()
        msl = manager.spawn(
            shooter_id="s1", target_id="s2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 500, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            munition_type=MunitionType.MISSILE,
        )

        assert not msl.armed
        # After 1s at 500 m/s + acceleration, should travel >300m
        for i in range(10):
            manager.tick(dt=0.1, sim_time=0.1 * (i + 1), ships={})

        assert msl.armed, "Missile should be armed after travelling >300m"

    def test_missile_proximity_detonation(self):
        """Missile detonates at MISSILE_PROXIMITY_FUSE (10m), not torpedo's 30m."""
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, TorpedoState, MunitionType, MISSILE_PROXIMITY_FUSE,
        )
        from hybrid.ship import Ship

        manager = TorpedoManager()
        target = Ship("s2", {
            "position": {"x": 1000, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
        })

        msl = manager.spawn(
            shooter_id="s1", target_id="s2",
            position={"x": 400, "y": 0, "z": 0},
            velocity={"x": 300, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 1000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            munition_type=MunitionType.MISSILE,
        )
        msl.armed = True

        events = []
        for i in range(20):
            new_events = manager.tick(dt=0.1, sim_time=0.1 * (i + 1), ships={"s2": target})
            events.extend(new_events)
            if not msl.alive:
                break

        assert not msl.alive
        assert msl.state == TorpedoState.DETONATED
        assert len(events) > 0
        assert events[0]["munition_type"] == "missile"

    def test_missile_fuel_consumption(self):
        """Missile should consume fuel and lose mass during guidance."""
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, MunitionType, MISSILE_FUEL_MASS,
        )

        manager = TorpedoManager()
        msl = manager.spawn(
            shooter_id="s1", target_id="s2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            munition_type=MunitionType.MISSILE,
        )

        initial_fuel = msl.fuel
        assert initial_fuel == MISSILE_FUEL_MASS

        for i in range(20):
            manager.tick(dt=0.1, sim_time=0.1 * (i + 1), ships={})

        assert msl.fuel < initial_fuel


class TestMissileFlightProfiles:
    """Test missile flight profiles modify midcourse behaviour."""

    def test_direct_profile_is_default(self):
        from hybrid.systems.combat.torpedo_manager import TorpedoManager, MunitionType

        manager = TorpedoManager()
        msl = manager.spawn(
            shooter_id="s1", target_id="s2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            munition_type=MunitionType.MISSILE,
        )
        assert msl.profile == "direct"

    def test_evasive_profile_accepted(self):
        from hybrid.systems.combat.torpedo_manager import TorpedoManager, MunitionType

        manager = TorpedoManager()
        msl = manager.spawn(
            shooter_id="s1", target_id="s2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            profile="evasive",
            munition_type=MunitionType.MISSILE,
        )
        assert msl.profile == "evasive"

    def test_terminal_pop_coasts_in_midcourse(self):
        """terminal_pop profile should coast cold (zero thrust) during midcourse."""
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, TorpedoState, MunitionType,
        )

        manager = TorpedoManager()
        msl = manager.spawn(
            shooter_id="s1", target_id="s2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 2000, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 50000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            profile="terminal_pop",
            munition_type=MunitionType.MISSILE,
        )

        # Force into midcourse to test coast behaviour
        msl.state = TorpedoState.MIDCOURSE
        fuel_before = msl.fuel

        # Tick a few times in midcourse
        for i in range(10):
            manager.tick(dt=0.1, sim_time=3.0 + 0.1 * (i + 1), ships={})
            if msl.state != TorpedoState.MIDCOURSE:
                break

        # terminal_pop should coast — fuel should not decrease during midcourse
        if msl.state == TorpedoState.MIDCOURSE:
            assert msl.fuel == fuel_before, (
                "terminal_pop should coast cold during midcourse"
            )


class TestMissileDetonation:
    """Test missile warhead produces correct damage values."""

    def test_missile_warhead_damage(self):
        """Missile warhead should deal 25 hull damage at lethal range."""
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, MunitionType, MISSILE_WARHEAD_BASE_DAMAGE,
            MISSILE_LETHAL_RADIUS,
        )
        from hybrid.ship import Ship

        manager = TorpedoManager()
        target = Ship("s2", {
            "position": {"x": 1000, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
        })

        # Spawn missile at point-blank (within lethal radius of 10m)
        msl = manager.spawn(
            shooter_id="s1", target_id="s2",
            position={"x": 995, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos=target.position,
            target_vel=target.velocity,
            munition_type=MunitionType.MISSILE,
        )
        msl.armed = True

        events = manager.tick(dt=0.1, sim_time=0.1, ships={"s2": target})
        assert len(events) > 0

        event = events[0]
        assert event["type"] == "missile_detonation"
        assert event["munition_type"] == "missile"

        damage_results = event["damage_results"]
        assert len(damage_results) > 0
        result = damage_results[0]
        assert result["hull_damage"] == MISSILE_WARHEAD_BASE_DAMAGE
        assert result["damage_factor"] == 1.0

    def test_missile_hits_fewer_subsystems_than_torpedo(self):
        """Missile shaped charge hits at most 2 subsystems (vs torpedo's 3)."""
        from hybrid.systems.combat.torpedo_manager import TorpedoManager, MunitionType
        from hybrid.ship import Ship

        manager = TorpedoManager()
        target = Ship("s2", {
            "position": {"x": 1000, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
            "systems": {
                "propulsion": {"enabled": True},
                "sensors": {"enabled": True},
                "weapons": {"enabled": True},
                "rcs": {"enabled": True},
                "reactor": {"enabled": True},
            },
        })

        msl = manager.spawn(
            shooter_id="s1", target_id="s2",
            position={"x": 995, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos=target.position,
            target_vel=target.velocity,
            munition_type=MunitionType.MISSILE,
        )
        msl.armed = True

        events = manager.tick(dt=0.1, sim_time=0.1, ships={"s2": target})
        assert len(events) > 0

        result = events[0]["damage_results"][0]
        assert len(result["subsystems_hit"]) <= 2

    def test_missile_feedback_says_missile(self):
        """Detonation feedback should say 'Missile impact', not 'Torpedo'."""
        from hybrid.systems.combat.torpedo_manager import TorpedoManager, MunitionType
        from hybrid.ship import Ship

        manager = TorpedoManager()
        target = Ship("s2", {
            "position": {"x": 1000, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
        })

        msl = manager.spawn(
            shooter_id="s1", target_id="s2",
            position={"x": 995, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos=target.position,
            target_vel=target.velocity,
            munition_type=MunitionType.MISSILE,
        )
        msl.armed = True

        events = manager.tick(dt=0.1, sim_time=0.1, ships={"s2": target})
        assert len(events) > 0
        assert events[0]["feedback"].startswith("Missile impact")


class TestMissileTelemetry:
    """Test missile state in telemetry output."""

    def test_get_state_includes_munition_type(self):
        from hybrid.systems.combat.torpedo_manager import TorpedoManager, MunitionType

        manager = TorpedoManager()
        manager.spawn(
            shooter_id="s1", target_id="s2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            munition_type=MunitionType.MISSILE,
        )

        state = manager.get_state()
        assert len(state) == 1
        assert state[0]["munition_type"] == "missile"
        assert state[0]["id"].startswith("msl_")

    def test_get_state_missile_fuel_uses_missile_max(self):
        """fuel_percent should be relative to MISSILE_FUEL_MASS, not torpedo."""
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, MunitionType, MISSILE_FUEL_MASS,
        )

        manager = TorpedoManager()
        manager.spawn(
            shooter_id="s1", target_id="s2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            munition_type=MunitionType.MISSILE,
        )

        state = manager.get_state()
        assert state[0]["fuel_percent"] == 100.0

    def test_get_state_missile_ir_signature(self):
        """Missile should use missile-specific IR signatures."""
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, MunitionType, MISSILE_THRUST_IR,
        )

        manager = TorpedoManager()
        manager.spawn(
            shooter_id="s1", target_id="s2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            munition_type=MunitionType.MISSILE,
        )

        state = manager.get_state()
        # In BOOST state with fuel, should use thrust IR
        assert state[0]["ir_signature"] == MISSILE_THRUST_IR


class TestCombatSystemMissileIntegration:
    """Test CombatSystem missile magazine tracking and launch."""

    def test_missile_config_defaults(self):
        """Default config: no missile launchers."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({})
        assert combat.missile_launchers == 0
        assert combat.missiles_loaded == 0

    def test_missile_config(self):
        """Missile config initialises launcher count and magazine."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({
            "missiles": 2,
            "missile_capacity": 6,
            "missile_reload_time": 10.0,
        })
        assert combat.missile_launchers == 2
        assert combat.missile_capacity == 6
        assert combat.missiles_loaded == 12  # 2 * 6
        assert combat.missile_reload_time == 10.0

    def test_launch_missile_no_launchers(self):
        from hybrid.systems.combat.combat_system import CombatSystem
        from hybrid.ship import Ship

        ship = Ship("s1", {
            "position": {"x": 0, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
            "systems": {"combat": {"missiles": 0}},
        })
        combat = ship.systems["combat"]
        combat._ship_ref = ship

        result = combat.launch_missile("s2")
        assert not result["ok"]
        assert result["error"] == "NO_LAUNCHERS"

    def test_launch_missile_no_ammo(self):
        from hybrid.systems.combat.combat_system import CombatSystem
        from hybrid.ship import Ship

        ship = Ship("s1", {
            "position": {"x": 0, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
            "systems": {"combat": {"missiles": 1, "missile_capacity": 4}},
        })
        combat = ship.systems["combat"]
        combat._ship_ref = ship
        combat.missiles_loaded = 0

        result = combat.launch_missile("s2")
        assert not result["ok"]
        assert result["error"] == "NO_MISSILES"

    def test_launch_missile_cooldown(self):
        from hybrid.systems.combat.combat_system import CombatSystem
        from hybrid.ship import Ship

        ship = Ship("s1", {
            "position": {"x": 0, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
            "systems": {"combat": {"missiles": 1, "missile_capacity": 4}},
        })
        combat = ship.systems["combat"]
        combat._ship_ref = ship
        combat._missile_cooldown = 5.0

        result = combat.launch_missile("s2")
        assert not result["ok"]
        assert result["error"] == "MISSILE_CYCLING"

    def test_launch_missile_invalid_profile(self):
        from hybrid.systems.combat.combat_system import CombatSystem
        from hybrid.systems.combat.torpedo_manager import TorpedoManager
        from hybrid.ship import Ship

        ship = Ship("s1", {
            "position": {"x": 0, "y": 0, "z": 0},
            "velocity": {"x": 100, "y": 0, "z": 0},
            "systems": {"combat": {"missiles": 1, "missile_capacity": 4}},
        })
        combat = ship.systems["combat"]
        combat._ship_ref = ship
        combat._torpedo_manager = TorpedoManager()

        target = Ship("s2", {
            "position": {"x": 10000, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
        })

        result = combat.launch_missile("s2", profile="bogus", all_ships={"s2": target})
        assert not result["ok"]
        assert result["error"] == "INVALID_PROFILE"

    def test_launch_missile_success(self):
        """Successful missile launch decrements magazine, sets cooldown."""
        from hybrid.systems.combat.combat_system import CombatSystem
        from hybrid.systems.combat.torpedo_manager import TorpedoManager
        from hybrid.ship import Ship

        ship = Ship("s1", {
            "position": {"x": 0, "y": 0, "z": 0},
            "velocity": {"x": 100, "y": 0, "z": 0},
            "systems": {"combat": {"missiles": 1, "missile_capacity": 8,
                                    "missile_reload_time": 8.0}},
        })
        combat = ship.systems["combat"]
        combat._ship_ref = ship
        combat._torpedo_manager = TorpedoManager()

        target = Ship("s2", {
            "position": {"x": 10000, "y": 0, "z": 0},
            "velocity": {"x": 50, "y": 0, "z": 0},
        })

        initial_count = combat.missiles_loaded
        assert initial_count == 8

        result = combat.launch_missile("s2", profile="evasive", all_ships={"s2": target})

        assert result["ok"]
        assert result["target"] == "s2"
        assert result["profile"] == "evasive"
        assert result["missiles_remaining"] == 7
        assert combat.missiles_loaded == 7
        assert combat._missile_cooldown == 8.0
        assert combat.missiles_launched == 1
        assert combat._torpedo_manager.active_count == 1

    def test_missile_mass_in_total_ammo(self):
        """Total ammo mass includes missiles."""
        from hybrid.systems.combat.combat_system import CombatSystem
        from hybrid.systems.combat.torpedo_manager import MISSILE_MASS

        combat = CombatSystem({
            "missiles": 1,
            "missile_capacity": 4,
            "railguns": 0,
            "pdcs": 0,
            "torpedoes": 0,
        })

        expected = 4 * MISSILE_MASS
        assert combat.get_total_ammo_mass() >= expected

    def test_missile_state_in_combat_state(self):
        """get_state() should include missiles block."""
        from hybrid.systems.combat.combat_system import CombatSystem
        from hybrid.systems.combat.torpedo_manager import MISSILE_MASS

        combat = CombatSystem({
            "missiles": 2,
            "missile_capacity": 6,
            "missile_reload_time": 10.0,
        })
        combat._missile_cooldown = 3.5
        combat.missiles_launched = 2

        state = combat.get_state()
        assert "missiles" in state
        msl_state = state["missiles"]
        assert msl_state["launchers"] == 2
        assert msl_state["loaded"] == 12
        assert msl_state["capacity"] == 12
        assert msl_state["cooldown"] == 3.5
        assert msl_state["launched"] == 2
        assert msl_state["mass_per_missile"] == MISSILE_MASS

    def test_missile_status_command(self):
        """missile_status action should return missile status."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({
            "missiles": 1,
            "missile_capacity": 8,
        })

        result = combat.command("missile_status", {})
        assert result["ok"]
        assert result["launchers"] == 1
        assert result["loaded"] == 8

    def test_missile_cooldown_ticks_down(self):
        """Missile cooldown should decrease each tick."""
        from hybrid.systems.combat.combat_system import CombatSystem
        from hybrid.ship import Ship

        ship = Ship("s1", {
            "position": {"x": 0, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
            "systems": {"combat": {"missiles": 1}},
        })
        combat = ship.systems["combat"]
        combat._missile_cooldown = 5.0
        combat.tick(1.0, ship, ship.event_bus)
        assert combat._missile_cooldown == 4.0


class TestCommandRegistration:
    """Verify launch_missile is registered in all three places."""

    def test_command_handler_has_launch_missile(self):
        from hybrid.command_handler import system_commands
        assert "launch_missile" in system_commands
        assert system_commands["launch_missile"] == ("combat", "launch_missile")

    def test_command_handler_has_missile_status(self):
        from hybrid.command_handler import system_commands
        assert "missile_status" in system_commands
        assert system_commands["missile_status"] == ("combat", "missile_status")

    def test_station_types_tactical_has_launch_missile(self):
        from server.stations.station_types import (
            StationType, STATION_DEFINITIONS, can_station_issue_command,
        )
        assert can_station_issue_command(StationType.TACTICAL, "launch_missile")

    def test_station_types_tactical_has_missile_status(self):
        from server.stations.station_types import (
            StationType, can_station_issue_command,
        )
        assert can_station_issue_command(StationType.TACTICAL, "missile_status")

    def test_combat_system_handles_launch_missile_action(self):
        """CombatSystem.command() should handle 'launch_missile' action."""
        from hybrid.systems.combat.combat_system import CombatSystem
        from hybrid.ship import Ship

        ship = Ship("s1", {
            "position": {"x": 0, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
            "systems": {"combat": {"missiles": 0}},
        })
        combat = ship.systems["combat"]
        combat._ship_ref = ship

        # Should reach the handler (and fail with NO_LAUNCHERS, not unknown action)
        result = combat.command("launch_missile", {"target": "s2"})
        assert result.get("error") == "NO_LAUNCHERS"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
