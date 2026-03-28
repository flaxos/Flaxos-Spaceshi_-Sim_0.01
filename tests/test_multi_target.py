# tests/test_multi_target.py
"""Tests for multi-target simultaneous tracking.

Validates:
- Track list management (add, remove, cycle)
- Bandwidth-sharing quality degradation
- PDC target assignment
- Split-fire weapon assignment
- Sensor health limiting max tracks
- Integration with TargetingSystem
- Command registration across all 3 required locations
"""

import pytest
from unittest.mock import MagicMock, patch
from hybrid.systems.targeting.multi_track import (
    MultiTrackManager,
    TrackSlot,
    BASE_MAX_TRACKS,
    QUALITY_PENALTY_PER_TRACK,
    SECONDARY_QUALITY_PENALTY,
)
from hybrid.systems.targeting.targeting_system import TargetingSystem, LockState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def manager():
    """Fresh MultiTrackManager with default settings."""
    return MultiTrackManager(base_max_tracks=4)


@pytest.fixture
def targeting():
    """TargetingSystem with a mock ship wired up."""
    ts = TargetingSystem({"lock_time": 0.5, "lock_range": 100000})
    ts._sensor_factor = 1.0
    ts._sim_time = 10.0
    return ts


def _make_mock_ship(contact_ids=None):
    """Create a mock ship with sensors that know about given contact IDs."""
    ship = MagicMock()
    ship.id = "player_ship"
    ship.position = {"x": 0, "y": 0, "z": 0}
    ship.velocity = {"x": 0, "y": 0, "z": 0}

    # Sensor system with contacts
    sensor_system = MagicMock()
    contacts = {}
    for cid in (contact_ids or []):
        contact = MagicMock()
        contact.id = cid
        contact.position = {"x": 1000, "y": 0, "z": 0}
        contact.velocity = {"x": 0, "y": 0, "z": 0}
        contact.confidence = 0.9
        contact.last_update = 10.0
        contact.detection_method = "ir"
        contact.bearing = {"az": 0, "el": 0}
        contact.distance = 1000
        contact.signature = 1.0
        contact.classification = "hostile"
        contact.name = f"Target-{cid}"
        contact.faction = "enemy"
        contacts[cid] = contact

    sensor_system.get_contact = lambda cid: contacts.get(cid)
    sensor_system.get_contacts = lambda: contacts

    # Combat system with weapons
    combat_system = MagicMock()
    combat_system.truth_weapons = {
        "railgun_1": MagicMock(),
        "pdc_1": MagicMock(),
        "pdc_2": MagicMock(),
    }

    ship.systems = {
        "sensors": sensor_system,
        "combat": combat_system,
        "targeting": None,  # Will be set per test
    }

    ship.get_effective_factor = MagicMock(return_value=1.0)
    ship.damage_model = MagicMock()
    ship.damage_model.get_degradation_factor = MagicMock(return_value=1.0)
    ship.event_bus = MagicMock()
    ship._all_ships_ref = []

    return ship


# ---------------------------------------------------------------------------
# MultiTrackManager unit tests
# ---------------------------------------------------------------------------

