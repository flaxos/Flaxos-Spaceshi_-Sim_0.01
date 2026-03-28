# tests/test_field_repair.py
"""Tests for the mid-mission field repair system.

Covers:
- Spare parts consumption and depletion
- G-load repair speed modifiers
- Field repair health cap at 50%
- Repair job lifecycle (start, pause, complete, cancel)
- Integration with OpsSystem repair teams
- Command handlers (dispatch, cancel, status, priority)
"""

import math
import pytest
from unittest.mock import MagicMock

from hybrid.systems.field_repair import (
    FieldRepairManager,
    RepairPriority,
    RepairJob,
    FIELD_REPAIR_HEALTH_CAP,
    PARTS_PER_HEALTH_POINT,
    G_LOAD_LOW,
    G_LOAD_HIGH,
    DEFAULT_SPARE_PARTS,
)
from hybrid.systems.damage_model import DamageModel, SubsystemStatus
from hybrid.systems.ops_system import OpsSystem, RepairTeamStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ship(
    subsystem_health: dict[str, float] | None = None,
    acceleration: dict[str, float] | None = None,
    spare_parts: float = DEFAULT_SPARE_PARTS,
) -> MagicMock:
    """Create a minimal mock ship for repair testing.

    Args:
        subsystem_health: Dict of subsystem -> health value
        acceleration: Ship acceleration vector
        spare_parts: Initial spare parts

    Returns:
        MagicMock: Ship mock with damage_model and acceleration
    """
    ship = MagicMock()
    ship.id = "test_ship"
    ship.acceleration = acceleration or {"x": 0.0, "y": 0.0, "z": 0.0}
    ship.event_bus = MagicMock()

    # Build damage model with specified health values
    health_map = subsystem_health or {"propulsion": 50.0, "sensors": 30.0}
    schema = {}
    config = {}
    for name, health in health_map.items():
        schema[name] = {"max_health": 100.0, "criticality": 1.0, "failure_threshold": 0.2}
        config[name] = {"health": health}

    ship.damage_model = DamageModel(config=config, schema=schema)
    ship.get_effective_factor = lambda sub: ship.damage_model.get_degradation_factor(sub)
    ship.cascade_manager = MagicMock()
    ship.cascade_manager.get_report.return_value = {"factors": {}, "active_cascades": []}

    return ship


def make_ops(spare_parts: float = DEFAULT_SPARE_PARTS) -> OpsSystem:
    """Create an OpsSystem with field repair configured.

    Args:
        spare_parts: Initial spare parts

    Returns:
        OpsSystem: Configured ops system
    """
    return OpsSystem({
        "repair_teams": 2,
        "field_repair": {"spare_parts": spare_parts, "max_spare_parts": spare_parts},
    })


# ---------------------------------------------------------------------------
# FieldRepairManager unit tests
# ---------------------------------------------------------------------------

class TestGLoadFactor:
    """G-load effects on repair speed."""

    def test_zero_g_full_speed(self):
        mgr = FieldRepairManager()
        assert mgr.get_g_load_factor(0.0) == 1.0

    def test_low_g_full_speed(self):
        mgr = FieldRepairManager()
        assert mgr.get_g_load_factor(G_LOAD_LOW) == 1.0

    def test_high_g_halted(self):
        mgr = FieldRepairManager()
        assert mgr.get_g_load_factor(G_LOAD_HIGH) == 0.0

    def test_extreme_g_halted(self):
        mgr = FieldRepairManager()
        assert mgr.get_g_load_factor(10.0) == 0.0

    def test_mid_g_partial(self):
        """Between LOW and HIGH thresholds, repair speed scales linearly."""
        mgr = FieldRepairManager()
        mid_g = (G_LOAD_LOW + G_LOAD_HIGH) / 2.0
        factor = mgr.get_g_load_factor(mid_g)
        assert 0.0 < factor < 1.0
        assert abs(factor - 0.5) < 0.01


class TestHealthCap:
    """Field repair health cap at 50%."""

    def test_cap_is_half_max(self):
        mgr = FieldRepairManager()
        assert mgr.get_field_repair_cap(100.0) == 50.0

    def test_cap_scales_with_max_health(self):
        mgr = FieldRepairManager()
        assert mgr.get_field_repair_cap(200.0) == 100.0


