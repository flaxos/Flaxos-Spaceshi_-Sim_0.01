# tests/systems/test_damage_model_v060.py
"""
Regression tests for v0.6.0 Damage Model enhancements.

Tests cover:
- SubsystemStatus state transitions (ONLINE -> DAMAGED -> OFFLINE -> DESTROYED)
- Heat management (generation, dissipation, overheat detection)
- Damage propagation to subsystems
- Event publishing for state changes
- Combined damage/heat factors
"""

import pytest
from unittest.mock import MagicMock


class TestSubsystemStatusTransitions:
    """Test v0.6.0 status state transitions."""

    def test_status_online_above_75_percent(self):
        """Status should be ONLINE when health > 75%."""
        from hybrid.systems.damage_model import DamageModel, SubsystemStatus

        model = DamageModel(schema={
            "propulsion": {"max_health": 100.0, "failure_threshold": 0.2},
        })

        # At 100% health -> ONLINE
        report = model.get_subsystem_report("propulsion")
        assert report["status"] == "online"

        # At 76% health -> ONLINE
        model.apply_damage("propulsion", 24.0)
        report = model.get_subsystem_report("propulsion")
        assert report["status"] == "online"

    def test_status_damaged_between_25_and_75_percent(self):
        """Status should be DAMAGED when health is 25-75%."""
        from hybrid.systems.damage_model import DamageModel, SubsystemStatus

        model = DamageModel(schema={
            "propulsion": {"max_health": 100.0, "failure_threshold": 0.2},
        })

        # At 74% health -> DAMAGED
        model.apply_damage("propulsion", 26.0)
        report = model.get_subsystem_report("propulsion")
        assert report["status"] == "damaged"

        # At 26% health -> DAMAGED
        model.apply_damage("propulsion", 48.0)
        report = model.get_subsystem_report("propulsion")
        assert report["status"] == "damaged"

    def test_status_offline_at_failure_threshold(self):
        """Status should be OFFLINE when health <= failure threshold."""
        from hybrid.systems.damage_model import DamageModel, SubsystemStatus

        model = DamageModel(schema={
            "propulsion": {"max_health": 100.0, "failure_threshold": 0.2},
        })

        # At 20% health (exactly at failure threshold) -> OFFLINE
        model.apply_damage("propulsion", 80.0)
        report = model.get_subsystem_report("propulsion")
        assert report["status"] == "offline"

    def test_status_destroyed_at_zero_health(self):
        """Status should be DESTROYED when health = 0."""
        from hybrid.systems.damage_model import DamageModel, SubsystemStatus

        model = DamageModel(schema={
            "propulsion": {"max_health": 100.0, "failure_threshold": 0.2},
        })

        # At 0% health -> DESTROYED
        model.apply_damage("propulsion", 100.0)
        report = model.get_subsystem_report("propulsion")
        assert report["status"] == "destroyed"

    def test_is_critical_detection(self):
        """Test is_critical() method for severe damage."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "sensors": {"max_health": 100.0, "failure_threshold": 0.15},
        })

        # At 24% health -> should be critical
        model.apply_damage("sensors", 76.0)
        subsystem = model.subsystems["sensors"]
        assert subsystem.is_critical()
        assert subsystem.get_status().value == "damaged"  # Still DAMAGED status

        # At 16% (still above failure threshold of 15%) -> critical
        model.apply_damage("sensors", 8.0)
        assert subsystem.is_critical()

        # At 14% (below failure threshold) -> not critical, it's OFFLINE
        model.apply_damage("sensors", 2.0)
        assert not subsystem.is_critical()  # Can't be critical if OFFLINE


class TestHeatManagement:
    """Test v0.6.0 heat management features."""

    def test_heat_initialization(self):
        """Heat should initialize from schema defaults."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "power": {
                "max_health": 120.0,
                "max_heat": 150.0,
                "heat_generation": 2.0,
                "heat_dissipation": 3.0,
                "overheat_threshold": 0.85,
                "overheat_penalty": 0.5,
            },
        })

        subsystem = model.subsystems["power"]
        assert subsystem.heat == 0.0
        assert subsystem.max_heat == 150.0
        assert subsystem.heat_generation == 2.0
        assert subsystem.heat_dissipation == 3.0
        assert subsystem.overheat_threshold == 0.85
        assert subsystem.overheat_penalty == 0.5

    def test_add_heat(self):
        """Test adding heat to subsystems."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "weapons": {"max_health": 100.0, "max_heat": 100.0},
        })

        # Add heat
        result = model.add_heat("weapons", 30.0)
        assert result["ok"]
        assert result["heat"] == 30.0
        assert result["heat_percent"] == 30.0
        assert not result["overheated"]

    def test_heat_capped_at_max(self):
        """Heat should not exceed max_heat."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "weapons": {"max_health": 100.0, "max_heat": 100.0},
        })

        # Add more heat than max
        model.add_heat("weapons", 150.0)
        subsystem = model.subsystems["weapons"]
        assert subsystem.heat == 100.0

    def test_overheat_detection(self):
        """Test overheat threshold detection."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "weapons": {
                "max_health": 100.0,
                "max_heat": 100.0,
                "overheat_threshold": 0.80,
            },
        })

        # At 79% heat -> not overheated
        model.add_heat("weapons", 79.0)
        subsystem = model.subsystems["weapons"]
        assert not subsystem.is_overheated()

        # At 80% heat -> overheated
        model.add_heat("weapons", 1.0)
        assert subsystem.is_overheated()

    def test_heat_dissipation(self):
        """Test heat dissipation over time."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "propulsion": {
                "max_health": 100.0,
                "max_heat": 100.0,
                "heat_dissipation": 10.0,  # 10 degrees per second
            },
        })

        # Add initial heat
        model.add_heat("propulsion", 50.0)

        # Dissipate for 2 seconds
        model.dissipate_heat(2.0)
        subsystem = model.subsystems["propulsion"]
        assert subsystem.heat == 30.0  # 50 - (10 * 2)

    def test_heat_factor_when_overheated(self):
        """Test performance penalty when overheated."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "rcs": {
                "max_health": 100.0,
                "max_heat": 100.0,
                "overheat_threshold": 0.80,
                "overheat_penalty": 0.4,
            },
        })

        # Not overheated -> factor = 1.0
        subsystem = model.subsystems["rcs"]
        assert subsystem.get_heat_factor() == 1.0

        # Overheated -> factor = penalty
        model.add_heat("rcs", 85.0)
        assert subsystem.get_heat_factor() == 0.4

    def test_combined_factor(self):
        """Test combined damage and heat factor."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "weapons": {
                "max_health": 100.0,
                "max_heat": 100.0,
                "overheat_threshold": 0.80,
                "overheat_penalty": 0.5,
            },
        })

        # Damage to 50% health -> degradation_factor = 0.5
        model.apply_damage("weapons", 50.0)
        # Overheat -> heat_factor = 0.5
        model.add_heat("weapons", 85.0)

        # Combined factor = 0.5 * 0.5 = 0.25
        combined = model.get_combined_factor("weapons")
        assert combined == pytest.approx(0.25)