class TestMultiTrackManager:
    """Tests for the standalone MultiTrackManager."""

    def test_add_track(self, manager):
        result = manager.add_track("C001", sensor_factor=1.0)
        assert result["ok"] is True
        assert manager.track_count == 1
        assert manager.primary_target == "C001"

    def test_add_multiple_tracks(self, manager):
        manager.add_track("C001", 1.0)
        manager.add_track("C002", 1.0)
        manager.add_track("C003", 1.0)
        assert manager.track_count == 3
        assert manager.primary_target == "C001"

    def test_add_duplicate_rejected(self, manager):
        manager.add_track("C001", 1.0)
        result = manager.add_track("C001", 1.0)
        assert result["ok"] is False
        assert "ALREADY_TRACKING" in result["error"]

    def test_max_tracks_enforced(self, manager):
        for i in range(4):
            manager.add_track(f"C{i:03d}", 1.0)
        result = manager.add_track("C999", 1.0)
        assert result["ok"] is False
        assert "TRACK_LIST_FULL" in result["error"]

    def test_max_tracks_scales_with_sensor_damage(self, manager):
        """Damaged sensors reduce available track slots."""
        # At 50% sensor health, max tracks = 2 (4 * 0.5 = 2)
        manager.add_track("C001", 0.5)
        manager.add_track("C002", 0.5)
        result = manager.add_track("C003", 0.5)
        assert result["ok"] is False
        assert result["max_tracks"] == 2

    def test_max_tracks_minimum_one(self, manager):
        """Even at very low sensor health, at least 1 track is allowed."""
        assert manager.max_tracks(0.1) >= 1

    def test_remove_track(self, manager):
        manager.add_track("C001", 1.0)
        manager.add_track("C002", 1.0)
        result = manager.remove_track("C001")
        assert result["ok"] is True
        assert manager.track_count == 1
        assert manager.primary_target == "C002"

    def test_remove_nonexistent(self, manager):
        result = manager.remove_track("C999")
        assert result["ok"] is False

    def test_cycle_primary(self, manager):
        manager.add_track("C001", 1.0)
        manager.add_track("C002", 1.0)
        manager.add_track("C003", 1.0)

        result = manager.cycle_primary()
        assert result["ok"] is True
        assert result["new_primary"] == "C002"
        assert result["previous_primary"] == "C001"
        assert manager.primary_target == "C002"

    def test_cycle_wraps_around(self, manager):
        manager.add_track("C001", 1.0)
        manager.add_track("C002", 1.0)

        manager.cycle_primary()  # C001 -> C002
        manager.cycle_primary()  # C002 -> C001
        assert manager.primary_target == "C001"

    def test_cycle_insufficient_tracks(self, manager):
        manager.add_track("C001", 1.0)
        result = manager.cycle_primary()
        assert result["ok"] is False

    def test_quality_modifier_single_target(self, manager):
        manager.add_track("C001", 1.0)
        assert manager.get_quality_modifier(0) == 1.0

    def test_quality_degrades_with_more_tracks(self, manager):
        manager.add_track("C001", 1.0)
        manager.add_track("C002", 1.0)
        manager.add_track("C003", 1.0)
        manager.update_quality_modifiers()

        # Primary should be better than secondaries
        primary_q = manager.tracks[0].quality_modifier
        secondary_q = manager.tracks[1].quality_modifier
        assert primary_q > secondary_q, (
            f"Primary quality {primary_q} should exceed secondary {secondary_q}"
        )
        # Both should be less than 1.0
        assert primary_q < 1.0
        assert secondary_q < 1.0

    def test_quality_modifier_floor(self, manager):
        """Quality should never drop below minimum even with many tracks."""
        mgr = MultiTrackManager(base_max_tracks=10)
        for i in range(10):
            mgr.add_track(f"C{i:03d}", 1.0)
        mgr.update_quality_modifiers()
        for track in mgr.tracks:
            assert track.quality_modifier >= 0.2

    def test_assign_pdc_target(self, manager):
        manager.add_track("C001", 1.0)
        manager.add_track("C002", 1.0)

        result = manager.assign_pdc_target("pdc_1", "C002", ["pdc_1", "pdc_2"])
        assert result["ok"] is True
        assert manager.pdc_assignments["pdc_1"] == "C002"

    def test_assign_pdc_invalid_mount(self, manager):
        manager.add_track("C001", 1.0)
        result = manager.assign_pdc_target("railgun_1", "C001", ["pdc_1", "pdc_2"])
        assert result["ok"] is False
        assert "INVALID_PDC" in result["error"]

    def test_assign_pdc_untracked_contact(self, manager):
        result = manager.assign_pdc_target("pdc_1", "C999", ["pdc_1"])
        assert result["ok"] is False
        assert "NOT_TRACKING" in result["error"]

    def test_split_fire(self, manager):
        manager.add_track("C001", 1.0)
        manager.add_track("C002", 1.0)

        result = manager.assign_split_fire(
            "railgun_1", "C002", ["railgun_1", "pdc_1"]
        )
        assert result["ok"] is True
        assert manager.split_fire_assignments["railgun_1"] == "C002"

    def test_get_weapon_target_split_fire(self, manager):
        manager.add_track("C001", 1.0)
        manager.add_track("C002", 1.0)
        manager.assign_split_fire("railgun_1", "C002", ["railgun_1"])

        # Railgun should target C002 (split-fire)
        assert manager.get_weapon_target("railgun_1") == "C002"
        # Unassigned weapons default to primary
        assert manager.get_weapon_target("pdc_1") == "C001"

    def test_get_weapon_target_pdc_assignment(self, manager):
        manager.add_track("C001", 1.0)
        manager.add_track("C002", 1.0)
        manager.assign_pdc_target("pdc_1", "C002", ["pdc_1"])

        assert manager.get_weapon_target("pdc_1") == "C002"

    def test_clear_assignments(self, manager):
        manager.add_track("C001", 1.0)
        manager.add_track("C002", 1.0)
        manager.assign_pdc_target("pdc_1", "C002", ["pdc_1"])
        manager.assign_split_fire("railgun_1", "C002", ["railgun_1"])

        result = manager.clear_assignments()
        assert result["ok"] is True
        assert len(manager.pdc_assignments) == 0
        assert len(manager.split_fire_assignments) == 0

    def test_prune_lost_contacts(self, manager):
        manager.add_track("C001", 1.0)
        manager.add_track("C002", 1.0)
        manager.add_track("C003", 1.0)

        pruned = manager.prune_lost_contacts({"C001", "C003"})
        assert "C002" in pruned
        assert manager.track_count == 2

    def test_prune_cleans_assignments(self, manager):
        manager.add_track("C001", 1.0)
        manager.add_track("C002", 1.0)
        manager.assign_pdc_target("pdc_1", "C002", ["pdc_1"])

        manager.prune_lost_contacts({"C001"})
        assert "pdc_1" not in manager.pdc_assignments

    def test_remove_track_reindexes_priorities(self, manager):
        manager.add_track("C001", 1.0)
        manager.add_track("C002", 1.0)
        manager.add_track("C003", 1.0)

        manager.remove_track("C002")
        priorities = [t.priority for t in manager.tracks]
        assert priorities == [0, 1]

    def test_get_state(self, manager):
        manager.add_track("C001", 1.0)
        state = manager.get_state()
        assert state["track_count"] == 1
        assert state["primary_target"] == "C001"
        assert len(state["tracks"]) == 1