class TestSpareParts:
    """Spare parts consumption."""

    def test_consume_parts_full(self):
        mgr = FieldRepairManager({"spare_parts": 100.0, "max_spare_parts": 100.0})
        actual = mgr.consume_parts(10.0)
        assert actual == 10.0
        assert mgr.spare_parts == pytest.approx(100.0 - 10.0 * PARTS_PER_HEALTH_POINT)

    def test_consume_parts_insufficient(self):
        """When parts run out, repair is capped to available parts."""
        mgr = FieldRepairManager({"spare_parts": 5.0, "max_spare_parts": 100.0})
        actual = mgr.consume_parts(10.0)
        assert actual == pytest.approx(5.0 / PARTS_PER_HEALTH_POINT)
        assert mgr.spare_parts == 0.0

    def test_consume_parts_empty(self):
        mgr = FieldRepairManager({"spare_parts": 0.0, "max_spare_parts": 100.0})
        actual = mgr.consume_parts(10.0)
        assert actual == 0.0

    def test_resupply(self):
        mgr = FieldRepairManager({"spare_parts": 50.0, "max_spare_parts": 200.0})
        result = mgr.resupply_parts(100.0)
        assert result == 150.0
        assert mgr.spare_parts == 150.0

    def test_resupply_cap(self):
        mgr = FieldRepairManager({"spare_parts": 180.0, "max_spare_parts": 200.0})
        result = mgr.resupply_parts(100.0)
        assert result == 200.0


class TestRepairConstraints:
    """Combined constraint application."""

    def test_normal_conditions(self):
        """At 0g with full parts, repair is unconstrained."""
        mgr = FieldRepairManager({"spare_parts": 200.0, "max_spare_parts": 200.0})
        actual, reason = mgr.apply_repair_constraints(
            subsystem="propulsion",
            raw_repair_amount=5.0,
            current_health=20.0,
            max_health=100.0,
            current_g=0.0,
        )
        assert actual == 5.0
        assert reason is None

    def test_high_g_blocks_repair(self):
        mgr = FieldRepairManager({"spare_parts": 200.0, "max_spare_parts": 200.0})
        actual, reason = mgr.apply_repair_constraints(
            subsystem="propulsion",
            raw_repair_amount=5.0,
            current_health=20.0,
            max_health=100.0,
            current_g=5.0,
        )
        assert actual == 0.0
        assert "g-load" in reason.lower()

    def test_health_cap_blocks_repair(self):
        """Repair halts when health reaches 50% cap."""
        mgr = FieldRepairManager({"spare_parts": 200.0, "max_spare_parts": 200.0})
        actual, reason = mgr.apply_repair_constraints(
            subsystem="propulsion",
            raw_repair_amount=5.0,
            current_health=50.0,  # Already at cap for max_health=100
            max_health=100.0,
            current_g=0.0,
        )
        assert actual == 0.0
        assert "50%" in reason

    def test_approaching_cap_partial(self):
        """Repair is reduced when close to cap to avoid overshoot."""
        mgr = FieldRepairManager({"spare_parts": 200.0, "max_spare_parts": 200.0})
        actual, reason = mgr.apply_repair_constraints(
            subsystem="propulsion",
            raw_repair_amount=10.0,
            current_health=48.0,  # 2 hp below cap
            max_health=100.0,
            current_g=0.0,
        )
        assert actual == pytest.approx(2.0)
        assert reason is None

    def test_no_parts_blocks_repair(self):
        mgr = FieldRepairManager({"spare_parts": 0.0, "max_spare_parts": 200.0})
        actual, reason = mgr.apply_repair_constraints(
            subsystem="propulsion",
            raw_repair_amount=5.0,
            current_health=20.0,
            max_health=100.0,
            current_g=0.0,
        )
        assert actual == 0.0
        assert "spare parts" in reason.lower()

    def test_partial_g_reduces_speed(self):
        """Mid-range g-load reduces repair amount proportionally."""
        mgr = FieldRepairManager({"spare_parts": 200.0, "max_spare_parts": 200.0})
        mid_g = (G_LOAD_LOW + G_LOAD_HIGH) / 2.0
        actual, reason = mgr.apply_repair_constraints(
            subsystem="propulsion",
            raw_repair_amount=10.0,
            current_health=20.0,
            max_health=100.0,
            current_g=mid_g,
        )
        assert actual == pytest.approx(5.0, abs=0.1)
        assert reason is None


