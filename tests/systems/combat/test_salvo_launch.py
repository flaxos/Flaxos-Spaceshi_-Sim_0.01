# tests/systems/combat/test_salvo_launch.py
"""Tests for server-side salvo launch — staggered missile/torpedo fire.

The salvo queue replaces client-side setTimeout stagger with authoritative
server tick-based timing.  Each tick pops one launch config from the queue
when the stagger interval has elapsed.
"""

import pytest
from unittest.mock import MagicMock, patch
from hybrid.systems.combat.combat_system import CombatSystem


def _make_combat(missiles: int = 8, torpedoes: int = 4) -> CombatSystem:
    """Create a CombatSystem with missile and torpedo launchers for testing."""
    config = {
        "railguns": 0,
        "pdcs": 0,
        "missiles": 1,
        "missile_capacity": missiles,
        "torpedoes": 1,
        "torpedo_capacity": torpedoes,
    }
    combat = CombatSystem(config)
    # Wire up a minimal ship reference so launch_salvo can resolve target
    ship = MagicMock()
    ship.id = "player_ship"
    ship.position = {"x": 0, "y": 0, "z": 0}
    ship.velocity = {"x": 0, "y": 0, "z": 0}
    ship._all_ships_ref = []
    targeting = MagicMock()
    targeting.locked_target = "enemy_1"
    ship.systems = {"targeting": targeting}
    combat._ship_ref = ship
    combat._damage_factor = 1.0
    return combat


class TestLaunchSalvoQueuing:
    """Verify that launch_salvo correctly queues munitions."""

    def test_salvo_queues_correct_count(self):
        """launch_salvo with count=4 should queue 4 items."""
        combat = _make_combat(missiles=8)
        result = combat.launch_salvo(target="enemy_1", count=4, munition_type="missile")
        assert result.get("ok") is True
        assert result["count_queued"] == 4
        assert result["munition_type"] == "missile"
        assert result["salvo_id"].startswith("salvo_")
        # 4 items should be in the queue (first fires on next tick when timer=0)
        assert len(combat._salvo_queue) == 4

    def test_salvo_partial_when_insufficient_ammo(self):
        """If only 3 missiles remain but count=6, queue 3 (partial salvo)."""
        combat = _make_combat(missiles=3)
        result = combat.launch_salvo(target="enemy_1", count=6, munition_type="missile")
        assert result.get("ok") is True
        assert result["count_queued"] == 3
        assert len(combat._salvo_queue) == 3

    def test_salvo_no_ammo_returns_error(self):
        """Salvo with 0 missiles should return an error, not queue anything."""
        combat = _make_combat(missiles=0)
        result = combat.launch_salvo(target="enemy_1", count=4, munition_type="missile")
        assert result.get("ok") is False
        assert len(combat._salvo_queue) == 0

    def test_salvo_torpedo_type(self):
        """launch_salvo with munition_type='torpedo' should queue torpedo launches."""
        combat = _make_combat(torpedoes=4)
        result = combat.launch_salvo(target="enemy_1", count=2, munition_type="torpedo")
        assert result.get("ok") is True
        assert result["count_queued"] == 2
        assert result["munition_type"] == "torpedo"
        assert combat._salvo_queue[0]["munition_type"] == "torpedo"

    def test_salvo_invalid_munition_type(self):
        """Invalid munition_type should return an error."""
        combat = _make_combat()
        result = combat.launch_salvo(target="enemy_1", count=2, munition_type="railgun")
        assert result.get("ok") is False
        assert result.get("error") == "INVALID_MUNITION"

    def test_salvo_no_target_returns_error(self):
        """Salvo without a target (and no locked target) should fail."""
        combat = _make_combat()
        # Remove locked target
        combat._ship_ref.systems["targeting"].locked_target = None
        result = combat.launch_salvo(target=None, count=2, munition_type="missile")
        assert result.get("ok") is False

    def test_salvo_uses_locked_target_when_none_provided(self):
        """Salvo with no explicit target should fall back to locked target."""
        combat = _make_combat()
        result = combat.launch_salvo(count=2, munition_type="missile")
        assert result.get("ok") is True
        # Should have resolved from targeting system
        assert combat._salvo_queue[0]["target"] == "enemy_1"

    def test_salvo_stagger_timing_set(self):
        """stagger_ms should be converted to seconds and stored."""
        combat = _make_combat()
        combat.launch_salvo(target="enemy_1", count=2, stagger_ms=200)
        assert combat._salvo_stagger == 0.2

    def test_salvo_stagger_floor(self):
        """Stagger should not go below 50ms floor."""
        combat = _make_combat()
        combat.launch_salvo(target="enemy_1", count=2, stagger_ms=10)
        assert combat._salvo_stagger == 0.05


