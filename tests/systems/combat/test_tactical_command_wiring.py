"""Regression coverage for tactical command wiring consistency."""

from unittest.mock import MagicMock


def test_dispatcher_launch_torpedo_uses_combat_system_not_legacy_weapons():
    """Typed tactical command path should launch through CombatSystem.

    The GUI's live path already routes launch_torpedo to combat. Keep the
    registered tactical command path aligned so tests, tools, and alternate
    dispatchers do not silently fall back to legacy weapons.fire().
    """
    from hybrid.commands.dispatch import create_default_dispatcher

    dispatcher = create_default_dispatcher()

    combat = MagicMock()
    combat.launch_torpedo.return_value = {"ok": True, "via": "combat"}

    targeting = MagicMock()
    targeting.locked_target = "C001"

    legacy_weapons = MagicMock()

    ship = MagicMock()
    ship.id = "player"
    ship.systems = {
        "combat": combat,
        "targeting": targeting,
        "weapons": legacy_weapons,
    }

    result = dispatcher.dispatch("launch_torpedo", ship, {"profile": "direct"})

    assert result["ok"] is True
    assert result["via"] == "combat"
    combat.launch_torpedo.assert_called_once_with(
        "C001", "direct", {},
        warhead_type=None, guidance_mode=None,
    )
    legacy_weapons.fire.assert_not_called()


def test_dispatcher_set_pdc_mode_uses_combat_command_path():
    """Registered tactical PDC mode command should delegate to combat.command()."""
    from hybrid.commands.dispatch import create_default_dispatcher

    dispatcher = create_default_dispatcher()

    combat = MagicMock()
    combat.command.return_value = {"ok": True, "mode": "network"}

    ship = MagicMock()
    ship.id = "player"
    ship.systems = {"combat": combat}

    result = dispatcher.dispatch("set_pdc_mode", ship, {"mode": "network"})

    assert result["ok"] is True
    assert result["mode"] == "network"
    combat.command.assert_called_once_with("set_pdc_mode", {"mode": "network"})


def test_dispatcher_set_pdc_priority_uses_combat_command_path():
    """Registered tactical PDC priority command should delegate to combat.command()."""
    from hybrid.commands.dispatch import create_default_dispatcher

    dispatcher = create_default_dispatcher()

    combat = MagicMock()
    combat.command.return_value = {"ok": True, "torpedo_ids": ["torp_1"]}

    ship = MagicMock()
    ship.id = "player"
    ship.systems = {"combat": combat}

    result = dispatcher.dispatch("set_pdc_priority", ship, {"torpedo_ids": ["torp_1"]})

    assert result["ok"] is True
    assert result["torpedo_ids"] == ["torp_1"]
    combat.command.assert_called_once_with("set_pdc_priority", {"torpedo_ids": ["torp_1"]})
