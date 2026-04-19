# tests/systems/combat/test_auto_fire.py
"""Tests for server-side auto-fire authorization manager."""

import pytest
from unittest.mock import MagicMock, PropertyMock
from enum import Enum

from hybrid.systems.combat.auto_fire_manager import AutoFireManager


class MockLockState(Enum):
    """Mock lock state enum matching targeting system."""
    NONE = "none"
    ACQUIRING = "acquiring"
    LOCKED = "locked"


def _make_mock_ship(locked_target: str = "C001", lock_state: str = "locked"):
    """Create a mock ship with targeting system.

    Args:
        locked_target: Contact ID of locked target, or None.
        lock_state: Lock state string.

    Returns:
        MagicMock: Ship mock with systems.targeting configured.
    """
    targeting = MagicMock()
    targeting.locked_target = locked_target
    targeting.lock_state = MockLockState(lock_state)

    ship = MagicMock()
    ship.systems = {"targeting": targeting}
    ship._all_ships_ref = []
    return ship


def _make_mock_combat(
    railgun_ammo: int = 10,
    railgun_can_fire: bool = True,
    railgun_solution_ready: bool = True,
    torpedoes_loaded: int = 4,
    torpedo_cooldown: float = 0.0,
    missiles_loaded: int = 8,
    missile_cooldown: float = 0.0,
    railgun_cycle_time: float = 5.0,
):
    """Create a mock CombatSystem with configurable state.

    Returns:
        MagicMock: CombatSystem mock.
    """
    combat = MagicMock()

    # Railgun mock
    railgun = MagicMock()
    railgun.ammo = railgun_ammo
    railgun.can_fire.return_value = railgun_can_fire
    railgun.specs = MagicMock()
    railgun.specs.cycle_time = railgun_cycle_time
    solution = MagicMock()
    solution.ready_to_fire = railgun_solution_ready
    railgun.current_solution = solution if railgun_solution_ready else None

    combat.truth_weapons = {"railgun_1": railgun}
    combat._sim_time = 100.0

    # Torpedo state
    combat.torpedoes_loaded = torpedoes_loaded
    combat._torpedo_cooldown = torpedo_cooldown
    combat.torpedo_reload_time = 15.0

    # Missile state
    combat.missiles_loaded = missiles_loaded
    combat._missile_cooldown = missile_cooldown
    combat.missile_reload_time = 8.0

    # fire_weapon returns success
    combat.fire_weapon.return_value = {"ok": True, "message": "Fired"}
    combat.launch_torpedo.return_value = {"ok": True, "message": "Torpedo launched"}
    combat.launch_missile.return_value = {"ok": True, "message": "Missile launched"}

    return combat


class TestAuthorization:
    """Tests for authorize/deauthorize state management."""

    def test_initial_state_all_deauthorized(self):
        """All weapon types start deauthorized."""
        mgr = AutoFireManager()
        state = mgr.get_state()
        assert state["authorized"] == {"railgun": False, "torpedo": False, "missile": False, "pdc": False}

    def test_authorize_railgun(self):
        """Authorizing railgun sets its state to True."""
        mgr = AutoFireManager()
        result = mgr.authorize("railgun")
        assert result["ok"] is True
        assert mgr.get_state()["authorized"]["railgun"] is True

    def test_authorize_torpedo(self):
        """Authorizing torpedo sets its state to True."""
        mgr = AutoFireManager()
        result = mgr.authorize("torpedo")
        assert result["ok"] is True
        assert mgr.get_state()["authorized"]["torpedo"] is True

    def test_authorize_missile_with_config(self):
        """Authorizing missile stores count and profile config."""
        mgr = AutoFireManager()
        result = mgr.authorize("missile", count=3, profile="evasive")
        assert result["ok"] is True
        assert mgr.get_state()["authorized"]["missile"] is True
        assert mgr.get_state()["missile_config"]["count"] == 3
        assert mgr.get_state()["missile_config"]["profile"] == "evasive"

    def test_deauthorize(self):
        """Deauthorizing a weapon sets its state to False."""
        mgr = AutoFireManager()
        mgr.authorize("railgun")
        result = mgr.deauthorize("railgun")
        assert result["ok"] is True
        assert mgr.get_state()["authorized"]["railgun"] is False

    def test_authorize_invalid_type(self):
        """Authorizing an invalid weapon type returns error."""
        mgr = AutoFireManager()
        result = mgr.authorize("laser")
        assert "error" in result

    def test_deauthorize_invalid_type(self):
        """Deauthorizing an invalid weapon type returns error."""
        mgr = AutoFireManager()
        result = mgr.deauthorize("phaser")
        assert "error" in result

    def test_cease_fire_clears_all(self):
        """Cease fire deauthorizes all weapon types."""
        mgr = AutoFireManager()
        mgr.authorize("railgun")
        mgr.authorize("torpedo")
        mgr.authorize("missile")

        result = mgr.cease_fire()
        assert result["ok"] is True
        state = mgr.get_state()
        assert state["authorized"] == {"railgun": False, "torpedo": False, "missile": False, "pdc": False}


