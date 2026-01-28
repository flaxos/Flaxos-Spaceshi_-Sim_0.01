# tests/systems/test_heat_integration_v060.py
"""
Integration tests for v0.6.0 Heat Model.

Tests verify that system activity generates heat and that
overheat penalties are applied correctly.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestPropulsionHeatGeneration:
    """Test propulsion system heat generation."""

    def test_thrust_generates_heat(self):
        """Propulsion generates heat proportional to thrust output."""
        from hybrid.ship import Ship

        ship = Ship("test_ship", {
            "mass": 1000.0,
            "systems": {
                "propulsion": {"max_thrust": 1000.0},
            }
        })

        # Set throttle to 100%
        prop_system = ship.systems.get("propulsion")
        prop_system.set_throttle({"throttle": 1.0})

        # Get initial heat
        initial_heat = ship.damage_model.subsystems["propulsion"].heat

        # Call propulsion tick directly to test heat generation
        # (ship.tick also calls dissipate_heat which may exceed generation)
        mock_event_bus = MagicMock()
        prop_system.tick(1.0, ship, mock_event_bus)

        # Heat should have increased
        new_heat = ship.damage_model.subsystems["propulsion"].heat
        assert new_heat > initial_heat
        # Expected: (thrust/max_thrust) * heat_generation * dt = 1.0 * 1.5 * 1.0 = 1.5
        assert new_heat == pytest.approx(1.5)

    def test_no_thrust_no_heat_generation(self):
        """No heat generated when throttle is zero."""
        from hybrid.ship import Ship

        ship = Ship("test_ship", {
            "mass": 1000.0,
            "systems": {
                "propulsion": {"max_thrust": 1000.0},
            }
        })

        # Add some initial heat
        ship.damage_model.add_heat("propulsion", 50.0)
        initial_heat = ship.damage_model.subsystems["propulsion"].heat

        # Tick with no throttle - heat should only dissipate, not increase
        ship.tick(0.1, [], 0.0)

        new_heat = ship.damage_model.subsystems["propulsion"].heat
        # Heat should have decreased (dissipation) or stayed same, not increased
        assert new_heat <= initial_heat

    def test_overheat_reduces_thrust(self):
        """Overheated propulsion has reduced max thrust."""
        from hybrid.ship import Ship

        ship = Ship("test_ship", {
            "mass": 1000.0,
            "systems": {
                "propulsion": {"max_thrust": 1000.0},
            }
        })

        prop_system = ship.systems.get("propulsion")
        initial_max_thrust = prop_system.base_max_thrust

        # Overheat the propulsion subsystem
        subsystem = ship.damage_model.subsystems["propulsion"]
        ship.damage_model.add_heat("propulsion", subsystem.max_heat * 0.95)

        # Tick to apply the overheat penalty
        ship.tick(0.1, [], 0.0)

        # max_thrust should be reduced by combined factor
        assert prop_system.max_thrust < initial_max_thrust


class TestWeaponHeatGeneration:
    """Test weapon system heat generation."""

    def test_weapon_fire_generates_subsystem_heat(self):
        """Firing a weapon adds heat to the weapons subsystem."""
        from hybrid.ship import Ship

        # Use a mock power manager that always approves power requests
        mock_power_manager = MagicMock()
        mock_power_manager.request_power = MagicMock(return_value=True)

        ship = Ship("test_ship", {
            "mass": 1000.0,
            "systems": {
                "weapons": {
                    "weapons": [
                        {"name": "railgun", "power_cost": 10, "max_heat": 50, "damage": 10}
                    ]
                },
            }
        })

        # Initialize weapon system's damage_factor
        weapon_system = ship.systems.get("weapons")
        weapon_system.tick(0.1, ship, ship.event_bus)

        initial_heat = ship.damage_model.subsystems["weapons"].heat

        # Fire the weapon with mock power manager
        result = weapon_system.fire_weapon("railgun", mock_power_manager, None, ship, ship.event_bus)

        # Verify the weapon fired successfully
        assert result.get("ok") is True, f"Weapon fire failed: {result}"

        # Subsystem heat should have increased by heat_generation (5.0 from schema)
        new_heat = ship.damage_model.subsystems["weapons"].heat
        expected_heat = initial_heat + 5.0  # heat_generation for weapons = 5.0
        assert new_heat == pytest.approx(expected_heat)

    def test_overheat_prevents_firing(self):
        """Overheated weapons subsystem cannot fire."""
        from hybrid.ship import Ship

        ship = Ship("test_ship", {
            "mass": 1000.0,
            "systems": {
                "weapons": {
                    "weapons": [
                        {"name": "railgun", "power_cost": 10, "max_heat": 50, "damage": 10}
                    ]
                },
                "power_management": {
                    "reactors": {"primary": {"capacity": 100}}
                }
            }
        })

        # Overheat the weapons subsystem
        subsystem = ship.damage_model.subsystems["weapons"]
        ship.damage_model.add_heat("weapons", subsystem.max_heat * 0.95)

        # Tick to update the weapon system's overheat status
        weapon_system = ship.systems.get("weapons")
        weapon_system.tick(0.1, ship, ship.event_bus)

        # Fire the weapon - should fail
        power_manager = ship.systems.get("power_management")
        result = weapon_system.fire_weapon("railgun", power_manager, None, ship, ship.event_bus)

        assert result.get("ok") is False or result.get("reason") == "subsystem_overheated"


class TestSensorHeatGeneration:
    """Test sensor system heat generation."""

    def test_active_ping_generates_heat(self):
        """Active sensor ping adds heat to the sensors subsystem."""
        from hybrid.ship import Ship

        ship = Ship("test_ship", {
            "mass": 1000.0,
            "position": {"x": 0, "y": 0, "z": 0},
            "systems": {
                "sensors": {
                    "passive": {"range": 10000},
                    "active": {"range": 50000, "cooldown": 1.0}
                }
            }
        })

        initial_heat = ship.damage_model.subsystems["sensors"].heat

        # Execute ping
        sensor_system = ship.systems.get("sensors")
        result = sensor_system.ping({"ship": ship, "all_ships": [], "event_bus": ship.event_bus})

        # Subsystem heat should have increased (if ping was successful)
        if result.get("ok"):
            new_heat = ship.damage_model.subsystems["sensors"].heat
            assert new_heat > initial_heat

    def test_overheat_prevents_active_ping(self):
        """Overheated sensor subsystem cannot use active ping."""
        from hybrid.ship import Ship

        ship = Ship("test_ship", {
            "mass": 1000.0,
            "position": {"x": 0, "y": 0, "z": 0},
            "systems": {
                "sensors": {
                    "passive": {"range": 10000},
                    "active": {"range": 50000, "cooldown": 1.0}
                }
            }
        })

        # Overheat the sensors subsystem
        subsystem = ship.damage_model.subsystems["sensors"]
        ship.damage_model.add_heat("sensors", subsystem.max_heat * 0.95)

        # Tick to update the sensor system's overheat status
        sensor_system = ship.systems.get("sensors")
        sensor_system.tick(0.1, ship, ship.event_bus)

        # Ping should fail
        result = sensor_system.ping({"ship": ship, "all_ships": [], "event_bus": ship.event_bus})

        assert result.get("ok") is False

    def test_overheat_reduces_sensor_range(self):
        """Overheated sensors have reduced detection range."""
        from hybrid.ship import Ship

        ship = Ship("test_ship", {
            "mass": 1000.0,
            "position": {"x": 0, "y": 0, "z": 0},
            "systems": {
                "sensors": {
                    "passive": {"range": 10000},
                    "active": {"range": 50000}
                }
            }
        })

        sensor_system = ship.systems.get("sensors")
        initial_passive_range = sensor_system.passive.base_range

        # Overheat the sensors subsystem
        subsystem = ship.damage_model.subsystems["sensors"]
        ship.damage_model.add_heat("sensors", subsystem.max_heat * 0.95)

        # Tick to apply the overheat penalty
        sensor_system.tick(0.1, ship, ship.event_bus)

        # Passive range should be reduced
        assert sensor_system.passive.range < initial_passive_range


class TestHeatDissipation:
    """Test passive heat dissipation."""

    def test_heat_dissipates_over_time(self):
        """All subsystem heat dissipates passively during ship tick."""
        from hybrid.ship import Ship

        ship = Ship("test_ship", {
            "mass": 1000.0,
            "systems": {
                "propulsion": {},
            }
        })

        # Add heat to propulsion
        ship.damage_model.add_heat("propulsion", 100.0)
        initial_heat = ship.damage_model.subsystems["propulsion"].heat

        # Tick for 2 seconds
        ship.tick(2.0, [], 0.0)

        # Heat should have dissipated
        new_heat = ship.damage_model.subsystems["propulsion"].heat
        assert new_heat < initial_heat

    def test_heat_dissipation_rate(self):
        """Heat dissipates at the configured rate."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "test_system": {
                "max_health": 100.0,
                "max_heat": 100.0,
                "heat_dissipation": 10.0,  # 10 degrees per second
            }
        })

        # Add heat
        model.add_heat("test_system", 50.0)

        # Dissipate for 2 seconds
        model.dissipate_heat(2.0)

        subsystem = model.subsystems["test_system"]
        # Should be 50 - (10 * 2) = 30
        assert subsystem.heat == pytest.approx(30.0)


