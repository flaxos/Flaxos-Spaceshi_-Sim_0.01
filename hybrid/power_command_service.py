"""Shared command helpers for power-management operations.

This keeps CLI and GUI paths aligned on the same command names/payload shapes.
"""


def toggle_system_command(system_name, enabled):
    return "toggle_system_power", {
        "system": system_name,
        "enabled": bool(enabled),
    }


def set_power_profile_command(profile_name):
    return "set_power_profile", {"profile": profile_name}


def set_power_allocation_command(allocation):
    return "set_power_allocation", {"allocation": allocation}


def get_power_profiles_command():
    return "get_power_profiles", {}


def get_power_telemetry_command():
    return "get_power_telemetry", {}


def get_draw_profile_command():
    return "get_draw_profile", {}

