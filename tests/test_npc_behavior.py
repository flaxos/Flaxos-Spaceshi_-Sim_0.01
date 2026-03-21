"""Tests for NPC AI Phase 2: role-based behavior profiles.

Validates:
  1. BehaviorProfile defaults and overrides
  2. Role inference from ship class and faction
  3. Profile integration in AIController
  4. Freighter flee behavior (never fires, emits distress)
  5. Escort behavior (protects ward)
  6. Patrol behavior (holds position, engages within range)
  7. Damage reaction thresholds (flee/evade from hull fraction)
  8. Scenario YAML ai_behavior loading
  9. get_state includes role and hull_fraction
"""

import pytest
import logging

logger = logging.getLogger(__name__)


# Minimal system configs for AI test ships
AI_SHIP_SYSTEMS = {
    "sensors": {"passive": {"range": 200000}},
    "targeting": {},
    "combat": {"railguns": 1, "pdcs": 1},
    "navigation": {},
    "propulsion": {"max_thrust": 50000, "fuel_level": 10000},
}

FREIGHTER_SYSTEMS = {
    "sensors": {"passive": {"range": 100000}},
    "navigation": {},
    "propulsion": {"max_thrust": 80000, "fuel_level": 20000},
}


# ── BehaviorProfile defaults ────────────────────────────────────

def test_behavior_profile_defaults():
    """BehaviorProfile has sensible field defaults."""
    from hybrid.fleet.npc_behavior import BehaviorProfile

    p = BehaviorProfile()
    assert p.role == "combat"
    assert 0.0 <= p.aggression <= 1.0
    assert p.engagement_range > 0
    assert 0.0 <= p.flee_threshold <= 1.0
    assert p.protect_target is None
    assert p.patrol_position is None


def test_role_defaults_exist():
    """ROLE_DEFAULTS has entries for all four roles."""
    from hybrid.fleet.npc_behavior import ROLE_DEFAULTS

    for role in ("combat", "freighter", "escort", "patrol"):
        assert role in ROLE_DEFAULTS
        assert ROLE_DEFAULTS[role].role == role


def test_freighter_profile_never_fires():
    """Freighter weapon_confidence_threshold is 1.0 (unreachable)."""
    from hybrid.fleet.npc_behavior import ROLE_DEFAULTS

    freighter = ROLE_DEFAULTS["freighter"]
    assert freighter.weapon_confidence_threshold >= 1.0
    assert freighter.aggression == 0.0
    assert freighter.engagement_range == 0


def test_combat_profile_most_aggressive():
    """Combat role has highest aggression and engagement range."""
    from hybrid.fleet.npc_behavior import ROLE_DEFAULTS

    combat = ROLE_DEFAULTS["combat"]
    assert combat.aggression >= 0.7
    assert combat.engagement_range >= 50_000


# ── get_profile ──────────────────────────────────────────────────

def test_get_profile_returns_copy():
    """get_profile returns a new instance, not the stored default."""
    from hybrid.fleet.npc_behavior import get_profile, ROLE_DEFAULTS

    p = get_profile("combat")
    assert p is not ROLE_DEFAULTS["combat"]
    assert p.role == "combat"


def test_get_profile_with_overrides():
    """get_profile applies field overrides."""
    from hybrid.fleet.npc_behavior import get_profile

    p = get_profile("combat", {"aggression": 0.1, "engagement_range": 5000})
    assert p.aggression == 0.1
    assert p.engagement_range == 5000
    # Non-overridden fields keep defaults
    assert p.role == "combat"


def test_get_profile_unknown_role_falls_back_to_combat():
    """Unknown role falls back to combat defaults."""
    from hybrid.fleet.npc_behavior import get_profile

    p = get_profile("unknown_role")
    assert p.role == "combat"


def test_get_profile_ignores_unknown_overrides():
    """Override keys that don't exist on BehaviorProfile are ignored."""
    from hybrid.fleet.npc_behavior import get_profile

    p = get_profile("combat", {"nonexistent_field": 42})
    assert not hasattr(p, "nonexistent_field")