class TestTickRailgun:
    """Tests for railgun auto-fire behavior in tick()."""

    def test_fires_when_all_conditions_met(self):
        """Railgun fires when authorized + locked + solution + ammo + cooldown."""
        mgr = AutoFireManager()
        mgr.authorize("railgun")

        combat = _make_mock_combat()
        ship = _make_mock_ship()

        events = mgr.tick(0.1, combat, ship)

        assert len(events) == 1
        assert events[0]["ok"] is True
        assert events[0]["weapon_type"] == "railgun"
        assert events[0]["auto_fire"] is True
        combat.fire_weapon.assert_called_once_with("railgun_1")

    def test_does_not_fire_when_no_lock(self):
        """Railgun does not fire when target is not locked."""
        mgr = AutoFireManager()
        mgr.authorize("railgun")

        combat = _make_mock_combat()
        ship = _make_mock_ship(lock_state="acquiring")

        events = mgr.tick(0.1, combat, ship)
        assert len(events) == 0
        combat.fire_weapon.assert_not_called()

    def test_does_not_fire_when_no_target(self):
        """Railgun does not fire when no target is locked."""
        mgr = AutoFireManager()
        mgr.authorize("railgun")

        combat = _make_mock_combat()
        ship = _make_mock_ship(locked_target=None, lock_state="none")

        events = mgr.tick(0.1, combat, ship)
        assert len(events) == 0

    def test_does_not_fire_when_no_ammo(self):
        """Railgun does not fire when ammo is depleted."""
        mgr = AutoFireManager()
        mgr.authorize("railgun")

        combat = _make_mock_combat(railgun_ammo=0)
        ship = _make_mock_ship()

        events = mgr.tick(0.1, combat, ship)
        assert len(events) == 0

    def test_does_not_fire_when_no_solution(self):
        """Railgun does not fire when firing solution is not ready."""
        mgr = AutoFireManager()
        mgr.authorize("railgun")

        combat = _make_mock_combat(railgun_solution_ready=False)
        ship = _make_mock_ship()

        events = mgr.tick(0.1, combat, ship)
        assert len(events) == 0

    def test_does_not_fire_when_not_authorized(self):
        """Railgun does not fire when not authorized."""
        mgr = AutoFireManager()
        # Not authorized

        combat = _make_mock_combat()
        ship = _make_mock_ship()

        events = mgr.tick(0.1, combat, ship)
        assert len(events) == 0

    def test_stays_authorized_after_fire(self):
        """Railgun stays authorized after firing (continuous mode)."""
        mgr = AutoFireManager()
        mgr.authorize("railgun")

        combat = _make_mock_combat()
        ship = _make_mock_ship()

        mgr.tick(0.1, combat, ship)
        assert mgr.get_state()["authorized"]["railgun"] is True

    def test_cooldown_prevents_rapid_fire(self):
        """Cooldown prevents railgun from firing on consecutive ticks."""
        mgr = AutoFireManager()
        mgr.authorize("railgun")

        combat = _make_mock_combat(railgun_cycle_time=5.0)
        ship = _make_mock_ship()

        # First tick: fires
        events1 = mgr.tick(0.1, combat, ship)
        assert len(events1) == 1

        # Reset fire_weapon mock call count
        combat.fire_weapon.reset_mock()

        # Second tick immediately after: cooldown blocks fire
        events2 = mgr.tick(0.1, combat, ship)
        assert len(events2) == 0
        combat.fire_weapon.assert_not_called()

        # After cooldown elapses (5s): fires again
        combat.fire_weapon.reset_mock()
        events3 = mgr.tick(5.0, combat, ship)
        assert len(events3) == 1


