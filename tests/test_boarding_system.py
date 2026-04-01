# tests/test_boarding_system.py
"""Tests for the boarding system (Phase 3B).

Covers:
- Precondition enforcement (docked, mission-killed, hull > 0)
- Progress advancement per tick
- Defender resistance reduces boarding rate
- Capture changes target faction
- Cancel aborts boarding
- BOARD_AND_CAPTURE objective type
"""

import pytest
from unittest.mock import MagicMock, patch

from hybrid.systems.boarding_system import (
    BoardingSystem,
    BoardingState,
    BASE_RATE,
)
from hybrid.systems.damage_model import DamageModel, SubsystemHealth
from hybrid.scenarios.objectives import (
    Objective,
    ObjectiveType,
    ObjectiveStatus,
)


# ---------------------------------------------------------------------------
# Helpers to build minimal ship-like objects for testing
# ---------------------------------------------------------------------------

def make_ship(ship_id: str, faction: str = "player", docked_to=None):
    """Create a minimal ship mock with the attributes boarding needs."""
    ship = MagicMock()
    ship.id = ship_id
    ship.faction = faction
    ship.docked_to = docked_to
    ship.hull_integrity = 100.0
    ship.max_hull_integrity = 100.0
    ship.event_bus = MagicMock()
    ship._all_ships_ref = None  # Set later when needed
    ship.systems = {}
    ship.crew_system = None
    return ship


def make_damage_model(mission_killed: bool = False, reactor_failed: bool = True,
                      weapons_failed: bool = True):
    """Create a DamageModel configured for boarding tests.

    By default: both propulsion and weapons failed (mission-killed),
    reactor failed (no resistance from reactor).
    """
    dm = DamageModel(config={
        "propulsion": {"max_health": 100, "health": 0 if mission_killed else 100},
        "weapons": {"max_health": 100, "health": 0 if weapons_failed else 100},
        "reactor": {"max_health": 100, "health": 0 if reactor_failed else 100},
        "targeting": {"max_health": 100, "health": 0},
    })
    return dm


# ---------------------------------------------------------------------------
# Precondition tests
# ---------------------------------------------------------------------------

class TestBoardingPreconditions:
    """Verify that begin_boarding rejects invalid states."""

    def test_fails_if_not_docked(self):
        bs = BoardingSystem()
        attacker = make_ship("attacker", docked_to=None)
        target = make_ship("target", faction="enemy")
        target.damage_model = make_damage_model(mission_killed=True)
        all_ships = {"target": target}

        result = bs.begin_boarding("target", attacker, all_ships)
        assert result["ok"] is False
        assert "Not docked" in result["error"]

    def test_fails_if_docked_to_wrong_ship(self):
        bs = BoardingSystem()
        attacker = make_ship("attacker", docked_to="some_other_ship")
        target = make_ship("target", faction="enemy")
        target.damage_model = make_damage_model(mission_killed=True)
        all_ships = {"target": target}

        result = bs.begin_boarding("target", attacker, all_ships)
        assert result["ok"] is False
        assert "Not docked" in result["error"]

    def test_fails_if_target_not_mission_killed(self):
        bs = BoardingSystem()
        attacker = make_ship("attacker", docked_to="target")
        target = make_ship("target", faction="enemy")
        target.damage_model = make_damage_model(mission_killed=False, weapons_failed=False)
        all_ships = {"target": target}

        result = bs.begin_boarding("target", attacker, all_ships)
        assert result["ok"] is False
        assert "not mission-killed" in result["error"]

    def test_fails_if_target_hull_destroyed(self):
        bs = BoardingSystem()
        attacker = make_ship("attacker", docked_to="target")
        target = make_ship("target", faction="enemy")
        target.hull_integrity = 0
        target.damage_model = make_damage_model(mission_killed=True)
        all_ships = {"target": target}

        result = bs.begin_boarding("target", attacker, all_ships)
        assert result["ok"] is False
        assert "hull destroyed" in result["error"]

    def test_fails_if_target_not_found(self):
        bs = BoardingSystem()
        attacker = make_ship("attacker", docked_to="ghost")
        all_ships = {}

        result = bs.begin_boarding("ghost", attacker, all_ships)
        assert result["ok"] is False
        assert "not found" in result["error"]

    def test_succeeds_with_valid_preconditions(self):
        bs = BoardingSystem()
        attacker = make_ship("attacker", docked_to="target")
        target = make_ship("target", faction="enemy")
        target.damage_model = make_damage_model(mission_killed=True)
        all_ships = {"target": target}

        result = bs.begin_boarding("target", attacker, all_ships)
        assert result["ok"] is True
        assert bs.state == BoardingState.BOARDING
        assert bs.progress == 0.0

    def test_fails_if_already_boarding(self):
        bs = BoardingSystem()
        attacker = make_ship("attacker", docked_to="target")
        target = make_ship("target", faction="enemy")
        target.damage_model = make_damage_model(mission_killed=True)
        all_ships = {"target": target}

        bs.begin_boarding("target", attacker, all_ships)
        result = bs.begin_boarding("target", attacker, all_ships)
        assert result["ok"] is False
        assert "already in progress" in result["error"]


