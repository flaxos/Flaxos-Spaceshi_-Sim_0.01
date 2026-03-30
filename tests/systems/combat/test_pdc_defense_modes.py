# tests/systems/combat/test_pdc_defense_modes.py
"""Tests for expanded PDC defense modes: priority, network, enhanced auto.

Covers:
- Priority defense: human-ordered threat engagement
- Network defense: coordinated multi-PDC target distribution
- Enhanced auto: re-acquisition delay, combat logging, intercept stats
- Command registration: set_pdc_priority, updated set_pdc_mode
- Telemetry: per-PDC engagement state and statistics
"""

import pytest
import math
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Helpers — lightweight stand-ins for torpedo and ship objects so tests
# don't need the full simulation stack.
# ---------------------------------------------------------------------------

@dataclass
class FakeTorpedo:
    """Minimal torpedo for PDC interception tests."""
    id: str
    target_id: str
    shooter_id: str = "enemy"
    position: Dict[str, float] = None
    velocity: Dict[str, float] = None
    hull_health: float = 20.0
    alive: bool = True

    def __post_init__(self):
        if self.position is None:
            self.position = {"x": 0, "y": 0, "z": 0}
        if self.velocity is None:
            self.velocity = {"x": 0, "y": 0, "z": 0}


class FakeTorpedoManager:
    """Minimal torpedo manager for PDC tests."""

    def __init__(self, torpedoes: List[FakeTorpedo] = None):
        self._torpedoes = list(torpedoes or [])
        self.active_count = len(self._torpedoes)

    def get_torpedoes_targeting(self, ship_id: str) -> List[FakeTorpedo]:
        return [t for t in self._torpedoes if t.alive and t.target_id == ship_id]

    def apply_pdc_damage(self, torpedo_id: str, damage: float, source: str = "") -> dict:
        for torp in self._torpedoes:
            if torp.id == torpedo_id and torp.alive:
                torp.hull_health -= damage
                if torp.hull_health <= 0:
                    torp.alive = False
                    return {"ok": True, "destroyed": True, "torpedo_id": torpedo_id}
                return {
                    "ok": True, "destroyed": False,
                    "torpedo_id": torpedo_id,
                    "hull_remaining": torp.hull_health,
                }
        return {"ok": False, "reason": "torpedo_not_found"}


def _make_ship(ship_id: str, pdcs: int = 2, railguns: int = 0,
               position: Dict[str, float] = None):
    """Create a minimal Ship with a CombatSystem for testing."""
    from hybrid.ship import Ship

    pos = position or {"x": 0, "y": 0, "z": 0}
    config = {
        "id": ship_id,
        "position": pos,
        "velocity": {"x": 0, "y": 0, "z": 0},
        "systems": {
            "combat": {"railguns": railguns, "pdcs": pdcs},
            "targeting": {},
            "sensors": {"passive": {"range": 50000}},
            "power_management": {
                "primary": {"output": 200},
                "secondary": {"output": 100},
            },
        },
    }
    ship = Ship(ship_id, config)
    ship.sim_time = 10.0  # Ensure weapons are off cooldown
    return ship


# ---------------------------------------------------------------------------
# Tests: CombatSystem PDC state
# ---------------------------------------------------------------------------

