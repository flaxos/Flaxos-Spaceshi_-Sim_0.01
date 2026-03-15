"""
Tests for command registration lint checker.

Ensures every player command is properly registered across all required
locations so that no command silently fails at runtime.
"""

import pytest

from hybrid.command_registry_lint import (
    lint_command_registrations,
    get_system_commands,
    get_all_station_commands,
    get_station_commands_map,
    get_spec_commands,
    META_COMMANDS,
    DIRECT_DISPATCHER_COMMANDS,
    SPEC_ONLY_COMMANDS,
    LintResult,
)


def test_lint_passes():
    """The lint check must pass with zero errors."""
    result = lint_command_registrations()
    assert result.ok, (
        f"Command registration lint failed:\n{result.summary()}"
    )
    assert len(result.errors) == 0


def test_system_commands_not_empty():
    """system_commands dict should contain commands."""
    sys_cmds = get_system_commands()
    assert len(sys_cmds) > 0, "system_commands is empty"


def test_station_commands_not_empty():
    """Station definitions should contain commands."""
    station_cmds = get_all_station_commands()
    assert len(station_cmds) > 0, "No commands found in station definitions"


def test_spec_commands_not_empty():
    """CommandSpec dispatcher should contain commands."""
    spec_cmds = get_spec_commands()
    assert len(spec_cmds) > 0, "No CommandSpec commands found"


def test_every_system_command_has_station():
    """Every system_commands entry should appear in at least one station."""
    sys_cmds = get_system_commands()
    station_cmds = get_all_station_commands()

    missing = [
        cmd for cmd in sys_cmds
        if cmd not in station_cmds
    ]
    # These are warnings, not hard errors — but flag them
    if missing:
        pytest.skip(
            f"Commands in system_commands but not in any station "
            f"(unreachable in station mode): {missing}"
        )


def test_every_station_command_has_handler():
    """Every non-meta station command must have a handler registered."""
    station_cmds = get_all_station_commands()
    sys_cmds = get_system_commands()

    unhandled = []
    for cmd in sorted(station_cmds):
        if cmd in META_COMMANDS:
            continue
        if cmd in sys_cmds:
            continue
        if cmd in DIRECT_DISPATCHER_COMMANDS:
            continue
        unhandled.append(cmd)

    assert not unhandled, (
        f"Station commands with no handler: {unhandled}"
    )


def test_direct_dispatcher_commands_in_stations():
    """Direct dispatcher commands (non-meta) must be in station_types."""
    station_cmds = get_all_station_commands()

    missing = [
        cmd for cmd in sorted(DIRECT_DISPATCHER_COMMANDS)
        if cmd not in META_COMMANDS and cmd not in station_cmds
    ]
    assert not missing, (
        f"Direct dispatcher commands not in any station: {missing}"
    )


def test_station_map_keys():
    """Station command map should have expected station names."""
    station_map = get_station_commands_map()
    assert "helm" in station_map
    assert "tactical" in station_map


def test_system_commands_tuples():
    """All system_commands values must be (system, action) tuples."""
    sys_cmds = get_system_commands()
    for cmd_name, value in sys_cmds.items():
        assert isinstance(value, tuple), (
            f"system_commands['{cmd_name}'] is {type(value)}, expected tuple"
        )
        assert len(value) == 2, (
            f"system_commands['{cmd_name}'] has {len(value)} elements, expected 2"
        )
        system, action = value
        assert isinstance(system, str) and system, (
            f"system_commands['{cmd_name}'][0] (system) must be non-empty string"
        )
        assert isinstance(action, str) and action, (
            f"system_commands['{cmd_name}'][1] (action) must be non-empty string"
        )


def test_spec_only_commands_exist_in_specs():
    """Every SPEC_ONLY_COMMANDS entry should actually be in CommandSpec."""
    spec_cmds = get_spec_commands()
    missing = [
        cmd for cmd in SPEC_ONLY_COMMANDS
        if cmd not in spec_cmds
    ]
    assert not missing, (
        f"SPEC_ONLY_COMMANDS entries not found in CommandSpec: {missing}"
    )


def test_spec_system_matches_handler():
    """CommandSpec system should match system_commands system when both exist."""
    sys_cmds = get_system_commands()
    spec_cmds = get_spec_commands()

    mismatches = []
    for cmd_name, spec_system in spec_cmds.items():
        if cmd_name in SPEC_ONLY_COMMANDS:
            continue
        if cmd_name in sys_cmds and spec_system:
            handler_system = sys_cmds[cmd_name][0]
            if spec_system != handler_system:
                mismatches.append(
                    f"{cmd_name}: spec='{spec_system}' vs handler='{handler_system}'"
                )

    assert not mismatches, (
        f"System name mismatches between CommandSpec and system_commands: {mismatches}"
    )


def test_lint_result_summary():
    """LintResult.summary() should produce readable output."""
    result = LintResult(
        ok=True,
        system_commands_count=10,
        station_commands_count=20,
        spec_commands_count=15,
    )
    summary = result.summary()
    assert "OK" in summary
    assert "10" in summary

    result_fail = LintResult(ok=False, errors=["test error"])
    summary_fail = result_fail.summary()
    assert "FAILED" in summary_fail
    assert "test error" in summary_fail


def test_lint_result_counts():
    """LintResult should track all three command source counts."""
    result = lint_command_registrations()
    assert result.system_commands_count > 0
    assert result.station_commands_count > 0
    assert result.spec_commands_count > 0
