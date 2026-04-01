# hybrid/commands/economy_commands.py
"""Station services commands for the between-mission economy.

These commands are available while docked at a station.  They let the
player spend credits on repairs, resupply, crew hiring, and upgrades.
All five commands route through the CAPTAIN station (any station can
issue them during the station-services phase).
"""

from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec
from hybrid.utils.errors import success_dict, error_dict
from hybrid.campaign.economy import EconomyManager, CampaignState


# ---------------------------------------------------------------------------
# Shared helper: extract economy state from the ship
# ---------------------------------------------------------------------------

def _get_campaign(ship) -> CampaignState:
    """Retrieve or create campaign state attached to a ship.

    The campaign state lives on ship._campaign_state so it persists
    across ticks.  Created lazily on first economy command so existing
    ships that predate the economy system work without migration.
    """
    if not hasattr(ship, "_campaign_state") or ship._campaign_state is None:
        ship._campaign_state = CampaignState()
    return ship._campaign_state


def _ship_state_snapshot(ship) -> dict:
    """Build a mutable dict snapshot of the ship state the economy needs.

    The economy module operates on plain dicts (not Ship objects) so it
    stays testable without a full ship instance.  Mutations to this dict
    are written back to the ship after the transaction succeeds.
    """
    # Hull
    state = {
        "hull_integrity": getattr(ship, "hull_integrity", 0),
        "max_hull_integrity": getattr(ship, "max_hull_integrity", 0),
    }

    # Subsystems from damage model
    subsystems = {}
    if hasattr(ship, "damage_model") and ship.damage_model:
        for name, data in ship.damage_model.subsystems.items():
            subsystems[name] = {
                "health": data.health,
                "max_health": data.max_health,
            }
    state["subsystems"] = subsystems

    # Fuel
    propulsion = ship.systems.get("propulsion")
    if propulsion and hasattr(propulsion, "fuel_level"):
        state["fuel_level"] = propulsion.fuel_level
    else:
        state["fuel_level"] = 0

    # Weapons (truth weapons on combat system)
    weapons = {}
    combat = ship.systems.get("combat")
    if combat:
        for wid, weapon in getattr(combat, "truth_weapons", {}).items():
            weapons[wid] = {
                "weapon_type": weapon.specs.weapon_type.value if weapon.specs else "",
                "ammo": weapon.ammo,
                "ammo_capacity": weapon.specs.ammo_capacity if weapon.specs else None,
            }
        state["torpedoes_loaded"] = getattr(combat, "torpedoes_loaded", 0)
        state["torpedo_capacity"] = (
            getattr(combat, "torpedo_tubes", 0)
            * getattr(combat, "torpedo_capacity", 4)
        )
        state["missiles_loaded"] = getattr(combat, "missiles_loaded", 0)
        state["missile_capacity"] = (
            getattr(combat, "missile_launchers", 0)
            * getattr(combat, "missile_capacity", 8)
        )
    state["weapons"] = weapons

    # Armor
    if hasattr(ship, "armor") and ship.armor:
        state["armor"] = ship.armor
    else:
        state["armor"] = {}

    # Sensors
    sensors_sys = ship.systems.get("sensors")
    if sensors_sys:
        state["sensors"] = {
            "passive": {"range": getattr(sensors_sys, "passive_range", 200000)},
        }
    else:
        state["sensors"] = {}

    # Weapon mounts
    state["weapon_mounts"] = getattr(ship, "weapon_mounts", []) or []

    # Power management
    power = ship.systems.get("power_management")
    if power and hasattr(power, "config"):
        state["power_management"] = power.config
    else:
        state["power_management"] = {}

    return state


def _apply_state_to_ship(ship, state: dict) -> None:
    """Write mutated economy state back onto the live ship object.

    Called after a successful repair/resupply/upgrade so the changes
    take effect in the running simulation.
    """
    # Hull
    ship.hull_integrity = state.get("hull_integrity", ship.hull_integrity)

    # Subsystems
    if hasattr(ship, "damage_model") and ship.damage_model:
        for name, info in state.get("subsystems", {}).items():
            sub = ship.damage_model.subsystems.get(name)
            if sub:
                sub.health = info.get("health", sub.health)

    # Fuel
    propulsion = ship.systems.get("propulsion")
    if propulsion and hasattr(propulsion, "fuel_level"):
        propulsion.fuel_level = state.get("fuel_level", propulsion.fuel_level)

    # Weapons
    combat = ship.systems.get("combat")
    if combat:
        for wid, wdata in state.get("weapons", {}).items():
            weapon = combat.truth_weapons.get(wid)
            if weapon:
                weapon.ammo = wdata.get("ammo", weapon.ammo)
        combat.torpedoes_loaded = state.get(
            "torpedoes_loaded", combat.torpedoes_loaded
        )
        combat.missiles_loaded = state.get(
            "missiles_loaded", combat.missiles_loaded
        )


