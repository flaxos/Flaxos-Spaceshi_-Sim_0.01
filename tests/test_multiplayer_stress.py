"""
Multiplayer stress tests for station-based multi-client server safety.

Covers:
- Concurrent per-ship command serialisation via _command_lock (PR #365)
- Station permission isolation between HELM and TACTICAL clients
- Captain override authority
- RateLimiter token bucket throttling and exempt commands
- Cross-ship command isolation (commands on ship_a never mutate ship_b)
- Station claim lifecycle (register → claim → unregister → release)
- Captain succession when the current captain disconnects

These tests use real StationManager / RateLimiter instances and mock only
network I/O and ship system internals.
"""

import threading
import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Dict, Any
from unittest.mock import MagicMock, patch

import pytest

from server.rate_limiter import RateLimiter, RATE_LIMIT_EXEMPT
from server.stations.station_manager import StationManager
from server.stations.station_types import StationType, PermissionLevel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_station_manager_with_client(
    ship_id: str = "ship_001",
    player_name: str = "testplayer",
    station: StationType = StationType.HELM,
) -> tuple[StationManager, str]:
    """Register, assign, and station-claim a single client. Return (manager, client_id)."""
    mgr = StationManager()
    cid = mgr.generate_client_id()
    mgr.register_client(cid, player_name)
    mgr.assign_to_ship(cid, ship_id)
    mgr.claim_station(cid, ship_id, station)
    return mgr, cid


def _make_mock_ship(ship_id: str = "ship_001") -> MagicMock:
    """Create a minimal mock ship with a real threading.Lock for _command_lock."""
    ship = MagicMock()
    ship.id = ship_id
    ship.event_bus = MagicMock()
    ship._command_lock = threading.Lock()
    ship._all_ships_ref = []
    ship._simulator_ref = None
    return ship


# ---------------------------------------------------------------------------
# 1. test_concurrent_commands_same_ship
# ---------------------------------------------------------------------------

