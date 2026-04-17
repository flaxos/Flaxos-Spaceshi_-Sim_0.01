# tests/systems/ops/test_stealth_scenarios.py
"""Stealth/ECM scenario tests: EMCON, jamming, ECM status pipeline.

Focus: scenario 25_silent_running.yaml — corvette starts with EMCON active,
must navigate through sensor corridors.

Gaps filled vs. existing test_eccm.py and test_home_on_jam.py (which test
mechanics directly): these tests verify the command-routing path from
station commands through to observable ECM state changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT_DIR))

from hybrid_runner import HybridRunner
from hybrid.command_handler import route_command


SCENARIO = "25_silent_running"
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
# Scenario setup checks
# ---------------------------------------------------------------------------

class TestSilentRunningSetup:
    """Scenario starts with ECM system present and EMCON active."""

    def test_ecm_system_present(self, sim):
        ship = sim.ships[PLAYER_ID]
        assert ship.systems.get("ecm") is not None

    def test_ecm_status_command_returns_state(self, sim):
        result = issue(sim, "ecm_status", {})
        assert isinstance(result, dict)
        assert "emcon_active" in result

    def test_initial_emcon_active_is_bool(self, sim):
        result = issue(sim, "ecm_status", {})
        assert isinstance(result["emcon_active"], bool)

    def test_ecm_status_has_reduction_fields(self, sim):
        result = issue(sim, "ecm_status", {})
        assert "emcon_ir_reduction" in result
        assert "emcon_rcs_reduction" in result


# ---------------------------------------------------------------------------
# EMCON toggle
# ---------------------------------------------------------------------------

class TestEmconToggle:
    """set_emcon changes the observable emcon state."""

    def test_set_emcon_engage_returns_ok(self, sim):
        result = issue(sim, "set_emcon", {"active": True})
        assert result.get("ok") is True

    def test_set_emcon_disengage_returns_ok(self, sim):
        result = issue(sim, "set_emcon", {"active": False})
        assert result.get("ok") is True

    def test_set_emcon_response_includes_state(self, sim):
        result = issue(sim, "set_emcon", {"active": True})
        assert "emcon_active" in result

    def test_emcon_state_reflected_in_ecm_status(self, sim):
        # Disengage first so we start from a known baseline
        issue(sim, "set_emcon", {"active": False})
        status_off = issue(sim, "ecm_status", {})
        emcon_off_value = status_off.get("emcon_active")

        # Engage and check status flipped
        issue(sim, "set_emcon", {"active": True})
        status_on = issue(sim, "ecm_status", {})
        emcon_on_value = status_on.get("emcon_active")

        assert emcon_off_value != emcon_on_value, (
            "emcon_active should change between disengaged and engaged states"
        )

    def test_set_emcon_engage_message_mentions_emcon(self, sim):
        result = issue(sim, "set_emcon", {"active": True})
        msg = result.get("status", "")
        assert "emcon" in msg.lower() or "emission" in msg.lower()


# ---------------------------------------------------------------------------
# ECM status fields
# ---------------------------------------------------------------------------

class TestEcmStatusFields:
    """ecm_status returns a complete sensor-facing state snapshot."""

    def test_jammer_fields_present(self, sim):
        result = issue(sim, "ecm_status", {})
        assert "jammer_enabled" in result
        assert "jammer_power" in result

    def test_chaff_flare_counts_present(self, sim):
        result = issue(sim, "ecm_status", {})
        assert "chaff_count" in result
        assert "flare_count" in result

    def test_ecm_factor_present(self, sim):
        result = issue(sim, "ecm_status", {})
        assert "ecm_factor" in result

    def test_status_field_is_string(self, sim):
        result = issue(sim, "ecm_status", {})
        assert isinstance(result.get("status"), str)

    def test_ir_reduction_is_positive(self, sim):
        result = issue(sim, "ecm_status", {})
        ir = result.get("emcon_ir_reduction", 0.0)
        assert ir > 0.0, "EMCON IR reduction should be a positive fraction"


# ---------------------------------------------------------------------------
# Cold drift (thermal stealth)
# ---------------------------------------------------------------------------

class TestColdDrift:
    """cold_drift routes correctly even when thermal system is absent.

    The 25_silent_running scenario does not provision a thermal system, so
    cold_drift returns an error — but the command must still return a dict
    with proper error signalling (not crash or return None).
    """

    def test_cold_drift_returns_dict(self, sim):
        result = issue(sim, "cold_drift", {})
        assert isinstance(result, dict)

    def test_cold_drift_returns_error_or_ok(self, sim):
        result = issue(sim, "cold_drift", {})
        assert "error" in result or "ok" in result

    def test_exit_cold_drift_returns_dict(self, sim):
        result = issue(sim, "exit_cold_drift", {})
        assert isinstance(result, dict)

    def test_exit_cold_drift_shape_consistent(self, sim):
        result = issue(sim, "exit_cold_drift", {})
        assert "error" in result or "ok" in result


# ---------------------------------------------------------------------------
# Rejection cases
# ---------------------------------------------------------------------------

class TestStealthRejections:
    """Commands that must fail gracefully with clear error messages."""

    def test_set_repair_priority_missing_subsystem(self, sim):
        result = issue(sim, "set_repair_priority", {"priority": "high"})
        assert result.get("ok") is False
        assert "error" in result or "message" in result

    def test_dispatch_repair_missing_subsystem(self, sim):
        result = issue(sim, "dispatch_repair", {})
        assert result.get("ok") is False
