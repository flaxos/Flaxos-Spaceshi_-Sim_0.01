# hybrid/commands/tactical_commands.py
"""Tactical station commands: target designation, firing solutions, weapon fire, PDC modes, damage assessment.

Commands:
    designate_target: Select a sensor contact for tracking (starts targeting pipeline)
    request_solution: Compute firing solution for the designated target
    fire_railgun: Execute firing solution with a railgun mount
    set_pdc_mode: Set PDC operating mode (auto, manual, hold_fire)
    launch_torpedo: Fire torpedo with target designation and attack profile
    assess_damage: Request sensor analysis of target subsystem state
"""

import logging
from hybrid.commands.dispatch import CommandSpec
from hybrid.commands.validators import ArgSpec
from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)


def cmd_designate_target(targeting, ship, params):
    """Select a sensor contact for tracking through the targeting pipeline.

    Starts the pipeline: contact -> track -> lock -> firing solution.
    The targeting system will build track quality over time before
    acquiring lock.

    Args:
        targeting: TargetingSystem instance
        ship: Ship object
        params: Validated parameters with contact_id and optional subsystem

    Returns:
        dict: Designation result with lock state and track quality
    """
    contact_id = params.get("contact_id")
    if not contact_id:
        return error_dict("MISSING_CONTACT", "Provide 'contact_id' of sensor contact to designate")

    target_subsystem = params.get("target_subsystem")

    return targeting.lock_target(
        contact_id=contact_id,
        sim_time=getattr(ship, "sim_time", None),
        target_subsystem=target_subsystem,
    )


def cmd_request_solution(targeting, ship, params):
    """Compute firing solution for the currently designated target.

    Returns the full solution data including per-weapon confidence,
    hit probability, lead angles, and time of flight.

    Args:
        targeting: TargetingSystem instance
        ship: Ship object
        params: Validated parameters (optional weapon_id for specific weapon)

    Returns:
        dict: Firing solution with confidence factors and weapon data
    """
    weapon_id = params.get("weapon_id")

    if weapon_id:
        return targeting.get_weapon_solution(weapon_id)

    return targeting.get_target_solution(ship)


def cmd_fire_railgun(combat, ship, params):
    """Execute firing solution with a railgun mount.

    Fires the specified railgun (or first available) at the locked target.
    Requires an active lock and valid firing solution. Spawns a ballistic
    projectile that travels at muzzle velocity + ship velocity.

    Args:
        combat: CombatSystem instance
        ship: Ship object
        params: Validated parameters with optional mount_id and target

    Returns:
        dict: Fire result with projectile_id, ballistic flag, damage info
    """
    mount_id = params.get("mount_id")

    # Find a railgun mount if not specified
    if not mount_id:
        for wid in combat.truth_weapons:
            if wid.startswith("railgun"):
                mount_id = wid
                break

    if not mount_id:
        return error_dict("NO_RAILGUN", "No railgun mount available")

    if mount_id not in combat.truth_weapons:
        return error_dict("UNKNOWN_MOUNT", f"Mount '{mount_id}' not found")

    if not mount_id.startswith("railgun"):
        return error_dict("NOT_RAILGUN", f"Mount '{mount_id}' is not a railgun")

    # Resolve target ship from all_ships
    target_ship = None
    target_id = params.get("target")
    all_ships = params.get("all_ships", {})

    if target_id:
        target_ship = all_ships.get(target_id)
    else:
        # Use locked target from targeting system
        targeting = ship.systems.get("targeting")
        if targeting and targeting.locked_target:
            target_id = targeting.locked_target
            target_ship = all_ships.get(target_id)

    target_subsystem = params.get("target_subsystem")

    return combat.fire_weapon(mount_id, target_ship, target_subsystem)


def cmd_set_pdc_mode(combat, ship, params):
    """Set PDC operating mode.

    Modes:
        auto: PDCs automatically engage threats in range (point defense)
        manual: PDCs only fire on explicit command
        hold_fire: PDCs cease all fire immediately

    Args:
        combat: CombatSystem instance
        ship: Ship object
        params: Validated parameters with mode

    Returns:
        dict: Mode change confirmation with affected PDC mounts
    """
    mode = params.get("mode")
    if mode not in ("auto", "manual", "hold_fire"):
        return error_dict("INVALID_MODE", f"PDC mode must be 'auto', 'manual', or 'hold_fire', got '{mode}'")

    affected = []
    for mount_id, weapon in combat.truth_weapons.items():
        if mount_id.startswith("pdc"):
            weapon.pdc_mode = mode
            if mode == "hold_fire":
                weapon.enabled = False
            elif mode in ("auto", "manual"):
                weapon.enabled = True
            affected.append(mount_id)

    if not affected:
        return error_dict("NO_PDC", "No PDC mounts available on this ship")

    # Publish event
    if hasattr(ship, "event_bus") and ship.event_bus:
        ship.event_bus.publish("pdc_mode_changed", {
            "ship_id": ship.id,
            "mode": mode,
            "mounts": affected,
        })

    return success_dict(
        f"PDC mode set to {mode.upper()}",
        mode=mode,
        affected_mounts=affected,
    )


def cmd_launch_torpedo(combat, ship, params):
    """Fire torpedo with target designation and attack profile.

    Currently routes through the legacy weapon fire system for torpedo
    weapons if available. Target designation uses the locked target
    from the targeting pipeline.

    Args:
        combat: CombatSystem instance
        ship: Ship object
        params: Validated parameters with optional target and profile

    Returns:
        dict: Launch result
    """
    target_id = params.get("target")
    profile = params.get("profile", "direct")

    # Try to get target from targeting system if not specified
    if not target_id:
        targeting = ship.systems.get("targeting")
        if targeting and targeting.locked_target:
            target_id = targeting.locked_target

    if not target_id:
        return error_dict("NO_TARGET", "No target designated for torpedo launch")

    # Route through legacy weapons system for torpedo
    weapons = ship.systems.get("weapons")
    if weapons and hasattr(weapons, "fire"):
        return weapons.fire({
            "weapon_type": "torpedo",
            "target": target_id,
            "profile": profile,
        })

    return error_dict("NO_TORPEDO", "No torpedo system available")