# ---------------------------------------------------------------------------
# Progress and resistance tests
# ---------------------------------------------------------------------------

class TestBoardingProgress:
    """Verify progress advances correctly with resistance."""

    def _setup_boarding(self, reactor_failed=True, weapons_failed=True,
                        attacker_command_skill=3, defender_dc_skill=3):
        """Helper: create ships and begin boarding."""
        bs = BoardingSystem()
        attacker = make_ship("attacker", faction="player", docked_to="target")
        target = make_ship("target", faction="enemy")
        target.damage_model = make_damage_model(
            mission_killed=True,
            reactor_failed=reactor_failed,
            weapons_failed=weapons_failed,
        )

        # Wire _all_ships_ref on attacker so tick() can resolve target
        attacker._all_ships_ref = [attacker, target]

        # Set crew skills if non-default
        if attacker_command_skill != 3:
            attacker_crew = MagicMock()
            member = MagicMock()
            member.skills = MagicMock()
            member.skills.command = attacker_command_skill
            attacker_crew.get_ship_crew = MagicMock(return_value=[member])
            attacker.crew_system = attacker_crew

        if defender_dc_skill != 3:
            target_crew = MagicMock()
            member = MagicMock()
            member.skills = MagicMock()
            member.skills.damage_control = defender_dc_skill
            target_crew.get_ship_crew = MagicMock(return_value=[member])
            target.crew_system = target_crew

        all_ships = {"attacker": attacker, "target": target}
        bs.begin_boarding("target", attacker, all_ships)

        return bs, attacker, target

    def test_progress_advances_per_tick(self):
        bs, attacker, target = self._setup_boarding()
        dt = 1.0
        bs.tick(dt, attacker)

        # Default skill=3, base_rate=0.01, resistance with all systems failed ~1.0
        # minus dc_penalty from skill 3: (3-1)*0.05 = 0.10
        # All weapons/targeting failed, reactor failed => no weapon/reactor penalty
        # factor = 1.0 - 0.10 = 0.90
        expected = 3 * BASE_RATE * dt * 0.90
        assert abs(bs.progress - expected) < 0.001

    def test_higher_skill_boards_faster(self):
        bs_low, attacker_low, _ = self._setup_boarding(attacker_command_skill=2)
        bs_high, attacker_high, _ = self._setup_boarding(attacker_command_skill=5)

        dt = 1.0
        bs_low.tick(dt, attacker_low)
        bs_high.tick(dt, attacker_high)

        assert bs_high.progress > bs_low.progress

    def test_active_weapons_slow_boarding(self):
        """Non-failed weapons on defender should reduce boarding rate."""
        bs_easy, attacker_easy, _ = self._setup_boarding(weapons_failed=True)
        bs_hard, attacker_hard, _ = self._setup_boarding(weapons_failed=False)

        dt = 1.0
        bs_easy.tick(dt, attacker_easy)
        bs_hard.tick(dt, attacker_hard)

        # With active weapons, progress should be lower
        assert bs_hard.progress < bs_easy.progress

    def test_active_reactor_slows_boarding(self):
        """Functioning reactor on defender should reduce boarding rate."""
        bs_easy, attacker_easy, _ = self._setup_boarding(reactor_failed=True)
        bs_hard, attacker_hard, _ = self._setup_boarding(reactor_failed=False)

        dt = 1.0
        bs_easy.tick(dt, attacker_easy)
        bs_hard.tick(dt, attacker_hard)

        assert bs_hard.progress < bs_easy.progress

    def test_defender_dc_skill_slows_boarding(self):
        """Higher DAMAGE_CONTROL skill on defender = slower boarding."""
        bs_easy, attacker_easy, _ = self._setup_boarding(defender_dc_skill=1)
        bs_hard, attacker_hard, _ = self._setup_boarding(defender_dc_skill=6)

        dt = 1.0
        bs_easy.tick(dt, attacker_easy)
        bs_hard.tick(dt, attacker_hard)

        assert bs_hard.progress < bs_easy.progress

    def test_capture_changes_faction(self):
        bs, attacker, target = self._setup_boarding()

        # Tick enough to reach 1.0 progress
        # With default skill 3, resistance 0.90 => rate = 0.027/tick
        # Need ~37 ticks at dt=1.0
        for _ in range(50):
            if bs.state == BoardingState.CAPTURED:
                break
            bs.tick(1.0, attacker)

        assert bs.state == BoardingState.CAPTURED
        assert bs.progress == 1.0
        assert target.faction == "player"

    def test_capture_publishes_event(self):
        bs, attacker, target = self._setup_boarding()

        for _ in range(50):
            if bs.state == BoardingState.CAPTURED:
                break
            bs.tick(1.0, attacker, attacker.event_bus)

        attacker.event_bus.publish.assert_any_call(
            "ship_captured",
            {
                "attacker": "attacker",
                "target": "target",
                "old_faction": "enemy",
                "new_faction": "player",
            },
        )


