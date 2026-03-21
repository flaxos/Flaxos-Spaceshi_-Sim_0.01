"""Tests for NPC AI Phase 1: enemy ships fight back.

Validates the full chain:
  1. Faction hostility rules
  2. ContactData faction field
  3. AIController auto-initialization
  4. AI threat detection from sensor contacts
  5. AI target locking and weapon firing
  6. AICrewManager skips ai_enabled ships
"""

import pytest
import logging

logger = logging.getLogger(__name__)


# Minimal system configs required for AI tests -- sensors, targeting,
# combat, navigation, and propulsion so the full combat loop works.
AI_SHIP_SYSTEMS = {
    "sensors": {"passive": {"range": 200000}},
    "targeting": {},
    "combat": {"railguns": 1, "pdcs": 1},
    "navigation": {},
    "propulsion": {"max_thrust": 50000, "fuel_level": 10000},
}

# ── Faction rules ─────────────────────────────────────────────────

def test_faction_hostility():
    """Faction pairs correctly identify hostile relationships."""
    from hybrid.fleet.faction_rules import are_hostile

    # Hostile pairs
    assert are_hostile("pirates", "unsa")
    assert are_hostile("PIRATES", "UNSA")  # Case insensitive
    assert are_hostile("hostile", "unsa")
    assert are_hostile("hostile", "civilian")
    assert are_hostile("hostile", "mars")
    assert are_hostile("mcrn", "unsa")

    # Non-hostile
    assert not are_hostile("unsa", "unsa")  # Same faction
    assert not are_hostile("unsa", "civilian")
    assert not are_hostile("", "pirates")  # Empty faction
    assert not are_hostile("neutral", "unsa")  # Neutral not in pairs
    assert not are_hostile(None, "pirates")  # None faction


# ── ContactData faction field ─────────────────────────────────────

def test_contact_data_has_faction():
    """ContactData dataclass includes the faction field."""
    from hybrid.systems.sensors.contact import ContactData

    contact = ContactData(
        id="C001",
        position={"x": 0, "y": 0, "z": 0},
        velocity={"x": 0, "y": 0, "z": 0},
        confidence=0.9,
        last_update=0.0,
        detection_method="ir",
        faction="pirates",
    )
    assert contact.faction == "pirates"


def test_contact_data_faction_default_none():
    """ContactData faction defaults to None for backward compatibility."""
    from hybrid.systems.sensors.contact import ContactData

    contact = ContactData(
        id="C001",
        position={"x": 0, "y": 0, "z": 0},
        velocity={"x": 0, "y": 0, "z": 0},
        confidence=0.9,
        last_update=0.0,
        detection_method="ir",
    )
    assert contact.faction is None


# ── Ship AI auto-initialization ───────────────────────────────────

def test_ship_auto_enables_ai():
    """Ship with ai_enabled=True auto-creates AIController in __init__."""
    from hybrid.ship import Ship

    ship = Ship("test_ai", {
        "name": "AI Ship",
        "mass": 5000,
        "faction": "pirates",
        "ai_enabled": True,
        "systems": AI_SHIP_SYSTEMS,
    })

    assert ship.ai_enabled is True
    assert ship.ai_controller is not None
    assert ship.ai_controller.ship is ship


def test_ship_no_ai_by_default():
    """Ship without ai_enabled does not create AIController."""
    from hybrid.ship import Ship

    ship = Ship("test_manual", {
        "name": "Manual Ship",
        "mass": 5000,
    })

    assert ship.ai_enabled is False
    assert ship.ai_controller is None


def test_ship_enable_ai_after_init():
    """Ship.enable_ai() works after construction."""
    from hybrid.ship import Ship
    from hybrid.fleet.ai_controller import AIBehavior

    ship = Ship("test_late_ai", {"mass": 5000, "systems": AI_SHIP_SYSTEMS})
    assert ship.ai_controller is None

    result = ship.enable_ai(AIBehavior.ATTACK)
    assert result is True
    assert ship.ai_enabled is True
    assert ship.ai_controller is not None
    assert ship.ai_controller.behavior == AIBehavior.ATTACK


# ── AIController threat detection ─────────────────────────────────

