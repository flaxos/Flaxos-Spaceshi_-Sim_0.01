"""Role-based AI behavior profiles for NPC ships.

Each ship role (combat, freighter, escort, patrol) has a tuned set of
thresholds that drive AI decisions.  Profiles are dataclass instances so
they're easy to inspect, override from scenario YAML, and test in
isolation.

Design rationale:
  - aggression gates whether the AI actively seeks combat vs waits
  - engagement_range is the distance at which the AI starts closing
  - flee/evade thresholds are hull-fraction triggers (hull / max_hull)
  - weapon_confidence_threshold prevents low-probability shots;
    freighters set this to 1.0 so they never fire
  - protect_target / patrol_position are role-specific data
"""

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class BehaviorProfile:
    """Role-based AI behavior configuration.

    Controls how an NPC ship reacts to threats, when it flees,
    and what weapons/throttle settings it uses.
    """

    role: str = "combat"
    aggression: float = 0.5          # 0-1, affects engagement thresholds
    engagement_range: float = 50_000.0   # metres -- start closing
    flee_threshold: float = 0.3      # flee when hull fraction < this
    evade_threshold: float = 0.5     # begin evasive when hull < this
    protect_target: Optional[str] = None   # ship_id to escort
    patrol_position: Optional[Dict[str, float]] = None  # {x,y,z}
    max_thrust_profile: float = 0.5  # throttle fraction for maneuvers
    weapon_confidence_threshold: float = 0.3  # min firing solution conf


# ── Default profiles per role ────────────────────────────────────

ROLE_DEFAULTS: Dict[str, BehaviorProfile] = {
    "combat": BehaviorProfile(
        role="combat",
        aggression=0.8,
        engagement_range=80_000,
        flee_threshold=0.2,
        evade_threshold=0.4,
        max_thrust_profile=0.5,
        weapon_confidence_threshold=0.2,
    ),
    "freighter": BehaviorProfile(
        role="freighter",
        aggression=0.0,
        engagement_range=0,         # never actively engages
        flee_threshold=0.9,         # runs at first scratch
        evade_threshold=1.0,        # always evading when threatened
        max_thrust_profile=0.3,     # cargo ships throttle gently
        weapon_confidence_threshold=1.0,  # impossible to meet -- never fires
    ),
    "escort": BehaviorProfile(
        role="escort",
        aggression=0.6,
        engagement_range=30_000,    # stays near ward, shorter leash
        flee_threshold=0.15,        # escorts fight harder before fleeing
        evade_threshold=0.35,
        max_thrust_profile=0.5,
        weapon_confidence_threshold=0.3,
    ),
    "patrol": BehaviorProfile(
        role="patrol",
        aggression=0.4,
        engagement_range=40_000,
        flee_threshold=0.3,
        evade_threshold=0.5,
        max_thrust_profile=0.3,
        weapon_confidence_threshold=0.4,
    ),
}


def get_profile(role: str, overrides: Optional[dict] = None) -> BehaviorProfile:
    """Get a behavior profile for a role, with optional field overrides.

    Args:
        role: One of "combat", "freighter", "escort", "patrol".
              Falls back to "combat" for unknown roles.
        overrides: Dict of field_name -> value to patch onto the base
                   profile.  Unknown keys are silently ignored.

    Returns:
        A new BehaviorProfile instance (never mutates ROLE_DEFAULTS).
    """
    base = ROLE_DEFAULTS.get(role, ROLE_DEFAULTS["combat"])
    # Shallow-copy so we never mutate the default
    profile = BehaviorProfile(**{k: v for k, v in base.__dict__.items()})
    if overrides:
        for k, v in overrides.items():
            if hasattr(profile, k):
                setattr(profile, k, v)
    return profile


def infer_role(ship_class: str, faction: str) -> str:
    """Infer AI role from ship class and faction strings.

    This provides a sensible default when the scenario YAML does not
    specify an explicit ai_behavior block.

    Args:
        ship_class: e.g. "corvette", "freighter", "station".
        faction: e.g. "pirates", "civilian", "unsa".

    Returns:
        Role string: "combat", "freighter", "escort", or "patrol".
    """
    class_lower = (ship_class or "").lower()
    faction_lower = (faction or "").lower()

    # Class-based rules first (most specific)
    if class_lower in ("freighter", "transport", "tanker", "hauler"):
        return "freighter"
    if class_lower == "station":
        return "patrol"  # stations hold position

    # Faction-based fallbacks
    if faction_lower in ("pirates", "hostile"):
        return "combat"
    if faction_lower == "civilian":
        return "freighter"

    # Military default
    return "combat"
