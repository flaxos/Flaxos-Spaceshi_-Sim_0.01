# tests/test_drone_system.py
"""Tests for the Phase 3A drone system.

Covers:
  - DroneBaySystem init, storage, tick pruning
  - Drone launch creates a Ship in the simulator
  - Drone recall sets autopilot
  - Drone status reports correctly
  - Command registration (system_commands, station_types, CommandSpec)
  - Ship class JSON files load through the registry
  - Decoy role in ROLE_DEFAULTS
"""

import pytest
import math
from unittest.mock import MagicMock, patch

from hybrid.systems.drone_bay import DroneBaySystem, DRONE_TYPES, DRONE_ROLE_MAP
from hybrid.ship import Ship
from hybrid.simulator import Simulator
from hybrid.fleet.npc_behavior import ROLE_DEFAULTS, get_profile, infer_role


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def parent_ship():
    """Create a minimal parent ship for testing."""
    ship = Ship("test_parent", {
        "name": "Test Corvette",
        "mass": 1200.0,
        "faction": "UNE",
        "position": {"x": 1000.0, "y": 2000.0, "z": 0.0},
        "velocity": {"x": 50.0, "y": 0.0, "z": 0.0},
    })
    ship._all_ships_ref = [ship]
    return ship


@pytest.fixture
def drone_bay_config():
    """Standard drone bay config with one of each type."""
    return {
        "capacity": 6,
        "stored_drones": [
            {"drone_type": "drone_sensor"},
            {"drone_type": "drone_sensor"},
            {"drone_type": "drone_combat"},
            {"drone_type": "drone_decoy"},
        ],
    }


@pytest.fixture
def drone_bay(drone_bay_config):
    """Create a DroneBaySystem with standard config."""
    return DroneBaySystem(drone_bay_config)


@pytest.fixture
def simulator():
    """Create a Simulator for spawn tests."""
    return Simulator(dt=0.1)


# ── Init Tests ───────────────────────────────────────────────────

class TestDroneBayInit:
    def test_capacity_from_config(self, drone_bay):
        assert drone_bay.capacity == 6

    def test_default_capacity(self):
        bay = DroneBaySystem({})
        assert bay.capacity == 4

    def test_stored_drones_loaded(self, drone_bay):
        assert len(drone_bay.stored_drones) == 4
        types = [s["drone_type"] for s in drone_bay.stored_drones]
        assert types.count("drone_sensor") == 2
        assert types.count("drone_combat") == 1
        assert types.count("drone_decoy") == 1

    def test_invalid_type_filtered(self):
        bay = DroneBaySystem({
            "stored_drones": [
                {"drone_type": "drone_sensor"},
                {"drone_type": "invalid_drone"},
                {"drone_type": "drone_combat"},
            ]
        })
        assert len(bay.stored_drones) == 2

    def test_empty_config(self):
        bay = DroneBaySystem()
        assert bay.capacity == 4
        assert bay.stored_drones == []
        assert bay.active_drones == {}


# ── Launch Tests ─────────────────────────────────────────────────

