# tests/systems/combat/test_combat_system.py
"""Tests for Sprint C combat system - truth weapons and mission kill."""

import pytest
import math


class TestTruthWeapons:
    """Tests for Railgun and PDC truth weapons."""

    def test_railgun_specs(self):
        """Test railgun specifications are correct."""
        from hybrid.systems.weapons.truth_weapons import RAILGUN_SPECS

        assert RAILGUN_SPECS.name == "Railgun"
        assert RAILGUN_SPECS.muzzle_velocity == 5000.0  # 5 km/s
        assert RAILGUN_SPECS.effective_range == 75000.0  # 75 km
        assert RAILGUN_SPECS.base_damage == 35.0
        assert RAILGUN_SPECS.cycle_time == 5.0  # 5 second cycle
        assert RAILGUN_SPECS.ammo_capacity == 20

    def test_pdc_specs(self):
        """Test PDC specifications are correct."""
        from hybrid.systems.weapons.truth_weapons import PDC_SPECS

        assert PDC_SPECS.name == "PDC"
        assert PDC_SPECS.muzzle_velocity == 1200.0  # 1.2 km/s
        assert PDC_SPECS.effective_range == 5000.0  # 5 km
        assert PDC_SPECS.base_damage == 5.0
        assert PDC_SPECS.cycle_time == 0.1  # Fast fire rate
        assert PDC_SPECS.ammo_capacity == 2000

    def test_create_railgun(self):
        """Test railgun creation."""
        from hybrid.systems.weapons.truth_weapons import create_railgun

        railgun = create_railgun("test_railgun")
        assert railgun.mount_id == "test_railgun"
        assert railgun.specs.name == "Railgun"
        assert railgun.ammo == 20
        assert railgun.enabled

    def test_create_pdc(self):
        """Test PDC creation."""
        from hybrid.systems.weapons.truth_weapons import create_pdc

        pdc = create_pdc("test_pdc")
        assert pdc.mount_id == "test_pdc"
        assert pdc.specs.name == "PDC"
        assert pdc.ammo == 2000
        assert pdc.enabled

    def test_firing_solution_calculation(self):
        """Test firing solution calculation with lead prediction."""
        from hybrid.systems.weapons.truth_weapons import create_railgun

        railgun = create_railgun("test")

        # Stationary target at 10km
        solution = railgun.calculate_solution(
            shooter_pos={"x": 0, "y": 0, "z": 0},
            shooter_vel={"x": 0, "y": 0, "z": 0},
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            target_id="target_1",
            sim_time=0.0
        )

        assert solution.valid
        assert solution.range_to_target == 10000.0
        assert solution.in_range  # Within 75km
        # Time of flight: 10000m / 5000m/s = 2 seconds
        assert abs(solution.time_of_flight - 2.0) < 0.1

    def test_firing_solution_moving_target(self):
        """Test lead calculation for moving target."""
        from hybrid.systems.weapons.truth_weapons import create_railgun

        railgun = create_railgun("test")

        # Target at 10km, moving perpendicular at 100 m/s
        solution = railgun.calculate_solution(
            shooter_pos={"x": 0, "y": 0, "z": 0},
            shooter_vel={"x": 0, "y": 0, "z": 0},
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 100, "z": 0},  # Moving in Y
            target_id="target_1",
            sim_time=0.0
        )

        assert solution.valid
        # Lead angle should show positive yaw to lead the target
        assert solution.lead_angle["yaw"] > 0
        # Intercept point should be ahead of current position
        assert solution.intercept_point["y"] > 0

    def test_out_of_range(self):
        """Test firing solution when target is out of range."""
        from hybrid.systems.weapons.truth_weapons import create_pdc

        pdc = create_pdc("test")

        # Target at 10km - beyond PDC's 5km range
        solution = pdc.calculate_solution(
            shooter_pos={"x": 0, "y": 0, "z": 0},
            shooter_vel={"x": 0, "y": 0, "z": 0},
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            target_id="target_1",
            sim_time=0.0
        )

        assert not solution.in_range
        assert not solution.ready_to_fire
        assert "out of range" in solution.reason.lower()