class TestDamageEvents:
    """Test event publishing for damage state changes."""

    def test_state_change_event_published(self):
        """Test subsystem_state_changed event on status transition."""
        from hybrid.systems.damage_model import DamageModel

        mock_event_bus = MagicMock()
        model = DamageModel(schema={
            "propulsion": {"max_health": 100.0, "failure_threshold": 0.2},
        })

        # Damage from ONLINE to DAMAGED
        model.apply_damage("propulsion", 30.0, source="railgun",
                          event_bus=mock_event_bus, ship_id="ship_001")

        mock_event_bus.publish.assert_called()
        call_args = mock_event_bus.publish.call_args
        assert call_args[0][0] == "subsystem_state_changed"
        event_data = call_args[0][1]
        assert event_data["subsystem"] == "propulsion"
        assert event_data["prev_status"] == "online"
        assert event_data["new_status"] == "damaged"
        assert event_data["ship_id"] == "ship_001"

    def test_offline_event_published(self):
        """Test subsystem_offline event when subsystem fails."""
        from hybrid.systems.damage_model import DamageModel

        mock_event_bus = MagicMock()
        model = DamageModel(schema={
            "weapons": {"max_health": 100.0, "failure_threshold": 0.2},
        })

        # Damage below failure threshold
        model.apply_damage("weapons", 82.0, event_bus=mock_event_bus, ship_id="ship_001")

        # Check subsystem_offline was published
        calls = [call[0][0] for call in mock_event_bus.publish.call_args_list]
        assert "subsystem_offline" in calls

    def test_destroyed_event_published(self):
        """Test subsystem_destroyed event when health reaches 0."""
        from hybrid.systems.damage_model import DamageModel

        mock_event_bus = MagicMock()
        model = DamageModel(schema={
            "sensors": {"max_health": 100.0},
        })

        # Destroy the subsystem
        model.apply_damage("sensors", 100.0, event_bus=mock_event_bus, ship_id="ship_001")

        calls = [call[0][0] for call in mock_event_bus.publish.call_args_list]
        assert "subsystem_destroyed" in calls

    def test_overheat_event_published(self):
        """Test subsystem_overheat event when overheating."""
        from hybrid.systems.damage_model import DamageModel

        mock_event_bus = MagicMock()
        model = DamageModel(schema={
            "power": {
                "max_health": 100.0,
                "max_heat": 100.0,
                "overheat_threshold": 0.80,
            },
        })

        # Cause overheat
        model.add_heat("power", 85.0, event_bus=mock_event_bus, ship_id="ship_001")

        mock_event_bus.publish.assert_called_once()
        call_args = mock_event_bus.publish.call_args
        assert call_args[0][0] == "subsystem_overheat"
        event_data = call_args[0][1]
        assert event_data["subsystem"] == "power"
        assert event_data["ship_id"] == "ship_001"

    def test_cooled_event_published(self):
        """Test subsystem_cooled event when cooling below threshold."""
        from hybrid.systems.damage_model import DamageModel

        mock_event_bus = MagicMock()
        model = DamageModel(schema={
            "propulsion": {
                "max_health": 100.0,
                "max_heat": 100.0,
                "overheat_threshold": 0.80,
                "heat_dissipation": 50.0,
            },
        })

        # Overheat first
        model.add_heat("propulsion", 85.0)
        mock_event_bus.reset_mock()

        # Dissipate to below threshold
        model.dissipate_heat(0.2, event_bus=mock_event_bus, ship_id="ship_001")

        # Should have published cooled event
        calls = [call[0][0] for call in mock_event_bus.publish.call_args_list]
        assert "subsystem_cooled" in calls