# ---------------------------------------------------------------------------
# Cancellation and failure tests
# ---------------------------------------------------------------------------

class TestBoardingCancelAndFail:
    """Verify cancel and failure scenarios."""

    def test_cancel_resets_state(self):
        bs = BoardingSystem()
        attacker = make_ship("attacker", docked_to="target")
        target = make_ship("target", faction="enemy")
        target.damage_model = make_damage_model(mission_killed=True)
        all_ships = {"target": target}

        bs.begin_boarding("target", attacker, all_ships)
        assert bs.state == BoardingState.BOARDING

        result = bs.cancel_boarding()
        assert result["ok"] is True
        assert bs.state == BoardingState.IDLE
        assert bs.progress == 0.0

    def test_cancel_fails_when_idle(self):
        bs = BoardingSystem()
        result = bs.cancel_boarding()
        assert result["ok"] is False

    def test_undock_during_boarding_causes_failure(self):
        bs = BoardingSystem()
        attacker = make_ship("attacker", faction="player", docked_to="target")
        target = make_ship("target", faction="enemy")
        target.damage_model = make_damage_model(mission_killed=True)
        attacker._all_ships_ref = [attacker, target]

        bs.begin_boarding("target", attacker, {"target": target})

        # Simulate undocking
        attacker.docked_to = None
        bs.tick(1.0, attacker)

        assert bs.state == BoardingState.FAILED
        assert "No longer docked" in bs.failure_reason

    def test_target_hull_destroyed_during_boarding_causes_failure(self):
        bs = BoardingSystem()
        attacker = make_ship("attacker", faction="player", docked_to="target")
        target = make_ship("target", faction="enemy")
        target.damage_model = make_damage_model(mission_killed=True)
        attacker._all_ships_ref = [attacker, target]

        bs.begin_boarding("target", attacker, {"target": target})

        # Simulate hull destruction
        target.hull_integrity = 0
        bs.tick(1.0, attacker)

        assert bs.state == BoardingState.FAILED
        assert "hull destroyed" in bs.failure_reason


# ---------------------------------------------------------------------------
# get_state / telemetry tests
# ---------------------------------------------------------------------------

class TestBoardingTelemetry:
    """Verify get_state returns correct telemetry."""

    def test_idle_state(self):
        bs = BoardingSystem()
        state = bs.get_state()
        assert state["state"] == "idle"
        assert state["target"] is None
        assert state["progress"] == 0.0

    def test_boarding_state_includes_resistance(self):
        bs = BoardingSystem()
        attacker = make_ship("attacker", docked_to="target")
        target = make_ship("target", faction="enemy")
        target.damage_model = make_damage_model(mission_killed=True)
        attacker._all_ships_ref = [attacker, target]

        bs.begin_boarding("target", attacker, {"target": target})
        bs.tick(1.0, attacker)

        state = bs.get_state()
        assert state["state"] == "boarding"
        assert state["target"] == "target"
        assert state["progress"] > 0
        assert "total_factor" in state["resistance"]


