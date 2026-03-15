"""
Command registration lint checker.

Verifies that every player command is properly registered in all required
locations. A command needs registration in:

1. hybrid/command_handler.py system_commands dict (OR a direct station
   dispatcher registration in server/stations/)
2. server/stations/station_types.py STATION_DEFINITIONS command sets
3. hybrid/commands/ domain command specs (CommandSpec registrations)

Commands that bypass permission checks (meta-commands like assign_ship,
claim_station) are excluded from cross-validation.

Run standalone:  python -m hybrid.command_registry_lint
Run in CI:       python -m hybrid.command_registry_lint --strict
Run in tests:    pytest tests/test_command_registry.py
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class LintResult:
    """Result of a command registration lint check."""
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    system_commands_count: int = 0
    station_commands_count: int = 0
    spec_commands_count: int = 0

    def summary(self) -> str:
        """Return a human-readable summary."""
        lines = []
        if self.ok:
            lines.append(
                f"Command registration OK: "
                f"{self.system_commands_count} handler commands, "
                f"{self.station_commands_count} station commands, "
                f"{self.spec_commands_count} spec commands"
            )
        else:
            lines.append(
                f"Command registration FAILED: {len(self.errors)} error(s), "
                f"{len(self.warnings)} warning(s)"
            )
        for err in self.errors:
            lines.append(f"  ERROR: {err}")
        for warn in self.warnings:
            lines.append(f"  WARN:  {warn}")
        return "\n".join(lines)


def get_system_commands() -> Dict[str, Tuple[str, str]]:
    """Get the system_commands dict from hybrid/command_handler.py."""
    from hybrid.command_handler import system_commands
    return dict(system_commands)


def get_station_commands_map() -> Dict[str, Set[str]]:
    """Get command sets from STATION_DEFINITIONS keyed by station name.

    Returns:
        Dict mapping station name to set of command names.
        The special 'all_commands' sentinel is excluded.
    """
    from server.stations.station_types import STATION_DEFINITIONS

    result: Dict[str, Set[str]] = {}
    for station_type, definition in STATION_DEFINITIONS.items():
        cmds = set(definition.commands)
        cmds.discard("all_commands")
        if cmds:
            result[station_type.value] = cmds
    return result


def get_all_station_commands() -> Set[str]:
    """Get the union of all commands across all station definitions."""
    all_cmds: Set[str] = set()
    for cmds in get_station_commands_map().values():
        all_cmds.update(cmds)
    return all_cmds


def get_spec_commands() -> Dict[str, Optional[str]]:
    """Get all commands registered via CommandSpec in hybrid/commands/.

    Returns:
        Dict mapping command name to system name (or None for ship-level).
    """
    from hybrid.commands.dispatch import create_default_dispatcher
    dispatcher = create_default_dispatcher()
    return {
        name: spec.system
        for name, spec in dispatcher.commands.items()
    }


# Commands registered directly with the StationAwareDispatcher that bypass
# station permission checks. These are meta/session commands not tied to
# ship systems and do not need entries in system_commands or station_types.
META_COMMANDS = frozenset({
    "register_client",
    "assign_ship",
    "claim_station",
    "release_station",
    "station_status",
    "my_status",
    "list_ships",
    "heartbeat",
    "promote_to_officer",
    "demote_from_officer",
    "transfer_station",
    "crew_status",
    "my_crew_status",
    "crew_rest",
    "fleet_status",  # Also registered as station meta-command
    "station_message",  # Inter-station comms, bypass_permission_check=True
    "get_station_messages",  # Inter-station comms, bypass_permission_check=True
})

# Commands registered directly with the StationAwareDispatcher (not via
# system_commands) that have proper station permission routing. These are
# valid gameplay commands that simply use a different dispatch path.
DIRECT_DISPATCHER_COMMANDS = frozenset({
    # helm_commands.py - registered directly with StationType.HELM
    "queue_helm_command",
    "queue_helm_commands",
    "clear_helm_queue",
    "interrupt_helm_queue",
    "helm_queue_status",
    "request_docking",
    "cancel_docking",
    # station_commands.py - registered with StationType.OPS
    "set_power_profile",
    "get_power_profiles",
    "get_draw_profile",
    # fleet_commands.py - registered for FLEET_COMMANDER
    "fleet_create",
    "fleet_add_ship",
    "fleet_form",
    "fleet_break_formation",
    "fleet_target",
    "fleet_fire",
    "fleet_cease_fire",
    "fleet_maneuver",
    "fleet_status",
    "fleet_tactical",
    "share_contact",
})

# Commands that exist in the CommandSpec dispatcher but use a different
# name than their system_commands entry. These are alternative dispatch-path
# commands (e.g. "thrust" spec vs "set_thrust" system_command) and are
# expected to NOT appear in system_commands.
SPEC_ONLY_COMMANDS = frozenset({
    "status",
    "position",
    "velocity",
    "orientation",
    "thrust",
    "heading",
    "refuel",
    "emergency_stop",
    "power_on",
    "power_off",
    "ping",
    "contacts",
    "target",
    "target_subsystem",
    "untarget",
    "cease_fire",
    "arm",
    "disarm",
    "flight_computer",
})


def lint_command_registrations() -> LintResult:
    """Check that all command registrations are consistent.

    Validates:
    1. Every command in system_commands has an entry in station_types
       (so it's accessible in station mode).
    2. Every gameplay command in station_types has either a system_commands
       entry or a known direct dispatcher registration.
    3. Every direct dispatcher command (non-meta) is in station_types.
    4. Commands in system_commands that have a matching CommandSpec should
       agree on the target system name.

    Returns:
        LintResult with errors and warnings.
    """
    result = LintResult(ok=True)

    sys_cmds = get_system_commands()
    station_cmds = get_all_station_commands()
    spec_cmds = get_spec_commands()

    result.system_commands_count = len(sys_cmds)
    result.station_commands_count = len(station_cmds)
    result.spec_commands_count = len(spec_cmds)

    # --- Check 1: system_commands entries must have station_types entries ---
    for cmd_name in sorted(sys_cmds.keys()):
        if cmd_name not in station_cmds:
            result.warnings.append(
                f"'{cmd_name}' in system_commands but not in any station's "
                f"command set (unreachable in station mode)"
            )

    # --- Check 2: station_types entries must have a handler ---
    for cmd_name in sorted(station_cmds):
        if cmd_name in META_COMMANDS:
            continue
        if cmd_name in sys_cmds:
            continue
        if cmd_name in DIRECT_DISPATCHER_COMMANDS:
            continue
        # No handler found for this station command
        result.errors.append(
            f"'{cmd_name}' in station_types but has no handler "
            f"(not in system_commands or direct dispatcher registrations)"
        )
        result.ok = False

    # --- Check 3: Direct dispatcher commands should be in station_types ---
    for cmd_name in sorted(DIRECT_DISPATCHER_COMMANDS):
        if cmd_name in META_COMMANDS:
            continue
        if cmd_name not in station_cmds:
            result.errors.append(
                f"'{cmd_name}' registered with station dispatcher but not "
                f"in any station's command set (unreachable)"
            )
            result.ok = False

    # --- Check 4: system mismatch between system_commands and CommandSpec ---
    for cmd_name in sorted(spec_cmds.keys()):
        if cmd_name in SPEC_ONLY_COMMANDS:
            continue
        if cmd_name in sys_cmds:
            spec_system = spec_cmds[cmd_name]
            handler_system = sys_cmds[cmd_name][0]
            if spec_system and spec_system != handler_system:
                result.warnings.append(
                    f"'{cmd_name}' system mismatch: CommandSpec says "
                    f"'{spec_system}', system_commands says '{handler_system}'"
                )

    # --- Check 5: spec commands that claim a system but have no route ---
    for cmd_name in sorted(spec_cmds.keys()):
        if cmd_name in SPEC_ONLY_COMMANDS:
            continue
        if cmd_name in META_COMMANDS:
            continue
        if cmd_name in sys_cmds:
            continue
        if cmd_name in DIRECT_DISPATCHER_COMMANDS:
            continue
        # Spec exists but no route through system_commands or direct dispatch
        result.warnings.append(
            f"'{cmd_name}' has CommandSpec but no system_commands entry "
            f"or direct dispatcher registration (only reachable via CLI dispatcher)"
        )

    return result


def check_on_startup() -> None:
    """Run the lint check and log results. Called during server startup."""
    result = lint_command_registrations()
    if result.ok:
        logger.info(result.summary())
    else:
        logger.error(result.summary())
    for warn in result.warnings:
        logger.warning(warn)


if __name__ == "__main__":
    import argparse
    import sys
    import os

    # Ensure project root is on sys.path
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    ap = argparse.ArgumentParser(
        description="Lint command registrations across all three locations."
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (for CI)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (for tooling)",
    )
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = lint_command_registrations()

    if args.json:
        import json
        output = {
            "ok": result.ok if not args.strict else (result.ok and not result.warnings),
            "errors": result.errors,
            "warnings": result.warnings,
            "counts": {
                "system_commands": result.system_commands_count,
                "station_commands": result.station_commands_count,
                "spec_commands": result.spec_commands_count,
            },
        }
        print(json.dumps(output, indent=2))
    else:
        print(result.summary())

    if args.strict and result.warnings:
        print(f"\n--strict: {len(result.warnings)} warning(s) treated as errors")
        sys.exit(1)

    sys.exit(0 if result.ok else 1)
