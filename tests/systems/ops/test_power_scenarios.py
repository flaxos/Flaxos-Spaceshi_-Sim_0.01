# tests/systems/ops/test_power_scenarios.py
"""Power management and fuel crisis scenario tests.

Focus: scenario 24_fuel_crisis.yaml — ship starts at 40% fuel with a pursuing
pirate and a distant fuel station. Tests the power/engineering command pipeline.

Gaps filled vs. existing test_fuel_enforcement.py and test_management.py
(which test models directly): these tests verify end-to-end command routing
from engineering station commands to observable state.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT_DIR))

from hybrid_runner import HybridRunner
from hybrid.command_handler import route_command


SCENARIO = "24_fuel_crisis"
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
# Fuel crisis scenario state
# ---------------------------------------------------------------------------

class TestFuelCrisisSetup:
    """Scenario starts with reduced fuel level."""

    def test_fuel_below_full(self, sim):
        result = issue(sim, "monitor_fuel", {})
        assert result.get("ok") is True
        assert result["fuel_percent"] < 100.0

    def test_delta_v_positive(self, sim):
        result = issue(sim, "monitor_fuel", {})
        assert result.get("delta_v_remaining", 0.0) > 0.0

    def test_power_management_system_present(self, sim):
        ship = sim.ships[PLAYER_ID]
        assert ship.systems.get("power_management") is not None


# ---------------------------------------------------------------------------
# Power profiles
# ---------------------------------------------------------------------------

class TestPowerProfiles:
    """Power profile enumeration and switching."""

    def test_get_power_profiles_returns_list(self, sim):
        result = issue(sim, "get_power_profiles", {})
        assert "profiles" in result
        assert isinstance(result["profiles"], list)

    def test_get_power_profiles_non_empty(self, sim):
        result = issue(sim, "get_power_profiles", {})
        assert len(result["profiles"]) > 0

    def test_set_power_profile_valid_returns_profile(self, sim):
        profiles_result = issue(sim, "get_power_profiles", {})
        profile = profiles_result["profiles"][0]
        result = issue(sim, "set_power_profile", {"profile": profile})
        # set_power_profile returns status dict without 'ok', includes 'profile'
        assert "profile" in result or result.get("ok") is True

    def test_set_power_profile_unknown_rejects(self, sim):
        result = issue(sim, "set_power_profile", {"profile": "warp_drive_max"})
        # set_power_profile returns {'error': ...} (no 'ok' key) on unknown profile
        assert result.get("ok") is False or "error" in result

    def test_get_power_profiles_includes_active(self, sim):
        result = issue(sim, "get_power_profiles", {})
        assert "active_profile" in result


# ---------------------------------------------------------------------------
# Power allocation
# ---------------------------------------------------------------------------

class TestPowerAllocation:
    """Power allocation across subsystems."""

    def test_set_power_allocation_returns_allocation(self, sim):
        result = issue(sim, "set_power_allocation", {
            "allocation": {"propulsion": 0.6, "sensors": 0.4},
        })
        assert "power_allocation" in result

    def test_get_draw_profile_returns_buses(self, sim):
        result = issue(sim, "get_draw_profile", {})
        assert "buses" in result

    def test_get_draw_profile_includes_totals(self, sim):
        result = issue(sim, "get_draw_profile", {})
        assert "totals" in result

    def test_get_draw_profile_has_active_profile(self, sim):
        result = issue(sim, "get_draw_profile", {})
        assert "active_profile" in result


# ---------------------------------------------------------------------------
# Reactor control
# ---------------------------------------------------------------------------

class TestReactorControl:
    """Reactor output adjustment."""

    def test_set_reactor_output_75_percent(self, sim):
        result = issue(sim, "set_reactor_output", {"output": 0.75})
        assert result.get("ok") is True
        assert abs(result.get("reactor_percent", 0) - 75.0) < 1.0

    def test_set_reactor_output_full(self, sim):
        result = issue(sim, "set_reactor_output", {"output": 1.0})
        assert result.get("ok") is True

    def test_set_reactor_output_response_has_percent(self, sim):
        result = issue(sim, "set_reactor_output", {"output": 0.5})
        assert "reactor_percent" in result
        assert "reactor_output" in result

    def test_set_reactor_output_missing_rejects(self, sim):
        result = issue(sim, "set_reactor_output", {})
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# Drive throttle
# ---------------------------------------------------------------------------

class TestDriveThrottle:
    """Drive limit (engineering throttle cap on helm thrust)."""

    def test_throttle_drive_50_percent(self, sim):
        result = issue(sim, "throttle_drive", {"limit": 0.5})
        assert result.get("ok") is True
        assert abs(result.get("drive_percent", 0) - 50.0) < 1.0

    def test_throttle_drive_full(self, sim):
        result = issue(sim, "throttle_drive", {"limit": 1.0})
        assert result.get("ok") is True

    def test_throttle_drive_clamps_below_zero(self, sim):
        result = issue(sim, "throttle_drive", {"limit": -0.5})
        assert result.get("ok") is True
        assert result.get("drive_limit", 1.0) >= 0.0

    def test_throttle_drive_missing_rejects(self, sim):
        result = issue(sim, "throttle_drive", {})
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# Fuel monitoring
# ---------------------------------------------------------------------------

class TestFuelMonitoring:
    """monitor_fuel returns a complete fuel-state snapshot."""

    def test_monitor_fuel_ok(self, sim):
        result = issue(sim, "monitor_fuel", {})
        assert result.get("ok") is True

    def test_monitor_fuel_level(self, sim):
        result = issue(sim, "monitor_fuel", {})
        assert "fuel_level" in result
        assert result["fuel_level"] > 0.0

    def test_monitor_fuel_percent(self, sim):
        result = issue(sim, "monitor_fuel", {})
        assert "fuel_percent" in result
        assert 0.0 < result["fuel_percent"] <= 100.0

    def test_monitor_fuel_delta_v(self, sim):
        result = issue(sim, "monitor_fuel", {})
        assert "delta_v_remaining" in result
        assert result["delta_v_remaining"] > 0.0

    def test_monitor_fuel_isp_positive(self, sim):
        result = issue(sim, "monitor_fuel", {})
        assert result.get("isp", 0) > 0

    def test_monitor_fuel_drive_limit_field(self, sim):
        result = issue(sim, "monitor_fuel", {})
        assert "drive_limit" in result
        assert "reactor_output" in result


# ---------------------------------------------------------------------------
# Radiator management
# ---------------------------------------------------------------------------

class TestRadiatorManagement:
    """manage_radiators routes correctly and returns a response dict."""

    def test_manage_radiators_deploy_returns_dict(self, sim):
        result = issue(sim, "manage_radiators", {"action": "deploy"})
        assert isinstance(result, dict)

    def test_manage_radiators_retract_returns_dict(self, sim):
        result = issue(sim, "manage_radiators", {"action": "retract"})
        assert isinstance(result, dict)

    def test_manage_radiators_has_ok_or_error(self, sim):
        result = issue(sim, "manage_radiators", {"action": "deploy"})
        assert "ok" in result or "error" in result