# ---------------------------------------------------------------------------
# Command interface tests
# ---------------------------------------------------------------------------

class TestBoardingCommand:
    """Verify the command() method routes correctly."""

    def test_begin_via_command(self):
        bs = BoardingSystem()
        attacker = make_ship("attacker", docked_to="target")
        target = make_ship("target", faction="enemy")
        target.damage_model = make_damage_model(mission_killed=True)
        attacker._all_ships_ref = [attacker, target]

        result = bs.command("begin_boarding", {
            "_ship": attacker,
            "target_ship_id": "target",
        })
        assert result["ok"] is True
        assert bs.state == BoardingState.BOARDING

    def test_cancel_via_command(self):
        bs = BoardingSystem()
        attacker = make_ship("attacker", docked_to="target")
        target = make_ship("target", faction="enemy")
        target.damage_model = make_damage_model(mission_killed=True)
        attacker._all_ships_ref = [attacker, target]

        bs.command("begin_boarding", {"_ship": attacker, "target_ship_id": "target"})
        result = bs.command("cancel_boarding", {"_ship": attacker})
        assert result["ok"] is True
        assert bs.state == BoardingState.IDLE

    def test_status_via_command(self):
        bs = BoardingSystem()
        result = bs.command("status", {})
        assert result["state"] == "idle"

    def test_missing_target_returns_error(self):
        bs = BoardingSystem()
        attacker = make_ship("attacker")
        result = bs.command("begin_boarding", {"_ship": attacker})
        assert result["ok"] is False
        assert "Missing target_ship_id" in result["error"]


# ---------------------------------------------------------------------------
# BOARD_AND_CAPTURE objective tests
# ---------------------------------------------------------------------------

class TestBoardAndCaptureObjective:
    """Verify the BOARD_AND_CAPTURE objective type."""

    def _make_sim(self, ships):
        sim = MagicMock()
        sim.ships = ships
        sim.time = 100.0
        return sim

    def test_incomplete_when_factions_differ(self):
        player = make_ship("player", faction="UNE")
        target = make_ship("target", faction="pirate")
        sim = self._make_sim({"player": player, "target": target})

        obj = Objective(
            "capture_target", ObjectiveType.BOARD_AND_CAPTURE,
            "Board and capture the pirate vessel",
            {"target": "target"}, required=True,
        )

        result = obj.check(sim, player)
        assert result is False
        assert obj.status == ObjectiveStatus.IN_PROGRESS

    def test_completes_when_factions_match(self):
        player = make_ship("player", faction="UNE")
        target = make_ship("target", faction="UNE")  # Already captured
        sim = self._make_sim({"player": player, "target": target})

        obj = Objective(
            "capture_target", ObjectiveType.BOARD_AND_CAPTURE,
            "Board and capture the pirate vessel",
            {"target": "target"}, required=True,
        )

        result = obj.check(sim, player)
        assert result is True
        assert obj.status == ObjectiveStatus.COMPLETED
        assert obj.progress == 1.0

    def test_fails_when_target_missing(self):
        player = make_ship("player", faction="UNE")
        sim = self._make_sim({"player": player})

        obj = Objective(
            "capture_target", ObjectiveType.BOARD_AND_CAPTURE,
            "Board and capture the pirate vessel",
            {"target": "target"}, required=True,
        )

        result = obj.check(sim, player)
        assert result is False
        assert obj.status == ObjectiveStatus.FAILED

    def test_mirrors_boarding_system_progress(self):
        player = make_ship("player", faction="UNE")
        target = make_ship("target", faction="pirate")
        sim = self._make_sim({"player": player, "target": target})

        # Give the player a boarding system with some progress
        boarding_mock = MagicMock()
        boarding_mock.progress = 0.45
        player.systems["boarding"] = boarding_mock

        obj = Objective(
            "capture_target", ObjectiveType.BOARD_AND_CAPTURE,
            "Board and capture", {"target": "target"}, required=True,
        )

        obj.check(sim, player)
        assert abs(obj.progress - 0.45) < 0.001
