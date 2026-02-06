import copy

from hybrid.ship import Ship
from hybrid.power_command_service import (
    get_draw_profile_command,
    get_power_profiles_command,
    get_power_telemetry_command,
    set_power_allocation_command,
    set_power_profile_command,
    toggle_system_command,
)


def _build_ship():
    cfg = {
        "systems": {
            "power_management": {
                "primary": {"capacity": 120.0, "output_rate": 60.0, "thermal_limit": 200.0},
                "secondary": {"capacity": 80.0, "output_rate": 40.0, "thermal_limit": 200.0},
                "tertiary": {"capacity": 40.0, "output_rate": 20.0, "thermal_limit": 200.0},
                "power_allocation": {"primary": 0.5, "secondary": 0.3, "tertiary": 0.2},
                "system_map": {
                    "propulsion": "primary",
                    "sensors": "secondary",
                    "bio": "tertiary",
                },
            },
            "propulsion": {"power_draw": 20.0},
            "sensors": {"power_draw": 10.0},
            "bio": {"power_draw": 5.0},
        },
    }
    return Ship("parity_ship", cfg)


def test_set_power_profile_parity_ship_vs_pm_command():
    ship = _build_ship()
    pm = ship.systems["power_management"]

    cmd, payload = set_power_profile_command("offensive")
    ship_result = ship.command(cmd, copy.deepcopy(payload))

    pm_ship = _build_ship()
    pm_result = pm_ship.systems["power_management"].command("set_power_profile", {**payload, "ship": pm_ship})

    assert ship_result["status"] == pm_result["status"]
    assert ship.systems["power_management"].active_profile == pm_ship.systems["power_management"].active_profile
    assert ship.systems["power_management"].power_allocation == pm_ship.systems["power_management"].power_allocation


def test_set_power_allocation_parity_ship_vs_pm_command():
    ship = _build_ship()
    pm_ship = _build_ship()

    keys = list(ship.systems["power_management"].reactors.keys())
    allocation = {name: idx + 1 for idx, name in enumerate(keys)}

    cmd, payload = set_power_allocation_command(allocation)
    ship_result = ship.command(cmd, copy.deepcopy(payload))
    pm_result = pm_ship.systems["power_management"].command("set_power_allocation", {**payload, "ship": pm_ship})

    assert ship_result["power_allocation"] == pm_result["power_allocation"]
    assert ship.systems["power_management"].power_allocation == pm_ship.systems["power_management"].power_allocation


def test_toggle_and_telemetry_commands_available_via_shared_paths():
    ship = _build_ship()

    toggle_cmd, toggle_payload = toggle_system_command("sensors", False)
    toggle_result = ship.command(toggle_cmd, toggle_payload)
    assert toggle_result["status"] == "system_power_state_updated"
    assert ship.systems["sensors"].enabled is False

    profiles_cmd, profiles_payload = get_power_profiles_command()
    profiles_result = ship.command(profiles_cmd, profiles_payload)
    assert "profiles" in profiles_result

    telemetry_cmd, telemetry_payload = get_power_telemetry_command()
    telemetry_result = ship.command(telemetry_cmd, telemetry_payload)
    assert "draw_by_bus_kw" in telemetry_result
    assert "supply_by_bus_kw" in telemetry_result

    draw_cmd, draw_payload = get_draw_profile_command()
    draw_result = ship.command(draw_cmd, draw_payload)
    assert "draw_by_bus" in draw_result
    assert "total_draw_kw" in draw_result