class TestDroneLaunch:
    def test_launch_creates_ship_in_sim(self, drone_bay, parent_ship, simulator):
        """Launching a drone should add a Ship to the simulator."""
        result = drone_bay._cmd_launch_drone({
            "drone_type": "drone_sensor",
            "ship": parent_ship,
            "_simulator": simulator,
        })

        assert result.get("ok") is True
        drone_id = result["drone_id"]

        # Ship exists in the simulator
        assert drone_id in simulator.ships
        drone_ship = simulator.ships[drone_id]

        # Parent reference is set
        assert drone_ship.parent_ship_id == parent_ship.id

    def test_launch_removes_from_stored(self, drone_bay, parent_ship, simulator):
        """Launch should consume one drone from stored inventory."""
        initial_count = len(drone_bay.stored_drones)
        drone_bay._cmd_launch_drone({
            "drone_type": "drone_sensor",
            "ship": parent_ship,
            "_simulator": simulator,
        })
        assert len(drone_bay.stored_drones) == initial_count - 1

    def test_launch_tracks_active(self, drone_bay, parent_ship, simulator):
        """Launched drone should appear in active_drones."""
        result = drone_bay._cmd_launch_drone({
            "drone_type": "drone_combat",
            "ship": parent_ship,
            "_simulator": simulator,
        })
        drone_id = result["drone_id"]
        assert drone_id in drone_bay.active_drones
        assert drone_bay.active_drones[drone_id]["drone_type"] == "drone_combat"

    def test_launch_position_offset(self, drone_bay, parent_ship, simulator):
        """Drone should spawn 50m from parent, not on top of it."""
        result = drone_bay._cmd_launch_drone({
            "drone_type": "drone_sensor",
            "ship": parent_ship,
            "_simulator": simulator,
        })
        drone_ship = simulator.ships[result["drone_id"]]

        dx = drone_ship.position["x"] - parent_ship.position["x"]
        dy = drone_ship.position["y"] - parent_ship.position["y"]
        dz = drone_ship.position["z"] - parent_ship.position["z"]
        dist = math.sqrt(dx*dx + dy*dy + dz*dz)

        assert abs(dist - 50.0) < 1.0, f"Expected ~50m offset, got {dist:.1f}m"

    def test_launch_matches_parent_velocity(self, drone_bay, parent_ship, simulator):
        """Drone should inherit parent velocity so it doesn't drift away."""
        result = drone_bay._cmd_launch_drone({
            "drone_type": "drone_sensor",
            "ship": parent_ship,
            "_simulator": simulator,
        })
        drone_ship = simulator.ships[result["drone_id"]]

        assert drone_ship.velocity["x"] == parent_ship.velocity["x"]
        assert drone_ship.velocity["y"] == parent_ship.velocity["y"]

    def test_launch_invalid_type(self, drone_bay, parent_ship, simulator):
        result = drone_bay._cmd_launch_drone({
            "drone_type": "drone_warship",
            "ship": parent_ship,
            "_simulator": simulator,
        })
        assert result.get("ok") is False
        assert "INVALID_TYPE" in result.get("error", "")

    def test_launch_empty_bay(self, parent_ship, simulator):
        """Cannot launch a drone type that is not in storage."""
        bay = DroneBaySystem({"stored_drones": [{"drone_type": "drone_sensor"}]})
        result = bay._cmd_launch_drone({
            "drone_type": "drone_combat",
            "ship": parent_ship,
            "_simulator": simulator,
        })
        assert result.get("ok") is False
        assert "NOT_IN_BAY" in result.get("error", "")

    def test_launch_no_simulator(self, drone_bay, parent_ship):
        """Launch fails gracefully without a simulator reference."""
        result = drone_bay._cmd_launch_drone({
            "drone_type": "drone_sensor",
            "ship": parent_ship,
            "_simulator": None,
        })
        assert result.get("ok") is False
        assert "NO_SIMULATOR" in result.get("error", "")

    def test_launch_inherits_faction(self, drone_bay, parent_ship, simulator):
        """Drone should have the same faction as the parent ship."""
        result = drone_bay._cmd_launch_drone({
            "drone_type": "drone_sensor",
            "ship": parent_ship,
            "_simulator": simulator,
        })
        drone_ship = simulator.ships[result["drone_id"]]
        assert drone_ship.faction == parent_ship.faction


# ── Tick / Pruning Tests ─────────────────────────────────────────

class TestDroneTick:
    def test_tick_prunes_destroyed_drones(self, drone_bay, parent_ship, simulator):
        """Destroyed drones are removed from active_drones on tick."""
        # Launch a drone
        result = drone_bay._cmd_launch_drone({
            "drone_type": "drone_sensor",
            "ship": parent_ship,
            "_simulator": simulator,
        })
        drone_id = result["drone_id"]
        assert drone_id in drone_bay.active_drones

        # Simulate destruction: remove from simulator
        simulator.remove_ship(drone_id)

        # Update parent's all_ships ref to reflect removal
        parent_ship._all_ships_ref = list(simulator.ships.values())

        # Tick should prune it
        drone_bay.tick(0.1, parent_ship)
        assert drone_id not in drone_bay.active_drones

    def test_tick_keeps_alive_drones(self, drone_bay, parent_ship, simulator):
        """Living drones remain in active_drones after tick."""
        result = drone_bay._cmd_launch_drone({
            "drone_type": "drone_sensor",
            "ship": parent_ship,
            "_simulator": simulator,
        })
        drone_id = result["drone_id"]

        parent_ship._all_ships_ref = list(simulator.ships.values())
        drone_bay.tick(0.1, parent_ship)
        assert drone_id in drone_bay.active_drones


# ── Recall Tests ─────────────────────────────────────────────────

class TestDroneRecall:
    def test_recall_unknown_drone(self, drone_bay, parent_ship, simulator):
        result = drone_bay._cmd_recall_drone({
            "drone_id": "nonexistent",
            "ship": parent_ship,
            "_simulator": simulator,
        })
        assert result.get("ok") is False
        assert "DRONE_NOT_FOUND" in result.get("error", "")

    def test_recall_destroyed_drone(self, drone_bay, parent_ship, simulator):
        """Recalling a destroyed drone cleans up tracking."""
        result = drone_bay._cmd_launch_drone({
            "drone_type": "drone_sensor",
            "ship": parent_ship,
            "_simulator": simulator,
        })
        drone_id = result["drone_id"]

        # Destroy it
        simulator.remove_ship(drone_id)

        recall_result = drone_bay._cmd_recall_drone({
            "drone_id": drone_id,
            "ship": parent_ship,
            "_simulator": simulator,
        })
        assert recall_result.get("ok") is False
        assert "DRONE_DESTROYED" in recall_result.get("error", "")
        # Should have cleaned up
        assert drone_id not in drone_bay.active_drones


# ── Status Tests ─────────────────────────────────────────────────

