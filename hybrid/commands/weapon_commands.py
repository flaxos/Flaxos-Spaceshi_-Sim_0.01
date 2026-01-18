# hybrid/commands/weapon_commands.py
"""Weapons and combat commands."""

from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec, validate_weapon_type
from hybrid.utils.errors import success_dict, error_dict, no_target_error

def cmd_fire(weapons, ship, params):
    """Fire a weapon."""
    weapon_type = params.get("weapon_type", "primary")

    # Check if target is locked
    target_id = getattr(ship, "target_id", None)
    if not target_id:
        return no_target_error()

    if weapons and hasattr(weapons, "fire"):
        return weapons.fire({
            "weapon_type": weapon_type,
            "target": target_id
        })

    return error_dict("NOT_IMPLEMENTED", "Weapons system not available")

def cmd_cease_fire(weapons, ship, params):
    """Cease all weapon fire."""
    if weapons and hasattr(weapons, "cease_fire"):
        return weapons.cease_fire()

    return success_dict("Cease fire")

def cmd_arm_weapon(weapons, ship, params):
    """Arm a weapon."""
    weapon_type = params.get("weapon_type")

    if weapons and hasattr(weapons, "arm_weapon"):
        return weapons.arm_weapon(weapon_type)

    return error_dict("NOT_IMPLEMENTED", "Weapon arming not available")

def cmd_disarm_weapon(weapons, ship, params):
    """Disarm a weapon."""
    weapon_type = params.get("weapon_type")

    if weapons and hasattr(weapons, "disarm_weapon"):
        return weapons.disarm_weapon(weapon_type)

    return error_dict("NOT_IMPLEMENTED", "Weapon disarming not available")

def register_commands(dispatcher):
    """Register all weapon commands with the dispatcher."""

    dispatcher.register("fire", CommandSpec(
        handler=cmd_fire,
        args=[
            ArgSpec("weapon_type", "str", required=False, default="primary",
                    description="Weapon type to fire (primary, secondary, torpedo, etc.)")
        ],
        help_text="Fire weapon at locked target",
        system="weapons"
    ))

    dispatcher.register("cease_fire", CommandSpec(
        handler=cmd_cease_fire,
        args=[],
        help_text="Cease all weapon fire",
        system="weapons"
    ))

    dispatcher.register("arm", CommandSpec(
        handler=cmd_arm_weapon,
        args=[
            ArgSpec("weapon_type", "str", required=True,
                    description="Weapon type to arm")
        ],
        help_text="Arm a weapon",
        system="weapons"
    ))

    dispatcher.register("disarm", CommandSpec(
        handler=cmd_disarm_weapon,
        args=[
            ArgSpec("weapon_type", "str", required=True,
                    description="Weapon type to disarm")
        ],
        help_text="Disarm a weapon",
        system="weapons"
    ))
