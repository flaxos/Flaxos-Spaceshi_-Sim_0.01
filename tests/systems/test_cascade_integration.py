# tests/systems/test_cascade_integration.py
"""Tests that cascade damage actually affects system performance factors.

Verifies the fix for the critical bug where CascadeManager computed correct
cascade factors but no system ever used them -- get_combined_factor() defaulted
cascade_factor to 1.0 and all callers relied on that default.

The fix: DamageModel.get_combined_factor() auto-queries the attached
CascadeManager when no explicit cascade_factor is passed.
"""

import pytest

from hybrid.systems.damage_model import DamageModel, SubsystemStatus
from hybrid.systems.cascade_manager import CascadeManager, CASCADE_RULES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_model_with_cascade(subsystems: dict) -> tuple:
    """Create a DamageModel + CascadeManager pair wired together.

    Args:
        subsystems: Dict of subsystem_name -> {max_health, ...}

    Returns:
        (DamageModel, CascadeManager) with the cascade link established
    """
    schema = {name: {"max_health": cfg.get("max_health", 100.0)}
              for name, cfg in subsystems.items()}
    model = DamageModel(schema=schema)
    cascade = CascadeManager()
    model.set_cascade_manager(cascade)
    return model, cascade


# ---------------------------------------------------------------------------
# Core integration tests
# ---------------------------------------------------------------------------

class TestCascadeIntegration:
    """Verify cascade factors flow through get_combined_factor automatically."""

    def test_destroyed_reactor_degrades_propulsion(self):
        """Destroyed reactor should reduce propulsion factor to 0.0."""
        model, cascade = _make_model_with_cascade({
            "reactor": {"max_health": 100.0},
            "propulsion": {"max_health": 100.0},
        })

        # Propulsion starts at full effectiveness
        assert model.get_combined_factor("propulsion") == pytest.approx(1.0)

        # Destroy the reactor
        model.apply_damage("reactor", 100.0)
        assert model.subsystems["reactor"].get_status() == SubsystemStatus.DESTROYED

        # Recompute cascades (normally called each tick by Ship.tick)
        cascade.tick(model)

        # Propulsion should now be fully denied power (penalty_failed=0.0)
        factor = model.get_combined_factor("propulsion")
        assert factor == pytest.approx(0.0), (
            f"Destroyed reactor should deny propulsion power, got factor={factor}"
        )

    def test_destroyed_reactor_degrades_weapons(self):
        """Destroyed reactor should reduce weapons factor to 0.0."""
        model, cascade = _make_model_with_cascade({
            "reactor": {"max_health": 100.0},
            "weapons": {"max_health": 100.0},
        })

        model.apply_damage("reactor", 100.0)
        cascade.tick(model)

        factor = model.get_combined_factor("weapons")
        assert factor == pytest.approx(0.0), (
            f"Destroyed reactor should deny weapons power, got factor={factor}"
        )

    def test_destroyed_reactor_degrades_sensors(self):
        """Destroyed reactor should reduce sensors factor to 0.0."""
        model, cascade = _make_model_with_cascade({
            "reactor": {"max_health": 100.0},
            "sensors": {"max_health": 100.0},
        })

        model.apply_damage("reactor", 100.0)
        cascade.tick(model)

        factor = model.get_combined_factor("sensors")
        assert factor == pytest.approx(0.0), (
            f"Destroyed reactor should deny sensors power, got factor={factor}"
        )

    def test_damaged_reactor_partially_degrades_propulsion(self):
        """Damaged reactor should partially reduce propulsion (penalty_damaged=0.5)."""
        model, cascade = _make_model_with_cascade({
            "reactor": {"max_health": 100.0},
            "propulsion": {"max_health": 100.0},
        })

        # Damage reactor to DAMAGED state (50% health)
        model.apply_damage("reactor", 50.0)
        assert model.subsystems["reactor"].get_status() == SubsystemStatus.DAMAGED

        cascade.tick(model)

        # Propulsion's own health is 100%, but cascade penalty_damaged=0.5
        factor = model.get_combined_factor("propulsion")
        assert factor == pytest.approx(0.5), (
            f"Damaged reactor should halve propulsion, got factor={factor}"
        )

    def test_cascade_stacks_with_own_damage(self):
        """Cascade penalty should multiply with the subsystem's own damage."""
        model, cascade = _make_model_with_cascade({
            "reactor": {"max_health": 100.0},
            "propulsion": {"max_health": 100.0},
        })

        # Damage reactor to DAMAGED (cascade penalty_damaged=0.5)
        model.apply_damage("reactor", 50.0)
        # Also damage propulsion itself to 50% (degradation_factor=0.5)
        model.apply_damage("propulsion", 50.0)

        cascade.tick(model)

        # Combined = propulsion_damage(0.5) * heat(1.0) * cascade(0.5) = 0.25
        factor = model.get_combined_factor("propulsion")
        assert factor == pytest.approx(0.25), (
            f"Cascade should multiply with own damage, got factor={factor}"
        )

    def test_healthy_reactor_no_cascade(self):
        """Healthy reactor should produce no cascade penalty."""
        model, cascade = _make_model_with_cascade({
            "reactor": {"max_health": 100.0},
            "propulsion": {"max_health": 100.0},
        })

        cascade.tick(model)

        factor = model.get_combined_factor("propulsion")
        assert factor == pytest.approx(1.0), (
            f"Healthy reactor should not penalize propulsion, got factor={factor}"
        )

    def test_sensors_cascade_to_targeting(self):
        """Destroyed sensors should deny targeting (penalty_failed=0.0)."""
        model, cascade = _make_model_with_cascade({
            "sensors": {"max_health": 100.0},
            "targeting": {"max_health": 100.0},
            "reactor": {"max_health": 100.0},
        })

        model.apply_damage("sensors", 100.0)
        cascade.tick(model)

        factor = model.get_combined_factor("targeting")
        assert factor == pytest.approx(0.0), (
            f"Destroyed sensors should blind targeting, got factor={factor}"
        )

    def test_multiple_cascades_stack(self):
        """Targeting gets cascade from both reactor and sensors."""
        model, cascade = _make_model_with_cascade({
            "reactor": {"max_health": 100.0},
            "sensors": {"max_health": 100.0},
            "targeting": {"max_health": 100.0},
            "rcs": {"max_health": 100.0},
        })

        # Damage reactor to DAMAGED (cascade to targeting: penalty_damaged=0.6)
        model.apply_damage("reactor", 50.0)
        # Damage sensors to DAMAGED (cascade to targeting: penalty_damaged=0.4)
        model.apply_damage("sensors", 50.0)

        cascade.tick(model)

        # Targeting cascade = reactor_cascade(0.6) * sensors_cascade(0.4) = 0.24
        factor = model.get_combined_factor("targeting")
        assert factor == pytest.approx(0.24), (
            f"Multiple cascades should stack multiplicatively, got factor={factor}"
        )

    def test_cascade_clears_on_repair(self):
        """Repairing the source should clear the cascade penalty."""
        model, cascade = _make_model_with_cascade({
            "reactor": {"max_health": 100.0},
            "propulsion": {"max_health": 100.0},
        })

        # Destroy reactor, verify cascade
        model.apply_damage("reactor", 100.0)
        cascade.tick(model)
        assert model.get_combined_factor("propulsion") == pytest.approx(0.0)

        # Repair reactor back to full
        model.repair_subsystem("reactor", 100.0)
        cascade.tick(model)

        # Cascade should be cleared
        factor = model.get_combined_factor("propulsion")
        assert factor == pytest.approx(1.0), (
            f"Repaired reactor should clear cascade, got factor={factor}"
        )


