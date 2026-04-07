"""Tests for AI surrender behavior.

Validates:
  1. Mobility-killed ship transitions to SURRENDERED
  2. Surrendered ship stops firing and holds position
  3. ship_surrendering event is published on surrender
  4. ship_captured event updates faction
"""

import pytest

from hybrid.fleet.ai_controller import AIBehavior
from hybrid.systems.sensors.contact import ContactData


# Minimal system configs for test ships -- same pattern as test_ai_doctrine
AI_SHIP_SYSTEMS = {
    "sensors": {"passive": {"range": 200000}},
    "targeting": {},
    "combat": {"railguns": 1, "pdcs": 1},
    "navigation": {},
    "propulsion": {"max_thrust": 50000, "fuel_level": 10000},
}


def _make_ship(ship_id: str = "npc_ship", faction: str = "hostile",
               hull: float = 100.0, max_hull: float = 100.0):
    """Create a test ship with AI enabled and a hostile contact injected."""
    from hybrid.ship import Ship

    ship = Ship(ship_id, {
        "mass": 5000,
        "faction": faction,
        "ai_enabled": True,
        "max_hull_integrity": max_hull,
        "hull_integrity": hull,
        "position": {"x": 0, "y": 0, "z": 0},
        "systems": AI_SHIP_SYSTEMS,
    })

    # Inject a hostile contact so damage reactions have a threat to
    # evaluate against (required for flee/evade/surrender paths).
    sensors = ship.systems.get("sensors")
    if sensors and hasattr(sensors, "contact_tracker"):
        enemy = ContactData(
            id="player",
            position={"x": 10_000, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            confidence=0.9,
            last_update=0.0,
            detection_method="ir",
            faction="unsa",
        )
        sensors.contact_tracker.update_contact("player", enemy, 0.0)

    return ship


class TestSurrenderTransition:
    """Tests for the surrender state transition."""

    def test_mobility_kill_below_flee_threshold_triggers_surrender(self):
        """Ship with destroyed propulsion AND hull below flee_threshold surrenders."""
        ship = _make_ship(hull=10.0, max_hull=100.0)  # 10% hull

        # Destroy propulsion -- mobility kill
        if hasattr(ship, "damage_model") and "propulsion" in ship.damage_model.subsystems:
            ship.damage_model.subsystems["propulsion"].health = 0.0

        ship.ai_controller.set_behavior(AIBehavior.ATTACK)
        ship.ai_controller.update(0.1, 3.0)

        assert ship.ai_controller.behavior == AIBehavior.SURRENDERED

    def test_mobility_kill_above_flee_threshold_does_not_surrender(self):
        """Ship with destroyed propulsion but healthy hull does NOT surrender.

        The flee_threshold for combat role is 0.2.  At 90% hull the
        ship is damaged but not desperate enough to yield.
        """
        ship = _make_ship(hull=90.0, max_hull=100.0)  # 90% hull

        # Destroy propulsion
        if hasattr(ship, "damage_model") and "propulsion" in ship.damage_model.subsystems:
            ship.damage_model.subsystems["propulsion"].health = 0.0

        ship.ai_controller.set_behavior(AIBehavior.ATTACK)
        ship.ai_controller.update(0.1, 3.0)

        # Should hold position (retreat doctrine) but NOT surrender
        assert ship.ai_controller.behavior != AIBehavior.SURRENDERED

    def test_low_hull_without_mobility_kill_does_not_surrender(self):
        """Ship with low hull but working propulsion flees, does not surrender.

        If propulsion works the ship can still run -- surrender requires
        that the ship has NO escape option (mobility kill).
        """
        ship = _make_ship(hull=10.0, max_hull=100.0)

        # Propulsion intact -- ship can still flee
        ship.ai_controller.set_behavior(AIBehavior.ATTACK)
        ship.ai_controller.update(0.1, 3.0)

        # Should flee, not surrender
        assert ship.ai_controller.behavior in (AIBehavior.FLEE, AIBehavior.EVADE)
        assert ship.ai_controller.behavior != AIBehavior.SURRENDERED

    def test_rcs_kill_triggers_surrender(self):
        """RCS destruction also counts as mobility kill for surrender."""
        ship = _make_ship(hull=10.0, max_hull=100.0)

        if hasattr(ship, "damage_model") and "rcs" in ship.damage_model.subsystems:
            ship.damage_model.subsystems["rcs"].health = 0.0

        ship.ai_controller.set_behavior(AIBehavior.ATTACK)
        ship.ai_controller.update(0.1, 3.0)

        assert ship.ai_controller.behavior == AIBehavior.SURRENDERED

    def test_already_surrendered_stays_surrendered(self):
        """Once surrendered, subsequent update() calls keep the state."""
        ship = _make_ship(hull=10.0, max_hull=100.0)

        if hasattr(ship, "damage_model") and "propulsion" in ship.damage_model.subsystems:
            ship.damage_model.subsystems["propulsion"].health = 0.0

        ship.ai_controller.set_behavior(AIBehavior.ATTACK)
        ship.ai_controller.update(0.1, 3.0)
        assert ship.ai_controller.behavior == AIBehavior.SURRENDERED

        # Second update -- should remain surrendered
        ship.ai_controller.update(0.1, 6.0)
        assert ship.ai_controller.behavior == AIBehavior.SURRENDERED


class TestSurrenderedBehavior:
    """Tests for what a surrendered ship does (and doesn't do)."""

    def test_surrendered_ship_stops_firing(self):
        """Surrendered ship has _firing_authorized = False."""
        ship = _make_ship(hull=10.0, max_hull=100.0)

        if hasattr(ship, "damage_model") and "propulsion" in ship.damage_model.subsystems:
            ship.damage_model.subsystems["propulsion"].health = 0.0

        ship.ai_controller.set_behavior(AIBehavior.ATTACK)
        ship.ai_controller.update(0.1, 3.0)

        assert ship.ai_controller.behavior == AIBehavior.SURRENDERED
        assert ship.ai_controller._firing_authorized is False

    def test_surrendered_ship_clears_target(self):
        """Surrendered ship has no current_target."""
        ship = _make_ship(hull=10.0, max_hull=100.0)

        if hasattr(ship, "damage_model") and "propulsion" in ship.damage_model.subsystems:
            ship.damage_model.subsystems["propulsion"].health = 0.0

        # Give it a target first
        ship.ai_controller.set_behavior(AIBehavior.ATTACK)
        ship.ai_controller.update(0.1, 3.0)

        assert ship.ai_controller.current_target is None

    def test_set_behavior_surrendered_disables_firing(self):
        """Setting behavior to SURRENDERED directly disables firing."""
        ship = _make_ship()
        ship.ai_controller.set_behavior(AIBehavior.SURRENDERED)

        assert ship.ai_controller._firing_authorized is False

    def test_set_behavior_away_from_surrendered_re_enables_firing(self):
        """Switching from SURRENDERED to another state re-enables firing."""
        ship = _make_ship()
        ship.ai_controller.set_behavior(AIBehavior.SURRENDERED)
        assert ship.ai_controller._firing_authorized is False

        ship.ai_controller.set_behavior(AIBehavior.IDLE)
        assert ship.ai_controller._firing_authorized is True


class TestSurrenderEvents:
    """Tests for surrender event publication and capture handling."""

    def test_ship_surrendering_event_published(self):
        """ship_surrendering event fires when AI transitions to SURRENDERED."""
        ship = _make_ship(hull=10.0, max_hull=100.0)

        # Capture events published to the bus
        captured_events = []
        if hasattr(ship, "event_bus"):
            ship.event_bus.subscribe(
                "ship_surrendering",
                lambda data: captured_events.append(data),
            )

        if hasattr(ship, "damage_model") and "propulsion" in ship.damage_model.subsystems:
            ship.damage_model.subsystems["propulsion"].health = 0.0

        ship.ai_controller.set_behavior(AIBehavior.ATTACK)
        ship.ai_controller.update(0.1, 3.0)

        assert len(captured_events) == 1
        assert captured_events[0]["ship_id"] == "npc_ship"
        assert captured_events[0]["hull_percent"] <= 10.0

    def test_ship_surrendering_event_not_published_twice(self):
        """Subsequent update() calls do not re-publish the event."""
        ship = _make_ship(hull=10.0, max_hull=100.0)

        captured_events = []
        if hasattr(ship, "event_bus"):
            ship.event_bus.subscribe(
                "ship_surrendering",
                lambda data: captured_events.append(data),
            )

        if hasattr(ship, "damage_model") and "propulsion" in ship.damage_model.subsystems:
            ship.damage_model.subsystems["propulsion"].health = 0.0

        ship.ai_controller.set_behavior(AIBehavior.ATTACK)
        ship.ai_controller.update(0.1, 3.0)
        # Second tick -- already surrendered, no new event
        ship.ai_controller.update(0.1, 6.0)

        assert len(captured_events) == 1

    def test_ship_captured_event_updates_faction(self):
        """ship_captured event changes the ship's faction."""
        ship = _make_ship(faction="hostile")
        ship.ai_controller.set_behavior(AIBehavior.SURRENDERED)

        # Simulate boarding system publishing capture event
        if hasattr(ship, "event_bus"):
            ship.event_bus.publish("ship_captured", {
                "ship_id": "npc_ship",
                "new_faction": "unsa",
            })

        assert ship.faction == "unsa"
        assert ship.ai_controller.behavior == AIBehavior.SURRENDERED

    def test_ship_captured_event_wrong_ship_id_ignored(self):
        """ship_captured for a different ship_id is ignored."""
        ship = _make_ship(faction="hostile")
        ship.ai_controller.set_behavior(AIBehavior.SURRENDERED)

        if hasattr(ship, "event_bus"):
            ship.event_bus.publish("ship_captured", {
                "ship_id": "some_other_ship",
                "new_faction": "unsa",
            })

        # Faction unchanged -- event was for a different ship
        assert ship.faction == "hostile"

    def test_ship_captured_without_new_faction_keeps_existing(self):
        """ship_captured without new_faction keeps the current faction."""
        ship = _make_ship(faction="pirates")
        ship.ai_controller.set_behavior(AIBehavior.SURRENDERED)

        if hasattr(ship, "event_bus"):
            ship.event_bus.publish("ship_captured", {
                "ship_id": "npc_ship",
            })

        assert ship.faction == "pirates"
        assert ship.ai_controller.behavior == AIBehavior.SURRENDERED


class TestSurrenderTelemetry:
    """Tests for surrender state in telemetry output."""

    def test_get_state_includes_surrendered(self):
        """get_state() reports surrendered status."""
        ship = _make_ship()
        ship.ai_controller.set_behavior(AIBehavior.SURRENDERED)

        state = ship.ai_controller.get_state()
        assert state["surrendered"] is True
        assert state["firing_authorized"] is False
        assert state["behavior"] == "surrendered"

    def test_get_state_not_surrendered(self):
        """get_state() reports non-surrendered status."""
        ship = _make_ship()
        state = ship.ai_controller.get_state()

        assert state["surrendered"] is False
        assert state["firing_authorized"] is True