class TestDamageModel:
    """Tests for damage model and mission kill detection."""

    def test_subsystem_damage(self):
        """Test applying damage to subsystems."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "propulsion": {"max_health": 100.0},
            "rcs": {"max_health": 80.0},
            "weapons": {"max_health": 100.0},
            "sensors": {"max_health": 90.0},
        })

        # Apply damage to propulsion
        result = model.apply_damage("propulsion", 30.0, source="railgun")
        assert result["ok"]
        assert result["health"] == 70.0
        # v0.6.0: Status names changed from "degraded" to "damaged"
        assert result["status"] == "damaged"

    def test_subsystem_failure(self):
        """Test subsystem failure threshold."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "propulsion": {"max_health": 100.0, "failure_threshold": 0.2},
        })

        # Damage to below failure threshold (20%)
        model.apply_damage("propulsion", 85.0)

        assert model.is_subsystem_failed("propulsion")
        assert model.get_degradation_factor("propulsion") == 0.0

    def test_mobility_kill(self):
        """Test mobility kill detection when propulsion fails."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "propulsion": {"max_health": 100.0, "failure_threshold": 0.2},
            "rcs": {"max_health": 80.0, "failure_threshold": 0.2},
            "weapons": {"max_health": 100.0},
        })

        # Ship should not be mobility killed initially
        assert not model.is_mobility_kill()
        assert not model.is_mission_kill()

        # Destroy propulsion
        model.apply_damage("propulsion", 100.0)

        assert model.is_mobility_kill()
        assert model.is_mission_kill()
        assert "mobility_kill" in model.get_mission_kill_reason()

    def test_firepower_kill(self):
        """Test firepower kill detection when weapons fail."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "propulsion": {"max_health": 100.0},
            "weapons": {"max_health": 100.0, "failure_threshold": 0.2},
        })

        # Destroy weapons
        model.apply_damage("weapons", 100.0)

        assert model.is_firepower_kill()
        assert model.is_mission_kill()
        assert "firepower_kill" in model.get_mission_kill_reason()

    def test_rcs_kill_causes_mobility_kill(self):
        """Test that RCS failure also causes mobility kill."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "propulsion": {"max_health": 100.0},
            "rcs": {"max_health": 80.0, "failure_threshold": 0.2},
            "weapons": {"max_health": 100.0},
        })

        # Propulsion still works, but RCS is destroyed
        model.apply_damage("rcs", 80.0)

        assert model.is_mobility_kill()
        assert model.is_mission_kill()

    def test_combat_summary(self):
        """Test combat summary reporting."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "propulsion": {"max_health": 100.0},
            "rcs": {"max_health": 80.0},
            "weapons": {"max_health": 100.0},
            "sensors": {"max_health": 90.0},
        })

        # Apply some damage
        model.apply_damage("propulsion", 30.0)
        model.apply_damage("sensors", 45.0)

        summary = model.get_combat_summary()

        assert not summary["mission_kill"]
        assert summary["propulsion_factor"] == 0.7  # 70/100
        assert summary["sensors_factor"] == 0.5  # 45/90
        assert summary["total_damage"] == 75.0
        assert summary["damage_events"] == 2


class TestTargetingSystem:
    """Tests for targeting system lock state progression."""

    def test_lock_state_progression(self):
        """Test that lock progresses through states."""
        from hybrid.systems.targeting.targeting_system import (
            TargetingSystem, LockState
        )

        targeting = TargetingSystem({})

        assert targeting.lock_state == LockState.NONE

        # Initiate lock
        result = targeting.lock_target("target_1", sim_time=0.0)

        assert result["ok"]
        assert targeting.lock_state == LockState.ACQUIRING
        assert targeting.locked_target == "target_1"

    def test_unlock_target(self):
        """Test unlocking a target."""
        from hybrid.systems.targeting.targeting_system import (
            TargetingSystem, LockState
        )

        targeting = TargetingSystem({})
        targeting.lock_target("target_1", sim_time=0.0)

        result = targeting.unlock_target()

        assert result["ok"]
        assert targeting.lock_state == LockState.NONE
        assert targeting.locked_target is None