def test_ai_detects_hostile_contacts():
    """AIController finds hostile contacts via faction rules."""
    from hybrid.ship import Ship
    from hybrid.systems.sensors.contact import ContactData, ContactTracker

    # Create AI ship with sensors
    ship = Ship("ai_corvette", {
        "mass": 5000,
        "faction": "unsa",
        "ai_enabled": True,
        "systems": AI_SHIP_SYSTEMS,
    })

    # Manually inject a contact into the sensor system
    sensors = ship.systems.get("sensors")
    assert sensors is not None, "Ship must have sensors"
    assert hasattr(sensors, "contact_tracker"), "Sensors must have contact_tracker"

    # Create a pirate contact
    pirate_contact = ContactData(
        id="pirate01",
        position={"x": 30000, "y": 0, "z": 0},
        velocity={"x": -100, "y": 0, "z": 0},
        confidence=0.9,
        last_update=0.0,
        detection_method="ir",
        classification="frigate",
        faction="pirates",
    )
    sensors.contact_tracker.update_contact("pirate01", pirate_contact, 0.0)

    # Create a friendly contact
    friendly_contact = ContactData(
        id="ally01",
        position={"x": -5000, "y": 0, "z": 0},
        velocity={"x": 50, "y": 0, "z": 0},
        confidence=0.9,
        last_update=0.0,
        detection_method="ir",
        classification="corvette",
        faction="unsa",
    )
    sensors.contact_tracker.update_contact("ally01", friendly_contact, 0.0)

    # AI should detect the pirate but not the ally
    threats = ship.ai_controller._get_hostile_contacts()
    assert len(threats) == 1

    # Threat should be the pirate
    contact_id, contact = threats[0]
    assert contact.faction == "pirates"


def test_ai_no_threats_when_no_hostiles():
    """AIController returns empty when all contacts are friendly."""
    from hybrid.ship import Ship
    from hybrid.systems.sensors.contact import ContactData

    ship = Ship("ai_ship", {
        "mass": 5000,
        "faction": "unsa",
        "ai_enabled": True,
        "systems": AI_SHIP_SYSTEMS,
    })

    sensors = ship.systems.get("sensors")
    # Add only friendly contacts
    friendly = ContactData(
        id="friend",
        position={"x": 1000, "y": 0, "z": 0},
        velocity={"x": 0, "y": 0, "z": 0},
        confidence=0.9,
        last_update=0.0,
        detection_method="ir",
        faction="unsa",
    )
    sensors.contact_tracker.update_contact("friend", friendly, 0.0)

    threats = ship.ai_controller._get_hostile_contacts()
    assert len(threats) == 0


# ── AI behavior transitions ──────────────────────────────────────

def test_ai_idle_switches_to_attack_on_threat():
    """AI in IDLE mode switches to ATTACK when threats are detected."""
    from hybrid.ship import Ship
    from hybrid.fleet.ai_controller import AIBehavior
    from hybrid.systems.sensors.contact import ContactData

    ship = Ship("ai_ship", {
        "mass": 5000,
        "faction": "unsa",
        "ai_enabled": True,
        "systems": AI_SHIP_SYSTEMS,
    })

    assert ship.ai_controller.behavior == AIBehavior.IDLE

    # Inject a hostile contact
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

    # Run AI update (sim_time > decision_interval)
    ship.ai_controller.update(0.1, 3.0)

    assert ship.ai_controller.behavior == AIBehavior.ATTACK
    assert ship.ai_controller.current_target is not None


def test_ai_attack_returns_to_idle_without_threats():
    """AI in ATTACK mode returns to IDLE when no threats remain."""
    from hybrid.ship import Ship
    from hybrid.fleet.ai_controller import AIBehavior

    ship = Ship("ai_ship", {
        "mass": 5000,
        "faction": "unsa",
        "ai_enabled": True,
        "systems": AI_SHIP_SYSTEMS,
    })

    ship.ai_controller.set_behavior(AIBehavior.ATTACK)
    assert ship.ai_controller.behavior == AIBehavior.ATTACK

    # No contacts = no threats
    ship.ai_controller.update(0.1, 3.0)

    assert ship.ai_controller.behavior == AIBehavior.IDLE


# ── AI target locking ─────────────────────────────────────────────

def test_ai_locks_target():
    """AIController uses targeting system lock_target API."""
    from hybrid.ship import Ship
    from hybrid.systems.sensors.contact import ContactData

    ship = Ship("ai_ship", {
        "mass": 5000,
        "faction": "unsa",
        "ai_enabled": True,
        "systems": AI_SHIP_SYSTEMS,
    })

    # Inject hostile contact
    sensors = ship.systems.get("sensors")
    pirate = ContactData(
        id="pirate",
        position={"x": 15000, "y": 0, "z": 0},
        velocity={"x": 0, "y": 0, "z": 0},
        confidence=0.9,
        last_update=0.0,
        detection_method="ir",
        faction="pirates",
    )
    sensors.contact_tracker.update_contact("pirate", pirate, 0.0)
    stable_id = sensors.contact_tracker.id_mapping.get("pirate")

    # Lock target
    ship.ai_controller._lock_target(stable_id)

    targeting = ship.systems.get("targeting")
    assert targeting is not None
    assert targeting.locked_target == stable_id


# ── AI resolve target ship ────────────────────────────────────────