class TestDamageModelReports:
    """Test damage model reporting includes v0.6.0 fields."""

    def test_subsystem_report_includes_heat(self):
        """Test subsystem report includes heat fields."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "weapons": {
                "max_health": 100.0,
                "max_heat": 120.0,
                "overheat_threshold": 0.85,
                "overheat_penalty": 0.0,
            },
        })

        model.add_heat("weapons", 50.0)
        report = model.get_subsystem_report("weapons")

        assert "heat" in report
        assert "max_heat" in report
        assert "heat_percent" in report
        assert "overheated" in report
        assert "heat_factor" in report
        assert "combined_factor" in report
        assert "is_critical" in report

        assert report["heat"] == 50.0
        assert report["max_heat"] == 120.0
        assert report["heat_percent"] == pytest.approx(41.67, rel=0.01)

    def test_full_report_includes_overheated_subsystems(self):
        """Test full report includes overheated_subsystems list."""
        from hybrid.systems.damage_model import DamageModel

        model = DamageModel(schema={
            "power": {"max_health": 100.0, "max_heat": 100.0, "overheat_threshold": 0.80},
            "weapons": {"max_health": 100.0, "max_heat": 100.0, "overheat_threshold": 0.80},
        })

        # Overheat power only
        model.add_heat("power", 85.0)

        report = model.get_report()
        assert "overheated_subsystems" in report
        assert "power" in report["overheated_subsystems"]
        assert "weapons" not in report["overheated_subsystems"]


class TestShipDamagePropagation:
    """Test damage propagation from hull to subsystems."""

    def test_apply_subsystem_damage(self):
        """Test direct subsystem damage application."""
        from hybrid.ship import Ship

        ship = Ship("test_ship", {
            "mass": 1000.0,
            "systems": {
                "propulsion": {},
            }
        })

        result = ship.apply_subsystem_damage("propulsion", 30.0, source="railgun")
        assert result["ok"]
        assert result["subsystem"] == "propulsion"
        assert result["damage_applied"] == 30.0

    def test_take_damage_with_subsystem_target(self):
        """Test hull damage with targeted subsystem."""
        from hybrid.ship import Ship

        ship = Ship("test_ship", {
            "mass": 1000.0,
            "hull_integrity": 100.0,
            "systems": {
                "weapons": {},
            }
        })

        initial_hull = ship.hull_integrity
        result = ship.take_damage(20.0, source="torpedo", target_subsystem="weapons")

        # Hull should be damaged
        assert ship.hull_integrity == initial_hull - 20.0

        # Subsystem should also be damaged (50% of hull damage)
        assert result["subsystem_damage"] is not None
        assert result["subsystem_damage"]["subsystem"] == "weapons"


class TestSchemaHeatDefaults:
    """Test systems_schema.py heat field defaults."""

    def test_power_heat_settings(self):
        """Test power subsystem has correct heat defaults."""
        from hybrid.systems_schema import get_heat_settings

        settings = get_heat_settings("power")
        assert settings["max_heat"] == 150.0
        assert settings["heat_generation"] == 2.0
        assert settings["heat_dissipation"] == 3.0
        assert settings["overheat_threshold"] == 0.85
        assert settings["overheat_penalty"] == 0.5

    def test_propulsion_heat_settings(self):
        """Test propulsion subsystem has correct heat defaults."""
        from hybrid.systems_schema import get_heat_settings

        settings = get_heat_settings("propulsion")
        assert settings["max_heat"] == 200.0
        assert settings["heat_generation"] == 1.5
        assert settings["overheat_penalty"] == 0.6

    def test_weapons_heat_settings(self):
        """Test weapons subsystem has correct heat defaults."""
        from hybrid.systems_schema import get_heat_settings

        settings = get_heat_settings("weapons")
        assert settings["max_heat"] == 120.0
        assert settings["overheat_penalty"] == 0.0  # Cannot fire when overheated

    def test_unknown_subsystem_defaults(self):
        """Test unknown subsystems get default heat settings."""
        from hybrid.systems_schema import get_heat_settings

        settings = get_heat_settings("unknown_system")
        assert settings["max_heat"] == 100.0
        assert settings["heat_generation"] == 1.0
        assert settings["heat_dissipation"] == 1.5
        assert settings["overheat_threshold"] == 0.80
        assert settings["overheat_penalty"] == 0.5