class TestCombatSystem:
    """Tests for combat system integration."""

    def test_combat_system_initialization(self):
        """Test combat system creates truth weapons."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({
            "railguns": 2,
            "pdcs": 4
        })

        assert len(combat.truth_weapons) == 6
        assert "railgun_1" in combat.truth_weapons
        assert "railgun_2" in combat.truth_weapons
        assert "pdc_1" in combat.truth_weapons
        assert "pdc_4" in combat.truth_weapons

    def test_combat_system_state(self):
        """Test combat system state reporting."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"railguns": 1, "pdcs": 2})
        state = combat.get_state()

        assert "truth_weapons" in state
        assert "railgun_1" in state["truth_weapons"]
        assert state["shots_fired"] == 0
        assert state["hits"] == 0

    def test_resupply(self):
        """Test resupply restores ammunition."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"railguns": 1, "pdcs": 1})

        # Deplete some ammo
        combat.truth_weapons["railgun_1"].ammo = 5
        combat.truth_weapons["pdc_1"].ammo = 100

        result = combat.resupply()

        assert result["ok"]
        assert combat.truth_weapons["railgun_1"].ammo == 20
        assert combat.truth_weapons["pdc_1"].ammo == 2000


class TestCombatIntegration:
    """Integration tests for combat loop."""

    def test_full_combat_flow(self):
        """Test complete combat flow: detect -> lock -> fire."""
        from hybrid.ship import Ship
        from hybrid.systems.damage_model import DamageModel

        # Create attacker ship with combat system
        attacker_config = {
            "id": "attacker",
            "position": {"x": 0, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
            "systems": {
                "combat": {"railguns": 1, "pdcs": 1},
                "targeting": {},
                "sensors": {"passive": {"range": 50000}},
                "power_management": {
                    "primary": {"output": 200},
                    "secondary": {"output": 100},
                }
            }
        }
        attacker = Ship("attacker", attacker_config)

        # Create target ship
        target_config = {
            "id": "target",
            "position": {"x": 10000, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
            "mass": 1000,
            "max_hull_integrity": 100,
            "hull_integrity": 100,
        }
        target = Ship("target", target_config)

        # Verify systems exist
        assert "combat" in attacker.systems
        assert "targeting" in attacker.systems

        # Verify target has damage model
        assert hasattr(target, "damage_model")
        assert hasattr(target, "hull_integrity")

    def test_targeted_subsystem_damage_via_command(self):
        """Test that targeted subsystem damage is applied from commands."""
        from hybrid.ship import Ship
        from hybrid.command_handler import execute_command

        attacker_config = {
            "id": "attacker",
            "position": {"x": 0, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
            "systems": {
                "weapons": {
                    "weapons": [
                        {
                            "name": "test_laser",
                            "power_cost": 1.0,
                            "max_heat": 100.0,
                            "damage": 12.0,
                        }
                    ]
                },
                "targeting": {},
                "power_management": {
                    "primary": {"output": 50},
                    "secondary": {"output": 25},
                },
            },
        }
        target_config = {
            "id": "target",
            "position": {"x": 1000, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
        }

        attacker = Ship("attacker", attacker_config)
        target = Ship("target", target_config)
        all_ships = {"attacker": attacker, "target": target}

        power_manager = attacker.systems["power_management"]
        for reactor in power_manager.reactors.values():
            reactor.available = reactor.capacity

        execute_command(attacker, "lock_target", {"contact_id": "target"})
        execute_command(attacker, "set_target_subsystem", {"target_subsystem": "sensors"})

        starting_health = target.damage_model.subsystems["sensors"].health
        result = execute_command(
            attacker,
            "fire_weapon",
            {"weapon": "test_laser"},
            all_ships=all_ships,
        )

        assert result["ok"]
        assert target.damage_model.subsystems["sensors"].health < starting_health


class TestInterceptScenario:
    """Tests for intercept scenario configuration."""

    def test_scenario_loads(self):
        """Test intercept mission scenario loads with mission objectives."""
        import os
        from hybrid.scenarios.loader import ScenarioLoader

        scenario_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", "scenarios", "06_intercept_mission.yaml"
        )

        scenario = ScenarioLoader.load(scenario_path)

        assert scenario["name"] == "Intercept: Mission Kill"
        assert len(scenario["ships"]) == 2
        assert scenario["ships"][0]["id"] == "player_ship"
        assert scenario["ships"][1]["id"] == "enemy_corvette"
        assert scenario["mission"] is not None
        assert scenario["mission"].name == "Intercept and Disable"

    def test_mission_win_fail_conditions(self):
        """Test mission system reports win/fail based on mission kill status."""
        import os
        from hybrid.scenarios.loader import ScenarioLoader
        from hybrid.ship import Ship

        scenario_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", "scenarios", "06_intercept_mission.yaml"
        )

        scenario = ScenarioLoader.load(scenario_path)
        player_config = next(ship for ship in scenario["ships"] if ship["id"] == "player_ship")
        enemy_config = next(ship for ship in scenario["ships"] if ship["id"] == "enemy_corvette")

        player_ship = Ship("player_ship", player_config)
        enemy_ship = Ship("enemy_corvette", enemy_config)

        class DummySim:
            def __init__(self, ships):
                self.ships = ships
                self.time = 0.0

        sim = DummySim({"player_ship": player_ship, "enemy_corvette": enemy_ship})
        mission = scenario["mission"]
        mission.start(sim.time)

        enemy_ship.damage_model.apply_damage("propulsion", 999.0)
        mission.update(sim, player_ship)

        assert mission.tracker.mission_status == "success"

        scenario_failure = ScenarioLoader.load(scenario_path)
        failing_player_config = next(
            ship for ship in scenario_failure["ships"] if ship["id"] == "player_ship"
        )
        failing_enemy_config = next(
            ship for ship in scenario_failure["ships"] if ship["id"] == "enemy_corvette"
        )

        failing_player = Ship("player_ship", failing_player_config)
        failing_enemy = Ship("enemy_corvette", failing_enemy_config)
        sim_failure = DummySim({"player_ship": failing_player, "enemy_corvette": failing_enemy})
        mission_failure = scenario_failure["mission"]
        mission_failure.start(sim_failure.time)

        failing_player.damage_model.apply_damage("weapons", 999.0)
        mission_failure.update(sim_failure, failing_player)

        assert mission_failure.tracker.mission_status == "failure"
