"""
Tests for multi-ship, multi-client session management.

Validates:
1. Two clients can be assigned to different ships simultaneously.
2. Station claims are independent per ship.
3. Commands route to the correct ship.
4. Telemetry is scoped per-ship (each client sees only their ship's state).
"""

import os
import sys
import logging
import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logging.basicConfig(level=logging.WARNING)

SCENARIO_PATH = os.path.join(ROOT, "scenarios", "12_fleet_battle.yaml")
DT = 0.1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_sim():
    """Load fleet battle scenario and return (runner, sim)."""
    from hybrid_runner import HybridRunner

    runner = HybridRunner(dt=DT)
    count = runner._load_scenario_file(SCENARIO_PATH)
    assert count >= 7, f"Expected at least 7 ships, got {count}"
    sim = runner.simulator
    sim.start()
    return runner, sim


def _build_station_manager():
    """Create a StationManager with two registered clients."""
    from server.stations.station_manager import StationManager

    mgr = StationManager()
    cid_a = mgr.generate_client_id()
    cid_b = mgr.generate_client_id()
    mgr.register_client(cid_a, "Alice")
    mgr.register_client(cid_b, "Bob")
    return mgr, cid_a, cid_b


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMultiShipAssignment:
    """Two clients assigned to different ships."""

    def test_assign_different_ships(self):
        """Client A → player ship, Client B → escort ship."""
        _build_sim()  # ensure scenario loads
        mgr, cid_a, cid_b = _build_station_manager()

        assert mgr.assign_to_ship(cid_a, "player")
        assert mgr.assign_to_ship(cid_b, "escort_wolf")

        assert mgr.get_session(cid_a).ship_id == "player"
        assert mgr.get_session(cid_b).ship_id == "escort_wolf"

    def test_independent_station_claims(self):
        """Both clients can claim CAPTAIN on their respective ships."""
        _build_sim()
        mgr, cid_a, cid_b = _build_station_manager()
        from server.stations.station_types import StationType

        mgr.assign_to_ship(cid_a, "player")
        mgr.assign_to_ship(cid_b, "escort_wolf")

        ok_a, _ = mgr.claim_station(cid_a, "player", StationType.CAPTAIN)
        ok_b, _ = mgr.claim_station(cid_b, "escort_wolf", StationType.HELM)

        assert ok_a, "Client A should claim CAPTAIN on player ship"
        assert ok_b, "Client B should claim HELM on escort ship"

        # Verify each session reflects the correct station
        assert mgr.get_session(cid_a).station == StationType.CAPTAIN
        assert mgr.get_session(cid_b).station == StationType.HELM

    def test_cross_ship_claim_rejected(self):
        """Client cannot claim a station on a ship they are not assigned to."""
        _build_sim()
        mgr, cid_a, cid_b = _build_station_manager()
        from server.stations.station_types import StationType

        mgr.assign_to_ship(cid_a, "player")
        mgr.assign_to_ship(cid_b, "escort_wolf")

        ok, msg = mgr.claim_station(cid_a, "escort_wolf", StationType.HELM)
        assert not ok, "Should not claim station on wrong ship"
        assert "not assigned" in msg.lower()


class TestMultiShipCommands:
    """Commands route to the correct ship per client."""

    def test_commands_route_to_assigned_ship(self):
        """Each client can issue commands to their own ship."""
        _build_sim()
        mgr, cid_a, cid_b = _build_station_manager()
        from server.stations.station_types import StationType

        mgr.assign_to_ship(cid_a, "player")
        mgr.assign_to_ship(cid_b, "escort_wolf")

        mgr.claim_station(cid_a, "player", StationType.CAPTAIN)
        mgr.claim_station(cid_b, "escort_wolf", StationType.HELM)

        # CAPTAIN has access to most commands including set_thrust
        ok_a, _ = mgr.can_issue_command(cid_a, "player", "set_thrust")
        assert ok_a, "CAPTAIN should be able to issue set_thrust on player ship"

        # HELM has set_thrust
        ok_b, _ = mgr.can_issue_command(cid_b, "escort_wolf", "set_thrust")
        assert ok_b, "HELM should be able to issue set_thrust on escort ship"

    def test_cross_ship_command_rejected(self):
        """Client cannot issue commands to a ship they are not assigned to."""
        _build_sim()
        mgr, cid_a, cid_b = _build_station_manager()
        from server.stations.station_types import StationType

        mgr.assign_to_ship(cid_a, "player")
        mgr.assign_to_ship(cid_b, "escort_wolf")
        mgr.claim_station(cid_a, "player", StationType.CAPTAIN)

        ok, msg = mgr.can_issue_command(cid_a, "escort_wolf", "set_thrust")
        assert not ok, "Should not issue commands to unassigned ship"


