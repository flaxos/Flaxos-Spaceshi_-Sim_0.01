# tests/systems/comms/test_comms_scenarios.py
"""Comms station scenario tests: hail, broadcast, transponder, branch choices.

Focus: scenario 21_diplomatic_incident.yaml — corvette must identify a spoofed
freighter via comms/sensors without firing on a neutral patrol.

Gaps filled vs. unit tests: verifies end-to-end command routing from comms
station through the CommsSystem, including the hail_contact/broadcast_message
response shape after the success_dict 'message' kwarg collision was fixed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT_DIR))

from hybrid_runner import HybridRunner
from hybrid.command_handler import route_command


SCENARIO = "21_diplomatic_incident"
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
    """Ping sensors, run ticks, return stable ID for suspect_freighter."""
    sim = runner.simulator
    ship = sim.ships[PLAYER_ID]
    ships = list(sim.ships.values())
    route_command(ship, {"command": "ping_sensors", "ship": PLAYER_ID}, ships)
    for _ in range(150):
        sim.tick()
    tracker = ship.systems["sensors"].contact_tracker
    cid = tracker.id_mapping.get("suspect_freighter") or next(
        (cid for orig, cid in tracker.id_mapping.items() if not orig.startswith("nav_")),
        None,
    )
    assert cid is not None, "No non-nav contact detected after ping + 150 ticks"
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
# Comms system presence
# ---------------------------------------------------------------------------

class TestCommsSetup:
    def test_comms_system_present(self, sim):
        ship = sim.ships[PLAYER_ID]
        assert ship.systems.get("comms") is not None

    def test_comms_status_returns_ok(self, sim):
        result = issue(sim, "comms_status", {})
        assert result.get("ok") is True

    def test_comms_status_transponder_fields(self, sim):
        result = issue(sim, "comms_status", {})
        assert "transponder_enabled" in result
        assert "transponder_code" in result

    def test_comms_status_distress_field(self, sim):
        result = issue(sim, "comms_status", {})
        assert "distress_active" in result

    def test_comms_status_radio_range(self, sim):
        result = issue(sim, "comms_status", {})
        assert "radio_range" in result
        assert result["radio_range"] > 0

    def test_comms_status_message_count(self, sim):
        result = issue(sim, "comms_status", {})
        assert "message_count" in result


# ---------------------------------------------------------------------------
# hail_contact
# ---------------------------------------------------------------------------

class TestHailContact:
    def test_hail_contact_returns_ok(self, sim, contact_id):
        result = issue(sim, "hail_contact", {"target": contact_id})
        assert result.get("ok") is True

    def test_hail_contact_includes_target(self, sim, contact_id):
        result = issue(sim, "hail_contact", {"target": contact_id})
        assert result.get("target") == contact_id

    def test_hail_contact_has_hail_message(self, sim, contact_id):
        result = issue(sim, "hail_contact", {"target": contact_id})
        assert "hail_message" in result

    def test_hail_contact_has_delay_seconds(self, sim, contact_id):
        result = issue(sim, "hail_contact", {"target": contact_id})
        assert "delay_seconds" in result
        assert result["delay_seconds"] >= 0.0

    def test_hail_contact_custom_message(self, sim, contact_id):
        result = issue(sim, "hail_contact", {
            "target": contact_id,
            "message": "Identify yourself and state your cargo",
        })
        assert result.get("ok") is True

    def test_hail_contact_no_target_rejects(self, sim):
        result = issue(sim, "hail_contact", {})
        assert result.get("ok") is False
        assert "error" in result or "message" in result


# ---------------------------------------------------------------------------
# broadcast_message — regression test for success_dict kwarg collision
# ---------------------------------------------------------------------------

class TestBroadcastMessage:
    def test_broadcast_message_returns_ok(self, sim):
        result = issue(sim, "broadcast_message", {"message": "All ships stand by"})
        assert result.get("ok") is True

    def test_broadcast_message_has_channel(self, sim):
        result = issue(sim, "broadcast_message", {"message": "Identify"})
        assert "channel" in result

    def test_broadcast_message_has_broadcast_message_field(self, sim):
        """broadcast_message key holds the text sent (not 'message' to avoid kwarg collision)."""
        result = issue(sim, "broadcast_message", {"message": "Test broadcast"})
        assert "broadcast_message" in result

    def test_broadcast_message_custom_channel(self, sim):
        result = issue(sim, "broadcast_message", {
            "message": "Hailing on channel 16",
            "channel": "16",
        })
        assert result.get("ok") is True

    def test_broadcast_message_missing_message_rejects(self, sim):
        result = issue(sim, "broadcast_message", {})
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# Transponder
# ---------------------------------------------------------------------------

class TestTransponder:
    def test_set_transponder_active(self, sim):
        result = issue(sim, "set_transponder", {"mode": "active"})
        assert result.get("ok") is True

    def test_set_transponder_returns_state(self, sim):
        result = issue(sim, "set_transponder", {"mode": "active"})
        assert "transponder_enabled" in result
        assert "transponder_code" in result

    def test_set_transponder_emcon_suppressed_field(self, sim):
        result = issue(sim, "set_transponder", {"mode": "active"})
        assert "emcon_suppressed" in result

    def test_set_transponder_is_spoofed_field(self, sim):
        result = issue(sim, "set_transponder", {"mode": "active"})
        assert "is_spoofed" in result


# ---------------------------------------------------------------------------
# Distress beacon
# ---------------------------------------------------------------------------

class TestDistressBeacon:
    def test_set_distress_on_returns_ok(self, sim):
        result = issue(sim, "set_distress", {"active": True})
        assert result.get("ok") is True

    def test_set_distress_off_returns_ok(self, sim):
        result = issue(sim, "set_distress", {"active": False})
        assert result.get("ok") is True

    def test_set_distress_reflects_state(self, sim):
        issue(sim, "set_distress", {"active": True})
        result = issue(sim, "comms_status", {})
        assert result.get("distress_active") is True
        issue(sim, "set_distress", {"active": False})

    def test_set_distress_returns_beacon_field(self, sim):
        result = issue(sim, "set_distress", {"active": False})
        assert "distress_beacon_enabled" in result


# ---------------------------------------------------------------------------
# Branch choices (diplomatic interaction)
# ---------------------------------------------------------------------------

class TestBranchComms:
    def test_get_comms_choices_returns_ok(self, sim):
        result = issue(sim, "get_comms_choices", {})
        assert result.get("ok") is True

    def test_get_comms_choices_has_choices_list(self, sim):
        result = issue(sim, "get_comms_choices", {})
        assert "choices" in result
        assert isinstance(result["choices"], list)

    def test_get_branch_status_returns_ok(self, sim):
        result = issue(sim, "get_branch_status", {})
        assert result.get("ok") is True

    def test_get_branch_status_has_active_branches(self, sim):
        result = issue(sim, "get_branch_status", {})
        assert "active_branches" in result

    def test_get_branch_status_has_history(self, sim):
        result = issue(sim, "get_branch_status", {})
        assert "branch_history" in result

    def test_comms_respond_unknown_choice_rejects(self, sim):
        result = issue(sim, "comms_respond", {"choice_id": "nonexistent"})
        assert result.get("ok") is False
        assert "error" in result or "message" in result