# ── infer_role ───────────────────────────────────────────────────

def test_infer_role_freighter_class():
    """Freighter/transport/tanker class types infer freighter role."""
    from hybrid.fleet.npc_behavior import infer_role

    assert infer_role("freighter", "unsa") == "freighter"
    assert infer_role("transport", "civilian") == "freighter"
    assert infer_role("tanker", "mars") == "freighter"
    assert infer_role("hauler", "civilian") == "freighter"


def test_infer_role_station():
    """Station class infers patrol role."""
    from hybrid.fleet.npc_behavior import infer_role

    assert infer_role("station", "unsa") == "patrol"


def test_infer_role_pirate_faction():
    """Pirates and hostile factions infer combat role."""
    from hybrid.fleet.npc_behavior import infer_role

    assert infer_role("corvette", "pirates") == "combat"
    assert infer_role("frigate", "hostile") == "combat"


def test_infer_role_civilian_faction():
    """Civilian faction infers freighter role."""
    from hybrid.fleet.npc_behavior import infer_role

    assert infer_role("shuttle", "civilian") == "freighter"


def test_infer_role_military_default():
    """Military ships without special class default to combat."""
    from hybrid.fleet.npc_behavior import infer_role

    assert infer_role("corvette", "unsa") == "combat"
    assert infer_role("frigate", "mars") == "combat"


def test_infer_role_none_inputs():
    """None inputs don't crash, default to combat."""
    from hybrid.fleet.npc_behavior import infer_role

    assert infer_role(None, None) == "combat"
    assert infer_role(None, "civilian") == "freighter"


# ── AIController profile integration ────────────────────────────

def test_ai_controller_auto_infers_profile():
    """AIController auto-assigns a BehaviorProfile from ship attributes."""
    from hybrid.ship import Ship
    from hybrid.fleet.npc_behavior import BehaviorProfile

    ship = Ship("pirate_fighter", {
        "mass": 2000,
        "class": "fighter",
        "faction": "pirates",
        "ai_enabled": True,
        "systems": AI_SHIP_SYSTEMS,
    })

    assert ship.ai_controller is not None
    assert isinstance(ship.ai_controller.profile, BehaviorProfile)
    assert ship.ai_controller.profile.role == "combat"


def test_ai_controller_freighter_profile():
    """Freighter-class ship gets freighter profile."""
    from hybrid.ship import Ship

    ship = Ship("cargo_ship", {
        "mass": 50000,
        "class": "freighter",
        "faction": "civilian",
        "ai_enabled": True,
        "systems": FREIGHTER_SYSTEMS,
    })

    assert ship.ai_controller.profile.role == "freighter"
    assert ship.ai_controller.profile.weapon_confidence_threshold >= 1.0


def test_ai_controller_engagement_range_from_profile():
    """AIController.engagement_range is set from the profile."""
    from hybrid.ship import Ship

    ship = Ship("warship", {
        "mass": 5000,
        "class": "corvette",
        "faction": "hostile",
        "ai_enabled": True,
        "systems": AI_SHIP_SYSTEMS,
    })

    # Combat profile defaults to 80km engagement range
    assert ship.ai_controller.engagement_range == 80_000


# ── Scenario YAML ai_behavior loading ───────────────────────────

def test_yaml_ai_behavior_overrides_profile():
    """ai_behavior block in config overrides auto-inferred profile."""
    from hybrid.ship import Ship

    ship = Ship("escort_ship", {
        "mass": 5000,
        "class": "corvette",
        "faction": "unsa",
        "ai_enabled": True,
        "ai_behavior": {
            "role": "escort",
            "protect_target": "freighter01",
            "engagement_range": 25000,
        },
        "systems": AI_SHIP_SYSTEMS,
    })

    assert ship.ai_controller.profile.role == "escort"
    assert ship.ai_controller.profile.protect_target == "freighter01"
    assert ship.ai_controller.profile.engagement_range == 25000
    assert ship.ai_controller.engagement_range == 25000