class TestCombatSystemPDCState:
    """Tests for PDC defense state on CombatSystem."""

    def test_pdc_stats_initialised(self):
        """Per-PDC stats dicts are created for each PDC mount on init."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"railguns": 1, "pdcs": 3})
        assert "pdc_1" in combat.pdc_stats
        assert "pdc_2" in combat.pdc_stats
        assert "pdc_3" in combat.pdc_stats
        # Railgun should not have PDC stats
        assert "railgun_1" not in combat.pdc_stats
        for stats in combat.pdc_stats.values():
            assert stats["intercepts"] == 0
            assert stats["misses"] == 0
            assert stats["engagements"] == 0

    def test_priority_targets_empty_by_default(self):
        """Priority target list starts empty."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"pdcs": 2})
        assert combat.pdc_priority_targets == []

    def test_pdc_engagements_empty_by_default(self):
        """Network engagement map starts empty."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"pdcs": 2})
        assert combat._pdc_engagements == {}

    def test_reacquire_delay_default(self):
        """Re-acquisition delay is 0.2 seconds."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"pdcs": 1})
        assert combat._pdc_reacquire_delay == 0.2

    def test_reacquire_timer_ticks_down(self):
        """Re-acquisition timers decrement during tick and auto-remove at zero."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"pdcs": 1})
        combat._pdc_reacquire_timers["pdc_1"] = 0.15

        # Create minimal mock ship
        ship = MagicMock()
        ship.sim_time = 1.0
        ship.systems = {}

        combat.tick(0.1, ship, None)
        # 0.15 - 0.1 = 0.05
        assert "pdc_1" in combat._pdc_reacquire_timers
        assert combat._pdc_reacquire_timers["pdc_1"] == pytest.approx(0.05)

        combat.tick(0.1, ship, None)
        # 0.05 - 0.1 <= 0, timer should be removed
        assert "pdc_1" not in combat._pdc_reacquire_timers


# ---------------------------------------------------------------------------
# Tests: set_pdc_mode command (expanded choices)
# ---------------------------------------------------------------------------

class TestSetPdcMode:
    """Tests for set_pdc_mode with new priority and network modes."""

    def test_mode_auto(self):
        """Auto mode enables PDCs."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"pdcs": 2})
        result = combat.command("set_pdc_mode", {"mode": "auto"})
        assert result["ok"]
        for mid in ("pdc_1", "pdc_2"):
            assert combat.truth_weapons[mid].pdc_mode == "auto"
            assert combat.truth_weapons[mid].enabled

    def test_mode_priority(self):
        """Priority mode enables PDCs and sets correct pdc_mode."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"pdcs": 2})
        result = combat.command("set_pdc_mode", {"mode": "priority"})
        assert result["ok"]
        assert result["mode"] == "priority"
        for mid in ("pdc_1", "pdc_2"):
            assert combat.truth_weapons[mid].pdc_mode == "priority"
            assert combat.truth_weapons[mid].enabled

    def test_mode_network(self):
        """Network mode enables PDCs and sets correct pdc_mode."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"pdcs": 2})
        result = combat.command("set_pdc_mode", {"mode": "network"})
        assert result["ok"]
        assert result["mode"] == "network"
        for mid in ("pdc_1", "pdc_2"):
            assert combat.truth_weapons[mid].pdc_mode == "network"
            assert combat.truth_weapons[mid].enabled

    def test_mode_hold_fire_disables(self):
        """Hold_fire mode disables PDCs."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"pdcs": 2})
        result = combat.command("set_pdc_mode", {"mode": "hold_fire"})
        assert result["ok"]
        for mid in ("pdc_1", "pdc_2"):
            assert not combat.truth_weapons[mid].enabled

    def test_invalid_mode_rejected(self):
        """Invalid mode string is rejected with error."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"pdcs": 1})
        result = combat.command("set_pdc_mode", {"mode": "turbo"})
        assert not result.get("ok")
        assert "INVALID_MODE" in result.get("error_code", result.get("error", ""))

    def test_mode_switch_clears_engagements(self):
        """Switching modes clears stale network engagement assignments."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"pdcs": 2})
        combat._pdc_engagements["pdc_1"] = "torp_old"
        result = combat.command("set_pdc_mode", {"mode": "auto"})
        assert result["ok"]
        assert combat._pdc_engagements == {}


# ---------------------------------------------------------------------------
# Tests: set_pdc_priority command
# ---------------------------------------------------------------------------

class TestSetPdcPriority:
    """Tests for set_pdc_priority command."""

    def test_set_priority_list(self):
        """Setting a priority list stores torpedo IDs in order."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"pdcs": 2})
        result = combat.command("set_pdc_priority", {
            "torpedo_ids": ["torp_3", "torp_1", "torp_2"],
        })
        assert result["ok"]
        assert combat.pdc_priority_targets == ["torp_3", "torp_1", "torp_2"]

    def test_set_priority_empty_list(self):
        """Setting an empty list clears priority queue."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"pdcs": 1})
        combat.pdc_priority_targets = ["torp_1"]
        result = combat.command("set_pdc_priority", {"torpedo_ids": []})
        assert result["ok"]
        assert combat.pdc_priority_targets == []

    def test_set_priority_invalid_type(self):
        """Non-list torpedo_ids is rejected."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"pdcs": 1})
        result = combat.command("set_pdc_priority", {"torpedo_ids": "torp_1"})
        assert not result.get("ok")

    def test_priority_appears_in_state(self):
        """Priority targets appear in get_state output."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"pdcs": 1})
        combat.pdc_priority_targets = ["torp_2", "torp_1"]
        state = combat.get_state()
        assert state["pdc_priority_targets"] == ["torp_2", "torp_1"]


# ---------------------------------------------------------------------------
# Tests: Command registration chain (3-place checklist)
# ---------------------------------------------------------------------------

class TestCommandRegistration:
    """Verify set_pdc_priority is registered in all 3 required places."""

    def test_registered_in_command_handler(self):
        """set_pdc_priority is in the system_commands routing dict."""
        from hybrid.command_handler import system_commands

        assert "set_pdc_priority" in system_commands
        system, action = system_commands["set_pdc_priority"]
        assert system == "combat"
        assert action == "set_pdc_priority"

    def test_registered_in_station_types(self):
        """set_pdc_priority is in TACTICAL station commands."""
        from server.stations.station_types import (
            STATION_DEFINITIONS, StationType, can_station_issue_command,
        )

        assert can_station_issue_command(StationType.TACTICAL, "set_pdc_priority")

    def test_registered_in_tactical_commands(self):
        """set_pdc_priority has a CommandSpec in tactical_commands."""
        from hybrid.commands.tactical_commands import cmd_set_pdc_priority
        # Handler exists and is callable
        assert callable(cmd_set_pdc_priority)


# ---------------------------------------------------------------------------
# Tests: Priority defense mode (simulator-level)
# ---------------------------------------------------------------------------

class TestPriorityDefenseMode:
    """Tests for priority defense mode in the simulator intercept loop."""

    def test_priority_engages_in_order(self):
        """In priority mode, PDC engages the first priority-listed torpedo
        even if it is farther away than another threat."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)

        ship = _make_ship("defender", pdcs=1)
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        # Set priority mode
        combat = ship.systems["combat"]
        combat.command("set_pdc_mode", {"mode": "priority"})
        combat.pdc_priority_targets = ["torp_far", "torp_close"]

        # Close torpedo at 500m, far torpedo at 1500m — both in range
        torp_close = FakeTorpedo(
            id="torp_close", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
        )
        torp_far = FakeTorpedo(
            id="torp_far", target_id="defender",
            position={"x": 1500, "y": 0, "z": 0},
        )
        sim.torpedo_manager = FakeTorpedoManager([torp_close, torp_far])

        # Patch randomness to always hit
        with patch("hybrid.simulator.random.random", return_value=0.0):
            sim._process_pdc_torpedo_intercept([ship])

        # Priority target (torp_far) should be engaged first even though
        # torp_close is nearer
        assert torp_far.hull_health < 20.0
        # torp_close should be untouched (only 1 PDC, 1 shot per tick)
        assert torp_close.hull_health == 20.0

    def test_priority_fallback_to_closest(self):
        """If priority list is empty or targets not in range, falls back
        to closest-first (auto behaviour)."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender", pdcs=1)
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        combat = ship.systems["combat"]
        combat.command("set_pdc_mode", {"mode": "priority"})
        # Empty priority list — should behave like auto
        combat.pdc_priority_targets = []

        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 800, "y": 0, "z": 0},
        )
        sim.torpedo_manager = FakeTorpedoManager([torp])

        with patch("hybrid.simulator.random.random", return_value=0.0):
            sim._process_pdc_torpedo_intercept([ship])

        assert torp.hull_health < 20.0


# ---------------------------------------------------------------------------
# Tests: Network defense mode (simulator-level)
# ---------------------------------------------------------------------------

class TestNetworkDefenseMode:
    """Tests for network defense mode in the simulator intercept loop."""

    def test_network_distributes_targets(self):
        """Two PDCs in network mode engage different torpedoes."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender", pdcs=2)
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        combat = ship.systems["combat"]
        combat.command("set_pdc_mode", {"mode": "network"})

        # Two torpedoes at different distances, both in range
        torp_1 = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 600, "y": 0, "z": 0},
        )
        torp_2 = FakeTorpedo(
            id="torp_2", target_id="defender",
            position={"x": 1200, "y": 0, "z": 0},
        )
        sim.torpedo_manager = FakeTorpedoManager([torp_1, torp_2])

        with patch("hybrid.simulator.random.random", return_value=0.0):
            sim._process_pdc_torpedo_intercept([ship])

        # Both torpedoes should be engaged by different PDCs
        assert torp_1.hull_health < 20.0
        assert torp_2.hull_health < 20.0

    def test_network_no_double_engage(self):
        """With 2 PDCs and only 1 torpedo, only one PDC engages it."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender", pdcs=2)
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        combat = ship.systems["combat"]
        combat.command("set_pdc_mode", {"mode": "network"})

        # One torpedo, two PDCs
        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
            hull_health=100.0,  # High health so it survives
        )
        sim.torpedo_manager = FakeTorpedoManager([torp])

        with patch("hybrid.simulator.random.random", return_value=0.0):
            sim._process_pdc_torpedo_intercept([ship])

        # Only one PDC should have fired (network assigns one per torpedo)
        # pdc_damage = 5.0 * 10 = 50 per burst
        # Only 1 PDC fired, so health should be 100 - 50 = 50
        assert torp.hull_health == 50.0

    def test_network_reassigns_after_kill(self):
        """After a PDC destroys its target, it picks the next unassigned threat
        on the following tick."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender", pdcs=2)
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        combat = ship.systems["combat"]
        combat.command("set_pdc_mode", {"mode": "network"})

        # Three torpedoes: first two assigned to PDC-1 and PDC-2
        torp_1 = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
            hull_health=10.0,  # Will be destroyed in one burst
        )
        torp_2 = FakeTorpedo(
            id="torp_2", target_id="defender",
            position={"x": 800, "y": 0, "z": 0},
            hull_health=100.0,
        )
        torp_3 = FakeTorpedo(
            id="torp_3", target_id="defender",
            position={"x": 1000, "y": 0, "z": 0},
            hull_health=100.0,
        )
        sim.torpedo_manager = FakeTorpedoManager([torp_1, torp_2, torp_3])

        # Tick 1: PDC-1 destroys torp_1, PDC-2 engages torp_2
        with patch("hybrid.simulator.random.random", return_value=0.0):
            sim._process_pdc_torpedo_intercept([ship])

        assert not torp_1.alive  # Destroyed
        assert torp_2.hull_health < 100.0  # Engaged by PDC-2
        # torp_3 not yet engaged (only 2 PDCs, 2 torpedoes assigned)

        # Reset cooldowns so PDCs can fire again on next tick
        for w in combat.truth_weapons.values():
            if w.mount_id.startswith("pdc"):
                w.last_fired = -10.0
        # Clear re-acquisition timers to simulate delay elapsed
        combat._pdc_reacquire_timers.clear()

        # Tick 2: freed PDC-1 should now pick up torp_3
        with patch("hybrid.simulator.random.random", return_value=0.0):
            sim._process_pdc_torpedo_intercept([ship])

        assert torp_3.hull_health < 100.0