class TestDroneStatus:
    def test_status_empty_bay(self):
        bay = DroneBaySystem()
        result = bay._cmd_drone_status({})
        assert result["ok"] is True
        assert result["capacity"] == 4
        assert result["stored_count"] == 0
        assert result["active_count"] == 0

    def test_status_with_stored(self, drone_bay):
        result = drone_bay._cmd_drone_status({})
        assert result["stored_count"] == 4
        assert len(result["stored_drones"]) == 4

    def test_status_with_active(self, drone_bay, parent_ship, simulator):
        drone_bay._cmd_launch_drone({
            "drone_type": "drone_sensor",
            "ship": parent_ship,
            "_simulator": simulator,
        })
        result = drone_bay._cmd_drone_status({
            "ship": parent_ship,
            "_simulator": simulator,
        })
        assert result["active_count"] == 1
        assert len(result["active_drones"]) == 1
        active = result["active_drones"][0]
        assert "drone_id" in active
        assert active["drone_type"] == "drone_sensor"


# ── Command Registration Tests ───────────────────────────────────

class TestDroneCommandRegistration:
    def test_system_commands_registered(self):
        """Drone commands exist in system_commands dict."""
        from hybrid.command_handler import system_commands
        for cmd in ("launch_drone", "recall_drone", "set_drone_behavior", "drone_status"):
            assert cmd in system_commands, f"{cmd} missing from system_commands"
            assert system_commands[cmd][0] == "drone_bay"

    def test_station_types_registered(self):
        """Drone commands exist in OPS station command set."""
        from server.stations.station_types import STATION_DEFINITIONS, StationType
        ops_cmds = STATION_DEFINITIONS[StationType.OPS].commands
        for cmd in ("launch_drone", "recall_drone", "set_drone_behavior", "drone_status"):
            assert cmd in ops_cmds, f"{cmd} missing from OPS station commands"

    def test_command_specs_registered(self):
        """Drone commands are registered in the CommandSpec dispatcher."""
        from hybrid.commands.dispatch import create_default_dispatcher
        dispatcher = create_default_dispatcher()
        for cmd in ("launch_drone", "recall_drone", "set_drone_behavior", "drone_status"):
            assert cmd in dispatcher.commands, f"{cmd} missing from dispatcher specs"

    def test_system_map_includes_drone_bay(self):
        """DroneBaySystem is in the systems __init__ registry."""
        from hybrid.systems import get_system_class
        cls = get_system_class("drone_bay")
        assert cls is DroneBaySystem


# ── Ship Class JSON Tests ────────────────────────────────────────

class TestDroneShipClasses:
    def test_all_drone_classes_loadable(self):
        """All three drone class JSONs load through the registry."""
        from hybrid.ship_class_registry import get_registry

        # Force reload to pick up new files
        import hybrid.ship_class_registry as mod
        mod._registry = None
        registry = get_registry()

        for class_id in ("drone_sensor", "drone_combat", "drone_decoy"):
            data = registry.get_class(class_id)
            assert data is not None, f"Ship class '{class_id}' not found"
            assert data["class_id"] == class_id

    def test_drone_sensor_has_no_weapons(self):
        from hybrid.ship_class_registry import get_registry
        import hybrid.ship_class_registry as mod
        mod._registry = None
        data = get_registry().get_class("drone_sensor")
        assert data["weapon_mounts"] == []
        assert "combat" not in data.get("systems", {})

    def test_drone_combat_has_pdc(self):
        from hybrid.ship_class_registry import get_registry
        import hybrid.ship_class_registry as mod
        mod._registry = None
        data = get_registry().get_class("drone_combat")
        mounts = data["weapon_mounts"]
        assert len(mounts) == 1
        assert mounts[0]["weapon_type"] == "pdc"

    def test_drone_decoy_has_ecm(self):
        from hybrid.ship_class_registry import get_registry
        import hybrid.ship_class_registry as mod
        mod._registry = None
        data = get_registry().get_class("drone_decoy")
        ecm = data["systems"]["ecm"]
        assert ecm["jammer_enabled"] is True
        assert ecm["jammer_power"] > 0

    def test_drone_decoy_inflated_ir(self):
        from hybrid.ship_class_registry import get_registry
        import hybrid.ship_class_registry as mod
        mod._registry = None
        data = get_registry().get_class("drone_decoy")
        ir = data["systems"]["sensors"]["ir_modifier"]
        assert ir >= 10.0, f"Decoy IR modifier should be >= 10x, got {ir}"


# ── NPC Behavior Tests ───────────────────────────────────────────

class TestDecoyRole:
    def test_decoy_in_role_defaults(self):
        assert "decoy" in ROLE_DEFAULTS

    def test_decoy_profile_values(self):
        profile = ROLE_DEFAULTS["decoy"]
        assert profile.aggression == 1.0
        assert profile.flee_threshold == 0.0
        assert profile.evade_threshold == 0.0
        # Decoys never fire — weapon_confidence_threshold is impossible to meet
        assert profile.weapon_confidence_threshold >= 1.0

    def test_get_profile_decoy(self):
        profile = get_profile("decoy")
        assert profile.role == "decoy"

    def test_infer_role_drone_classes(self):
        assert infer_role("drone_sensor", "UNE") == "patrol"
        assert infer_role("drone_combat", "UNE") == "defender"
        assert infer_role("drone_decoy", "UNE") == "decoy"