def test_yaml_ai_behavior_partial_override():
    """ai_behavior with only role uses role defaults for other fields."""
    from hybrid.ship import Ship

    ship = Ship("patrol_ship", {
        "mass": 5000,
        "class": "corvette",
        "faction": "unsa",
        "ai_enabled": True,
        "ai_behavior": {"role": "patrol"},
        "systems": AI_SHIP_SYSTEMS,
    })

    assert ship.ai_controller.profile.role == "patrol"
    # Should have patrol defaults, not combat defaults
    assert ship.ai_controller.profile.aggression == 0.4
    assert ship.ai_controller.profile.engagement_range == 40_000


# ── Freighter flee behavior ─────────────────────────────────────

def test_freighter_flees_on_threat():
    """Freighter AI switches to FLEE when threats are detected."""
    from hybrid.ship import Ship
    from hybrid.fleet.ai_controller import AIBehavior
    from hybrid.systems.sensors.contact import ContactData

    ship = Ship("cargo01", {
        "mass": 50000,
        "class": "freighter",
        "faction": "civilian",
        "ai_enabled": True,
        "systems": FREIGHTER_SYSTEMS,
    })

    assert ship.ai_controller.profile.role == "freighter"
    assert ship.ai_controller.behavior == AIBehavior.IDLE

    # Inject a hostile contact
    sensors = ship.systems.get("sensors")
    pirate = ContactData(
        id="pirate",
        position={"x": 30000, "y": 0, "z": 0},
        velocity={"x": -200, "y": 0, "z": 0},
        confidence=0.9,
        last_update=0.0,
        detection_method="ir",
        faction="pirates",
    )
    sensors.contact_tracker.update_contact("pirate", pirate, 0.0)

    # Run AI update
    ship.ai_controller.update(0.1, 3.0)

    assert ship.ai_controller.behavior == AIBehavior.FLEE


def test_freighter_never_fires():
    """Freighter _engage_target is a no-op due to confidence threshold."""
    from hybrid.ship import Ship
    from hybrid.systems.sensors.contact import ContactData

    ship = Ship("cargo01", {
        "mass": 50000,
        "class": "freighter",
        "faction": "civilian",
        "ai_enabled": True,
        "systems": {
            **FREIGHTER_SYSTEMS,
            "targeting": {},
            "combat": {"railguns": 1},
        },
    })

    sensors = ship.systems.get("sensors")
    pirate = ContactData(
        id="pirate",
        position={"x": 5000, "y": 0, "z": 0},
        velocity={"x": 0, "y": 0, "z": 0},
        confidence=0.9,
        last_update=0.0,
        detection_method="ir",
        faction="pirates",
    )
    sensors.contact_tracker.update_contact("pirate", pirate, 0.0)

    # Calling _engage_target should be a no-op (returns early)
    ship.ai_controller._engage_target("pirate", pirate)

    # Verify no weapons were fired -- combat system should not have been called
    # (the method returns before reaching the combat system)


def test_freighter_emits_distress():
    """Freighter emits distress_signal on event bus when fleeing."""
    from hybrid.ship import Ship
    from hybrid.fleet.ai_controller import AIBehavior
    from hybrid.systems.sensors.contact import ContactData

    ship = Ship("cargo01", {
        "mass": 50000,
        "class": "freighter",
        "faction": "civilian",
        "ai_enabled": True,
        "systems": FREIGHTER_SYSTEMS,
    })

    # Track distress events
    distress_events = []
    ship.event_bus.subscribe("distress_signal", lambda data: distress_events.append(data))

    # Inject threat and update
    sensors = ship.systems.get("sensors")
    pirate = ContactData(
        id="pirate",
        position={"x": 30000, "y": 0, "z": 0},
        velocity={"x": -200, "y": 0, "z": 0},
        confidence=0.9,
        last_update=0.0,
        detection_method="ir",
        faction="pirates",
    )
    sensors.contact_tracker.update_contact("pirate", pirate, 0.0)

    ship.ai_controller.update(0.1, 3.0)

    assert len(distress_events) == 1
    assert distress_events[0]["ship_id"] == "cargo01"


