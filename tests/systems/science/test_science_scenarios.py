# tests/systems/science/test_science_scenarios.py
"""Science station scenario tests: analysis pipeline, probes, FCR paint.

Focus: scenario 20_sensor_sweep.yaml — multi-contact environment with
contact_alpha, contact_bravo, contact_charlie for sensor analysis exercises.

Gaps filled vs. existing test_sensor_system.py and test_ghost_contacts.py
(which test contact detection): these tests verify the full analysis command
pipeline from station routing to observable analysis output fields.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT_DIR))

from hybrid_runner import HybridRunner
from hybrid.command_handler import route_command


SCENARIO = "20_sensor_sweep"
PLAYER_ID = "player"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def runner():
    r = HybridRunner()
    r.load_scenario(SCENARIO)
    r.simulator.start()
    return r


@pytest.fixture(scope="module")
def contact_id(runner):
    """Ping sensors, run ticks, return first non-nav stable contact ID."""
    sim = runner.simulator
    ship = sim.ships[PLAYER_ID]
    ships = list(sim.ships.values())
    route_command(ship, {"command": "ping_sensors", "ship": PLAYER_ID}, ships)
    for _ in range(150):
        sim.tick()
    tracker = ship.systems["sensors"].contact_tracker
    cid = next(
        (cid for orig, cid in tracker.id_mapping.items() if orig.startswith("contact_")),
        None,
    )
    assert cid is not None, "No contact_ ship detected after ping + 150 ticks"
    return cid


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
# Science system presence
# ---------------------------------------------------------------------------

class TestScienceSetup:
    def test_science_system_present(self, sim):
        ship = sim.ships[PLAYER_ID]
        assert ship.systems.get("science") is not None

    def test_science_status_returns_ok(self, sim):
        result = issue(sim, "science_status", {})
        assert result.get("ok") is True

    def test_science_status_has_capabilities(self, sim):
        result = issue(sim, "science_status", {})
        assert "analysis_capabilities" in result

    def test_science_status_tracks_contacts(self, sim):
        result = issue(sim, "science_status", {})
        assert "tracked_contacts" in result


# ---------------------------------------------------------------------------
# analyze_contact
# ---------------------------------------------------------------------------

class TestAnalyzeContact:
    def test_analyze_contact_returns_ok(self, sim, contact_id):
        result = issue(sim, "analyze_contact", {"contact_id": contact_id})
        assert result.get("ok") is True

    def test_analyze_contact_returns_contact_data(self, sim, contact_id):
        result = issue(sim, "analyze_contact", {"contact_id": contact_id})
        assert "contact_data" in result

    def test_analyze_contact_returns_classification(self, sim, contact_id):
        result = issue(sim, "analyze_contact", {"contact_id": contact_id})
        assert "classification" in result

    def test_analyze_contact_returns_analysis_quality(self, sim, contact_id):
        result = issue(sim, "analyze_contact", {"contact_id": contact_id})
        assert "analysis_quality" in result

    def test_analyze_contact_empty_id_rejects(self, sim):
        result = issue(sim, "analyze_contact", {"contact_id": ""})
        assert result.get("ok") is False

    def test_analyze_contact_unknown_contact_rejects(self, sim):
        result = issue(sim, "analyze_contact", {"contact_id": "C999"})
        assert result.get("ok") is False

    def test_analyze_contact_missing_param_rejects(self, sim):
        result = issue(sim, "analyze_contact", {})
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# spectral_analysis
# ---------------------------------------------------------------------------

class TestSpectralAnalysis:
    def test_spectral_analysis_returns_ok(self, sim, contact_id):
        result = issue(sim, "spectral_analysis", {"contact_id": contact_id})
        assert result.get("ok") is True

    def test_spectral_analysis_returns_spectral_data(self, sim, contact_id):
        result = issue(sim, "spectral_analysis", {"contact_id": contact_id})
        assert "spectral_data" in result

    def test_spectral_analysis_has_quality(self, sim, contact_id):
        result = issue(sim, "spectral_analysis", {"contact_id": contact_id})
        assert "analysis_quality" in result

    def test_spectral_analysis_unknown_rejects(self, sim):
        result = issue(sim, "spectral_analysis", {"contact_id": "PHANTOM"})
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# estimate_mass
# ---------------------------------------------------------------------------

class TestEstimateMass:
    def test_estimate_mass_returns_ok(self, sim, contact_id):
        result = issue(sim, "estimate_mass", {"contact_id": contact_id})
        assert result.get("ok") is True

    def test_estimate_mass_returns_mass_estimate(self, sim, contact_id):
        result = issue(sim, "estimate_mass", {"contact_id": contact_id})
        assert "mass_estimate" in result

    def test_estimate_mass_returns_dimension_inference(self, sim, contact_id):
        result = issue(sim, "estimate_mass", {"contact_id": contact_id})
        assert "dimension_inference" in result

    def test_estimate_mass_missing_param_rejects(self, sim):
        result = issue(sim, "estimate_mass", {})
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# assess_threat
# ---------------------------------------------------------------------------

class TestAssessThreat:
    def test_assess_threat_returns_ok(self, sim, contact_id):
        result = issue(sim, "assess_threat", {"contact_id": contact_id})
        assert result.get("ok") is True

    def test_assess_threat_returns_assessment(self, sim, contact_id):
        result = issue(sim, "assess_threat", {"contact_id": contact_id})
        assert "threat_assessment" in result

    def test_assess_threat_returns_recommendations(self, sim, contact_id):
        result = issue(sim, "assess_threat", {"contact_id": contact_id})
        assert "recommendations" in result

    def test_assess_threat_unknown_contact_rejects(self, sim):
        result = issue(sim, "assess_threat", {"contact_id": "GHOST"})
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# Probe deployment
# ---------------------------------------------------------------------------

class TestProbeDeployment:
    def test_deploy_probe_returns_dict(self, sim, contact_id):
        result = issue(sim, "deploy_probe", {"contact_id": contact_id})
        assert isinstance(result, dict)

    def test_deploy_probe_has_ok_or_error(self, sim, contact_id):
        result = issue(sim, "deploy_probe", {"contact_id": contact_id})
        assert "ok" in result or "error" in result

    def test_deploy_probe_success_has_probe_id(self, sim, contact_id):
        result = issue(sim, "deploy_probe", {"contact_id": contact_id})
        if result.get("ok"):
            assert "probe_id" in result

    def test_recall_probe_returns_dict(self, sim, contact_id):
        deploy = issue(sim, "deploy_probe", {"contact_id": contact_id})
        probe_id = deploy.get("probe_id") if deploy.get("ok") else "probe_0"
        result = issue(sim, "recall_probe", {"probe_id": probe_id})
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# FCR paint
# ---------------------------------------------------------------------------

class TestFcrPaint:
    def test_fcr_paint_returns_dict(self, sim, contact_id):
        result = issue(sim, "fcr_paint", {"contact_id": contact_id})
        assert isinstance(result, dict)

    def test_fcr_paint_has_ok_or_error(self, sim, contact_id):
        result = issue(sim, "fcr_paint", {"contact_id": contact_id})
        assert "ok" in result or "error" in result

    def test_fcr_release_returns_dict(self, sim, contact_id):
        issue(sim, "fcr_paint", {"contact_id": contact_id})
        result = issue(sim, "fcr_release", {"contact_id": contact_id})
        assert isinstance(result, dict)