class TestCascadeWithoutManager:
    """Verify backward compatibility when no cascade manager is attached."""

    def test_standalone_model_defaults_to_no_cascade(self):
        """DamageModel without cascade_manager should return factor=1.0 for healthy systems."""
        schema = {"weapons": {"max_health": 100.0}}
        model = DamageModel(schema=schema)
        # No set_cascade_manager call

        assert model.get_combined_factor("weapons") == pytest.approx(1.0)

    def test_standalone_model_damage_still_works(self):
        """DamageModel without cascade_manager should still apply damage degradation."""
        schema = {"weapons": {"max_health": 100.0}}
        model = DamageModel(schema=schema)

        model.apply_damage("weapons", 50.0)

        factor = model.get_combined_factor("weapons")
        assert factor == pytest.approx(0.5)

    def test_explicit_cascade_factor_overrides_auto_query(self):
        """Passing an explicit cascade_factor should bypass the auto-query."""
        model, cascade = _make_model_with_cascade({
            "reactor": {"max_health": 100.0},
            "propulsion": {"max_health": 100.0},
        })

        # Destroy reactor -- auto-query would give cascade=0.0
        model.apply_damage("reactor", 100.0)
        cascade.tick(model)

        # But explicit factor=1.0 overrides the auto-query
        factor = model.get_combined_factor("propulsion", cascade_factor=1.0)
        assert factor == pytest.approx(1.0), (
            "Explicit cascade_factor should override auto-query"
        )


class TestShipCascadeIntegration:
    """Integration test: verify cascade flows through actual Ship object."""

    def test_ship_cascade_wired_on_init(self):
        """Ship should wire cascade_manager into damage_model on creation."""
        from hybrid.ship import Ship

        ship = Ship("test_cascade", {
            "systems": {
                "reactor": {"max_health": 100.0},
                "propulsion": {"max_thrust": 100.0},
            }
        })

        # The link should be established
        assert ship.damage_model._cascade_manager is ship.cascade_manager

    def test_ship_destroyed_reactor_affects_propulsion(self):
        """Full integration: destroy reactor on a Ship, verify propulsion degrades.

        Ship uses the schema-defined reactor health (130 HP, threshold 0.15),
        so we must deal enough damage to actually destroy it.
        """
        from hybrid.ship import Ship

        ship = Ship("test_cascade_full", {
            "systems": {
                "reactor": {"max_health": 100.0},
                "propulsion": {"max_thrust": 100.0},
            }
        })

        # Propulsion should start at full
        factor_before = ship.damage_model.get_combined_factor("propulsion")
        assert factor_before == pytest.approx(1.0)

        # Destroy reactor — deal enough damage to exceed its actual max_health
        # (schema may define reactor at 130 HP, so 100 is not enough)
        reactor_hp = ship.damage_model.subsystems["reactor"].max_health
        ship.damage_model.apply_damage("reactor", reactor_hp)
        assert ship.damage_model.subsystems["reactor"].get_status() == SubsystemStatus.DESTROYED

        # Run cascade tick (normally called by ship.tick)
        ship.cascade_manager.tick(ship.damage_model, ship.event_bus, ship.id)

        # Now propulsion should be denied by cascade
        factor_after = ship.damage_model.get_combined_factor("propulsion")
        assert factor_after == pytest.approx(0.0), (
            f"Destroyed reactor should deny propulsion on Ship, got factor={factor_after}"
        )