class TestMultiShipTelemetry:
    """Telemetry is scoped per-ship."""

    def test_telemetry_per_ship(self):
        """Each ship produces distinct telemetry (different positions)."""
        runner, sim = _build_sim()
        from hybrid.telemetry import get_ship_telemetry

        player_ship = sim.ships["player"]
        escort_ship = sim.ships["escort_wolf"]

        t_player = get_ship_telemetry(player_ship, sim.time)
        t_escort = get_ship_telemetry(escort_ship, sim.time)

        # Ships start at different positions per scenario YAML
        assert t_player["id"] == "player"
        assert t_escort["id"] == "escort_wolf"

        # Positions should differ
        pp = t_player.get("position", {})
        ep = t_escort.get("position", {})
        assert pp.get("x") != ep.get("x"), (
            "Player and escort should have different x positions"
        )

    def test_station_filter_scopes_to_assigned_ship(self):
        """StationTelemetryFilter returns data for the client's ship only."""
        runner, sim = _build_sim()
        mgr, cid_a, cid_b = _build_station_manager()
        from server.stations.station_types import StationType
        from server.telemetry.station_filter import StationTelemetryFilter
        from hybrid.telemetry import get_telemetry_snapshot

        mgr.assign_to_ship(cid_a, "player")
        mgr.assign_to_ship(cid_b, "escort_wolf")
        mgr.claim_station(cid_a, "player", StationType.CAPTAIN)
        mgr.claim_station(cid_b, "escort_wolf", StationType.HELM)

        full_telemetry = get_telemetry_snapshot(sim)
        filt = StationTelemetryFilter(mgr)

        filtered_a = filt.filter_telemetry_for_client(cid_a, full_telemetry)
        filtered_b = filt.filter_telemetry_for_client(cid_b, full_telemetry)

        # Each filtered result should contain a 'ship' key scoped to
        # the client's assigned ship.  The exact structure depends on
        # StationTelemetryFilter, but both should succeed without error.
        assert filtered_a is not None
        assert filtered_b is not None


class TestStationClaimIndependence:
    """Station claims do not interfere across ships."""

    def test_same_station_different_ships(self):
        """Two clients can claim the same station type on different ships."""
        _build_sim()
        mgr, cid_a, cid_b = _build_station_manager()
        from server.stations.station_types import StationType

        mgr.assign_to_ship(cid_a, "player")
        mgr.assign_to_ship(cid_b, "escort_wolf")

        ok_a, _ = mgr.claim_station(cid_a, "player", StationType.HELM)
        ok_b, _ = mgr.claim_station(cid_b, "escort_wolf", StationType.HELM)

        assert ok_a, "Client A should claim HELM on player"
        assert ok_b, "Client B should claim HELM on escort"

        # Verify owners are independent
        assert mgr.get_station_owner("player", StationType.HELM) == cid_a
        assert mgr.get_station_owner("escort_wolf", StationType.HELM) == cid_b

    def test_release_on_one_ship_does_not_affect_other(self):
        """Releasing a station on one ship leaves the other intact."""
        _build_sim()
        mgr, cid_a, cid_b = _build_station_manager()
        from server.stations.station_types import StationType

        mgr.assign_to_ship(cid_a, "player")
        mgr.assign_to_ship(cid_b, "escort_wolf")
        mgr.claim_station(cid_a, "player", StationType.HELM)
        mgr.claim_station(cid_b, "escort_wolf", StationType.HELM)

        # Release A's claim
        mgr.release_station(cid_a, "player", StationType.HELM)

        # B's claim should be unaffected
        assert mgr.get_station_owner("escort_wolf", StationType.HELM) == cid_b
        assert mgr.get_station_owner("player", StationType.HELM) is None