# ---------------------------------------------------------------------------
# Tests: Enhanced auto mode
# ---------------------------------------------------------------------------

class TestEnhancedAutoMode:
    """Tests for enhanced auto mode: re-acquisition delay, stats, events."""

    def test_reacquire_delay_blocks_immediate_refire(self):
        """After destroying a torpedo, PDC cannot immediately engage the next one."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender", pdcs=1)
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        combat = ship.systems["combat"]
        # Auto mode
        combat.command("set_pdc_mode", {"mode": "auto"})

        # First torpedo dies in one burst, second should be delayed
        torp_1 = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
            hull_health=1.0,  # Dies instantly
        )
        torp_2 = FakeTorpedo(
            id="torp_2", target_id="defender",
            position={"x": 800, "y": 0, "z": 0},
            hull_health=100.0,
        )
        sim.torpedo_manager = FakeTorpedoManager([torp_1, torp_2])

        with patch("hybrid.simulator.random.random", return_value=0.0):
            sim._process_pdc_torpedo_intercept([ship])

        assert not torp_1.alive
        # Re-acquisition timer should be set
        assert "pdc_1" in combat._pdc_reacquire_timers
        assert combat._pdc_reacquire_timers["pdc_1"] == pytest.approx(0.2)
        # torp_2 should NOT have been engaged yet
        assert torp_2.hull_health == 100.0

    def test_intercept_stats_tracked(self):
        """PDC stats track intercepts and misses."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender", pdcs=1)
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        combat = ship.systems["combat"]

        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
            hull_health=100.0,
        )
        sim.torpedo_manager = FakeTorpedoManager([torp])

        # Force a hit
        with patch("hybrid.simulator.random.random", return_value=0.0):
            sim._process_pdc_torpedo_intercept([ship])

        assert combat.pdc_stats["pdc_1"]["engagements"] == 1
        assert combat.pdc_stats["pdc_1"]["intercepts"] == 1
        assert combat.pdc_stats["pdc_1"]["misses"] == 0

        # Reset cooldown and force a miss
        combat.truth_weapons["pdc_1"].last_fired = -10.0
        torp.hull_health = 100.0
        torp.alive = True
        sim.torpedo_manager = FakeTorpedoManager([torp])

        with patch("hybrid.simulator.random.random", return_value=1.0):
            sim._process_pdc_torpedo_intercept([ship])

        assert combat.pdc_stats["pdc_1"]["engagements"] == 2
        assert combat.pdc_stats["pdc_1"]["intercepts"] == 1
        assert combat.pdc_stats["pdc_1"]["misses"] == 1

    def test_event_published_on_engage(self):
        """pdc_torpedo_engage event is published with mode field."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender", pdcs=1)
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        combat = ship.systems["combat"]

        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
        )
        sim.torpedo_manager = FakeTorpedoManager([torp])

        events = []
        sim._event_bus.subscribe("pdc_torpedo_engage", lambda payload: events.append(payload))

        with patch("hybrid.simulator.random.random", return_value=0.0):
            sim._process_pdc_torpedo_intercept([ship])

        assert len(events) == 1
        assert events[0]["ship_id"] == "defender"
        assert events[0]["pdc_mount"] == "pdc_1"
        assert events[0]["torpedo_id"] == "torp_1"
        assert events[0]["hit"] is True
        assert events[0]["mode"] == "auto"

    def test_miss_still_consumes_ammo(self):
        """A miss still consumes ammo and sets cooldown (burst was fired)."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender", pdcs=1)
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        weapon = ship.systems["combat"].truth_weapons["pdc_1"]
        initial_ammo = weapon.ammo

        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
        )
        sim.torpedo_manager = FakeTorpedoManager([torp])

        with patch("hybrid.simulator.random.random", return_value=1.0):
            sim._process_pdc_torpedo_intercept([ship])

        # Ammo consumed even on miss
        assert weapon.ammo < initial_ammo
        assert weapon.ammo == initial_ammo - weapon.specs.burst_count