# ---------------------------------------------------------------------------
# TargetingSystem integration tests
# ---------------------------------------------------------------------------

class TestTargetingMultiTrackIntegration:
    """Tests for multi-track integration with TargetingSystem."""

    def test_lock_target_adds_to_track_list(self, targeting):
        ship = _make_mock_ship(["C001"])
        targeting._ship_ref = ship

        targeting.lock_target("C001")
        assert targeting.multi_track.track_count == 1
        assert targeting.multi_track.primary_target == "C001"

    def test_unlock_removes_from_track_list(self, targeting):
        ship = _make_mock_ship(["C001"])
        targeting._ship_ref = ship

        targeting.lock_target("C001")
        targeting.unlock_target()
        assert targeting.multi_track.track_count == 0

    def test_add_track_command(self, targeting):
        ship = _make_mock_ship(["C001", "C002"])
        targeting._ship_ref = ship

        # Lock primary
        targeting.lock_target("C001")
        # Add secondary via command
        result = targeting.command("add_track", {"contact_id": "C002"})
        assert result["ok"] is True
        assert targeting.multi_track.track_count == 2

    def test_cycle_target_command(self, targeting):
        ship = _make_mock_ship(["C001", "C002"])
        targeting._ship_ref = ship

        targeting.lock_target("C001")
        targeting.add_track("C002")

        result = targeting.command("cycle_target", {})
        assert result["ok"] is True
        assert targeting.locked_target == "C002"
        assert targeting.multi_track.primary_target == "C002"

    def test_assign_pdc_target_command(self, targeting):
        ship = _make_mock_ship(["C001", "C002"])
        targeting._ship_ref = ship
        ship.systems["targeting"] = targeting

        targeting.lock_target("C001")
        targeting.add_track("C002")

        result = targeting.command("assign_pdc_target", {
            "mount_id": "pdc_1",
            "contact_id": "C002",
        })
        assert result["ok"] is True

    def test_split_fire_command(self, targeting):
        ship = _make_mock_ship(["C001", "C002"])
        targeting._ship_ref = ship
        ship.systems["targeting"] = targeting

        targeting.lock_target("C001")
        targeting.add_track("C002")

        result = targeting.command("split_fire", {
            "mount_id": "railgun_1",
            "contact_id": "C002",
        })
        assert result["ok"] is True
        assert targeting.multi_track.get_weapon_target("railgun_1") == "C002"

    def test_track_list_command(self, targeting):
        ship = _make_mock_ship(["C001"])
        targeting._ship_ref = ship

        targeting.lock_target("C001")
        result = targeting.command("track_list", {})
        assert result["ok"] is True
        assert result["track_count"] == 1

    def test_clear_assignments_command(self, targeting):
        ship = _make_mock_ship(["C001", "C002"])
        targeting._ship_ref = ship
        ship.systems["targeting"] = targeting

        targeting.lock_target("C001")
        targeting.add_track("C002")
        targeting.split_fire("railgun_1", "C002")

        result = targeting.command("clear_assignments", {})
        assert result["ok"] is True

    def test_multitrack_quality_modifier_applied(self, targeting):
        """With multiple tracks, quality modifier should be < 1.0."""
        ship = _make_mock_ship(["C001", "C002", "C003"])
        targeting._ship_ref = ship

        targeting.lock_target("C001")
        targeting.add_track("C002")
        targeting.add_track("C003")

        modifier = targeting._get_multitrack_quality_modifier()
        assert modifier < 1.0, (
            f"Quality modifier should be < 1.0 with 3 tracks, got {modifier}"
        )

    def test_single_track_no_quality_penalty(self, targeting):
        """Single target should have no quality penalty."""
        ship = _make_mock_ship(["C001"])
        targeting._ship_ref = ship

        targeting.lock_target("C001")
        modifier = targeting._get_multitrack_quality_modifier()
        assert modifier == 1.0

    def test_get_state_includes_multi_track(self, targeting):
        ship = _make_mock_ship(["C001"])
        targeting._ship_ref = ship
        targeting.lock_target("C001")

        state = targeting.get_state()
        assert "multi_track" in state
        assert state["multi_track"]["track_count"] == 1