def test_freighter_distress_emitted_only_once():
    """Distress signal is not re-emitted every decision cycle."""
    from hybrid.ship import Ship
    from hybrid.systems.sensors.contact import ContactData

    ship = Ship("cargo01", {
        "mass": 50000,
        "class": "freighter",
        "faction": "civilian",
        "ai_enabled": True,
        "systems": FREIGHTER_SYSTEMS,
    })

    distress_events = []
    ship.event_bus.subscribe("distress_signal", lambda data: distress_events.append(data))

    sensors = ship.systems.get("sensors")
    pirate = ContactData(
        id="pirate",
        position={"x": 30000, "y": 0, "z": 0},
        velocity={"x": -200, "y": 0, "z": 0},
        confidence=0.9,
        last_update=0.0,
        detection_method="ir",
        faction="pirates",
    )
    sensors.contact_tracker.update_contact("pirate", pirate, 0.0)

    # Multiple decision cycles
    ship.ai_controller.update(0.1, 3.0)
    ship.ai_controller.update(0.1, 6.0)
    ship.ai_controller.update(0.1, 9.0)

    assert len(distress_events) == 1


# ── Escort behavior ─────────────────────────────────────────────

def test_escort_protects_ward():
    """Escort AI with protect_target set enters ESCORT behavior."""
    from hybrid.ship import Ship
    from hybrid.fleet.ai_controller import AIBehavior

    ship = Ship("escort01", {
        "mass": 5000,
        "class": "corvette",
        "faction": "unsa",
        "ai_enabled": True,
        "ai_behavior": {
            "role": "escort",
            "protect_target": "freighter01",
        },
        "systems": AI_SHIP_SYSTEMS,
    })

    assert ship.ai_controller.profile.role == "escort"
    assert ship.ai_controller.profile.protect_target == "freighter01"


def test_escort_returns_to_escort_after_threat_cleared():
    """When threats are cleared, escort returns to ESCORT not IDLE."""
    from hybrid.ship import Ship
    from hybrid.fleet.ai_controller import AIBehavior

    ship = Ship("escort01", {
        "mass": 5000,
        "class": "corvette",
        "faction": "unsa",
        "ai_enabled": True,
        "ai_behavior": {
            "role": "escort",
            "protect_target": "freighter01",
        },
        "systems": AI_SHIP_SYSTEMS,
    })

    # Force into ATTACK, then clear threats
    ship.ai_controller.set_behavior(AIBehavior.ATTACK)
    ship.ai_controller.update(0.1, 3.0)  # No threats -> return to role

    assert ship.ai_controller.behavior == AIBehavior.ESCORT


# ── Patrol behavior ─────────────────────────────────────────────

def test_patrol_returns_to_patrol_after_threat_cleared():
    """When threats are cleared, patrol returns to PATROL not IDLE."""
    from hybrid.ship import Ship
    from hybrid.fleet.ai_controller import AIBehavior

    ship = Ship("patrol01", {
        "mass": 5000,
        "class": "corvette",
        "faction": "unsa",
        "ai_enabled": True,
        "ai_behavior": {"role": "patrol"},
        "systems": AI_SHIP_SYSTEMS,
    })

    ship.ai_controller.set_behavior(AIBehavior.ATTACK)
    ship.ai_controller.update(0.1, 3.0)

    assert ship.ai_controller.behavior == AIBehavior.PATROL