def cmd_assess_damage(targeting, ship, params):
    """Request sensor analysis of target subsystem state.

    Uses sensor data and track quality to estimate the health of each
    subsystem on the locked target. Accuracy depends on sensor quality
    and range — degraded sensors produce uncertain readings.

    Args:
        targeting: TargetingSystem instance
        ship: Ship object
        params: Validated parameters

    Returns:
        dict: Target damage assessment with subsystem health estimates
    """
    if not targeting.locked_target:
        return error_dict("NO_TARGET", "No target locked for damage assessment")

    if targeting.lock_state.value not in ("locked", "tracking", "acquiring"):
        return error_dict(
            "INSUFFICIENT_TRACK",
            f"Lock state '{targeting.lock_state.value}' insufficient for damage assessment"
        )

    # Get sensor quality for assessment accuracy
    sensor_factor = getattr(targeting, "_sensor_factor", 1.0)
    track_quality = targeting.track_quality

    # Assessment quality degrades with poor sensors/track
    assessment_quality = min(sensor_factor, track_quality)

    # Try to get actual target damage data from all_ships
    all_ships = params.get("all_ships", {})
    target_ship = all_ships.get(targeting.locked_target)

    subsystems = {}
    if target_ship and hasattr(target_ship, "damage_model"):
        dm = target_ship.damage_model
        for subsys_name in dm.subsystems:
            actual_health = dm.get_combined_factor(subsys_name)

            # Degrade accuracy based on assessment quality
            # Good sensors: accurate reading. Bad sensors: noisy estimate.
            if assessment_quality > 0.8:
                reported_health = actual_health
                confidence = "high"
            elif assessment_quality > 0.5:
                # Add some noise — round to nearest 25%
                reported_health = round(actual_health * 4) / 4
                confidence = "moderate"
            elif assessment_quality > 0.2:
                # Coarse estimate — round to nearest 50%
                reported_health = round(actual_health * 2) / 2
                confidence = "low"
            else:
                reported_health = None
                confidence = "none"

            status = "unknown"
            if reported_health is not None:
                if reported_health > 0.75:
                    status = "nominal"
                elif reported_health > 0.25:
                    status = "impaired"
                elif reported_health > 0:
                    status = "critical"
                else:
                    status = "destroyed"

            subsystems[subsys_name] = {
                "health": reported_health,
                "status": status,
                "confidence": confidence,
            }
    else:
        # No target ship data available — return unknown
        for subsys in ["propulsion", "rcs", "sensors", "weapons", "reactor"]:
            subsystems[subsys] = {
                "health": None,
                "status": "unknown",
                "confidence": "none",
            }

    return success_dict(
        f"Damage assessment for {targeting.locked_target}",
        target_id=targeting.locked_target,
        assessment_quality=round(assessment_quality, 2),
        subsystems=subsystems,
    )


def register_commands(dispatcher):
    """Register all tactical commands with the dispatcher."""

    dispatcher.register("designate_target", CommandSpec(
        handler=cmd_designate_target,
        args=[
            ArgSpec("contact_id", "str", required=True,
                    description="Sensor contact ID to designate for tracking"),
            ArgSpec("target_subsystem", "str", required=False,
                    description="Optional subsystem to target (e.g. propulsion, weapons)"),
        ],
        help_text="Select a sensor contact for tracking through the targeting pipeline",
        system="targeting",
    ))

    dispatcher.register("request_solution", CommandSpec(
        handler=cmd_request_solution,
        args=[
            ArgSpec("weapon_id", "str", required=False,
                    description="Specific weapon mount ID for per-weapon solution"),
        ],
        help_text="Compute firing solution for the designated target",
        system="targeting",
    ))

    dispatcher.register("fire_railgun", CommandSpec(
        handler=cmd_fire_railgun,
        args=[
            ArgSpec("mount_id", "str", required=False,
                    description="Railgun mount ID (e.g. railgun_1). Uses first available if omitted"),
            ArgSpec("target", "str", required=False,
                    description="Target ship ID (uses locked target if omitted)"),
            ArgSpec("target_subsystem", "str", required=False,
                    description="Subsystem to target on the target ship"),
        ],
        help_text="Fire railgun at locked target (spawns ballistic projectile)",
        system="combat",
    ))

    dispatcher.register("set_pdc_mode", CommandSpec(
        handler=cmd_set_pdc_mode,
        args=[
            ArgSpec("mode", "str", required=True,
                    choices=["auto", "manual", "hold_fire"],
                    description="PDC mode: auto (point defense), manual (fire on command), hold_fire (cease)"),
        ],
        help_text="Set PDC operating mode (auto, manual, hold_fire)",
        system="combat",
    ))

    dispatcher.register("launch_torpedo", CommandSpec(
        handler=cmd_launch_torpedo,
        args=[
            ArgSpec("target", "str", required=False,
                    description="Target ship ID (uses locked target if omitted)"),
            ArgSpec("profile", "str", required=False, default="direct",
                    choices=["direct", "evasive", "terminal"],
                    description="Attack profile for torpedo approach"),
        ],
        help_text="Launch torpedo with target designation and attack profile",
        system="combat",
    ))

    dispatcher.register("assess_damage", CommandSpec(
        handler=cmd_assess_damage,
        args=[],
        help_text="Request sensor analysis of target subsystem state",
        system="targeting",
    ))
