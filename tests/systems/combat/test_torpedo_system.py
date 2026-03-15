# tests/systems/combat/test_torpedo_system.py
"""Tests for torpedo system - guided self-propelled munitions."""

import pytest
import math


class TestTorpedoManager:
    """Tests for TorpedoManager spawning, guidance, and detonation."""

    def test_torpedo_spawn(self):
        """Test spawning a torpedo with correct initial state."""
        from hybrid.systems.combat.torpedo_manager import TorpedoManager, TorpedoState, TORPEDO_MASS

        manager = TorpedoManager()
        assert manager.active_count == 0

        # Spawn torpedo
        torpedo = manager.spawn(
            shooter_id="ship_1",
            target_id="ship_2",
            position={"x": 1000, "y": 2000, "z": 3000},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 2000, "z": 3000},
            target_vel={"x": 50, "y": 0, "z": 0},
            profile="direct",
        )

        assert manager.active_count == 1
        assert torpedo.id == "torp_1"
        assert torpedo.shooter_id == "ship_1"
        assert torpedo.target_id == "ship_2"
        assert torpedo.position == {"x": 1000, "y": 2000, "z": 3000}
        assert torpedo.velocity == {"x": 100, "y": 0, "z": 0}
        assert torpedo.state == TorpedoState.BOOST
        assert torpedo.mass == TORPEDO_MASS
        assert torpedo.alive
        assert not torpedo.armed  # Not armed until ARM_DISTANCE

    def test_torpedo_multiple_spawn(self):
        """Test spawning multiple torpedoes generates unique IDs."""
        from hybrid.systems.combat.torpedo_manager import TorpedoManager

        manager = TorpedoManager()

        torp1 = manager.spawn(
            shooter_id="ship_1",
            target_id="ship_2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 1000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
        )

        torp2 = manager.spawn(
            shooter_id="ship_1",
            target_id="ship_3",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 2000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
        )

        assert manager.active_count == 2
        assert torp1.id != torp2.id
        assert torp1.id == "torp_1"
        assert torp2.id == "torp_2"

    def test_torpedo_state_tracking(self):
        """Test get_state returns torpedo telemetry."""
        from hybrid.systems.combat.torpedo_manager import TorpedoManager

        manager = TorpedoManager()

        manager.spawn(
            shooter_id="ship_1",
            target_id="ship_2",
            position={"x": 1000, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=5.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 50, "y": 0, "z": 0},
        )

        state = manager.get_state()
        assert len(state) == 1

        torp_state = state[0]
        assert torp_state["id"] == "torp_1"
        assert torp_state["shooter"] == "ship_1"
        assert torp_state["target"] == "ship_2"
        assert torp_state["position"] == {"x": 1000, "y": 0, "z": 0}
        assert torp_state["alive"]
        assert torp_state["state"] == "boost"
        assert torp_state["fuel_percent"] == 100.0

    def test_torpedo_guidance_basic(self):
        """Test torpedo tick advances position and applies guidance."""
        from hybrid.systems.combat.torpedo_manager import TorpedoManager, TORPEDO_ARM_DISTANCE

        manager = TorpedoManager()

        # Spawn torpedo
        torpedo = manager.spawn(
            shooter_id="ship_1",
            target_id="ship_2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            profile="direct",
        )

        initial_x = torpedo.position["x"]

        # Tick with 0.1 second dt
        events = manager.tick(dt=0.1, sim_time=0.1, ships={})

        # Position should have advanced
        assert torpedo.position["x"] > initial_x
        # Should still be alive
        assert torpedo.alive
        # No detonations yet
        assert len(events) == 0

        # Tick multiple times to reach arming distance (500m)
        for i in range(50):  # 5 seconds at 0.1s dt
            manager.tick(dt=0.1, sim_time=0.1 * (i + 2), ships={})

        # Should be armed after traveling >500m
        assert torpedo.armed

    def test_torpedo_proximity_detonation(self):
        """Test torpedo detonates at proximity fuse range."""
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, TorpedoState, TORPEDO_PROXIMITY_FUSE
        )
        from hybrid.ship import Ship

        manager = TorpedoManager()

        # Create target ship very close
        target_ship = Ship("ship_2", {
            "position": {"x": 1000, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
        })

        # Spawn torpedo 600m away (past arming distance)
        torpedo = manager.spawn(
            shooter_id="ship_1",
            target_id="ship_2",
            position={"x": 400, "y": 0, "z": 0},
            velocity={"x": 200, "y": 0, "z": 0},  # Closing fast
            sim_time=0.0,
            target_pos={"x": 1000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
        )

        ships = {"ship_2": target_ship}

        # Force arming (simulate having traveled 500m)
        torpedo.armed = True

        # Initial state
        assert torpedo.alive
        assert torpedo.state == TorpedoState.BOOST

        # Tick until proximity detonation (torpedo is 600m away, moving 200m/s toward target)
        # Should detonate when <30m from target (TORPEDO_PROXIMITY_FUSE)
        events = []
        for i in range(10):  # Multiple ticks
            new_events = manager.tick(dt=0.1, sim_time=0.1 * (i + 1), ships=ships)
            events.extend(new_events)
            if not torpedo.alive:
                break

        # Should have detonated
        assert not torpedo.alive
        assert torpedo.state == TorpedoState.DETONATED
        assert len(events) > 0
        assert events[0]["type"] == "torpedo_detonation"
        assert events[0]["target"] == "ship_2"

    def test_torpedo_pdc_damage(self):
        """Test PDC can damage and destroy torpedoes."""
        from hybrid.systems.combat.torpedo_manager import TorpedoManager, TorpedoState

        manager = TorpedoManager()

        torpedo = manager.spawn(
            shooter_id="ship_1",
            target_id="ship_2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
        )

        assert torpedo.hull_health == 100.0
        assert torpedo.alive

        # Apply PDC damage (multiple hits)
        result1 = manager.apply_pdc_damage("torp_1", damage=30.0, source="ship_2:pdc_1")
        assert result1["ok"]
        assert not result1["destroyed"]
        assert result1["hull_remaining"] == 70.0

        # More damage
        result2 = manager.apply_pdc_damage("torp_1", damage=40.0, source="ship_2:pdc_1")
        assert result2["ok"]
        assert not result2["destroyed"]
        assert result2["hull_remaining"] == 30.0

        # Finishing blow
        result3 = manager.apply_pdc_damage("torp_1", damage=35.0, source="ship_2:pdc_1")
        assert result3["ok"]
        assert result3["destroyed"]

        # Torpedo should be dead and intercepted
        assert not torpedo.alive
        assert torpedo.state == TorpedoState.INTERCEPTED

    def test_torpedo_expiration(self):
        """Test torpedo expires after max lifetime."""
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, TorpedoState, TORPEDO_MAX_LIFETIME
        )

        manager = TorpedoManager()

        torpedo = manager.spawn(
            shooter_id="ship_1",
            target_id="ship_2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},  # Stationary (no fuel burn)
            sim_time=0.0,
            target_pos={"x": 100000, "y": 0, "z": 0},  # Very far
            target_vel={"x": 0, "y": 0, "z": 0},
        )

        assert torpedo.alive

        # Tick past max lifetime (TORPEDO_MAX_LIFETIME = 120s)
        manager.tick(dt=0.1, sim_time=TORPEDO_MAX_LIFETIME + 1, ships={})

        assert not torpedo.alive
        assert torpedo.state == TorpedoState.EXPIRED

    def test_torpedo_fuel_consumption(self):
        """Test torpedo consumes fuel during guidance."""
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, TORPEDO_FUEL_MASS
        )

        manager = TorpedoManager()

        torpedo = manager.spawn(
            shooter_id="ship_1",
            target_id="ship_2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
        )

        initial_fuel = torpedo.fuel
        assert initial_fuel == TORPEDO_FUEL_MASS

        # Tick with guidance active (BOOST phase)
        for i in range(20):  # 2 seconds of thrusting
            manager.tick(dt=0.1, sim_time=0.1 * (i + 1), ships={})

        # Fuel should have decreased
        assert torpedo.fuel < initial_fuel
        # Mass should have decreased
        assert torpedo.mass < torpedo.mass + initial_fuel - torpedo.fuel

    def test_torpedo_get_torpedoes_targeting(self):
        """Test filtering torpedoes by target."""
        from hybrid.systems.combat.torpedo_manager import TorpedoManager

        manager = TorpedoManager()

        # Spawn multiple torpedoes with different targets
        manager.spawn(
            shooter_id="ship_1",
            target_id="ship_2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 1000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
        )

        manager.spawn(
            shooter_id="ship_1",
            target_id="ship_3",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 2000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
        )

        manager.spawn(
            shooter_id="ship_1",
            target_id="ship_2",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 1000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
        )

        # Get torpedoes targeting ship_2
        targeting_ship2 = manager.get_torpedoes_targeting("ship_2")
        assert len(targeting_ship2) == 2
        assert all(t.target_id == "ship_2" for t in targeting_ship2)

        # Get torpedoes targeting ship_3
        targeting_ship3 = manager.get_torpedoes_targeting("ship_3")
        assert len(targeting_ship3) == 1
        assert targeting_ship3[0].target_id == "ship_3"