# ---------------------------------------------------------------------------
# Ship class helper -- extract from ship config or fall back to defaults
# ---------------------------------------------------------------------------

def _get_ship_class(ship) -> dict:
    """Best-effort ship class dict for capacity lookups."""
    # If the ship has the raw systems config, use it
    config = getattr(ship, "_systems_config", None) or {}
    return {"systems": config}


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_station_repair(ship, params: dict) -> dict:
    """Repair all damage (deducts credits)."""
    campaign = _get_campaign(ship)
    state = _ship_state_snapshot(ship)

    try:
        result = EconomyManager.apply_repair(campaign, state)
    except ValueError as e:
        return error_dict("INSUFFICIENT_CREDITS", str(e))

    if result.get("ok"):
        _apply_state_to_ship(ship, state)
    return result


def cmd_station_resupply(ship, params: dict) -> dict:
    """Resupply all ammo and fuel (deducts credits)."""
    campaign = _get_campaign(ship)
    state = _ship_state_snapshot(ship)
    ship_class = _get_ship_class(ship)

    try:
        result = EconomyManager.apply_resupply(campaign, state, ship_class)
    except ValueError as e:
        return error_dict("INSUFFICIENT_CREDITS", str(e))

    if result.get("ok"):
        _apply_state_to_ship(ship, state)
    return result


def cmd_station_hire_crew(ship, params: dict) -> dict:
    """Hire a new crew member (deducts credits)."""
    campaign = _get_campaign(ship)
    skill_level = params.get("skill_level", "competent")
    name = params.get("name", "New Recruit")

    try:
        result = EconomyManager.hire_crew(campaign, skill_level, name)
    except ValueError as e:
        return error_dict("HIRE_FAILED", str(e))

    return result


def cmd_station_upgrade(ship, params: dict) -> dict:
    """Apply a ship upgrade (deducts credits)."""
    campaign = _get_campaign(ship)
    state = _ship_state_snapshot(ship)
    upgrade_type = params.get("upgrade_type", "")
    target = params.get("target", "")

    try:
        result = EconomyManager.apply_upgrade(campaign, state, upgrade_type, target)
    except ValueError as e:
        return error_dict("UPGRADE_FAILED", str(e))

    if result.get("ok"):
        _apply_state_to_ship(ship, state)
    return result


def cmd_station_prices(ship, params: dict) -> dict:
    """Return current price list and player balance."""
    campaign = _get_campaign(ship)
    state = _ship_state_snapshot(ship)
    ship_class = _get_ship_class(ship)

    prices = EconomyManager.get_price_list()
    repair_cost = EconomyManager.calculate_repair_cost(state)
    resupply_cost = EconomyManager.calculate_resupply_cost(state, ship_class)

    return success_dict(
        "Station services price list",
        credits=campaign.credits,
        prices=prices,
        repair_estimate=repair_cost,
        resupply_estimate=resupply_cost,
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_commands(dispatcher) -> None:
    """Register all economy commands with the dispatcher."""

    dispatcher.register("station_repair", CommandSpec(
        handler=cmd_station_repair,
        args=[],
        help_text="Repair all damage (deducts credits)",
        system=None,  # Ship-level command, not system-level
    ))

    dispatcher.register("station_resupply", CommandSpec(
        handler=cmd_station_resupply,
        args=[],
        help_text="Resupply all ammo and fuel (deducts credits)",
        system=None,
    ))

    dispatcher.register("station_hire_crew", CommandSpec(
        handler=cmd_station_hire_crew,
        args=[
            ArgSpec("skill_level", "str", required=True,
                    choices=["competent", "skilled", "expert"],
                    description="Skill level of the new crew member"),
            ArgSpec("name", "str", required=False, default="New Recruit",
                    description="Display name for the crew member"),
        ],
        help_text="Hire a crew member at a given skill level (deducts credits)",
        system=None,
    ))

    dispatcher.register("station_upgrade", CommandSpec(
        handler=cmd_station_upgrade,
        args=[
            ArgSpec("upgrade_type", "str", required=True,
                    choices=["armor", "sensor_range", "gimbal",
                             "torpedo_tube", "drone_bay", "reactor"],
                    description="Type of upgrade to apply"),
            ArgSpec("target", "str", required=False, default="",
                    description="Target for the upgrade (section, mount_id, etc.)"),
        ],
        help_text="Apply a ship upgrade (deducts credits)",
        system=None,
    ))

    dispatcher.register("station_prices", CommandSpec(
        handler=cmd_station_prices,
        args=[],
        help_text="Get current station services price list and balance",
        system=None,
    ))
