"""Role-based AI behavior profiles for NPC ships.

Each ship role (combat, freighter, escort, patrol, raider, defender,
sniper, swarm) has a tuned set of thresholds that drive AI decisions.
Profiles are dataclass instances so they're easy to inspect, override
from scenario YAML, and test in isolation.

Design rationale:
  - aggression gates whether the AI actively seeks combat vs waits
  - engagement_range is the distance at which the AI starts closing
  - flee/evade thresholds are hull-fraction triggers (hull / max_hull)
  - weapon_confidence_threshold prevents low-probability shots;
    freighters set this to 1.0 so they never fire
  - protect_target / patrol_position are role-specific data
  - preferred_weapon hints at ordnance selection (raider doctrine)
  - disengage_after_salvo drives hit-and-run attack cycling
  - hold_position returns the AI to spawn point after engagement
  - min_engagement_range keeps snipers at standoff distance
  - pack_targeting converges swarm ships onto fleet lead's target
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

    # ── Phase 2B: advanced role fields ────────────────────────────
    # These have safe defaults so existing profiles are unaffected.

    # Preferred ordnance type: "torpedo", "missile", "railgun", or
    # None (let combat system choose).  Raider doctrine fires
    # torpedoes/missiles at standoff range.
    preferred_weapon: Optional[str] = None

    # Hit-and-run doctrine: fire one salvo then evade for
    # disengage_cooldown seconds before re-approaching.
    disengage_after_salvo: bool = False
    disengage_cooldown: float = 30.0  # seconds in EVADE after salvo

    # Station-keeping: return to initial spawn position after
    # engagement ends or target is destroyed.
    hold_position: bool = False

    # Standoff range: AI repositions AWAY from target when closer
    # than this.  Snipers use this to maintain railgun range.
    # 0 means no minimum range enforced.
    min_engagement_range: float = 0.0

    # Pack targeting: all ships with this flag in the same faction
    # converge on the fleet lead's target instead of spreading fire.
    pack_targeting: bool = False


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

    # ── Phase 2B roles ────────────────────────────────────────────

    "raider": BehaviorProfile(
        # Hit-and-run doctrine: close to torpedo range, fire one
        # salvo, then disengage for 30s before re-approaching.
        # Pirates and ambush attackers use this profile.
        role="raider",
        aggression=0.8,
        engagement_range=60_000,       # torpedo effective range
        flee_threshold=0.4,            # runs early -- survival > glory
        evade_threshold=0.3,           # starts evading early
        max_thrust_profile=0.5,
        weapon_confidence_threshold=0.3,
        preferred_weapon="torpedo",
        disengage_after_salvo=True,
        disengage_cooldown=30.0,
    ),
    "defender": BehaviorProfile(
        # Station guard doctrine: holds position, engages only
        # close threats, evades readily but almost never flees.
        # Garrison ships and station guards use this profile.
        role="defender",
        aggression=0.3,
        engagement_range=20_000,       # short leash -- defend, don't chase
        flee_threshold=0.1,            # fights to near-death
        evade_threshold=0.6,           # evades readily to stay alive
        max_thrust_profile=0.4,
        weapon_confidence_threshold=0.3,
        hold_position=True,
    ),
    "sniper": BehaviorProfile(
        # Long-range fire support: engages at extreme railgun range
        # and actively repositions to MAINTAIN distance.  Only fires
        # when firing solution confidence is high.
        role="sniper",
        aggression=0.5,
        engagement_range=150_000,      # extreme railgun range
        flee_threshold=0.3,
        evade_threshold=0.5,
        max_thrust_profile=0.4,
        weapon_confidence_threshold=0.7,  # only fires confident shots
        min_engagement_range=50_000,   # never closes below 50km
    ),
    "swarm": BehaviorProfile(
        # Overwhelming numbers doctrine: very high aggression,
        # converges on the fleet lead's target.  Fights to near-death.
        # Fighter wings and drone groups use this profile.
        role="swarm",
        aggression=0.95,
        engagement_range=30_000,       # medium range -- close fast
        flee_threshold=0.15,           # fights to near-death
        evade_threshold=0.1,           # barely evades -- aggression first
        max_thrust_profile=0.6,        # fast closure
        weapon_confidence_threshold=0.2,
        pack_targeting=True,
    ),
}


def get_profile(role: str, overrides: Optional[dict] = None) -> BehaviorProfile:
    """Get a behavior profile for a role, with optional field overrides.

    Args:
        role: One of "combat", "freighter", "escort", "patrol",
              "raider", "defender", "sniper", "swarm".
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
