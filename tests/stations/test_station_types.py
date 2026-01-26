"""Tests for station types and definitions"""

import pytest
from server.stations.station_types import (
    StationType,
    PermissionLevel,
    StationDefinition,
    STATION_DEFINITIONS,
    get_station_commands,
    get_station_for_command,
    can_station_issue_command
)


def test_station_type_enum():
    """Test StationType enum exists with expected values"""
    assert StationType.CAPTAIN.value == "captain"
    assert StationType.HELM.value == "helm"
    assert StationType.TACTICAL.value == "tactical"
    assert StationType.OPS.value == "ops"
    assert StationType.ENGINEERING.value == "engineering"
    assert StationType.COMMS.value == "comms"
    assert StationType.FLEET_COMMANDER.value == "fleet_commander"


def test_permission_level_hierarchy():
    """Test PermissionLevel hierarchy values"""
    assert PermissionLevel.OBSERVER.value < PermissionLevel.CREW.value
    assert PermissionLevel.CREW.value < PermissionLevel.OFFICER.value
    assert PermissionLevel.OFFICER.value < PermissionLevel.CAPTAIN.value


def test_all_stations_have_definitions():
    """Test all station types have definitions"""
    for station_type in StationType:
        assert station_type in STATION_DEFINITIONS
        definition = STATION_DEFINITIONS[station_type]
        assert isinstance(definition, StationDefinition)
        assert definition.station_type == station_type


def test_captain_has_all_commands():
    """Test CAPTAIN station can access all commands"""
    captain_def = STATION_DEFINITIONS[StationType.CAPTAIN]
    assert "all_commands" in captain_def.commands


def test_helm_commands():
    """Test HELM station has navigation commands"""
    helm_cmds = get_station_commands(StationType.HELM)
    assert "set_thrust" in helm_cmds
    assert "autopilot" in helm_cmds
    assert "set_orientation" in helm_cmds


def test_tactical_commands():
    """Test TACTICAL station has weapons commands"""
    tactical_cmds = get_station_commands(StationType.TACTICAL)
    assert "fire_weapon" in tactical_cmds
    assert "lock_target" in tactical_cmds


def test_ops_commands():
    """Test OPS station has sensor commands"""
    ops_cmds = get_station_commands(StationType.OPS)
    assert "ping_sensors" in ops_cmds


def test_engineering_commands():
    """Test ENGINEERING station has power management commands"""
    eng_cmds = get_station_commands(StationType.ENGINEERING)
    assert "override_bio_monitor" in eng_cmds


def test_get_station_for_command():
    """Test command to station mapping"""
    # Test known command mappings
    helm_station = get_station_for_command("set_thrust")
    assert helm_station == StationType.HELM or helm_station == StationType.CAPTAIN

    tactical_station = get_station_for_command("lock_target")
    assert tactical_station == StationType.TACTICAL or tactical_station == StationType.CAPTAIN


def test_can_station_issue_command_helm():
    """Test HELM can issue helm commands"""
    assert can_station_issue_command(StationType.HELM, "set_thrust")
    assert can_station_issue_command(StationType.HELM, "autopilot")

    # HELM should NOT be able to fire weapons
    assert not can_station_issue_command(StationType.HELM, "fire_weapon")


def test_can_station_issue_command_tactical():
    """Test TACTICAL can issue weapons commands"""
    assert can_station_issue_command(StationType.TACTICAL, "lock_target")

    # TACTICAL should NOT be able to control helm
    assert not can_station_issue_command(StationType.TACTICAL, "set_thrust")


def test_captain_can_issue_all_commands():
    """Test CAPTAIN can issue any command"""
    test_commands = [
        "set_thrust",
        "fire_weapon",
        "ping_sensors",
        "override_bio_monitor",
        "autopilot",
    ]
    for cmd in test_commands:
        assert can_station_issue_command(StationType.CAPTAIN, cmd)


def test_station_displays():
    """Test each station has appropriate displays defined"""
    helm_def = STATION_DEFINITIONS[StationType.HELM]
    assert len(helm_def.displays) > 0
    # Helm should see navigation-related displays
    assert any("nav" in d.lower() or "position" in d.lower() or "velocity" in d.lower()
               for d in helm_def.displays)

    tactical_def = STATION_DEFINITIONS[StationType.TACTICAL]
    assert len(tactical_def.displays) > 0
    # Tactical should see weapons-related displays
    assert any("weapon" in d.lower() or "target" in d.lower()
               for d in tactical_def.displays)


def test_station_required_systems():
    """Test stations have required systems defined"""
    helm_def = STATION_DEFINITIONS[StationType.HELM]
    tactical_def = STATION_DEFINITIONS[StationType.TACTICAL]
    ops_def = STATION_DEFINITIONS[StationType.OPS]

    # These stations should have required systems
    assert len(helm_def.required_systems) > 0
    assert len(tactical_def.required_systems) > 0
    assert len(ops_def.required_systems) > 0