# ---------------------------------------------------------------------------
# Tests: Telemetry includes PDC defense state
# ---------------------------------------------------------------------------

class TestPDCTelemetry:
    """Tests for PDC state in weapons telemetry."""

    def test_get_state_includes_pdc_fields(self):
        """CombatSystem.get_state() includes new PDC defense fields."""
        from hybrid.systems.combat.combat_system import CombatSystem

        combat = CombatSystem({"pdcs": 2})
        combat.pdc_priority_targets = ["torp_1"]
        combat._pdc_engagements = {"pdc_1": "torp_1"}

        state = combat.get_state()

        assert "pdc_priority_targets" in state
        assert state["pdc_priority_targets"] == ["torp_1"]
        assert "pdc_engagements" in state
        assert state["pdc_engagements"] == {"pdc_1": "torp_1"}
        assert "pdc_stats" in state
        assert "pdc_1" in state["pdc_stats"]

    def test_weapons_telemetry_includes_pdc_fields(self):
        """get_weapons_status() propagates PDC defense state."""
        ship = _make_ship("test_ship", pdcs=2)
        combat = ship.systems["combat"]
        combat.pdc_priority_targets = ["torp_2"]
        combat._pdc_engagements = {"pdc_2": "torp_2"}
        combat.pdc_stats["pdc_1"]["intercepts"] = 3

        from hybrid.telemetry import get_weapons_status
        telemetry = get_weapons_status(ship)

        assert telemetry["pdc_priority_targets"] == ["torp_2"]
        assert telemetry["pdc_engagements"] == {"pdc_2": "torp_2"}
        assert telemetry["pdc_stats"]["pdc_1"]["intercepts"] == 3