# ---------------------------------------------------------------------------
# Command registration tests
# ---------------------------------------------------------------------------

class TestCommandRegistration:
    """Verify multi-target commands are registered in all 3 required places."""

    MULTI_TARGET_COMMANDS = [
        "cycle_target",
        "add_track",
        "remove_track",
        "assign_pdc_target",
        "split_fire",
        "clear_assignments",
        "track_list",
    ]

    def test_commands_in_system_commands(self):
        """All multi-target commands must be in command_handler.system_commands."""
        from hybrid.command_handler import system_commands
        for cmd in self.MULTI_TARGET_COMMANDS:
            assert cmd in system_commands, (
                f"'{cmd}' missing from hybrid/command_handler.py system_commands"
            )

    def test_commands_in_station_types(self):
        """All multi-target commands must be in TACTICAL station commands."""
        from server.stations.station_types import STATION_DEFINITIONS, StationType
        tactical_cmds = STATION_DEFINITIONS[StationType.TACTICAL].commands
        for cmd in self.MULTI_TARGET_COMMANDS:
            assert cmd in tactical_cmds, (
                f"'{cmd}' missing from TACTICAL station commands in station_types.py"
            )

    def test_commands_routed_to_targeting_system(self):
        """All multi-target commands should route to the targeting system."""
        from hybrid.command_handler import system_commands
        for cmd in self.MULTI_TARGET_COMMANDS:
            system_name, _ = system_commands[cmd]
            assert system_name == "targeting", (
                f"'{cmd}' routes to '{system_name}', expected 'targeting'"
            )

    def test_command_specs_registered(self):
        """Commands with args should have CommandSpec registrations."""
        from hybrid.commands.dispatch import create_default_dispatcher
        dispatcher = create_default_dispatcher()
        spec_commands = [
            "cycle_target", "add_track", "remove_track",
            "assign_pdc_target", "split_fire",
        ]
        for cmd in spec_commands:
            assert cmd in dispatcher.commands, (
                f"'{cmd}' missing from CommandSpec dispatcher"
            )

    def test_lint_still_passes(self):
        """The full command registration lint check should still pass."""
        from hybrid.command_registry_lint import lint_command_registrations
        result = lint_command_registrations()
        assert result.ok, (
            f"Command registration lint failed:\n{result.summary()}"
        )
