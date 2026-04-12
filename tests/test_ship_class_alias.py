"""Regression tests for backward-compatible ship class resolution.

Several legacy scenarios still declare hulls with ``class: corvette`` instead
of ``ship_class: corvette``. Those ships must still inherit their class-defined
systems and mass metadata, otherwise station wiring silently disappears.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


SCENARIO_01 = ROOT_DIR / "scenarios" / "01_tutorial_intercept.yaml"


def _reset_registry() -> None:
    import hybrid.ship_class_registry as registry_module

    registry_module._registry = None


def test_class_field_resolves_known_ship_class() -> None:
    """Known hull IDs in ``class`` should resolve just like ``ship_class``."""
    _reset_registry()

    from hybrid.ship_class_registry import get_registry

    registry = get_registry()
    resolved = registry.resolve_ship_config({
        "id": "player",
        "class": "corvette",
        "systems": {
            "propulsion": {
                "max_thrust": 500000,
                "fuel_level": 10000,
                "max_fuel": 10000,
            }
        },
    })

    systems = resolved.get("systems", {})
    assert resolved.get("dry_mass") == 1200.0
    assert systems["propulsion"]["max_thrust"] == 500000
    assert "power_management" in systems
    assert "combat" in systems
    assert systems["power_management"]["primary"]["output"] == 100.0


def test_tutorial_player_inherits_class_defined_systems() -> None:
    """Tutorial intercept player ship must load its full corvette baseline."""
    from hybrid.scenarios.loader import ScenarioLoader

    scenario = ScenarioLoader.load(str(SCENARIO_01))
    player = next(ship for ship in scenario["ships"] if ship["id"] == "player")

    systems = player["systems"]
    assert "power_management" in systems
    assert "combat" in systems
    assert player["dry_mass"] == 1200.0


def test_tutorial_player_can_accelerate_with_power_management_enabled() -> None:
    """The tutorial player ship must still thrust after class systems resolve."""
    from hybrid.command_handler import route_command
    from hybrid_runner import HybridRunner

    runner = HybridRunner(dt=0.1)
    count = runner._load_scenario_file(str(SCENARIO_01))
    assert count >= 1
    runner.simulator.start()

    player = runner.simulator.ships["player"]
    start_speed = math.sqrt(sum(player.velocity[axis] ** 2 for axis in ("x", "y", "z")))

    result = route_command(
        player,
        {"command": "set_thrust", "ship": "player", "thrust": 0.25},
        list(runner.simulator.ships.values()),
    )
    assert not result.get("error"), result

    for _ in range(50):
        runner.simulator.tick()

    end_speed = math.sqrt(sum(player.velocity[axis] ** 2 for axis in ("x", "y", "z")))
    assert end_speed > start_speed + 10.0, (
        f"Expected manual thrust to accelerate the tutorial ship, got start={start_speed:.2f} end={end_speed:.2f}"
    )