# ---------------------------------------------------------------------------
# Tests: Manual and hold_fire modes are not engaged
# ---------------------------------------------------------------------------

class TestInactiveModes:
    """Verify that manual and hold_fire PDCs do not auto-engage."""

    def test_manual_mode_no_engagement(self):
        """PDCs in manual mode do not auto-engage incoming torpedoes."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender", pdcs=1)
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        ship.systems["combat"].command("set_pdc_mode", {"mode": "manual"})

        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
        )
        sim.torpedo_manager = FakeTorpedoManager([torp])

        with patch("hybrid.simulator.random.random", return_value=0.0):
            sim._process_pdc_torpedo_intercept([ship])

        # Torpedo untouched
        assert torp.hull_health == 20.0

    def test_hold_fire_no_engagement(self):
        """PDCs in hold_fire mode do not auto-engage."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender", pdcs=1)
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        ship.systems["combat"].command("set_pdc_mode", {"mode": "hold_fire"})

        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
        )
        sim.torpedo_manager = FakeTorpedoManager([torp])

        with patch("hybrid.simulator.random.random", return_value=0.0):
            sim._process_pdc_torpedo_intercept([ship])

        assert torp.hull_health == 20.0


# ---------------------------------------------------------------------------
# Tests: _pick_priority_target static method
# ---------------------------------------------------------------------------

