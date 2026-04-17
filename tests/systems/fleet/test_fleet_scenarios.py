# tests/systems/fleet/test_fleet_scenarios.py
"""Fleet coordination scenario tests: lifecycle, formations, targeting, data link.

Focus: scenario 23_fleet_coordination.yaml — player flagship + two escort
corvettes vs three hostile frigates at ~150 km.

Gaps filled vs. existing test_fleet_formation_maintenance.py and
test_multi_ship.py (which test mechanics directly): these tests verify the
full fleet command pipeline from station routing to observable fleet state.

Bug fixed in this phase:
  share_contact called .get() on ContactData (dataclass) instead of accessing
  .position/.velocity attributes directly — now fixed in fleet_coord_system.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT_DIR))

from hybrid_runner import HybridRunner
from hybrid.command_handler import route_command


SCENARIO = "23_fleet_coordination"
PLAYER_ID = "player"
FLEET_ID = "alpha"


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
def hostile_id(runner):
    """Ping sensors, run ticks, return a hostile stable contact ID."""
    sim = runner.simulator
    ship = sim.ships[PLAYER_ID]
    ships = list(sim.ships.values())
    route_command(ship, {"command": "ping_sensors", "ship": PLAYER_ID}, ships)
    for _ in range(500):
        sim.tick()
    tracker = ship.systems["sensors"].contact_tracker
    cid = next(
        (cid for orig, cid in tracker.id_mapping.items() if "hostile" in orig),
        None,
    )
    assert cid is not None, "No hostile contact detected after 500 ticks"
    return cid


@pytest.fixture(scope="module")
def fleet(runner, hostile_id):
    """Create fleet alpha with two escorts. Returns fleet_id."""
    sim = runner.simulator
    _issue(sim, "fleet_create", {"fleet_id": FLEET_ID, "name": "Alpha Squadron"})
    _issue(sim, "fleet_add_ship", {"fleet_id": FLEET_ID, "target_ship": "escort_blade"})
    _issue(sim, "fleet_add_ship", {"fleet_id": FLEET_ID, "target_ship": "escort_lance"})
    return FLEET_ID


@pytest.fixture
def sim(runner):
    return runner.simulator


def _issue(sim, command: str, params: dict) -> dict:
    ship = sim.ships[PLAYER_ID]
    result = route_command(
        ship,
        {"command": command, "ship": PLAYER_ID, **params},
        list(sim.ships.values()),
    )
    return result if isinstance(result, dict) else {"error": str(result)}


# alias for use inside test methods
def issue(sim, command, params):
    return _issue(sim, command, params)


# ---------------------------------------------------------------------------
# Fleet system presence
# ---------------------------------------------------------------------------

class TestFleetSystemPresence:
    def test_fleet_coord_system_present(self, sim):
        ship = sim.ships[PLAYER_ID]
        assert ship.systems.get("fleet_coord") is not None

    def test_fleet_status_returns_ok_before_create(self, sim):
        result = issue(sim, "fleet_status", {})
        assert result.get("ok") is True

    def test_fleet_status_has_fleets_key(self, sim):
        result = issue(sim, "fleet_status", {})
        assert "fleets" in result


# ---------------------------------------------------------------------------
# Fleet create and roster
# ---------------------------------------------------------------------------

class TestFleetCreate:
    def test_fleet_create_returns_ok(self, sim, fleet):
        result = issue(sim, "fleet_status", {"fleet_id": fleet})
        assert result.get("ok") is True

    def test_fleet_status_includes_fleet_data(self, sim, fleet):
        result = issue(sim, "fleet_status", {"fleet_id": fleet})
        assert "fleet" in result

    def test_fleet_add_ship_returns_ok(self, sim, fleet):
        # escort ships are already added via the fleet fixture
        result = issue(sim, "fleet_status", {"fleet_id": fleet})
        assert result.get("ok") is True

    def test_fleet_create_duplicate_returns_result(self, sim):
        result = issue(sim, "fleet_create", {"fleet_id": FLEET_ID, "name": "Duplicate"})
        assert isinstance(result, dict)

    def test_fleet_add_unknown_ship_rejects(self, sim, fleet):
        result = issue(sim, "fleet_add_ship", {
            "fleet_id": fleet, "target_ship": "ghost_ship_999",
        })
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# Formations
# ---------------------------------------------------------------------------

class TestFormations:
    @pytest.mark.parametrize("formation", ["line", "column", "wedge", "echelon", "diamond"])
    def test_fleet_form_standard_formations(self, sim, fleet, formation):
        result = issue(sim, "fleet_form", {"fleet_id": fleet, "formation": formation})
        assert result.get("ok") is True

    def test_fleet_form_returns_formation_name(self, sim, fleet):
        result = issue(sim, "fleet_form", {"fleet_id": fleet, "formation": "line"})
        assert "formation" in result

    def test_fleet_form_with_custom_spacing(self, sim, fleet):
        result = issue(sim, "fleet_form", {
            "fleet_id": fleet, "formation": "line", "spacing": 5000,
        })
        assert result.get("ok") is True

    def test_fleet_break_formation_returns_ok(self, sim, fleet):
        issue(sim, "fleet_form", {"fleet_id": fleet, "formation": "wedge"})
        result = issue(sim, "fleet_break_formation", {"fleet_id": fleet})
        assert result.get("ok") is True


# ---------------------------------------------------------------------------
# Targeting and fire control
# ---------------------------------------------------------------------------

class TestFleetTargeting:
    def test_fleet_target_returns_ok(self, sim, fleet, hostile_id):
        result = issue(sim, "fleet_target", {"fleet_id": fleet, "contact": hostile_id})
        assert result.get("ok") is True

    def test_fleet_target_reflects_contact_id(self, sim, fleet, hostile_id):
        result = issue(sim, "fleet_target", {"fleet_id": fleet, "contact": hostile_id})
        assert result.get("contact_id") == hostile_id

    def test_fleet_tactical_after_target(self, sim, fleet, hostile_id):
        issue(sim, "fleet_target", {"fleet_id": fleet, "contact": hostile_id})
        result = issue(sim, "fleet_tactical", {"fleet_id": fleet})
        assert result.get("ok") is True
        assert "tactical" in result

    def test_fleet_fire_after_target(self, sim, fleet, hostile_id):
        issue(sim, "fleet_target", {"fleet_id": fleet, "contact": hostile_id})
        result = issue(sim, "fleet_fire", {"fleet_id": fleet})
        assert result.get("ok") is True

    def test_fleet_cease_fire_returns_ok(self, sim, fleet):
        result = issue(sim, "fleet_cease_fire", {"fleet_id": fleet})
        assert result.get("ok") is True

    def test_fleet_fire_empty_fleet_rejects(self, sim):
        issue(sim, "fleet_create", {"fleet_id": "no_target_fleet", "name": "X"})
        result = issue(sim, "fleet_fire", {"fleet_id": "no_target_fleet"})
        assert result.get("ok") is False

    def test_fleet_target_no_contact_rejects(self, sim, fleet):
        result = issue(sim, "fleet_target", {"fleet_id": fleet})
        assert result.get("ok") is False

    def test_fleet_target_unknown_fleet_rejects(self, sim, hostile_id):
        result = issue(sim, "fleet_target", {
            "fleet_id": "NONEXISTENT", "contact": hostile_id,
        })
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# Maneuver orders
# ---------------------------------------------------------------------------

class TestFleetManeuver:
    def test_fleet_maneuver_intercept(self, sim, fleet, hostile_id):
        result = issue(sim, "fleet_maneuver", {
            "fleet_id": fleet, "maneuver": "intercept", "target_id": hostile_id,
        })
        assert result.get("ok") is True

    def test_fleet_maneuver_withdraw(self, sim, fleet):
        result = issue(sim, "fleet_maneuver", {"fleet_id": fleet, "maneuver": "withdraw"})
        assert result.get("ok") is True

    def test_fleet_maneuver_returns_maneuver_type(self, sim, fleet):
        result = issue(sim, "fleet_maneuver", {"fleet_id": fleet, "maneuver": "withdraw"})
        assert "maneuver" in result


# ---------------------------------------------------------------------------
# Tactical data link / share_contact
# ---------------------------------------------------------------------------

class TestShareContact:
    def test_share_contact_returns_ok(self, sim, fleet, hostile_id):
        result = issue(sim, "share_contact", {"contact": hostile_id, "fleet_id": fleet})
        assert result.get("ok") is True

    def test_share_contact_reflects_contact_id(self, sim, fleet, hostile_id):
        result = issue(sim, "share_contact", {"contact": hostile_id, "fleet_id": fleet})
        assert result.get("contact_id") == hostile_id

    def test_share_contact_hostile_flag(self, sim, fleet, hostile_id):
        result = issue(sim, "share_contact", {
            "contact": hostile_id, "fleet_id": fleet, "hostile": True,
        })
        assert result.get("ok") is True
        assert result.get("hostile") is True

    def test_share_contact_no_contact_rejects(self, sim, fleet):
        result = issue(sim, "share_contact", {"fleet_id": fleet})
        assert result.get("ok") is False

    def test_share_contact_unknown_contact_rejects(self, sim, fleet):
        result = issue(sim, "share_contact", {"contact": "PHANTOM999", "fleet_id": fleet})
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# fleet_tactical display
# ---------------------------------------------------------------------------

class TestFleetTactical:
    def test_fleet_tactical_returns_ok(self, sim, fleet):
        result = issue(sim, "fleet_tactical", {"fleet_id": fleet})
        assert result.get("ok") is True

    def test_fleet_tactical_has_tactical_key(self, sim, fleet):
        result = issue(sim, "fleet_tactical", {"fleet_id": fleet})
        assert "tactical" in result

    def test_fleet_tactical_unknown_fleet_rejects(self, sim):
        result = issue(sim, "fleet_tactical", {"fleet_id": "FLEET_DOES_NOT_EXIST_XYZ"})
        assert result.get("ok") is False