class TestSalvoTickProcessing:
    """Verify that tick() correctly dequeues salvo items."""

    def test_tick_dequeues_one_per_stagger(self):
        """After stagger interval elapses, one item should be popped from queue."""
        combat = _make_combat(missiles=8)
        combat.launch_salvo(target="enemy_1", count=4, munition_type="missile")
        initial_count = len(combat._salvo_queue)
        assert initial_count == 4

        # Patch launch_missile to avoid full missile launch logic
        with patch.object(combat, "launch_missile", return_value={"ok": True}) as mock_launch:
            ship = combat._ship_ref
            # First tick with dt=0 — timer is 0, should fire immediately
            combat._tick_salvo_queue(0.0, ship)
            assert mock_launch.call_count == 1
            assert len(combat._salvo_queue) == 3

    def test_tick_respects_stagger_timing(self):
        """Items should not dequeue until stagger timer elapses."""
        combat = _make_combat(missiles=8)
        combat.launch_salvo(target="enemy_1", count=4, munition_type="missile", stagger_ms=200)

        with patch.object(combat, "launch_missile", return_value={"ok": True}) as mock_launch:
            ship = combat._ship_ref
            # First tick fires immediately (timer starts at 0)
            combat._tick_salvo_queue(0.0, ship)
            assert mock_launch.call_count == 1

            # Tick with dt=0.1s — not enough for 200ms stagger
            combat._tick_salvo_queue(0.1, ship)
            assert mock_launch.call_count == 1  # no new launch

            # Tick with dt=0.15s — total 0.25s > 0.2s stagger, should fire
            combat._tick_salvo_queue(0.15, ship)
            assert mock_launch.call_count == 2

    def test_tick_drains_full_salvo(self):
        """Enough ticks should drain the entire salvo queue."""
        combat = _make_combat(missiles=8)
        combat.launch_salvo(target="enemy_1", count=3, munition_type="missile", stagger_ms=100)

        with patch.object(combat, "launch_missile", return_value={"ok": True}) as mock_launch:
            ship = combat._ship_ref
            # Fire all 3 with generous dt per tick
            for _ in range(10):
                combat._tick_salvo_queue(0.15, ship)

            assert mock_launch.call_count == 3
            assert len(combat._salvo_queue) == 0

    def test_tick_torpedo_salvo_calls_launch_torpedo(self):
        """Torpedo salvo should route through launch_torpedo, not launch_missile."""
        combat = _make_combat(torpedoes=4)
        combat.launch_salvo(target="enemy_1", count=2, munition_type="torpedo")

        with patch.object(combat, "launch_torpedo", return_value={"ok": True}) as mock_torp:
            with patch.object(combat, "launch_missile", return_value={"ok": True}) as mock_miss:
                ship = combat._ship_ref
                combat._tick_salvo_queue(0.0, ship)
                assert mock_torp.call_count == 1
                assert mock_miss.call_count == 0

    def test_empty_queue_is_noop(self):
        """Ticking with an empty queue should not error or launch anything."""
        combat = _make_combat()
        ship = combat._ship_ref
        # Should be a no-op
        combat._tick_salvo_queue(0.1, ship)
        assert len(combat._salvo_queue) == 0


class TestSalvoCommandRouting:
    """Verify the command() method routes launch_salvo correctly."""

    def test_command_routes_launch_salvo(self):
        """combat.command('launch_salvo', ...) should queue a salvo."""
        combat = _make_combat(missiles=8)
        result = combat.command("launch_salvo", {
            "count": 4,
            "munition_type": "missile",
            "profile": "evasive",
            "stagger_ms": 150,
        })
        assert result.get("ok") is True
        assert result["count_queued"] == 4
        assert len(combat._salvo_queue) == 4
        # Verify profile propagated
        assert combat._salvo_queue[0]["profile"] == "evasive"