class TestPickPriorityTarget:
    """Unit tests for the priority target selection helper."""

    def test_picks_first_in_range_priority(self):
        """Selects the first priority-listed torpedo that is in range."""
        from hybrid.simulator import Simulator

        torp_a = FakeTorpedo(id="a", target_id="x", position={"x": 1800, "y": 0, "z": 0})
        torp_b = FakeTorpedo(id="b", target_id="x", position={"x": 500, "y": 0, "z": 0})
        torp_c = FakeTorpedo(id="c", target_id="x", position={"x": 1000, "y": 0, "z": 0})

        sorted_by_dist = [torp_b, torp_c, torp_a]
        torp_distances = {"a": 1800.0, "b": 500.0, "c": 1000.0}

        result = Simulator._pick_priority_target(
            priority_list=["c", "b", "a"],
            sorted_by_dist=sorted_by_dist,
            torp_distances=torp_distances,
            effective_range=2000.0,
        )
        # "c" is first in priority list and in range
        assert result.id == "c"

    def test_skips_out_of_range_priority(self):
        """Skips priority targets that are out of range."""
        from hybrid.simulator import Simulator

        torp_far = FakeTorpedo(id="far", target_id="x", position={"x": 5000, "y": 0, "z": 0})
        torp_close = FakeTorpedo(id="close", target_id="x", position={"x": 800, "y": 0, "z": 0})

        sorted_by_dist = [torp_close, torp_far]
        torp_distances = {"far": 5000.0, "close": 800.0}

        result = Simulator._pick_priority_target(
            priority_list=["far", "close"],
            sorted_by_dist=sorted_by_dist,
            torp_distances=torp_distances,
            effective_range=2000.0,
        )
        # "far" is out of range, should fall through to "close"
        assert result.id == "close"

    def test_fallback_to_closest_on_empty_priority(self):
        """Empty priority list falls back to closest in-range torpedo."""
        from hybrid.simulator import Simulator

        torp_a = FakeTorpedo(id="a", target_id="x", position={"x": 1500, "y": 0, "z": 0})
        torp_b = FakeTorpedo(id="b", target_id="x", position={"x": 600, "y": 0, "z": 0})

        sorted_by_dist = [torp_b, torp_a]
        torp_distances = {"a": 1500.0, "b": 600.0}

        result = Simulator._pick_priority_target(
            priority_list=[],
            sorted_by_dist=sorted_by_dist,
            torp_distances=torp_distances,
            effective_range=2000.0,
        )
        assert result.id == "b"

    def test_returns_none_when_nothing_in_range(self):
        """Returns None when no torpedoes are within range."""
        from hybrid.simulator import Simulator

        torp = FakeTorpedo(id="far", target_id="x", position={"x": 5000, "y": 0, "z": 0})
        result = Simulator._pick_priority_target(
            priority_list=["far"],
            sorted_by_dist=[torp],
            torp_distances={"far": 5000.0},
            effective_range=2000.0,
        )
        assert result is None
