# hybrid/systems/combat/auto_fire_manager.py
"""Server-side auto-fire authorization manager.

Manages standing fire authorization per weapon category.  When a weapon
type is authorized, the manager checks conditions each tick and fires
automatically when all prerequisites are met:

- Target is locked (targeting system has active lock)
- Firing solution is ready (combat system has valid solution)
- Ammo is available
- Cooldown has elapsed

Behavior per weapon type:
- Railgun: continuous auto-fire while authorized (respects weapon cycle time)
- Torpedo: single-shot — fires once when conditions met, then auto-deauthorizes
- Missile: fires one missile when conditions met, then auto-deauthorizes

This replaces the client-side _processAutoExecute() in weapon-controls.js,
making fire authorization server-authoritative.
"""

import logging
from typing import Optional

from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)

# Valid weapon types that can be authorized
VALID_WEAPON_TYPES = {"railgun", "torpedo", "missile"}


class AutoFireManager:
    """Manages standing fire authorization per weapon category.

    The manager is ticked each simulation step by the CombatSystem.
    It inspects targeting and weapon state to decide when to fire,
    keeping all fire decisions server-side.
    """

    def __init__(self) -> None:
        self._authorized: dict[str, bool] = {
            "railgun": False,
            "torpedo": False,
            "missile": False,
        }
        # Per-type cooldown remaining (seconds).  Prevents double-commanding
        # the same weapon mount within its cycle time.
        self._cooldowns: dict[str, float] = {
            "railgun": 0.0,
            "torpedo": 0.0,
            "missile": 0.0,
        }
        # Missile launch configuration (count reserved for future salvo support)
        self._missile_config: dict = {"count": 1, "profile": "direct"}

    # ------------------------------------------------------------------
    # Public API — called by command handlers
    # ------------------------------------------------------------------

    def authorize(self, weapon_type: str, **kwargs) -> dict:
        """Authorize a weapon type for auto-fire.

        Args:
            weapon_type: One of "railgun", "torpedo", "missile".
            **kwargs: For missiles — count (int) and profile (str).

        Returns:
            dict: Success/error result.
        """
        if weapon_type not in VALID_WEAPON_TYPES:
            return error_dict(
                "INVALID_WEAPON_TYPE",
                f"weapon_type must be one of {sorted(VALID_WEAPON_TYPES)}, got '{weapon_type}'",
            )

        self._authorized[weapon_type] = True
        # Reset cooldown so the first shot fires on the next eligible tick
        self._cooldowns[weapon_type] = 0.0

        # Store missile-specific config
        if weapon_type == "missile":
            self._missile_config["count"] = kwargs.get("count", 1)
            self._missile_config["profile"] = kwargs.get("profile", "direct")

        logger.info("Auto-fire authorized: %s", weapon_type)
        return success_dict(
            f"{weapon_type.upper()} auto-fire authorized",
            weapon_type=weapon_type,
            authorized=True,
        )

    def deauthorize(self, weapon_type: str) -> dict:
        """Remove authorization for a weapon type.

        Args:
            weapon_type: One of "railgun", "torpedo", "missile".

        Returns:
            dict: Success/error result.
        """
        if weapon_type not in VALID_WEAPON_TYPES:
            return error_dict(
                "INVALID_WEAPON_TYPE",
                f"weapon_type must be one of {sorted(VALID_WEAPON_TYPES)}, got '{weapon_type}'",
            )

        self._authorized[weapon_type] = False
        logger.info("Auto-fire deauthorized: %s", weapon_type)
        return success_dict(
            f"{weapon_type.upper()} auto-fire deauthorized",
            weapon_type=weapon_type,
            authorized=False,
        )

    def cease_fire(self) -> dict:
        """Deauthorize all weapon types.

        Returns:
            dict: Success result.
        """
        for wtype in VALID_WEAPON_TYPES:
            self._authorized[wtype] = False
        logger.info("Cease fire — all auto-fire deauthorized")
        return success_dict("All auto-fire deauthorized")

    # ------------------------------------------------------------------
    # Tick — called every simulation step by CombatSystem
    # ------------------------------------------------------------------

    def tick(self, dt: float, combat_system, ship) -> list[dict]:
        """Check conditions and fire authorized weapons.

        For each authorized weapon type, verifies:
        1. Cooldown has elapsed
        2. Target is locked (targeting system)
        3. Firing solution is ready (truth weapon has valid solution)
        4. Ammo is available

        If all conditions are met, fires the weapon through the combat
        system's existing fire methods.

        Args:
            dt: Time delta in seconds.
            combat_system: CombatSystem instance (has fire_weapon, launch_torpedo, etc.).
            ship: Ship object (has systems dict with targeting system).

        Returns:
            list[dict]: Fire event results from this tick (may be empty).
        """
        # Tick down cooldowns
        for wtype in self._cooldowns:
            if self._cooldowns[wtype] > 0:
                self._cooldowns[wtype] = max(0.0, self._cooldowns[wtype] - dt)

        events: list[dict] = []

        # Check if we have a locked target
        targeting = ship.systems.get("targeting") if hasattr(ship, "systems") else None
        if not targeting or not targeting.locked_target:
            return events

        has_lock = targeting.lock_state.value == "locked" if hasattr(targeting.lock_state, "value") else False
        if not has_lock:
            return events

        # --- Railgun: continuous fire while authorized ---
        if self._authorized["railgun"] and self._cooldowns["railgun"] <= 0:
            result = self._try_fire_railgun(combat_system)
            if result:
                events.append(result)

        # --- Torpedo: single-shot, then deauthorize ---
        if self._authorized["torpedo"] and self._cooldowns["torpedo"] <= 0:
            result = self._try_fire_torpedo(combat_system, ship)
            if result:
                events.append(result)
                self._authorized["torpedo"] = False

        # --- Missile: fire one, then deauthorize ---
        if self._authorized["missile"] and self._cooldowns["missile"] <= 0:
            result = self._try_fire_missile(combat_system, ship)
            if result:
                events.append(result)
                self._authorized["missile"] = False

        return events

    # ------------------------------------------------------------------
    # Internal fire helpers
    # ------------------------------------------------------------------

    def _try_fire_railgun(self, combat_system) -> Optional[dict]:
        """Attempt to fire a railgun if conditions are met.

        Finds the first railgun mount with a ready solution and ammo,
        then fires it.  Sets cooldown to weapon cycle time to prevent
        double-commanding the same mount within its reload window.

        Args:
            combat_system: CombatSystem instance.

        Returns:
            dict or None: Fire result if fired, None otherwise.
        """
        for mount_id, weapon in combat_system.truth_weapons.items():
            if not mount_id.startswith("railgun"):
                continue
            if weapon.ammo <= 0:
                continue
            if not weapon.can_fire(combat_system._sim_time):
                continue
            solution = weapon.current_solution
            if not solution or not solution.ready_to_fire:
                continue

            result = combat_system.fire_weapon(mount_id)
            if result.get("ok"):
                # Cooldown = weapon cycle time so we don't re-fire before reload
                self._cooldowns["railgun"] = weapon.specs.cycle_time
                result["auto_fire"] = True
                result["weapon_type"] = "railgun"
                return result
        return None

    def _try_fire_torpedo(self, combat_system, ship) -> Optional[dict]:
        """Attempt to launch a torpedo if conditions are met.

        Args:
            combat_system: CombatSystem instance.
            ship: Ship object for target resolution.

        Returns:
            dict or None: Launch result if fired, None otherwise.
        """
        if combat_system.torpedoes_loaded <= 0:
            return None
        if combat_system._torpedo_cooldown > 0:
            return None

        targeting = ship.systems.get("targeting")
        if not targeting or not targeting.locked_target:
            return None

        # Build all_ships dict for target resolution
        all_ships_list = getattr(ship, "_all_ships_ref", None) or []
        all_ships = (
            {s.id: s for s in all_ships_list}
            if isinstance(all_ships_list, list)
            else {}
        )

        result = combat_system.launch_torpedo(
            targeting.locked_target, "direct", all_ships,
        )
        if result.get("ok"):
            self._cooldowns["torpedo"] = combat_system.torpedo_reload_time
            result["auto_fire"] = True
            result["weapon_type"] = "torpedo"
            return result
        return None

    def _try_fire_missile(self, combat_system, ship) -> Optional[dict]:
        """Attempt to launch a missile if conditions are met.

        Args:
            combat_system: CombatSystem instance.
            ship: Ship object for target resolution.

        Returns:
            dict or None: Launch result if fired, None otherwise.
        """
        if combat_system.missiles_loaded <= 0:
            return None
        if combat_system._missile_cooldown > 0:
            return None

        targeting = ship.systems.get("targeting")
        if not targeting or not targeting.locked_target:
            return None

        profile = self._missile_config.get("profile", "direct")

        # Build all_ships dict for target resolution
        all_ships_list = getattr(ship, "_all_ships_ref", None) or []
        all_ships = (
            {s.id: s for s in all_ships_list}
            if isinstance(all_ships_list, list)
            else {}
        )

        result = combat_system.launch_missile(
            targeting.locked_target, profile, all_ships,
        )
        if result.get("ok"):
            self._cooldowns["missile"] = combat_system.missile_reload_time
            result["auto_fire"] = True
            result["weapon_type"] = "missile"
            return result
        return None

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Return current authorization state for telemetry.

        Returns:
            dict: Authorization state per weapon type, plus missile config.
        """
        return {
            "authorized": dict(self._authorized),
            "cooldowns": {k: round(v, 2) for k, v in self._cooldowns.items()},
            "missile_config": dict(self._missile_config),
        }