class TestRepairJobs:
    """Repair job lifecycle management."""

    def test_start_repair(self):
        mgr = FieldRepairManager()
        job = mgr.start_repair("propulsion")
        assert job.subsystem == "propulsion"
        assert job.priority == RepairPriority.NORMAL
        assert "propulsion" in mgr.repair_jobs

    def test_start_repair_with_priority(self):
        mgr = FieldRepairManager()
        job = mgr.start_repair("propulsion", RepairPriority.CRITICAL)
        assert job.priority == RepairPriority.CRITICAL

    def test_cancel_repair(self):
        mgr = FieldRepairManager()
        mgr.start_repair("propulsion")
        cancelled = mgr.cancel_repair("propulsion")
        assert cancelled is not None
        assert "propulsion" not in mgr.repair_jobs

    def test_cancel_nonexistent(self):
        mgr = FieldRepairManager()
        assert mgr.cancel_repair("propulsion") is None

    def test_complete_repair(self):
        mgr = FieldRepairManager()
        mgr.start_repair("propulsion")
        mgr.complete_repair("propulsion")
        assert "propulsion" not in mgr.repair_jobs
        assert len(mgr.completed_repairs) == 1

    def test_repair_queue_sorted_by_priority(self):
        mgr = FieldRepairManager()
        mgr.start_repair("sensors", RepairPriority.LOW)
        mgr.start_repair("propulsion", RepairPriority.CRITICAL)
        mgr.start_repair("weapons", RepairPriority.HIGH)

        queue = mgr.get_repair_queue()
        assert queue[0].subsystem == "propulsion"
        assert queue[1].subsystem == "weapons"
        assert queue[2].subsystem == "sensors"


# ---------------------------------------------------------------------------
# OpsSystem integration tests
# ---------------------------------------------------------------------------