class TestCombatSystemTorpedoIntegration:
    """Tests for CombatSystem torpedo tube integration."""

    def test_combat_system_torpedo_config(self):
        """Test CombatSystem initializes torpedo tubes from config."""
        from hybrid.systems.combat.combat_system import CombatSystem
        from hybrid.systems.combat.torpedo_manager import TORPEDO_MASS

        config = {
            "torpedoes": 2,
            "torpedo_capacity": 4,
            "torpedo_reload_time": 15.0,
        }

        combat = CombatSystem(config)

        assert combat.torpedo_tubes == 2
        assert combat.torpedo_capacity == 4
        assert combat.torpedoes_loaded == 8  # 2 tubes * 4 capacity
        assert combat.torpedo_reload_time == 15.0
        assert combat._torpedo_cooldown == 0.0

    def test_combat_system_torpedo_defaults(self):
        """Test CombatSystem uses default torpedo config when not specified."""
        from hybrid.systems.combat.combat_system import CombatSystem

        config = {}
        combat = CombatSystem(config)

        assert combat.torpedo_tubes == 0  # Default: no torpedoes
        assert combat.torpedo_capacity == 4
        assert combat.torpedoes_loaded == 0

    def test_combat_system_torpedo_mass_tracking(self):
        """Test CombatSystem includes torpedo mass in total ammo mass."""
        from hybrid.systems.combat.combat_system import CombatSystem
        from hybrid.systems.combat.torpedo_manager import TORPEDO_MASS

        config = {
            "torpedoes": 2,
            "torpedo_capacity": 4,
        }

        combat = CombatSystem(config)

        # 8 torpedoes * 250 kg = 2000 kg
        expected_torpedo_mass = 8 * TORPEDO_MASS
        total_ammo_mass = combat.get_total_ammo_mass()

        # Should include torpedo mass (plus any railgun/PDC ammo)
        assert total_ammo_mass >= expected_torpedo_mass

    def test_launch_torpedo_validation(self):
        """Test torpedo launch validation."""
        from hybrid.systems.combat.combat_system import CombatSystem
        from hybrid.ship import Ship

        # Ship with no torpedo tubes
        ship = Ship("ship_1", {
            "position": {"x": 0, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
            "systems": {
                "combat": {
                    "torpedoes": 0,
                }
            }
        })

        combat = ship.systems["combat"]
        combat._ship_ref = ship

        # Should fail with no tubes
        result = combat.launch_torpedo("ship_2")
        assert not result["ok"]
        assert result["error"] == "NO_TUBES"

    def test_launch_torpedo_no_ammo(self):
        """Test torpedo launch fails when out of torpedoes."""
        from hybrid.systems.combat.combat_system import CombatSystem
        from hybrid.ship import Ship

        ship = Ship("ship_1", {
            "position": {"x": 0, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
            "systems": {
                "combat": {
                    "torpedoes": 2,
                    "torpedo_capacity": 4,
                }
            }
        })

        combat = ship.systems["combat"]
        combat._ship_ref = ship
        combat.torpedoes_loaded = 0  # Out of torpedoes

        result = combat.launch_torpedo("ship_2")
        assert not result["ok"]
        assert result["error"] == "NO_TORPEDOES"

    def test_launch_torpedo_cooldown(self):
        """Test torpedo launch respects cooldown timer."""
        from hybrid.systems.combat.combat_system import CombatSystem
        from hybrid.ship import Ship

        ship = Ship("ship_1", {
            "position": {"x": 0, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
            "systems": {
                "combat": {
                    "torpedoes": 2,
                    "torpedo_capacity": 4,
                    "torpedo_reload_time": 15.0,
                }
            }
        })

        combat = ship.systems["combat"]
        combat._ship_ref = ship
        combat._torpedo_cooldown = 10.0  # Still cooling down

        result = combat.launch_torpedo("ship_2")
        assert not result["ok"]
        assert result["error"] == "TORPEDO_CYCLING"

    def test_launch_torpedo_success(self):
        """Test successful torpedo launch decrements ammo and sets cooldown."""
        from hybrid.systems.combat.combat_system import CombatSystem
        from hybrid.systems.combat.torpedo_manager import TorpedoManager
        from hybrid.ship import Ship

        ship = Ship("ship_1", {
            "position": {"x": 0, "y": 0, "z": 0},
            "velocity": {"x": 100, "y": 0, "z": 0},
            "systems": {
                "combat": {
                    "torpedoes": 2,
                    "torpedo_capacity": 4,
                    "torpedo_reload_time": 15.0,
                }
            }
        })

        combat = ship.systems["combat"]
        combat._ship_ref = ship
        combat._torpedo_manager = TorpedoManager()  # Wire up manager

        target_ship = Ship("ship_2", {
            "position": {"x": 10000, "y": 0, "z": 0},
            "velocity": {"x": 50, "y": 0, "z": 0},
        })

        all_ships = {"ship_2": target_ship}

        initial_count = combat.torpedoes_loaded
        assert initial_count == 8

        result = combat.launch_torpedo("ship_2", profile="direct", all_ships=all_ships)

        assert result["ok"]
        assert result["target"] == "ship_2"
        assert result["profile"] == "direct"
        assert result["torpedoes_remaining"] == 7
        assert combat.torpedoes_loaded == 7
        assert combat._torpedo_cooldown == 15.0
        assert combat.torpedoes_launched == 1
        assert combat._torpedo_manager.active_count == 1

    def test_torpedo_status(self):
        """Test get_torpedo_status returns correct telemetry."""
        from hybrid.systems.combat.combat_system import CombatSystem

        config = {
            "torpedoes": 3,
            "torpedo_capacity": 6,
            "torpedo_reload_time": 20.0,
        }

        combat = CombatSystem(config)
        combat._torpedo_cooldown = 5.5

        status = combat.get_torpedo_status()

        assert status["ok"]
        assert status["tubes"] == 3
        assert status["loaded"] == 18  # 3 * 6
        assert status["capacity"] == 18
        assert status["cooldown"] == 5.5
        assert status["launched"] == 0

    def test_torpedo_state_in_combat_state(self):
        """Test torpedo state appears in combat system get_state."""
        from hybrid.systems.combat.combat_system import CombatSystem
        from hybrid.systems.combat.torpedo_manager import TORPEDO_MASS

        config = {
            "torpedoes": 2,
            "torpedo_capacity": 5,
            "torpedo_reload_time": 18.0,
        }

        combat = CombatSystem(config)
        combat._torpedo_cooldown = 3.2
        combat.torpedoes_launched = 4

        state = combat.get_state()

        assert "torpedoes" in state
        torp_state = state["torpedoes"]
        assert torp_state["tubes"] == 2
        assert torp_state["loaded"] == 10
        assert torp_state["capacity"] == 10
        assert torp_state["cooldown"] == 3.2
        assert torp_state["launched"] == 4
        assert torp_state["mass_per_torpedo"] == TORPEDO_MASS


class TestTorpedoDetonation:
    """Tests for torpedo warhead detonation and damage application."""

    def test_detonation_damage_calculation(self):
        """Test warhead damage scales with proximity."""
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, TORPEDO_LETHAL_RADIUS, TORPEDO_BLAST_RADIUS,
            WARHEAD_BASE_DAMAGE, WARHEAD_SUBSYSTEM_DAMAGE
        )
        from hybrid.ship import Ship

        manager = TorpedoManager()

        # Create target ship
        target = Ship("ship_2", {
            "position": {"x": 1000, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
        })

        # Spawn torpedo at point-blank range (within lethal radius)
        torpedo = manager.spawn(
            shooter_id="ship_1",
            target_id="ship_2",
            position={"x": 980, "y": 0, "z": 0},  # 20m away (< 30m lethal radius)
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos=target.position,
            target_vel=target.velocity,
        )

        torpedo.armed = True
        ships = {"ship_2": target}

        # Tick to trigger detonation
        events = manager.tick(dt=0.1, sim_time=0.1, ships=ships)

        assert len(events) > 0
        event = events[0]
        assert event["type"] == "torpedo_detonation"

        # Check damage results
        damage_results = event["damage_results"]
        assert len(damage_results) > 0

        result = damage_results[0]
        assert result["ship_id"] == "ship_2"
        assert result["distance"] <= TORPEDO_LETHAL_RADIUS
        assert result["damage_factor"] == 1.0  # Full damage at lethal range
        assert result["hull_damage"] == WARHEAD_BASE_DAMAGE

    def test_detonation_subsystem_targeting(self):
        """Test torpedo blast damages multiple subsystems."""
        from hybrid.systems.combat.torpedo_manager import TorpedoManager
        from hybrid.ship import Ship

        manager = TorpedoManager()

        # Create target with subsystems
        target = Ship("ship_2", {
            "position": {"x": 1000, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
            "systems": {
                "propulsion": {"enabled": True},
                "sensors": {"enabled": True},
                "weapons": {"enabled": True},
                "rcs": {"enabled": True},
                "reactor": {"enabled": True},
            }
        })

        torpedo = manager.spawn(
            shooter_id="ship_1",
            target_id="ship_2",
            position={"x": 980, "y": 0, "z": 0},  # Close detonation
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos=target.position,
            target_vel=target.velocity,
        )

        torpedo.armed = True
        ships = {"ship_2": target}

        events = manager.tick(dt=0.1, sim_time=0.1, ships=ships)

        assert len(events) > 0
        event = events[0]

        damage_results = event["damage_results"]
        assert len(damage_results) > 0

        result = damage_results[0]
        # Should hit multiple subsystems (fragmentation warhead)
        assert len(result["subsystems_hit"]) > 0
        assert len(result["subsystems_hit"]) <= 3  # Capped at 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
