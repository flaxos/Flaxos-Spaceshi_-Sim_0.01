"""Default values and factory for new campaigns.

Separated from campaign_state.py to keep each module under 300 lines.
These constants and the starter crew/ship definitions are only used
when creating a brand-new campaign.
"""

from __future__ import annotations

from typing import Any, Dict, List

# -- Faction defaults ---------------------------------------------------

DEFAULT_FACTIONS: Dict[str, int] = {"UNS": 0, "OPA": 0, "Corporate": 0}

# -- Economy ------------------------------------------------------------

STARTING_CREDITS = 5000

# Credits awarded per mission outcome tier
CREDIT_REWARDS: Dict[str, int] = {
    "success": 1000,
    "partial": 500,
    "failure": 100,
}

# -- Ship defaults ------------------------------------------------------

STARTING_FUEL = 10000
STARTING_AMMO: Dict[str, int] = {
    "railgun": 20,
    "pdc": 6000,
    "torpedo": 4,
    "missile": 8,
}


def make_starter_ship(ship_class: str = "corvette") -> Dict[str, Any]:
    """Build the default ship state dict for a new campaign.

    Args:
        ship_class: Ship class identifier (e.g. "corvette", "frigate").

    Returns:
        Ship state dict ready for CampaignState.ship_state.
    """
    return {
        "class": ship_class,
        "hull_percent": 100.0,
        "subsystems": {
            "propulsion": 100.0,
            "sensors": 100.0,
            "weapons": 100.0,
            "reactor": 100.0,
            "rcs": 100.0,
            "radiators": 100.0,
        },
        "ammo": dict(STARTING_AMMO),
        "fuel": STARTING_FUEL,
        "max_fuel": STARTING_FUEL,
    }


# -- Crew defaults ------------------------------------------------------

def make_starter_crew() -> List[Dict[str, Any]]:
    """Build the default crew roster for a new campaign.

    Returns two crew members with competent-to-skilled levels:
    a commanding officer and an engineering specialist.

    Returns:
        List of crew dicts matching CrewMember.to_dict() format.
    """
    return [
        {
            "name": "Commander Vasquez",
            "crew_id": "crew_cpt",
            "skills": {
                "piloting": 4, "navigation": 4, "gunnery": 3,
                "targeting": 3, "sensors": 3, "electronic_warfare": 2,
                "engineering": 3, "damage_control": 3,
                "communications": 4, "command": 5, "fleet_tactics": 3,
            },
            "fatigue": 0.0,
            "stress": 0.0,
            "health": 1.0,
        },
        {
            "name": "Ensign Park",
            "crew_id": "crew_eng",
            "skills": {
                "piloting": 3, "navigation": 3, "gunnery": 2,
                "targeting": 2, "sensors": 3, "electronic_warfare": 2,
                "engineering": 4, "damage_control": 4,
                "communications": 2, "command": 2, "fleet_tactics": 1,
            },
            "fatigue": 0.0,
            "stress": 0.0,
            "health": 1.0,
        },
    ]
