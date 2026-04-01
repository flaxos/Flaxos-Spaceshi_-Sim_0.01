# hybrid/campaign/economy.py
"""Economy system for campaign credit transactions.

Credits are the campaign currency.  Earned by completing missions,
salvaging wrecks, and collecting bounties.  Spent on repairs, resupply,
crew hiring, and ship upgrades between missions.

Design notes:
- Pricing is intentionally transparent -- the player should always be
  able to predict what an action costs before committing.
- Difficulty multiplier rewards harder missions exponentially (easy=0.5x,
  extreme=4x) so campaign progression gates on risk-vs-reward.
- Upgrade costs are tuned so a full corvette refit costs roughly 3-4
  medium-difficulty missions, keeping late-campaign spending meaningful.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Pricing constants ────────────────────────────────────────
# Repair
REPAIR_COST_PER_HULL_POINT = 10
REPAIR_COST_PER_SUBSYSTEM_POINT = 5

# Ammunition (per unit)
AMMO_COST_RAILGUN = 2        # per round -- tungsten slugs are cheap to fab
AMMO_COST_TORPEDO = 50       # per torpedo -- heavy guided ordnance
AMMO_COST_MISSILE = 20       # per missile -- lighter guided ordnance
AMMO_COST_PDC = 0.1          # per round -- bulk 40mm, fabricated in batches

# Fuel
FUEL_COST_PER_UNIT = 1       # per kg of reaction mass

# Crew hiring
CREW_COST_COMPETENT = 100
CREW_COST_SKILLED = 250
CREW_COST_EXPERT = 500

# Ship upgrades (late campaign)
UPGRADE_ARMOR_PER_CM = 150       # per section per cm added
UPGRADE_SENSOR_RANGE = 200       # flat cost for +20% sensor range
UPGRADE_GIMBAL_CONVERT = 500     # convert fixed mount to gimbal
UPGRADE_TORPEDO_TUBE = 1000      # add 1 torpedo tube (4 capacity)
UPGRADE_DRONE_BAY = 800          # add drone bay (4 drones)
UPGRADE_REACTOR_OUTPUT = 300     # +10% reactor output

# Mission reward bases -- indexed by difficulty string
_DIFFICULTY_BASE_REWARD: Dict[str, int] = {
    "easy": 100,
    "medium": 200,
    "hard": 400,
    "extreme": 800,
}

# Bonus credits
_OPTIONAL_OBJECTIVE_BONUS = 50   # per optional objective completed
_ZERO_DAMAGE_BONUS = 100         # bonus for completing without taking damage


# ── Campaign state container ─────────────────────────────────

@dataclass
class CampaignState:
    """Persistent campaign state carried between missions.

    Holds the player's credit balance, transaction history, and any
    purchased upgrades so the economy can be audited after the fact.
    """
    credits: int = 500  # Starting credits -- enough for one resupply
    transactions: List[Dict[str, Any]] = field(default_factory=list)

    def add_credits(self, amount: int, reason: str) -> int:
        """Add credits and record the transaction.

        Args:
            amount: Credits to add (positive).
            reason: Human-readable reason for the transaction.

        Returns:
            New balance after the deposit.
        """
        self.credits += amount
        self.transactions.append({
            "type": "credit",
            "amount": amount,
            "reason": reason,
            "balance": self.credits,
        })
        logger.info(f"Economy +{amount} cr ({reason}) -> balance {self.credits}")
        return self.credits

    def deduct_credits(self, amount: int, reason: str) -> int:
        """Deduct credits and record the transaction.

        Args:
            amount: Credits to deduct (positive).
            reason: Human-readable reason for the deduction.

        Returns:
            New balance after the deduction.

        Raises:
            ValueError: If insufficient credits.
        """
        if amount > self.credits:
            raise ValueError(
                f"Insufficient credits: need {amount}, have {self.credits}"
            )
        self.credits -= amount
        self.transactions.append({
            "type": "debit",
            "amount": amount,
            "reason": reason,
            "balance": self.credits,
        })
        logger.info(f"Economy -{amount} cr ({reason}) -> balance {self.credits}")
        return self.credits

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for save/telemetry."""
        return {
            "credits": self.credits,
            "transactions": self.transactions[-20:],  # last 20 for brevity
        }