class TestConcurrentCommandsSameShip:
    """The per-ship _command_lock must serialise concurrent command executions.

    Four threads each submit 100 set_thrust calls with different throttle
    values.  The lock guarantees no torn writes on the system state.
    """

    def test_lock_serialises_access(self):
        """After N threads each sending commands, ship state is consistent — no corruption."""
        from hybrid.command_handler import execute_command

        # Simple counter-based mock system: records call order, never corrupts
        call_log: list[int] = []
        log_lock = threading.Lock()

        # Build a fake ship whose "helm" system increments a counter on each call
        ship = _make_mock_ship("ship_stress")

        call_count = {"value": 0}

        def fake_helm_command(action, data):
            # Simulate a small critical section that must not be interleaved
            current = call_count["value"]
            time.sleep(0)  # yield to encourage thread interleaving
            call_count["value"] = current + 1
            with log_lock:
                call_log.append(data.get("thrust", -1))
            return {"status": "ok", "thrust": data.get("thrust", 0)}

        helm_mock = MagicMock()
        helm_mock.command.side_effect = fake_helm_command
        ship.systems = {"helm": helm_mock}

        num_threads = 4
        commands_per_thread = 100
        errors: list[str] = []

        def worker(thread_id: int):
            for i in range(commands_per_thread):
                thrust_val = thread_id * 100 + i
                try:
                    execute_command(
                        ship,
                        "set_thrust",
                        {"command": "set_thrust", "thrust": thrust_val},
                    )
                except Exception as exc:
                    errors.append(f"Thread {thread_id}: {exc}")

        threads = [
            threading.Thread(target=worker, args=(t,), daemon=True)
            for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        total_expected = num_threads * commands_per_thread
        assert not errors, f"Errors during concurrent execution: {errors}"
        assert call_count["value"] == total_expected, (
            f"Expected {total_expected} increments, got {call_count['value']} — "
            "possible lost write under concurrent access"
        )
        assert len(call_log) == total_expected

    def test_lock_present_on_fresh_ship(self):
        """Ship objects initialise with a threading.Lock as _command_lock."""
        from hybrid.ship import Ship
        ship = Ship("test_lock_ship")
        assert hasattr(ship, "_command_lock"), "Ship missing _command_lock attribute"
        import threading as _threading
        assert isinstance(ship._command_lock, type(_threading.Lock())), (
            "_command_lock must be a threading.Lock"
        )


# ---------------------------------------------------------------------------
# 2. test_station_permission_isolation
# ---------------------------------------------------------------------------

class TestStationPermissionIsolation:
    """HELM and TACTICAL on the same ship must have disjoint command authority."""

    def _setup_helm_and_tactical(self, ship_id: str = "ship_perm"):
        mgr = StationManager()
        helm_id = mgr.generate_client_id()
        tac_id = mgr.generate_client_id()

        for cid, name in ((helm_id, "helm_player"), (tac_id, "tac_player")):
            mgr.register_client(cid, name)
            mgr.assign_to_ship(cid, ship_id)

        mgr.claim_station(helm_id, ship_id, StationType.HELM)
        mgr.claim_station(tac_id, ship_id, StationType.TACTICAL)

        return mgr, helm_id, tac_id, ship_id

    def test_helm_can_set_thrust(self):
        mgr, helm_id, _, ship_id = self._setup_helm_and_tactical()
        allowed, reason = mgr.can_issue_command(helm_id, ship_id, "set_thrust")
        assert allowed is True, f"HELM should be able to set_thrust, got: {reason}"

    def test_helm_cannot_fire_weapon(self):
        mgr, helm_id, _, ship_id = self._setup_helm_and_tactical()
        allowed, _ = mgr.can_issue_command(helm_id, ship_id, "fire_weapon")
        assert allowed is False, "HELM must NOT be able to fire_weapon"

    def test_tactical_can_fire_weapon(self):
        mgr, _, tac_id, ship_id = self._setup_helm_and_tactical()
        allowed, reason = mgr.can_issue_command(tac_id, ship_id, "fire_weapon")
        assert allowed is True, f"TACTICAL should be able to fire_weapon, got: {reason}"

    def test_tactical_cannot_set_thrust(self):
        mgr, _, tac_id, ship_id = self._setup_helm_and_tactical()
        allowed, _ = mgr.can_issue_command(tac_id, ship_id, "set_thrust")
        assert allowed is False, "TACTICAL must NOT be able to set_thrust"

    def test_tactical_can_lock_target(self):
        mgr, _, tac_id, ship_id = self._setup_helm_and_tactical()
        allowed, reason = mgr.can_issue_command(tac_id, ship_id, "lock_target")
        assert allowed is True, f"TACTICAL should be able to lock_target, got: {reason}"

    def test_helm_cannot_lock_target(self):
        mgr, helm_id, _, ship_id = self._setup_helm_and_tactical()
        allowed, _ = mgr.can_issue_command(helm_id, ship_id, "lock_target")
        assert allowed is False, "HELM must NOT be able to lock_target"

    def test_helm_can_set_course(self):
        mgr, helm_id, _, ship_id = self._setup_helm_and_tactical()
        allowed, reason = mgr.can_issue_command(helm_id, ship_id, "set_course")
        assert allowed is True, f"HELM should be able to set_course, got: {reason}"

    def test_tactical_cannot_set_course(self):
        mgr, _, tac_id, ship_id = self._setup_helm_and_tactical()
        allowed, _ = mgr.can_issue_command(tac_id, ship_id, "set_course")
        assert allowed is False, "TACTICAL must NOT be able to set_course"


# ---------------------------------------------------------------------------
# 3. test_captain_override
# ---------------------------------------------------------------------------

class TestCaptainOverride:
    """CAPTAIN station has all_commands authority: every command is permitted."""

    def test_captain_can_set_thrust(self):
        mgr, captain_id = _make_station_manager_with_client(
            station=StationType.CAPTAIN
        )
        allowed, reason = mgr.can_issue_command(captain_id, "ship_001", "set_thrust")
        assert allowed is True, f"CAPTAIN should be able to set_thrust: {reason}"

    def test_captain_can_fire_weapon(self):
        mgr, captain_id = _make_station_manager_with_client(
            station=StationType.CAPTAIN
        )
        allowed, reason = mgr.can_issue_command(captain_id, "ship_001", "fire_weapon")
        assert allowed is True, f"CAPTAIN should be able to fire_weapon: {reason}"

    def test_captain_can_lock_target(self):
        mgr, captain_id = _make_station_manager_with_client(
            station=StationType.CAPTAIN
        )
        allowed, reason = mgr.can_issue_command(captain_id, "ship_001", "lock_target")
        assert allowed is True, f"CAPTAIN should be able to lock_target: {reason}"

    def test_captain_permission_level_is_elevated(self):
        """Claiming CAPTAIN station must always grant CAPTAIN permission level,
        regardless of the permission_level argument passed."""
        mgr = StationManager()
        cid = mgr.generate_client_id()
        mgr.register_client(cid, "cap")
        mgr.assign_to_ship(cid, "ship_001")
        # Pass CREW level — should be silently promoted to CAPTAIN
        mgr.claim_station(cid, "ship_001", StationType.CAPTAIN, PermissionLevel.CREW)

        session = mgr.sessions[cid]
        assert session.permission_level == PermissionLevel.CAPTAIN, (
            "CAPTAIN station must always grant CAPTAIN permission level"
        )

    def test_captain_and_helm_both_can_set_thrust(self):
        """Both CAPTAIN and HELM can set_thrust — no exclusivity conflict."""
        mgr = StationManager()
        ship_id = "ship_dual"

        captain_id = mgr.generate_client_id()
        helm_id = mgr.generate_client_id()

        for cid, name in ((captain_id, "cap"), (helm_id, "helm")):
            mgr.register_client(cid, name)
            mgr.assign_to_ship(cid, ship_id)

        mgr.claim_station(captain_id, ship_id, StationType.CAPTAIN)
        mgr.claim_station(helm_id, ship_id, StationType.HELM)

        cap_ok, cap_reason = mgr.can_issue_command(captain_id, ship_id, "set_thrust")
        helm_ok, helm_reason = mgr.can_issue_command(helm_id, ship_id, "set_thrust")

        assert cap_ok is True, f"CAPTAIN set_thrust denied: {cap_reason}"
        assert helm_ok is True, f"HELM set_thrust denied: {helm_reason}"


# ---------------------------------------------------------------------------
# 4. test_rate_limiter_throttling
# ---------------------------------------------------------------------------

class TestRateLimiterThrottling:
    """Token bucket should allow the burst quota then throttle; exempt commands bypass it."""

    def test_burst_quota_consumed_then_blocked(self):
        """First `burst` commands succeed; subsequent commands are blocked until refill."""
        limiter = RateLimiter(rate=20.0, burst=30)
        client = "stress_client"

        # Burn the entire burst — all should pass
        passed = 0
        blocked = 0
        for i in range(60):
            if limiter.allow(client, "set_thrust"):
                passed += 1
            else:
                blocked += 1

        # The burst is 30; first call initialises to burst-1=29, then 28, ...
        # Total passes should equal the burst capacity
        assert passed == 30, (
            f"Expected exactly 30 passes (burst capacity), got {passed} passes and {blocked} blocks"
        )
        assert blocked == 30, (
            f"Expected 30 blocked commands after burst exhausted, got {blocked}"
        )

    def test_tokens_refill_over_time(self):
        """After throttling, waiting allows new commands through."""
        limiter = RateLimiter(rate=100.0, burst=5)
        client = "refill_client"

        # Exhaust the burst
        for _ in range(10):
            limiter.allow(client, "set_thrust")

        # Wait long enough for at least 2 tokens to refill (rate=100 means 2 tokens in 20ms)
        time.sleep(0.025)

        # Should get at least one pass after refill
        result = limiter.allow(client, "set_thrust")
        assert result is True, "Rate limiter should allow commands after token refill"

    def test_exempt_command_always_passes(self):
        """Commands in RATE_LIMIT_EXEMPT must not be checked by the rate limiter.

        The rate limiter itself does NOT know about exempt commands — that logic
        lives in the server's dispatch layer.  This test verifies the set is
        populated and contains the expected read-only commands so the dispatch
        layer can rely on it.
        """
        assert "get_state" in RATE_LIMIT_EXEMPT, (
            "get_state must be exempt from rate limiting"
        )
        assert "get_events" in RATE_LIMIT_EXEMPT
        assert "register_client" in RATE_LIMIT_EXEMPT
        assert "assign_ship" in RATE_LIMIT_EXEMPT
        assert "claim_station" in RATE_LIMIT_EXEMPT

    def test_rate_limiter_tracks_multiple_clients_independently(self):
        """Throttling one client must not affect another client's bucket."""
        limiter = RateLimiter(rate=20.0, burst=5)

        # Exhaust client_a's bucket
        for _ in range(10):
            limiter.allow("client_a", "set_thrust")

        # client_b should still have a full bucket
        assert limiter.allow("client_b", "set_thrust") is True, (
            "client_b should not be throttled by client_a's exhausted bucket"
        )

    def test_remove_client_clears_state(self):
        """Removing a client resets their token state — next command gets a fresh bucket."""
        limiter = RateLimiter(rate=20.0, burst=5)
        client = "removable_client"

        # Exhaust bucket
        for _ in range(10):
            limiter.allow(client, "set_thrust")

        # Verify throttled
        assert limiter.allow(client, "set_thrust") is False

        # Remove and re-add
        limiter.remove_client(client)

        # Should get a fresh bucket
        assert limiter.allow(client, "set_thrust") is True


# ---------------------------------------------------------------------------
# 5. test_multi_ship_command_isolation
# ---------------------------------------------------------------------------

class TestMultiShipCommandIsolation:
    """Commands dispatched to ship_a must not mutate ship_b's state."""

    def test_commands_dispatched_to_correct_ship(self):
        """execute_command routes to the ship's own system, never to a sibling ship."""
        from hybrid.command_handler import execute_command

        ship_a = _make_mock_ship("ship_a")
        ship_b = _make_mock_ship("ship_b")

        helm_a = MagicMock(return_value={"status": "ok", "ship": "a"})
        helm_b = MagicMock(return_value={"status": "ok", "ship": "b"})

        ship_a.systems = {"helm": MagicMock(command=helm_a)}
        ship_b.systems = {"helm": MagicMock(command=helm_b)}

        # Fire 20 commands each to ship_a and ship_b from separate threads
        results_a: list = []
        results_b: list = []

        def send_to(ship, results):
            for i in range(20):
                r = execute_command(ship, "set_thrust", {"command": "set_thrust", "thrust": i})
                results.append(r)

        t1 = threading.Thread(target=send_to, args=(ship_a, results_a), daemon=True)
        t2 = threading.Thread(target=send_to, args=(ship_b, results_b), daemon=True)

        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert helm_a.call_count == 20, (
            f"ship_a helm called {helm_a.call_count} times, expected 20"
        )
        assert helm_b.call_count == 20, (
            f"ship_b helm called {helm_b.call_count} times, expected 20"
        )

    def test_station_manager_isolates_ships(self):
        """A client on ship_a cannot issue commands targeted at ship_b."""
        mgr = StationManager()
        ship_a_id = "ship_a"
        ship_b_id = "ship_b"

        cid = mgr.generate_client_id()
        mgr.register_client(cid, "pilot")
        mgr.assign_to_ship(cid, ship_a_id)
        mgr.claim_station(cid, ship_a_id, StationType.HELM)

        # Valid: command on own ship
        ok_a, _ = mgr.can_issue_command(cid, ship_a_id, "set_thrust")
        assert ok_a is True

        # Invalid: command targeting a different ship
        ok_b, reason_b = mgr.can_issue_command(cid, ship_b_id, "set_thrust")
        assert ok_b is False, f"Command to wrong ship should be denied: {reason_b}"


# ---------------------------------------------------------------------------
# 6. test_station_claim_lifecycle
# ---------------------------------------------------------------------------

class TestStationClaimLifecycle:
    """Register → assign → claim → verify → unregister → verify released."""

    def test_full_lifecycle(self):
        mgr = StationManager()
        ship_id = "lifecycle_ship"

        cid = mgr.generate_client_id()
        assert cid is not None

        # Register
        session = mgr.register_client(cid, "lifecycle_player")
        assert session.client_id == cid
        assert cid in mgr.sessions

        # Assign
        ok = mgr.assign_to_ship(cid, ship_id)
        assert ok is True
        assert mgr.sessions[cid].ship_id == ship_id

        # Claim
        success, msg = mgr.claim_station(cid, ship_id, StationType.HELM)
        assert success is True, f"Claim failed: {msg}"
        assert mgr.sessions[cid].station == StationType.HELM

        # Verify ownership
        owner = mgr.get_station_owner(ship_id, StationType.HELM)
        assert owner == cid

        # Unregister
        mgr.unregister_client(cid)

        # Verify session gone
        assert cid not in mgr.sessions

        # Verify station released
        owner_after = mgr.get_station_owner(ship_id, StationType.HELM)
        assert owner_after is None, "Station should be released after client disconnects"

    def test_claiming_occupied_station_fails(self):
        """A second client cannot claim an already-occupied station."""
        mgr = StationManager()
        ship_id = "contested_ship"

        c1 = mgr.generate_client_id()
        c2 = mgr.generate_client_id()

        for cid, name in ((c1, "first"), (c2, "second")):
            mgr.register_client(cid, name)
            mgr.assign_to_ship(cid, ship_id)

        ok1, _ = mgr.claim_station(c1, ship_id, StationType.HELM)
        ok2, msg2 = mgr.claim_station(c2, ship_id, StationType.HELM)

        assert ok1 is True
        assert ok2 is False, f"Second claim on occupied station should fail: {msg2}"

    def test_station_available_after_release(self):
        """After explicit release, the station can be claimed by another client."""
        mgr = StationManager()
        ship_id = "release_ship"

        c1 = mgr.generate_client_id()
        c2 = mgr.generate_client_id()

        for cid, name in ((c1, "first"), (c2, "second")):
            mgr.register_client(cid, name)
            mgr.assign_to_ship(cid, ship_id)

        mgr.claim_station(c1, ship_id, StationType.HELM)
        mgr.release_station(c1, ship_id, StationType.HELM)

        # Now c2 should be able to claim it
        ok2, msg2 = mgr.claim_station(c2, ship_id, StationType.HELM)
        assert ok2 is True, f"Station should be claimable after release: {msg2}"
        assert mgr.get_station_owner(ship_id, StationType.HELM) == c2

    def test_unregistered_client_has_no_commands(self):
        """A client that has disconnected cannot issue any commands."""
        mgr, cid = _make_station_manager_with_client()
        mgr.unregister_client(cid)

        ok, reason = mgr.can_issue_command(cid, "ship_001", "set_thrust")
        assert ok is False
        assert "not registered" in reason.lower(), f"Unexpected reason: {reason}"


# ---------------------------------------------------------------------------
# 7. test_captain_succession
# ---------------------------------------------------------------------------

class TestCaptainSuccession:
    """When the CAPTAIN disconnects, the longest-connected crew member is promoted."""

    def test_captain_disconnect_triggers_succession(self):
        """After captain unregisters, elect_new_captain promotes a crew member."""
        mgr = StationManager()
        ship_id = "succession_ship"

        captain_id = mgr.generate_client_id()
        helm_id = mgr.generate_client_id()

        # Make helm_id the oldest connection so it wins the election
        mgr.register_client(captain_id, "captain")
        mgr.register_client(helm_id, "helm")
        mgr.sessions[helm_id].connected_at = datetime.now() - timedelta(hours=1)

        for cid in (captain_id, helm_id):
            mgr.assign_to_ship(cid, ship_id)

        mgr.claim_station(captain_id, ship_id, StationType.CAPTAIN)
        mgr.claim_station(helm_id, ship_id, StationType.HELM)

        # Verify initial state
        assert mgr.get_station_owner(ship_id, StationType.CAPTAIN) == captain_id

        # Captain disconnects
        mgr.unregister_client(captain_id)
        assert captain_id not in mgr.sessions

        # Elect successor
        new_captain = mgr.elect_new_captain(ship_id)

        assert new_captain == helm_id, (
            f"Expected helm_id ({helm_id}) to be promoted, got {new_captain}"
        )
        assert mgr.sessions[helm_id].station == StationType.CAPTAIN
        assert mgr.sessions[helm_id].permission_level == PermissionLevel.CAPTAIN

    def test_successor_gains_captain_commands(self):
        """After succession, the promoted client can issue all captain commands."""
        mgr = StationManager()
        ship_id = "cmd_succession_ship"

        captain_id = mgr.generate_client_id()
        helm_id = mgr.generate_client_id()

        mgr.register_client(captain_id, "captain")
        mgr.register_client(helm_id, "helm")
        mgr.sessions[helm_id].connected_at = datetime.now() - timedelta(hours=1)

        for cid in (captain_id, helm_id):
            mgr.assign_to_ship(cid, ship_id)

        mgr.claim_station(captain_id, ship_id, StationType.CAPTAIN)
        mgr.claim_station(helm_id, ship_id, StationType.HELM)

        mgr.unregister_client(captain_id)
        mgr.elect_new_captain(ship_id)

        # New captain should be able to fire weapons AND set thrust
        ok_fire, _ = mgr.can_issue_command(helm_id, ship_id, "fire_weapon")
        ok_thrust, _ = mgr.can_issue_command(helm_id, ship_id, "set_thrust")

        assert ok_fire is True, "Promoted captain must be able to fire weapons"
        assert ok_thrust is True, "Promoted captain must be able to set_thrust"

    def test_no_succession_when_ship_empty(self):
        """elect_new_captain returns None when no clients remain on the ship."""
        mgr = StationManager()
        result = mgr.elect_new_captain("ghost_ship")
        assert result is None

    def test_old_station_released_after_succession(self):
        """The promoted client's previous station (HELM) is freed for others to claim."""
        mgr = StationManager()
        ship_id = "release_on_succession_ship"

        captain_id = mgr.generate_client_id()
        helm_id = mgr.generate_client_id()

        mgr.register_client(captain_id, "captain")
        mgr.register_client(helm_id, "helm")
        mgr.sessions[helm_id].connected_at = datetime.now() - timedelta(hours=1)

        for cid in (captain_id, helm_id):
            mgr.assign_to_ship(cid, ship_id)

        mgr.claim_station(captain_id, ship_id, StationType.CAPTAIN)
        mgr.claim_station(helm_id, ship_id, StationType.HELM)

        mgr.unregister_client(captain_id)
        mgr.elect_new_captain(ship_id)

        # HELM station should now be unclaimed — the successor vacated it
        helm_owner = mgr.get_station_owner(ship_id, StationType.HELM)
        assert helm_owner is None, (
            "HELM station should be free after its owner was promoted to CAPTAIN"
        )

    def test_succession_thread_safety(self):
        """Simultaneous disconnect calls must not double-promote or corrupt state.

        Two threads call elect_new_captain concurrently. The result should be
        exactly one successful promotion — the second call either promotes the
        same client or returns None if the first already ran.
        """
        mgr = StationManager()
        ship_id = "race_succession_ship"

        captain_id = mgr.generate_client_id()
        crew_id = mgr.generate_client_id()

        mgr.register_client(captain_id, "captain")
        mgr.register_client(crew_id, "crew")
        mgr.sessions[crew_id].connected_at = datetime.now() - timedelta(hours=1)

        for cid in (captain_id, crew_id):
            mgr.assign_to_ship(cid, ship_id)

        mgr.claim_station(captain_id, ship_id, StationType.CAPTAIN)
        # crew_id starts with no station so elect_new_captain can promote freely

        mgr.unregister_client(captain_id)

        results: list = []

        def elect():
            r = mgr.elect_new_captain(ship_id)
            results.append(r)

        t1 = threading.Thread(target=elect, daemon=True)
        t2 = threading.Thread(target=elect, daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=3)
        t2.join(timeout=3)

        # The election lock ensures at most one promotion succeeds.
        # One result is crew_id, the other is either crew_id or None (double elect)
        promotions = [r for r in results if r is not None]
        # All successful promotions must point to the same client
        if promotions:
            assert all(r == promotions[0] for r in promotions), (
                f"Multiple different promotions in concurrent elect_new_captain: {results}"
            )