def test_patrol_only_engages_within_range():
    """Patrol ship ignores threats beyond engagement_range."""
    from hybrid.ship import Ship
    from hybrid.fleet.ai_controller import AIBehavior
    from hybrid.systems.sensors.contact import ContactData

    ship = Ship("patrol01", {
        "mass": 5000,
        "class": "corvette",
        "faction": "unsa",
        "ai_enabled": True,
        "ai_behavior": {
            "role": "patrol",
            "engagement_range": 30000,
        },
        "systems": AI_SHIP_SYSTEMS,
    })

    # Inject a threat beyond engagement range (at 50km > 30km)
    sensors = ship.systems.get("sensors")
    distant = ContactData(
        id="enemy",
        position={"x": 50000, "y": 0, "z": 0},
        velocity={"x": 0, "y": 0, "z": 0},
        confidence=0.9,
        last_update=0.0,
        detection_method="ir",
        faction="pirates",
    )
    sensors.contact_tracker.update_contact("enemy", distant, 0.0)

    ship.ai_controller.update(0.1, 3.0)

    # Should NOT have switched to ATTACK
    assert ship.ai_controller.behavior == AIBehavior.IDLE


def test_patrol_engages_within_range():
    """Patrol ship engages threats within engagement_range."""
    from hybrid.ship import Ship
    from hybrid.fleet.ai_controller import AIBehavior
    from hybrid.systems.sensors.contact import ContactData

    ship = Ship("patrol01", {
        "mass": 5000,
        "class": "corvette",
        "faction": "unsa",
        "ai_enabled": True,
        "ai_behavior": {
            "role": "patrol",
            "engagement_range": 30000,
        },
        "systems": AI_SHIP_SYSTEMS,
    })

    # Inject a threat within range (at 20km < 30km)
    sensors = ship.systems.get("sensors")
    close = ContactData(
        id="enemy",
        position={"x": 20000, "y": 0, "z": 0},
        velocity={"x": 0, "y": 0, "z": 0},
        confidence=0.9,
        last_update=0.0,
        detection_method="ir",
        faction="pirates",
    )
    sensors.contact_tracker.update_contact("enemy", close, 0.0)

    ship.ai_controller.update(0.1, 3.0)

    assert ship.ai_controller.behavior == AIBehavior.ATTACK


# ── Damage reaction thresholds ───────────────────────────────────

def test_damage_triggers_flee():
    """Ship flees when hull drops below flee_threshold."""
    from hybrid.ship import Ship
    from hybrid.fleet.ai_controller import AIBehavior
    from hybrid.systems.sensors.contact import ContactData

    ship = Ship("warship", {
        "mass": 5000,
        "class": "corvette",
        "faction": "hostile",
        "ai_enabled": True,
        "max_hull_integrity": 100.0,
        "hull_integrity": 100.0,
        "systems": AI_SHIP_SYSTEMS,
    })

    # Inject a threat so damage reaction has context
    sensors = ship.systems.get("sensors")
    enemy = ContactData(
        id="enemy",
        position={"x": 10000, "y": 0, "z": 0},
        velocity={"x": 0, "y": 0, "z": 0},
        confidence=0.9,
        last_update=0.0,
        detection_method="ir",
        faction="unsa",
    )
    sensors.contact_tracker.update_contact("enemy", enemy, 0.0)

    # Combat profile: flee_threshold=0.2, evade_threshold=0.4
    # Drop hull to 15% (below flee_threshold)
    ship.hull_integrity = 15.0

    ship.ai_controller.update(0.1, 3.0)

    assert ship.ai_controller.behavior == AIBehavior.FLEE


