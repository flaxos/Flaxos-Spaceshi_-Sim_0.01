# tests/test_economy_system.py
"""Tests for the campaign economy system (Phase 4B).

Covers:
- Mission reward calculation (difficulty, optional objectives, zero-damage)
- Repair cost calculation (hull + subsystem breakdown)
- Resupply cost calculation (fuel + ammo categories)
- Apply repair deducts credits and restores health
- Apply resupply deducts credits and fills ammo/fuel
- Hire crew deducts credits at correct tier
- Apply upgrade mutates ship state correctly
- Insufficient credits returns error
- Price list structure is complete
"""

import pytest
from hybrid.campaign.economy import (
    CampaignState,
    EconomyManager,
    REPAIR_COST_PER_HULL_POINT,
    REPAIR_COST_PER_SUBSYSTEM_POINT,
    AMMO_COST_RAILGUN,
    AMMO_COST_TORPEDO,
    AMMO_COST_MISSILE,
    AMMO_COST_PDC,
    FUEL_COST_PER_UNIT,
    CREW_COST_COMPETENT,
    CREW_COST_SKILLED,
    CREW_COST_EXPERT,
    UPGRADE_ARMOR_PER_CM,
    UPGRADE_SENSOR_RANGE,
    UPGRADE_REACTOR_OUTPUT,
    UPGRADE_TORPEDO_TUBE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_campaign(credits: int = 5000) -> CampaignState:
    """Create a campaign state with a specified credit balance."""
    return CampaignState(credits=credits)


def make_damaged_ship_state() -> dict:
    """Ship state dict with some hull and subsystem damage."""
    return {
        "hull_integrity": 100.0,
        "max_hull_integrity": 150.0,
        "subsystems": {
            "propulsion": {"health": 60.0, "max_health": 80.0},
            "weapons": {"health": 40.0, "max_health": 70.0},
            "sensors": {"health": 50.0, "max_health": 50.0},  # full health
        },
    }


def make_depleted_ship_state() -> dict:
    """Ship state dict with partially depleted ammo and fuel."""
    return {
        "hull_integrity": 150.0,
        "max_hull_integrity": 150.0,
        "subsystems": {},
        "fuel_level": 200.0,
        "weapons": {
            "railgun_1": {
                "weapon_type": "kinetic",  # contains 'railgun' substring won't match
                "ammo": 10,
                "ammo_capacity": 20,
            },
        },
        "torpedoes_loaded": 2,
        "torpedo_capacity": 8,
        "missiles_loaded": 4,
        "missile_capacity": 16,
    }


def make_depleted_ship_state_with_railgun() -> dict:
    """Ship state with railgun-type weapon for resupply cost test."""
    return {
        "hull_integrity": 150.0,
        "max_hull_integrity": 150.0,
        "subsystems": {},
        "fuel_level": 200.0,
        "weapons": {
            "railgun_1": {
                "weapon_type": "railgun",
                "ammo": 10,
                "ammo_capacity": 20,
            },
            "pdc_1": {
                "weapon_type": "pdc",
                "ammo": 2000,
                "ammo_capacity": 3000,
            },
        },
        "torpedoes_loaded": 2,
        "torpedo_capacity": 8,
        "missiles_loaded": 4,
        "missile_capacity": 16,
    }


def make_ship_class() -> dict:
    """Minimal ship class definition for capacity lookups."""
    return {
        "systems": {
            "propulsion": {"max_fuel": 400.0},
        },
    }


def make_success_result(optional_completed: int = 0,
                        damage_taken: float = 0) -> dict:
    """Mission result dict for a successful mission."""
    objectives = [
        {"id": "primary", "required": True, "status": "completed"},
    ]
    for i in range(optional_completed):
        objectives.append({
            "id": f"optional_{i}",
            "required": False,
            "status": "completed",
        })
    return {
        "status": "success",
        "objectives": objectives,
        "total_damage_taken": damage_taken,
    }


# ---------------------------------------------------------------------------
# Mission reward tests
# ---------------------------------------------------------------------------

class TestMissionReward:
    def test_easy_base_reward(self):
        result = EconomyManager.calculate_mission_reward(
            make_success_result(), "easy"
        )
        # easy base=100 + zero-damage bonus=100
        assert result["base"] == 100
        assert result["damage_bonus"] == 100
        assert result["total"] == 200

    def test_medium_base_reward(self):
        result = EconomyManager.calculate_mission_reward(
            make_success_result(), "medium"
        )
        assert result["base"] == 200

    def test_hard_base_reward(self):
        result = EconomyManager.calculate_mission_reward(
            make_success_result(), "hard"
        )
        assert result["base"] == 400

    def test_extreme_base_reward(self):
        result = EconomyManager.calculate_mission_reward(
            make_success_result(), "extreme"
        )
        assert result["base"] == 800

    def test_optional_objective_bonus(self):
        result = EconomyManager.calculate_mission_reward(
            make_success_result(optional_completed=3), "medium"
        )
        assert result["optional_bonus"] == 150  # 3 * 50
        assert result["total"] == 200 + 150 + 100  # base + optional + zero-damage

    def test_zero_damage_bonus(self):
        result = EconomyManager.calculate_mission_reward(
            make_success_result(damage_taken=0), "medium"
        )
        assert result["damage_bonus"] == 100

    def test_damage_taken_no_bonus(self):
        result = EconomyManager.calculate_mission_reward(
            make_success_result(damage_taken=50.0), "medium"
        )
        assert result["damage_bonus"] == 0
        assert result["total"] == 200

    def test_failure_pays_nothing(self):
        result = EconomyManager.calculate_mission_reward(
            {"status": "failure", "objectives": []}, "hard"
        )
        assert result["total"] == 0

    def test_unknown_difficulty_defaults_to_200(self):
        result = EconomyManager.calculate_mission_reward(
            make_success_result(), "nightmare"
        )
        assert result["base"] == 200


# ---------------------------------------------------------------------------
# Repair cost tests
# ---------------------------------------------------------------------------

class TestRepairCost:
    def test_damaged_ship_cost(self):
        state = make_damaged_ship_state()
        cost = EconomyManager.calculate_repair_cost(state)

        # Hull: 50 damage * 10 = 500
        assert cost["hull"] == 500
        # Propulsion: 20 damage * 5 = 100
        assert cost["subsystems"]["propulsion"] == 100
        # Weapons: 30 damage * 5 = 150
        assert cost["subsystems"]["weapons"] == 150
        # Sensors: 0 damage = not in dict
        assert "sensors" not in cost["subsystems"]
        assert cost["total"] == 500 + 100 + 150

    def test_full_health_zero_cost(self):
        state = {
            "hull_integrity": 150.0,
            "max_hull_integrity": 150.0,
            "subsystems": {
                "propulsion": {"health": 80.0, "max_health": 80.0},
            },
        }
        cost = EconomyManager.calculate_repair_cost(state)
        assert cost["total"] == 0


# ---------------------------------------------------------------------------
# Resupply cost tests
# ---------------------------------------------------------------------------

class TestResupplyCost:
    def test_depleted_ship_cost(self):
        state = make_depleted_ship_state_with_railgun()
        ship_class = make_ship_class()
        cost = EconomyManager.calculate_resupply_cost(state, ship_class)

        # Fuel: (400 - 200) * 1 = 200
        assert cost["fuel"] == 200
        # Railgun: 10 rounds * 2 = 20
        assert cost["railgun"] == 20
        # PDC: 1000 rounds * 0.1 = 100 (rounded up)
        assert cost["pdc"] == 100
        # Torpedoes: 6 * 50 = 300
        assert cost["torpedo"] == 300
        # Missiles: 12 * 20 = 240
        assert cost["missile"] == 240
        assert cost["total"] == 200 + 20 + 100 + 300 + 240

    def test_full_supply_zero_cost(self):
        state = {
            "fuel_level": 400.0,
            "weapons": {},
            "torpedoes_loaded": 8,
            "torpedo_capacity": 8,
            "missiles_loaded": 16,
            "missile_capacity": 16,
        }
        ship_class = {"systems": {"propulsion": {"max_fuel": 400.0}}}
        cost = EconomyManager.calculate_resupply_cost(state, ship_class)
        assert cost["total"] == 0


# ---------------------------------------------------------------------------
# Apply repair tests
# ---------------------------------------------------------------------------

class TestApplyRepair:
    def test_repair_deducts_and_restores(self):
        campaign = make_campaign(credits=5000)
        state = make_damaged_ship_state()

        result = EconomyManager.apply_repair(campaign, state)

        assert result["ok"] is True
        assert campaign.credits == 5000 - result["cost"]["total"]
        assert state["hull_integrity"] == 150.0
        assert state["subsystems"]["propulsion"]["health"] == 80.0
        assert state["subsystems"]["weapons"]["health"] == 70.0

    def test_repair_no_damage(self):
        campaign = make_campaign(credits=5000)
        state = {
            "hull_integrity": 150.0,
            "max_hull_integrity": 150.0,
            "subsystems": {},
        }
        result = EconomyManager.apply_repair(campaign, state)
        assert result["ok"] is True
        assert campaign.credits == 5000  # no deduction

    def test_repair_insufficient_credits(self):
        campaign = make_campaign(credits=10)
        state = make_damaged_ship_state()

        with pytest.raises(ValueError, match="Insufficient credits"):
            EconomyManager.apply_repair(campaign, state)


# ---------------------------------------------------------------------------
# Apply resupply tests
# ---------------------------------------------------------------------------

class TestApplyResupply:
    def test_resupply_deducts_and_fills(self):
        campaign = make_campaign(credits=5000)
        state = make_depleted_ship_state_with_railgun()
        ship_class = make_ship_class()

        result = EconomyManager.apply_resupply(campaign, state, ship_class)

        assert result["ok"] is True
        assert campaign.credits < 5000
        assert state["fuel_level"] == 400.0
        assert state["weapons"]["railgun_1"]["ammo"] == 20
        assert state["torpedoes_loaded"] == 8
        assert state["missiles_loaded"] == 16

    def test_resupply_insufficient_credits(self):
        campaign = make_campaign(credits=1)
        state = make_depleted_ship_state_with_railgun()
        ship_class = make_ship_class()

        with pytest.raises(ValueError, match="Insufficient credits"):
            EconomyManager.apply_resupply(campaign, state, ship_class)


# ---------------------------------------------------------------------------
# Hire crew tests
# ---------------------------------------------------------------------------

class TestHireCrew:
    def test_hire_competent(self):
        campaign = make_campaign(credits=1000)
        result = EconomyManager.hire_crew(campaign, "competent", "Ensign Kim")

        assert result["ok"] is True
        assert result["skill_level"] == "competent"
        assert result["skill_value"] == 3
        assert result["cost"] == CREW_COST_COMPETENT
        assert campaign.credits == 1000 - CREW_COST_COMPETENT

    def test_hire_skilled(self):
        campaign = make_campaign(credits=1000)
        result = EconomyManager.hire_crew(campaign, "skilled")
        assert result["cost"] == CREW_COST_SKILLED

    def test_hire_expert(self):
        campaign = make_campaign(credits=1000)
        result = EconomyManager.hire_crew(campaign, "expert")
        assert result["cost"] == CREW_COST_EXPERT

    def test_hire_unknown_level(self):
        campaign = make_campaign(credits=1000)
        with pytest.raises(ValueError, match="Unknown skill level"):
            EconomyManager.hire_crew(campaign, "legendary")

    def test_hire_insufficient_credits(self):
        campaign = make_campaign(credits=10)
        with pytest.raises(ValueError, match="Insufficient credits"):
            EconomyManager.hire_crew(campaign, "expert")


# ---------------------------------------------------------------------------
# Apply upgrade tests
# ---------------------------------------------------------------------------

class TestApplyUpgrade:
    def test_upgrade_armor(self):
        campaign = make_campaign(credits=5000)
        state = {
            "armor": {
                "fore": {"thickness_cm": 3.0, "material": "composite_cermet"},
            },
        }
        result = EconomyManager.apply_upgrade(campaign, state, "armor", "fore")

        assert result["ok"] is True
        assert result["cost"] == UPGRADE_ARMOR_PER_CM
        assert state["armor"]["fore"]["thickness_cm"] == 4.0

    def test_upgrade_armor_invalid_section(self):
        campaign = make_campaign(credits=5000)
        state = {"armor": {}}
        result = EconomyManager.apply_upgrade(campaign, state, "armor", "nonexistent")

        assert result["ok"] is False
        # Credits should be refunded
        assert campaign.credits == 5000

    def test_upgrade_sensor_range(self):
        campaign = make_campaign(credits=5000)
        state = {"sensors": {"passive": {"range": 200000}}}
        result = EconomyManager.apply_upgrade(campaign, state, "sensor_range")

        assert result["ok"] is True
        assert result["cost"] == UPGRADE_SENSOR_RANGE
        assert state["sensors"]["passive"]["range"] == 240000  # +20%

    def test_upgrade_reactor(self):
        campaign = make_campaign(credits=5000)
        state = {"power_management": {"primary": {"output": 100.0}}}
        result = EconomyManager.apply_upgrade(campaign, state, "reactor")

        assert result["ok"] is True
        assert result["cost"] == UPGRADE_REACTOR_OUTPUT
        assert state["power_management"]["primary"]["output"] == 110.0

    def test_upgrade_torpedo_tube(self):
        campaign = make_campaign(credits=5000)
        state = {"torpedo_tubes": 1, "torpedo_capacity": 4}
        result = EconomyManager.apply_upgrade(campaign, state, "torpedo_tube")

        assert result["ok"] is True
        assert state["torpedo_tubes"] == 2
        assert state["torpedo_capacity"] == 8

    def test_upgrade_insufficient_credits(self):
        campaign = make_campaign(credits=10)
        state = {}
        with pytest.raises(ValueError, match="Insufficient credits"):
            EconomyManager.apply_upgrade(campaign, state, "reactor")

    def test_upgrade_unknown_type(self):
        campaign = make_campaign(credits=5000)
        state = {}
        # Unknown type gets past get_upgrade_cost but refunds in apply_upgrade
        with pytest.raises(ValueError, match="Unknown upgrade type"):
            EconomyManager.apply_upgrade(campaign, state, "warp_drive")


# ---------------------------------------------------------------------------
# Campaign state tests
# ---------------------------------------------------------------------------

class TestCampaignState:
    def test_add_credits(self):
        cs = make_campaign(credits=100)
        cs.add_credits(50, "bounty")
        assert cs.credits == 150
        assert len(cs.transactions) == 1
        assert cs.transactions[0]["type"] == "credit"

    def test_deduct_credits(self):
        cs = make_campaign(credits=100)
        cs.deduct_credits(30, "repair")
        assert cs.credits == 70
        assert cs.transactions[0]["type"] == "debit"

    def test_deduct_over_balance_raises(self):
        cs = make_campaign(credits=100)
        with pytest.raises(ValueError, match="Insufficient credits"):
            cs.deduct_credits(200, "too_expensive")

    def test_to_dict(self):
        cs = make_campaign(credits=500)
        cs.add_credits(100, "reward")
        d = cs.to_dict()
        assert d["credits"] == 600
        assert len(d["transactions"]) == 1


# ---------------------------------------------------------------------------
# Price list test
# ---------------------------------------------------------------------------

class TestPriceList:
    def test_price_list_structure(self):
        prices = EconomyManager.get_price_list()
        assert "repair" in prices
        assert "ammo" in prices
        assert "fuel" in prices
        assert "crew" in prices
        assert "upgrades" in prices
        assert prices["ammo"]["railgun"] == AMMO_COST_RAILGUN
        assert prices["crew"]["expert"] == CREW_COST_EXPERT
        assert prices["upgrades"]["torpedo_tube"] == UPGRADE_TORPEDO_TUBE