class TestTickTorpedo:
    """Tests for torpedo auto-fire behavior in tick()."""

    def test_fires_and_deauthorizes(self):
        """Torpedo fires once and auto-deauthorizes."""
        mgr = AutoFireManager()
        mgr.authorize("torpedo")

        combat = _make_mock_combat()
        ship = _make_mock_ship()

        events = mgr.tick(0.1, combat, ship)

        assert len(events) == 1
        assert events[0]["weapon_type"] == "torpedo"
        # Torpedo should auto-deauthorize after firing
        assert mgr.get_state()["authorized"]["torpedo"] is False

    def test_does_not_fire_when_no_torpedoes(self):
        """Torpedo does not fire when magazine is empty."""
        mgr = AutoFireManager()
        mgr.authorize("torpedo")

        combat = _make_mock_combat(torpedoes_loaded=0)
        ship = _make_mock_ship()

        events = mgr.tick(0.1, combat, ship)
        assert len(events) == 0
        # Should still be authorized (conditions not met, not fired)
        assert mgr.get_state()["authorized"]["torpedo"] is True

    def test_does_not_fire_when_on_cooldown(self):
        """Torpedo does not fire when launcher is on cooldown."""
        mgr = AutoFireManager()
        mgr.authorize("torpedo")

        combat = _make_mock_combat(torpedo_cooldown=10.0)
        ship = _make_mock_ship()

        events = mgr.tick(0.1, combat, ship)
        assert len(events) == 0


class TestTickMissile:
    """Tests for missile auto-fire behavior in tick()."""

    def test_fires_and_deauthorizes(self):
        """Missile fires once and auto-deauthorizes."""
        mgr = AutoFireManager()
        mgr.authorize("missile", profile="evasive")

        combat = _make_mock_combat()
        ship = _make_mock_ship()

        events = mgr.tick(0.1, combat, ship)

        assert len(events) == 1
        assert events[0]["weapon_type"] == "missile"
        # Missile should auto-deauthorize after firing
        assert mgr.get_state()["authorized"]["missile"] is False
        # Verify profile was passed
        combat.launch_missile.assert_called_once()
        call_args = combat.launch_missile.call_args
        assert call_args[0][1] == "evasive"

    def test_does_not_fire_when_no_missiles(self):
        """Missile does not fire when magazine is empty."""
        mgr = AutoFireManager()
        mgr.authorize("missile")

        combat = _make_mock_combat(missiles_loaded=0)
        ship = _make_mock_ship()

        events = mgr.tick(0.1, combat, ship)
        assert len(events) == 0
        assert mgr.get_state()["authorized"]["missile"] is True


class TestCooldownDecay:
    """Tests for cooldown tick-down behavior."""

    def test_cooldowns_decay_over_time(self):
        """Cooldowns decrease by dt each tick."""
        mgr = AutoFireManager()
        mgr._cooldowns["railgun"] = 5.0

        # Tick with no authorized weapons (just decay cooldowns)
        ship = _make_mock_ship(locked_target=None, lock_state="none")
        combat = _make_mock_combat()

        mgr.tick(2.0, combat, ship)
        assert mgr._cooldowns["railgun"] == pytest.approx(3.0)

    def test_cooldowns_do_not_go_negative(self):
        """Cooldowns clamp at zero."""
        mgr = AutoFireManager()
        mgr._cooldowns["torpedo"] = 1.0

        ship = _make_mock_ship(locked_target=None, lock_state="none")
        combat = _make_mock_combat()

        mgr.tick(5.0, combat, ship)
        assert mgr._cooldowns["torpedo"] == 0.0