class TestOpsFieldRepairIntegration:
    """Test OpsSystem tick with field repair constraints."""

    def test_repair_at_zero_g(self):
        """Repair proceeds normally at zero g."""
        ops = make_ops(spare_parts=200.0)
        ship = make_ship({"propulsion": 30.0})

        # Dispatch a team
        result = ops._cmd_dispatch_repair({
            "subsystem": "propulsion",
            "_ship": ship,
            "event_bus": ship.event_bus,
        })
        assert result["ok"]

        # Advance past transit
        for _ in range(20):
            ops.tick(1.0, ship=ship, event_bus=ship.event_bus)

        # Health should have increased
        sub = ship.damage_model.subsystems["propulsion"]
        assert sub.health > 30.0

    def test_repair_capped_at_50_percent(self):
        """Repair stops at field repair cap (50% of max_health)."""
        ops = make_ops(spare_parts=200.0)
        ship = make_ship({"propulsion": 40.0})

        ops._cmd_dispatch_repair({
            "subsystem": "propulsion",
            "_ship": ship,
            "event_bus": ship.event_bus,
        })

        # Run many ticks to reach cap
        for _ in range(100):
            ops.tick(1.0, ship=ship, event_bus=ship.event_bus)

        sub = ship.damage_model.subsystems["propulsion"]
        # Should stop at 50.0 (cap for max_health=100)
        assert sub.health <= 50.0 + 0.1  # Small tolerance for floating point

    def test_repair_blocked_at_high_g(self):
        """High g-load prevents repair progress."""
        ops = make_ops(spare_parts=200.0)
        # 5g acceleration = ~49 m/s^2
        ship = make_ship(
            {"propulsion": 30.0},
            acceleration={"x": 49.05, "y": 0.0, "z": 0.0},
        )

        ops._cmd_dispatch_repair({
            "subsystem": "propulsion",
            "_ship": ship,
            "event_bus": ship.event_bus,
        })

        initial_health = ship.damage_model.subsystems["propulsion"].health

        # Advance past transit and into repair phase
        for _ in range(30):
            ops.tick(1.0, ship=ship, event_bus=ship.event_bus)

        # Health should not increase (g-load too high)
        sub = ship.damage_model.subsystems["propulsion"]
        assert sub.health == pytest.approx(initial_health, abs=0.1)

    def test_spare_parts_deplete(self):
        """Repair stops when spare parts run out."""
        ops = make_ops(spare_parts=5.0)  # Very few parts
        ship = make_ship({"propulsion": 30.0})

        ops._cmd_dispatch_repair({
            "subsystem": "propulsion",
            "_ship": ship,
            "event_bus": ship.event_bus,
        })

        # Run enough ticks to deplete parts
        for _ in range(50):
            ops.tick(1.0, ship=ship, event_bus=ship.event_bus)

        sub = ship.damage_model.subsystems["propulsion"]
        # Should have gained at most 5 hp (limited by parts)
        assert sub.health <= 35.0 + 0.1
        assert ops.field_repair.spare_parts == pytest.approx(0.0, abs=0.01)

    def test_cancel_repair_command(self):
        """cancel_repair recalls the team and removes the job."""
        ops = make_ops()
        ship = make_ship({"propulsion": 30.0})

        ops._cmd_dispatch_repair({
            "subsystem": "propulsion",
            "_ship": ship,
            "event_bus": ship.event_bus,
        })

        result = ops._cmd_cancel_repair({
            "subsystem": "propulsion",
            "_ship": ship,
            "event_bus": ship.event_bus,
        })
        assert result["ok"]

        # Team should be idle
        team = ops.repair_teams[0]
        assert team.status == RepairTeamStatus.IDLE
        assert team.assigned_subsystem is None

    def test_repair_status_command(self):
        """repair_status returns spare parts and g-load info."""
        ops = make_ops(spare_parts=150.0)
        ship = make_ship({"propulsion": 30.0})

        result = ops._cmd_repair_status({"_ship": ship})
        assert result["ok"]
        assert result["field_repair"]["spare_parts"] == 150.0
        assert "current_g" in result
        assert "g_load_repair_factor" in result

    def test_set_repair_priority_command(self):
        """set_repair_priority updates priority on manager."""
        ops = make_ops()
        result = ops._cmd_set_repair_priority({
            "subsystem": "propulsion",
            "priority": "critical",
        })
        assert result["ok"]
        assert result["priority"] == "critical"
        assert ops.field_repair.priorities["propulsion"] == RepairPriority.CRITICAL

    def test_destroyed_subsystem_not_repairable(self):
        """Destroyed subsystems cannot be field repaired."""
        ops = make_ops()
        ship = make_ship({"propulsion": 0.0})

        result = ops._cmd_dispatch_repair({
            "subsystem": "propulsion",
            "_ship": ship,
            "event_bus": ship.event_bus,
        })
        assert not result["ok"]
        assert "DESTROYED" in result["error"]

    def test_g_load_slows_transit(self):
        """High g-load also slows team transit to the repair site."""
        ops_normal = make_ops()
        ship_normal = make_ship({"propulsion": 30.0})

        ops_highg = make_ops()
        # ~2g, which gives a factor between 0 and 1
        ship_highg = make_ship(
            {"propulsion": 30.0},
            acceleration={"x": 19.62, "y": 0.0, "z": 0.0},
        )

        ops_normal._cmd_dispatch_repair({
            "subsystem": "propulsion", "_ship": ship_normal,
            "event_bus": ship_normal.event_bus,
        })
        ops_highg._cmd_dispatch_repair({
            "subsystem": "propulsion", "_ship": ship_highg,
            "event_bus": ship_highg.event_bus,
        })

        # After same number of ticks, the high-g team should have more
        # transit remaining (slower movement)
        for _ in range(5):
            ops_normal.tick(1.0, ship=ship_normal, event_bus=ship_normal.event_bus)
            ops_highg.tick(1.0, ship=ship_highg, event_bus=ship_highg.event_bus)

        team_normal = ops_normal.repair_teams[0]
        team_highg = ops_highg.repair_teams[0]

        # High-g team should still be in transit or have more remaining
        assert team_highg.transit_remaining >= team_normal.transit_remaining


class TestFieldRepairTelemetry:
    """Test telemetry output from field repair system."""

    def test_get_state_includes_field_repair(self):
        ops = make_ops(spare_parts=150.0)
        state = ops.get_state()
        assert "field_repair" in state
        assert state["field_repair"]["spare_parts"] == 150.0
        assert "active_repairs" in state["field_repair"]

    def test_repair_job_serialization(self):
        job = RepairJob(
            subsystem="sensors",
            priority=RepairPriority.HIGH,
            health_restored=15.5,
            parts_consumed=15.5,
        )
        d = job.to_dict()
        assert d["subsystem"] == "sensors"
        assert d["priority"] == "high"
        assert d["health_restored"] == 15.5