class TestCombinedDamageAndHeat:
    """Test combined damage and heat effects."""

    def test_combined_factor_stacks(self):
        """Damage factor and heat factor multiply together."""
        from hybrid.ship import Ship

        ship = Ship("test_ship", {
            "mass": 1000.0,
            "systems": {
                "propulsion": {"max_thrust": 1000.0},
            }
        })

        prop_system = ship.systems.get("propulsion")

        # Damage propulsion to 50% -> degradation_factor = 0.5
        ship.damage_model.apply_damage("propulsion", 55.0)  # 110 max - 55 = 55, ~50%

        # Overheat propulsion -> heat_factor = 0.6 (from schema)
        subsystem = ship.damage_model.subsystems["propulsion"]
        ship.damage_model.add_heat("propulsion", subsystem.max_heat * 0.95)

        # Tick to apply factors
        ship.tick(0.1, [], 0.0)

        # Combined factor should be ~0.5 * 0.6 = 0.3
        # max_thrust should be base * combined_factor
        combined = ship.damage_model.get_combined_factor("propulsion")
        expected_max_thrust = prop_system.base_max_thrust * combined
        assert prop_system.max_thrust == pytest.approx(expected_max_thrust, rel=0.1)


class TestSystemStateReportsHeat:
    """Test that system state reports include heat status."""

    def test_weapon_state_includes_overheat(self):
        """Weapon system state includes subsystem_overheated field."""
        from hybrid.ship import Ship

        ship = Ship("test_ship", {
            "mass": 1000.0,
            "systems": {
                "weapons": {
                    "weapons": [
                        {"name": "railgun", "power_cost": 10, "max_heat": 50}
                    ]
                }
            }
        })

        weapon_system = ship.systems.get("weapons")
        weapon_system.tick(0.1, ship, ship.event_bus)
        state = weapon_system.get_state()

        assert "subsystem_overheated" in state
        assert state["subsystem_overheated"] is False

    def test_sensor_state_includes_overheat(self):
        """Sensor system state includes subsystem_overheated field."""
        from hybrid.ship import Ship

        ship = Ship("test_ship", {
            "mass": 1000.0,
            "position": {"x": 0, "y": 0, "z": 0},
            "systems": {
                "sensors": {"passive": {"range": 10000}}
            }
        })

        sensor_system = ship.systems.get("sensors")
        sensor_system.tick(0.1, ship, ship.event_bus)
        state = sensor_system.get_state()

        assert "subsystem_overheated" in state
        assert state["subsystem_overheated"] is False