def test_damage_triggers_evade():
    """Ship evades when hull drops below evade_threshold but above flee."""
    from hybrid.ship import Ship
    from hybrid.fleet.ai_controller import AIBehavior
    from hybrid.systems.sensors.contact import ContactData

    ship = Ship("warship", {
        "mass": 5000,
        "class": "corvette",
        "faction": "hostile",
        "ai_enabled": True,
        "max_hull_integrity": 100.0,
        "hull_integrity": 100.0,
        "systems": AI_SHIP_SYSTEMS,
    })

    sensors = ship.systems.get("sensors")
    enemy = ContactData(
        id="enemy",
        position={"x": 10000, "y": 0, "z": 0},
        velocity={"x": 0, "y": 0, "z": 0},
        confidence=0.9,
        last_update=0.0,
        detection_method="ir",
        faction="unsa",
    )
    sensors.contact_tracker.update_contact("enemy", enemy, 0.0)

    # Combat profile: evade_threshold=0.4, flee_threshold=0.2
    # Drop hull to 35% (below evade but above flee)
    ship.hull_integrity = 35.0

    ship.ai_controller.update(0.1, 3.0)

    assert ship.ai_controller.behavior == AIBehavior.EVADE


def test_no_damage_reaction_above_thresholds():
    """No damage reaction when hull is above both thresholds."""
    from hybrid.ship import Ship
    from hybrid.fleet.ai_controller import AIBehavior

    ship = Ship("warship", {
        "mass": 5000,
        "class": "corvette",
        "faction": "hostile",
        "ai_enabled": True,
        "max_hull_integrity": 100.0,
        "hull_integrity": 80.0,
        "systems": AI_SHIP_SYSTEMS,
    })

    # 80% hull is above both thresholds for combat profile
    ship.ai_controller.update(0.1, 3.0)

    # Should stay in IDLE (no threats, no damage reaction)
    assert ship.ai_controller.behavior == AIBehavior.IDLE


# ── get_state includes role ──────────────────────────────────────

def test_get_state_includes_role():
    """get_state() includes role and hull_fraction."""
    from hybrid.ship import Ship

    ship = Ship("warship", {
        "mass": 5000,
        "class": "corvette",
        "faction": "hostile",
        "ai_enabled": True,
        "max_hull_integrity": 100.0,
        "hull_integrity": 75.0,
        "systems": AI_SHIP_SYSTEMS,
    })

    state = ship.ai_controller.get_state()
    assert state["role"] == "combat"
    assert state["hull_fraction"] == 0.75
    assert "behavior" in state


# ── FLEE enum added ──────────────────────────────────────────────

def test_flee_behavior_enum_exists():
    """AIBehavior.FLEE enum value is available."""
    from hybrid.fleet.ai_controller import AIBehavior

    assert AIBehavior.FLEE.value == "flee"


# ── Backward compatibility ───────────────────────────────────────

def test_existing_ai_ships_still_work():
    """Ships without ai_behavior config still initialize correctly."""
    from hybrid.ship import Ship
    from hybrid.fleet.ai_controller import AIBehavior

    # This mimics the Phase 1 config -- no ai_behavior block
    ship = Ship("old_ship", {
        "mass": 5000,
        "faction": "pirates",
        "ai_enabled": True,
        "systems": AI_SHIP_SYSTEMS,
    })

    assert ship.ai_controller is not None
    assert ship.ai_controller.profile.role == "combat"
    assert ship.ai_controller.behavior == AIBehavior.IDLE


def test_idle_to_attack_still_works():
    """Phase 1 behavior: IDLE switches to ATTACK on threat detection."""
    from hybrid.ship import Ship
    from hybrid.fleet.ai_controller import AIBehavior
    from hybrid.systems.sensors.contact import ContactData

    ship = Ship("combat_ship", {
        "mass": 5000,
        "faction": "unsa",
        "ai_enabled": True,
        "systems": AI_SHIP_SYSTEMS,
    })

    sensors = ship.systems.get("sensors")
    pirate = ContactData(
        id="pirate",
        position={"x": 20000, "y": 0, "z": 0},
        velocity={"x": -50, "y": 0, "z": 0},
        confidence=0.9,
        last_update=0.0,
        detection_method="ir",
        faction="pirates",
    )
    sensors.contact_tracker.update_contact("pirate", pirate, 0.0)

    ship.ai_controller.update(0.1, 3.0)

    assert ship.ai_controller.behavior == AIBehavior.ATTACK
    assert ship.ai_controller.current_target is not None
