# tests/systems/ops/test_damage_control_scenarios.py
"""Damage control scenario tests: repair pipeline, system triage, emergency shutdown.

Focus: scenario 22_damage_control.yaml — pre-damaged ship with sensors at 60%,
propulsion at 70%, RCS at 85%, weapons at 80%.

Gaps filled vs. existing unit tests in test_cascade_integration.py and
test_damage_model_v060.py:
- Repair dispatch/cancel/priority via command routing (not direct method calls)
- Emergency shutdown + restart cycle through command handler
- System priority and power allocation under damage conditions
- report_status includes subsystem damage in the response
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT_DIR))

from hybrid_runner import HybridRunner
from hybrid.command_handler import route_command


SCENARIO = "22_damage_control"
PLAYER_ID = "player"


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def runner():
    r = HybridRunner()
    r.load_scenario(SCENARIO)
    r.simulator.start()
    return r


@pytest.fixture
def sim(runner):
    return runner.simulator


def issue(sim, command: str, params: dict) -> dict:
    ship = sim.ships[PLAYER_ID]
    result = route_command(
        ship,
        {"command": command, "ship": PLAYER_ID, **params},
        list(sim.ships.values()),
    )
    return result if isinstance(result, dict) else {"error": str(result)}


# ---------------------------------------------------------------------------
# Pre-damaged state
# ---------------------------------------------------------------------------

class TestPreDamagedState:
    """Scenario starts with subsystems below 100% health."""

    def test_sensors_pre_damaged(self, sim):
        ship = sim.ships[PLAYER_ID]
        dm = ship.damage_model
        assert dm.subsystems["sensors"].health < 100.0, (
            "sensors should start below full health in damage_control scenario"
        )

    def test_propulsion_pre_damaged(self, sim):
        ship = sim.ships[PLAYER_ID]
        dm = ship.damage_model
        assert dm.subsystems["propulsion"].health < 100.0

    def test_report_status_reflects_damage(self, sim):
        result = issue(sim, "report_status", {})
        assert result.get("ok") is True
        report = result.get("subsystem_report", {})
        subsystems = report.get("subsystems", {})
        assert "sensors" in subsystems or "propulsion" in subsystems, (
            "report_status subsystem_report.subsystems should list damaged systems"
        )


# ---------------------------------------------------------------------------
# Repair dispatch
# ---------------------------------------------------------------------------

class TestRepairDispatch:
    """Dispatching teams and tracking status via command routing."""

    def _fresh_dispatch(self, sim, subsystem: str = "sensors") -> dict:
        issue(sim, "cancel_repair", {"subsystem": subsystem})
        return issue(sim, "dispatch_repair", {"subsystem": subsystem})

    def test_dispatch_repair_returns_ok(self, sim):
        result = self._fresh_dispatch(sim, "sensors")
        assert result.get("ok") is True

    def test_dispatch_repair_includes_team(self, sim):
        result = self._fresh_dispatch(sim, "sensors")
        assert result.get("ok") is True
        team = result.get("team", {})
        assert team.get("assigned_subsystem") == "sensors"

    def test_dispatch_repair_provides_eta(self, sim):
        result = self._fresh_dispatch(sim, "sensors")
        assert result.get("ok") is True
        assert result.get("eta") is not None

    def test_repair_status_lists_active_teams(self, sim):
        self._fresh_dispatch(sim, "propulsion")
        result = issue(sim, "repair_status", {})
        assert "repair_teams" in result

    def test_cancel_repair_returns_dict(self, sim):
        self._fresh_dispatch(sim, "sensors")
        result = issue(sim, "cancel_repair", {"subsystem": "sensors"})
        assert isinstance(result, dict)

    def test_dispatch_repair_no_subsystem_rejects(self, sim):
        result = issue(sim, "dispatch_repair", {})
        assert result.get("ok") is False

    def test_set_repair_priority_returns_ok(self, sim):
        result = issue(sim, "set_repair_priority", {
            "subsystem": "sensors", "priority": "high",
        })
        assert result.get("ok") is True

    def test_set_repair_priority_invalid_rejects(self, sim):
        result = issue(sim, "set_repair_priority", {
            "subsystem": "sensors", "priority": "ultra_max_extreme",
        })
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# Emergency shutdown / restart
# ---------------------------------------------------------------------------

class TestEmergencyShutdown:
    """Emergency shutdown and restart cycle."""

    def _ensure_online(self, sim, subsystem: str) -> None:
        """Restart a system if it was left shut down by a prior test."""
        issue(sim, "restart_system", {"subsystem": subsystem})

    def test_emergency_shutdown_returns_ok(self, sim):
        self._ensure_online(sim, "sensors")
        result = issue(sim, "emergency_shutdown", {"subsystem": "sensors"})
        assert result.get("ok") is True

    def test_emergency_shutdown_lists_subsystem_in_response(self, sim):
        self._ensure_online(sim, "sensors")
        result = issue(sim, "emergency_shutdown", {"subsystem": "sensors"})
        assert result.get("ok") is True
        assert result.get("subsystem") == "sensors"

    def test_restart_system_returns_ok(self, sim):
        issue(sim, "emergency_shutdown", {"subsystem": "sensors"})
        result = issue(sim, "restart_system", {"subsystem": "sensors"})
        assert result.get("ok") is True

    def test_restart_clears_shutdown_list(self, sim):
        self._ensure_online(sim, "weapons")
        issue(sim, "emergency_shutdown", {"subsystem": "weapons"})
        result = issue(sim, "restart_system", {"subsystem": "weapons"})
        assert result.get("ok") is True
        assert "weapons" not in result.get("shutdown_systems", [])

    def test_emergency_shutdown_missing_subsystem_rejects(self, sim):
        result = issue(sim, "emergency_shutdown", {})
        assert result.get("ok") is False

    def test_restart_missing_subsystem_rejects(self, sim):
        result = issue(sim, "restart_system", {})
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# System priority and power allocation under damage
# ---------------------------------------------------------------------------

class TestSystemTriage:
    """Power allocation and priority assignment while subsystems are degraded."""

    def test_set_system_priority_returns_ok(self, sim):
        result = issue(sim, "set_system_priority", {
            "subsystem": "propulsion", "priority": 8,
        })
        assert result.get("ok") is True

    def test_set_system_priority_zero_returns_ok(self, sim):
        result = issue(sim, "set_system_priority", {
            "subsystem": "sensors", "priority": 0,
        })
        assert result.get("ok") is True

    def test_set_system_priority_missing_subsystem_rejects(self, sim):
        result = issue(sim, "set_system_priority", {"priority": 5})
        assert result.get("ok") is False

    def test_allocate_power_returns_ok(self, sim):
        result = issue(sim, "allocate_power", {
            "allocation": {"propulsion": 0.6, "sensors": 0.4},
        })
        assert result.get("ok") is True

    def test_allocate_power_reflects_allocation(self, sim):
        allocation = {"propulsion": 0.7, "sensors": 0.3}
        result = issue(sim, "allocate_power", {"allocation": allocation})
        assert result.get("ok") is True
        returned = result.get("allocation", {})
        assert "propulsion" in returned or result.get("status") is not None

    def test_allocate_power_missing_allocation_rejects(self, sim):
        result = issue(sim, "allocate_power", {})
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# report_status completeness
# ---------------------------------------------------------------------------

class TestReportStatus:
    """report_status must return a comprehensive view of ship systems."""

    def test_report_status_returns_ok(self, sim):
        result = issue(sim, "report_status", {})
        assert result.get("ok") is True

    def test_report_status_power_allocation(self, sim):
        result = issue(sim, "report_status", {})
        assert "power_allocation" in result

    def test_report_status_subsystem_report(self, sim):
        result = issue(sim, "report_status", {})
        assert "subsystem_report" in result

    def test_report_status_repair_teams(self, sim):
        result = issue(sim, "report_status", {})
        assert "repair_teams" in result

    def test_report_status_cascade_effects(self, sim):
        result = issue(sim, "report_status", {})
        assert "cascade_effects" in result