def test_ai_resolves_target_ship():
    """AIController resolves contact ID to Ship object."""
    from hybrid.ship import Ship
    from hybrid.systems.sensors.contact import ContactData

    # Create AI ship and target ship
    ai_ship = Ship("ai_corvette", {
        "mass": 5000,
        "faction": "unsa",
        "ai_enabled": True,
        "systems": AI_SHIP_SYSTEMS,
    })
    target_ship = Ship("pirate_frigate", {
        "mass": 8000,
        "faction": "pirates",
        "position": {"x": 30000, "y": 0, "z": 0},
    })

    # Simulate tick to set _all_ships_ref
    ai_ship._all_ships_ref = [ai_ship, target_ship]

    # Inject contact into sensors
    sensors = ai_ship.systems.get("sensors")
    pirate = ContactData(
        id="pirate_frigate",
        position={"x": 30000, "y": 0, "z": 0},
        velocity={"x": 0, "y": 0, "z": 0},
        confidence=0.9,
        last_update=0.0,
        detection_method="ir",
        faction="pirates",
    )
    sensors.contact_tracker.update_contact("pirate_frigate", pirate, 0.0)
    stable_id = sensors.contact_tracker.id_mapping.get("pirate_frigate")

    # Resolve
    resolved = ai_ship.ai_controller._resolve_target_ship(stable_id)
    assert resolved is not None
    assert resolved.id == "pirate_frigate"


# ── AICrewManager skips AI ships ──────────────────────────────────

def test_ai_crew_skips_ai_enabled_ships():
    """AICrewManager.tick() skips ships with ai_enabled=True."""
    from server.stations.ai_crew import AICrewManager

    manager = AICrewManager()
    manager.register_ship("ai_ship")
    manager.register_ship("player_ship")

    class MockShip:
        def __init__(self, ship_id, ai_enabled):
            self.id = ship_id
            self.ai_enabled = ai_enabled
            self.systems = {}

    ships = {
        "ai_ship": MockShip("ai_ship", True),
        "player_ship": MockShip("player_ship", False),
    }

    # Should not raise -- AI ship is skipped, player ship runs normally
    manager.tick(ships, 0.1)


# ── AIController get_state ────────────────────────────────────────

def test_ai_controller_get_state():
    """get_state returns valid dict with or without a target."""
    from hybrid.ship import Ship

    ship = Ship("ai_ship", {
        "mass": 5000,
        "faction": "unsa",
        "ai_enabled": True,
        "systems": AI_SHIP_SYSTEMS,
    })

    state = ship.ai_controller.get_state()
    assert state["behavior"] == "idle"
    assert state["current_target"] is None


# ── Threat assessment with ContactData ────────────────────────────

def test_threat_assessment_with_contact_data():
    """AIThreatAssessment works with ContactData objects."""
    from hybrid.ship import Ship
    from hybrid.fleet.ai_controller import AIThreatAssessment
    from hybrid.systems.sensors.contact import ContactData

    ship = Ship("own_ship", {
        "mass": 5000,
        "position": {"x": 0, "y": 0, "z": 0},
        "velocity": {"x": 0, "y": 0, "z": 0},
    })

    # Close contact = high threat
    close_contact = ContactData(
        id="C001",
        position={"x": 5000, "y": 0, "z": 0},
        velocity={"x": -100, "y": 0, "z": 0},
        confidence=0.9,
        last_update=0.0,
        detection_method="ir",
        classification="destroyer",
        faction="hostile",
    )

    # Far contact = lower threat
    far_contact = ContactData(
        id="C002",
        position={"x": 200000, "y": 0, "z": 0},
        velocity={"x": 0, "y": 0, "z": 0},
        confidence=0.5,
        last_update=0.0,
        detection_method="ir",
        classification="Unknown",
        faction="hostile",
    )

    close_threat = AIThreatAssessment.assess_threat("C001", close_contact, ship)
    far_threat = AIThreatAssessment.assess_threat("C002", far_contact, ship)

    assert close_threat > far_threat
    assert close_threat > 0
    assert far_threat >= 0


def test_threat_prioritization():
    """Contacts are sorted by threat level (highest first)."""
    from hybrid.ship import Ship
    from hybrid.fleet.ai_controller import AIThreatAssessment
    from hybrid.systems.sensors.contact import ContactData

    ship = Ship("own_ship", {
        "mass": 5000,
        "position": {"x": 0, "y": 0, "z": 0},
    })

    contacts = [
        ("C002", ContactData(
            id="C002",
            position={"x": 200000, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            confidence=0.5, last_update=0.0,
            detection_method="ir", faction="hostile",
        )),
        ("C001", ContactData(
            id="C001",
            position={"x": 5000, "y": 0, "z": 0},
            velocity={"x": -100, "y": 0, "z": 0},
            confidence=0.9, last_update=0.0,
            detection_method="ir", classification="destroyer",
            faction="hostile",
        )),
    ]

    sorted_contacts = AIThreatAssessment.prioritize_targets(contacts, ship)
    # Close destroyer should be first
    assert sorted_contacts[0][0] == "C001"