# ── Economy manager ──────────────────────────────────────────

class EconomyManager:
    """Stateless helper that calculates costs and applies transactions.

    All mutation goes through CampaignState.add_credits / deduct_credits
    so the transaction log stays consistent.
    """

    # ── Rewards ──────────────────────────────────────────────

    @staticmethod
    def calculate_mission_reward(
        mission_result: Dict[str, Any],
        difficulty: str,
    ) -> Dict[str, Any]:
        """Compute credits earned for a completed mission.

        Args:
            mission_result: Dict with keys 'status' (success/failure),
                'objectives' (list of objective dicts with 'required' and
                'status' fields), and optionally 'total_damage_taken'.
            difficulty: One of 'easy', 'medium', 'hard', 'extreme'.

        Returns:
            Breakdown dict with base, optional_bonus, damage_bonus, total.
        """
        base = _DIFFICULTY_BASE_REWARD.get(difficulty, 200)

        # Only successful missions pay out
        if mission_result.get("status") != "success":
            return {"base": 0, "optional_bonus": 0, "damage_bonus": 0, "total": 0}

        # Count completed optional objectives
        objectives = mission_result.get("objectives", [])
        optional_completed = sum(
            1 for obj in objectives
            if not obj.get("required", True)
            and obj.get("status") == "completed"
        )
        optional_bonus = optional_completed * _OPTIONAL_OBJECTIVE_BONUS

        # Zero-damage bonus -- incentivises clean play
        total_damage = mission_result.get("total_damage_taken", 0)
        damage_bonus = _ZERO_DAMAGE_BONUS if total_damage == 0 else 0

        total = base + optional_bonus + damage_bonus
        return {
            "base": base,
            "optional_bonus": optional_bonus,
            "damage_bonus": damage_bonus,
            "total": total,
        }

    # ── Cost calculations ────────────────────────────────────

    @staticmethod
    def calculate_repair_cost(ship_state: Dict[str, Any]) -> Dict[str, Any]:
        """Break down the cost to fully repair a ship.

        Args:
            ship_state: Dict with 'hull_integrity', 'max_hull_integrity',
                and 'subsystems' (name -> {health, max_health}).

        Returns:
            Dict with hull cost, per-subsystem costs, and total.
        """
        hull_current = ship_state.get("hull_integrity", 0)
        hull_max = ship_state.get("max_hull_integrity", hull_current)
        hull_damage = max(0, hull_max - hull_current)
        hull_cost = int(hull_damage * REPAIR_COST_PER_HULL_POINT)

        subsystems: Dict[str, int] = {}
        subsystems_data = ship_state.get("subsystems", {})
        for name, info in subsystems_data.items():
            current = info.get("health", 0)
            maximum = info.get("max_health", current)
            damage = max(0, maximum - current)
            if damage > 0:
                subsystems[name] = int(damage * REPAIR_COST_PER_SUBSYSTEM_POINT)

        subsystem_total = sum(subsystems.values())
        return {
            "hull": hull_cost,
            "subsystems": subsystems,
            "total": hull_cost + subsystem_total,
        }

    @staticmethod
    def calculate_resupply_cost(
        ship_state: Dict[str, Any],
        ship_class: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Cost to fully resupply ammo and fuel.

        Uses ship_class for max capacities and ship_state for current levels.

        Args:
            ship_state: Dict with 'weapons' (per-weapon ammo state),
                'torpedoes', 'missiles', and 'fuel_level' fields.
            ship_class: Ship class definition with capacity info.

        Returns:
            Dict with per-category costs and total.
        """
        # Fuel
        fuel_current = ship_state.get("fuel_level", 0)
        fuel_max = ship_class.get("systems", {}).get(
            "propulsion", {}
        ).get("max_fuel", fuel_current)
        fuel_needed = max(0, fuel_max - fuel_current)
        fuel_cost = int(fuel_needed * FUEL_COST_PER_UNIT)

        # Railgun ammo -- sum across all railgun mounts
        railgun_cost = 0
        torpedo_cost = 0
        missile_cost = 0
        pdc_cost = 0

        weapons = ship_state.get("weapons", {})
        for _wid, wdata in weapons.items():
            wtype = wdata.get("weapon_type", "")
            current_ammo = wdata.get("ammo", 0) or 0
            max_ammo = wdata.get("ammo_capacity", current_ammo) or current_ammo
            needed = max(0, max_ammo - current_ammo)
            if "railgun" in wtype:
                railgun_cost += int(needed * AMMO_COST_RAILGUN)
            elif "pdc" in wtype:
                # PDC cost is fractional -- round up to nearest credit
                pdc_cost += max(0, int(needed * AMMO_COST_PDC + 0.99))

        # Torpedoes and missiles
        torp_current = ship_state.get("torpedoes_loaded", 0)
        torp_max = ship_state.get("torpedo_capacity", torp_current)
        torpedo_cost = max(0, torp_max - torp_current) * AMMO_COST_TORPEDO

        missile_current = ship_state.get("missiles_loaded", 0)
        missile_max = ship_state.get("missile_capacity", missile_current)
        missile_cost = max(0, missile_max - missile_current) * AMMO_COST_MISSILE

        total = fuel_cost + railgun_cost + int(torpedo_cost) + int(missile_cost) + pdc_cost
        return {
            "fuel": fuel_cost,
            "railgun": railgun_cost,
            "torpedo": int(torpedo_cost),
            "missile": int(missile_cost),
            "pdc": pdc_cost,
            "total": total,
        }

    @staticmethod
    def get_upgrade_cost(upgrade_type: str) -> int:
        """Get the credit cost for an upgrade type.

        Args:
            upgrade_type: One of armor, sensor_range, gimbal, torpedo_tube,
                drone_bay, reactor.

        Returns:
            Cost in credits.

        Raises:
            ValueError: If upgrade_type is unknown.
        """
        costs = {
            "armor": UPGRADE_ARMOR_PER_CM,
            "sensor_range": UPGRADE_SENSOR_RANGE,
            "gimbal": UPGRADE_GIMBAL_CONVERT,
            "torpedo_tube": UPGRADE_TORPEDO_TUBE,
            "drone_bay": UPGRADE_DRONE_BAY,
            "reactor": UPGRADE_REACTOR_OUTPUT,
        }
        if upgrade_type not in costs:
            raise ValueError(f"Unknown upgrade type: {upgrade_type}")
        return costs[upgrade_type]

    @staticmethod
    def get_crew_cost(skill_level: str) -> int:
        """Get cost to hire a crew member at a given skill level.

        Args:
            skill_level: One of 'competent', 'skilled', 'expert'.

        Returns:
            Cost in credits.

        Raises:
            ValueError: If skill_level is unknown.
        """
        costs = {
            "competent": CREW_COST_COMPETENT,
            "skilled": CREW_COST_SKILLED,
            "expert": CREW_COST_EXPERT,
        }
        if skill_level not in costs:
            raise ValueError(f"Unknown skill level: {skill_level}")
        return costs[skill_level]

    # ── Mutations (require CampaignState) ────────────────────

    @staticmethod
    def apply_repair(
        campaign: CampaignState,
        ship_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Deduct credits and restore ship to full health.

        Args:
            campaign: Mutable campaign state (credits will be deducted).
            ship_state: Mutable ship state dict (health will be restored).

        Returns:
            Dict with cost breakdown and updated ship_state.

        Raises:
            ValueError: If insufficient credits.
        """
        cost = EconomyManager.calculate_repair_cost(ship_state)
        if cost["total"] == 0:
            return {"ok": True, "cost": cost, "message": "No repairs needed"}

        campaign.deduct_credits(cost["total"], "station_repair")

        # Restore hull
        ship_state["hull_integrity"] = ship_state.get(
            "max_hull_integrity", ship_state.get("hull_integrity", 0)
        )

        # Restore subsystems
        for name, info in ship_state.get("subsystems", {}).items():
            info["health"] = info.get("max_health", info.get("health", 0))

        return {
            "ok": True,
            "cost": cost,
            "credits_remaining": campaign.credits,
            "message": f"Repairs complete (-{cost['total']} cr)",
        }

    @staticmethod
    def apply_resupply(
        campaign: CampaignState,
        ship_state: Dict[str, Any],
        ship_class: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Deduct credits and restore ammo/fuel to max.

        Args:
            campaign: Mutable campaign state.
            ship_state: Mutable ship state dict.
            ship_class: Ship class definition for capacities.

        Returns:
            Dict with cost breakdown and updated ship_state.

        Raises:
            ValueError: If insufficient credits.
        """
        cost = EconomyManager.calculate_resupply_cost(ship_state, ship_class)
        if cost["total"] == 0:
            return {"ok": True, "cost": cost, "message": "Already fully supplied"}

        campaign.deduct_credits(cost["total"], "station_resupply")

        # Restore fuel
        fuel_max = ship_class.get("systems", {}).get(
            "propulsion", {}
        ).get("max_fuel", ship_state.get("fuel_level", 0))
        ship_state["fuel_level"] = fuel_max

        # Restore weapon ammo
        for _wid, wdata in ship_state.get("weapons", {}).items():
            cap = wdata.get("ammo_capacity")
            if cap is not None:
                wdata["ammo"] = cap

        # Restore torpedoes and missiles
        ship_state["torpedoes_loaded"] = ship_state.get("torpedo_capacity", 0)
        ship_state["missiles_loaded"] = ship_state.get("missile_capacity", 0)

        return {
            "ok": True,
            "cost": cost,
            "credits_remaining": campaign.credits,
            "message": f"Resupply complete (-{cost['total']} cr)",
        }

    @staticmethod
    def hire_crew(
        campaign: CampaignState,
        skill_level: str,
        name: str = "New Recruit",
    ) -> Dict[str, Any]:
        """Deduct credits and create a crew member record.

        Does not directly mutate a CrewManager -- returns the skill data
        so the caller can wire it into whichever crew system is active.

        Args:
            campaign: Mutable campaign state.
            skill_level: 'competent', 'skilled', or 'expert'.
            name: Display name for the crew member.

        Returns:
            Dict with crew info and cost.

        Raises:
            ValueError: If insufficient credits or unknown skill level.
        """
        cost = EconomyManager.get_crew_cost(skill_level)
        campaign.deduct_credits(cost, f"hire_crew_{skill_level}")

        # Map skill level to numeric value for CrewSkills
        skill_values = {"competent": 3, "skilled": 4, "expert": 5}
        skill_val = skill_values[skill_level]

        return {
            "ok": True,
            "name": name,
            "skill_level": skill_level,
            "skill_value": skill_val,
            "cost": cost,
            "credits_remaining": campaign.credits,
            "message": f"Hired {skill_level} crew member (-{cost} cr)",
        }

    @staticmethod
    def apply_upgrade(
        campaign: CampaignState,
        ship_state: Dict[str, Any],
        upgrade_type: str,
        target: str = "",
    ) -> Dict[str, Any]:
        """Apply a ship upgrade by deducting credits and mutating state.

        Args:
            campaign: Mutable campaign state.
            ship_state: Mutable ship state dict.
            upgrade_type: One of armor, sensor_range, gimbal, torpedo_tube,
                drone_bay, reactor.
            target: Context-dependent target -- section name for armor,
                mount_id for gimbal, etc.

        Returns:
            Dict with upgrade details and cost.

        Raises:
            ValueError: If insufficient credits or invalid upgrade.
        """
        cost = EconomyManager.get_upgrade_cost(upgrade_type)
        campaign.deduct_credits(cost, f"upgrade_{upgrade_type}_{target}")

        description = ""

        if upgrade_type == "armor":
            # Add 1cm of armor to the target section
            armor = ship_state.get("armor", {})
            section = armor.get(target, {})
            if not section:
                # Refund -- invalid section
                campaign.add_credits(cost, f"refund_upgrade_armor_{target}")
                return {
                    "ok": False,
                    "error": f"Unknown armor section: {target}",
                }
            current = section.get("thickness_cm", 0)
            section["thickness_cm"] = current + 1.0
            description = f"+1cm armor on {target} (now {current + 1.0}cm)"

        elif upgrade_type == "sensor_range":
            sensors = ship_state.get("sensors", {})
            passive = sensors.get("passive", {})
            current_range = passive.get("range", 200000)
            new_range = int(current_range * 1.2)
            passive["range"] = new_range
            description = f"Sensor range +20% (now {new_range / 1000:.0f}km)"

        elif upgrade_type == "gimbal":
            # Convert a fixed weapon mount to gimbal-tracked
            mounts = ship_state.get("weapon_mounts", [])
            found = False
            for mount in mounts:
                if mount.get("mount_id") == target:
                    mount["gimbal"] = True
                    found = True
                    description = f"Mount {target} converted to gimbal"
                    break
            if not found:
                campaign.add_credits(cost, f"refund_upgrade_gimbal_{target}")
                return {"ok": False, "error": f"Unknown mount: {target}"}

        elif upgrade_type == "torpedo_tube":
            current = ship_state.get("torpedo_tubes", 0)
            ship_state["torpedo_tubes"] = current + 1
            # Each tube holds 4 torpedoes
            ship_state["torpedo_capacity"] = ship_state.get(
                "torpedo_capacity", current * 4
            ) + 4
            description = f"+1 torpedo tube (now {current + 1})"

        elif upgrade_type == "drone_bay":
            current = ship_state.get("drone_bays", 0)
            ship_state["drone_bays"] = current + 1
            ship_state["drone_capacity"] = ship_state.get(
                "drone_capacity", current * 4
            ) + 4
            description = f"+1 drone bay (now {current + 1})"

        elif upgrade_type == "reactor":
            power = ship_state.get("power_management", {})
            primary = power.get("primary", {})
            current_output = primary.get("output", 100)
            new_output = round(current_output * 1.1, 1)
            primary["output"] = new_output
            description = f"Reactor +10% (now {new_output})"

        else:
            campaign.add_credits(cost, f"refund_upgrade_unknown_{upgrade_type}")
            return {"ok": False, "error": f"Unknown upgrade type: {upgrade_type}"}

        return {
            "ok": True,
            "upgrade_type": upgrade_type,
            "target": target,
            "description": description,
            "cost": cost,
            "credits_remaining": campaign.credits,
            "message": f"{description} (-{cost} cr)",
        }

    # ── Price list ───────────────────────────────────────────

    @staticmethod
    def get_price_list() -> Dict[str, Any]:
        """Return full price list for display in station services UI."""
        return {
            "repair": {
                "per_hull_point": REPAIR_COST_PER_HULL_POINT,
                "per_subsystem_point": REPAIR_COST_PER_SUBSYSTEM_POINT,
            },
            "ammo": {
                "railgun": AMMO_COST_RAILGUN,
                "torpedo": AMMO_COST_TORPEDO,
                "missile": AMMO_COST_MISSILE,
                "pdc": AMMO_COST_PDC,
            },
            "fuel": {
                "per_unit": FUEL_COST_PER_UNIT,
            },
            "crew": {
                "competent": CREW_COST_COMPETENT,
                "skilled": CREW_COST_SKILLED,
                "expert": CREW_COST_EXPERT,
            },
            "upgrades": {
                "armor": UPGRADE_ARMOR_PER_CM,
                "sensor_range": UPGRADE_SENSOR_RANGE,
                "gimbal": UPGRADE_GIMBAL_CONVERT,
                "torpedo_tube": UPGRADE_TORPEDO_TUBE,
                "drone_bay": UPGRADE_DRONE_BAY,
                "reactor": UPGRADE_REACTOR_OUTPUT,
            },
        }
