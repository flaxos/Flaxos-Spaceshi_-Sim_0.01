# tests/systems/combat/test_combat_log_events.py
"""Tests for combat log event subscriptions.

Verifies that the CombatLog correctly handles events published by:
- projectile_manager (railgun slug lifecycle)
- simulator (PDC torpedo intercept)
- ship (damage taken, destruction)

Each test publishes an event through the EventBus and checks that a
CombatLogEntry appears with the correct type, severity, and key details.
"""

import pytest
from hybrid.core.event_bus import EventBus
from hybrid.systems.combat.combat_log import CombatLog, CombatLogEntry


@pytest.fixture(autouse=True)
def fresh_event_bus():
    """Reset the EventBus singleton between tests.

    The CombatLog subscribes in __init__, so we need a clean bus each
    time to avoid duplicate handlers from previous tests.
    """
    EventBus._instance = None
    yield
    EventBus._instance = None


@pytest.fixture
def combat_log():
    """Create a fresh CombatLog wired to the singleton EventBus."""
    return CombatLog()


@pytest.fixture
def bus():
    """Get the EventBus instance (same one the combat_log fixture uses)."""
    return EventBus.get_instance()


# ── Railgun Projectile Events ─────────────────────────────────


class TestProjectileSpawned:
    """projectile_spawned: railgun slug leaves the barrel."""

    def test_creates_entry(self, combat_log, bus):
        bus.publish("projectile_spawned", {
            "projectile_id": "proj_1",
            "weapon": "UNE-440 Railgun",
            "shooter": "corvette_1",
            "target": "freighter_1",
            "position": {"x": 0, "y": 0, "z": 0},
        })

        entries = combat_log.get_entries(limit=10)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["event_type"] == "projectile_fired"
        assert entry["weapon"] == "UNE-440 Railgun"
        assert entry["severity"] == "info"
        assert entry["ship_id"] == "corvette_1"
        assert entry["target_id"] == "freighter_1"

    def test_summary_mentions_weapon_and_target(self, combat_log, bus):
        bus.publish("projectile_spawned", {
            "projectile_id": "proj_1",
            "weapon": "UNE-440 Railgun",
            "shooter": "corvette_1",
            "target": "freighter_1",
        })

        entry = combat_log.get_entries()[0]
        assert "UNE-440 Railgun" in entry["summary"]
        assert "freighter_1" in entry["summary"]


class TestProjectileImpactHit:
    """projectile_impact with hit=True: slug connected."""

    def test_hit_entry(self, combat_log, bus):
        bus.publish("projectile_impact", {
            "projectile_id": "proj_1",
            "weapon": "UNE-440 Railgun",
            "shooter": "corvette_1",
            "target": "freighter_1",
            "hit": True,
            "damage": 35.0,
            "subsystem_hit": "propulsion",
            "subsystem_damage": 17.5,
            "flight_time": 5.0,
            "confidence_at_fire": 0.85,
            "feedback": "Hit -- drive system on freighter_1",
            "hit_location": {
                "armor_section": "aft",
                "angle_of_incidence": 12.3,
                "is_ricochet": False,
            },
            "armor_ablation": {
                "description": "Slug penetrated 2.1cm of 3.0cm armor",
            },
        })

        entries = combat_log.get_entries()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["event_type"] == "projectile_hit"
        assert entry["severity"] == "hit"
        assert entry["weapon"] == "UNE-440 Railgun"
        assert entry["details"]["damage"] == 35.0
        assert entry["details"]["subsystem_hit"] == "propulsion"
        assert entry["details"]["flight_time"] == 5.0

    def test_hit_chain_includes_impact_details(self, combat_log, bus):
        bus.publish("projectile_impact", {
            "projectile_id": "proj_2",
            "weapon": "UNE-440 Railgun",
            "shooter": "corvette_1",
            "target": "freighter_1",
            "hit": True,
            "damage": 35.0,
            "subsystem_hit": "sensors",
            "subsystem_damage": 10.0,
            "flight_time": 3.0,
            "confidence_at_fire": 0.7,
            "hit_location": {"armor_section": "fore"},
        })

        chain = combat_log.get_entries()[0]["chain"]
        assert any("IMPACT CONFIRMED" in step for step in chain)
        assert any("sensors" in step for step in chain)


class TestProjectileImpactMiss:
    """projectile_impact with hit=False: slug passed close but missed."""

    def test_miss_entry(self, combat_log, bus):
        bus.publish("projectile_impact", {
            "projectile_id": "proj_3",
            "weapon": "UNE-440 Railgun",
            "shooter": "corvette_1",
            "target": "freighter_1",
            "hit": False,
            "damage": 0,
            "flight_time": 12.0,
            "confidence_at_fire": 0.4,
            "feedback": "Miss -- target maneuvered at 1.2g",
        })

        entry = combat_log.get_entries()[0]
        assert entry["event_type"] == "projectile_miss"
        assert entry["severity"] == "miss"
        assert entry["details"]["hit"] is False
        assert "Miss" in entry["summary"]


class TestProjectileExpired:
    """projectile_expired: slug lifetime exceeded without intercept."""

    def test_expired_entry(self, combat_log, bus):
        bus.publish("projectile_expired", {
            "projectile_id": "proj_4",
            "weapon": "UNE-440 Railgun",
            "shooter": "corvette_1",
            "target": "freighter_1",
            "flight_time": 60.0,
            "confidence_at_fire": 0.3,
            "feedback": "Miss -- slug expired after 60.0s flight",
        })

        entry = combat_log.get_entries()[0]
        assert entry["event_type"] == "projectile_miss"
        assert entry["severity"] == "miss"
        assert entry["weapon"] == "UNE-440 Railgun"
        assert entry["details"]["flight_time"] == 60.0

    def test_expired_uses_feedback_string(self, combat_log, bus):
        """The feedback string from projectile_manager should be used as-is."""
        bus.publish("projectile_expired", {
            "projectile_id": "proj_5",
            "weapon": "UNE-440 Railgun",
            "shooter": "corvette_1",
            "target": "freighter_1",
            "flight_time": 45.0,
            "confidence_at_fire": 0.2,
            "feedback": "Miss -- slug expired after 45.0s flight, solution confidence was 20%",
        })

        entry = combat_log.get_entries()[0]
        assert entry["summary"] == "Miss -- slug expired after 45.0s flight, solution confidence was 20%"


# ── PDC Torpedo Intercept Events ──────────────────────────────


class TestPdcTorpedoEngage:
    """pdc_torpedo_engage: PDC auto-fires at incoming torpedo."""

    def test_pdc_destroyed_torpedo(self, combat_log, bus):
        bus.publish("pdc_torpedo_engage", {
            "ship_id": "corvette_1",
            "pdc_mount": "pdc_1",
            "torpedo_id": "torp_1",
            "distance": 1500.0,
            "hit": True,
            "destroyed": True,
            "rounds_fired": 10,
            "burst_hits": 3,
        })

        entry = combat_log.get_entries()[0]
        assert entry["event_type"] == "pdc_intercept"
        assert entry["severity"] == "hit"
        assert entry["weapon"] == "Narwhal-III PDC"
        assert "destroyed" in entry["summary"].lower()
        assert entry["details"]["destroyed"] is True
        assert entry["details"]["rounds_fired"] == 10
        assert entry["details"]["burst_hits"] == 3

    def test_pdc_hit_but_not_destroyed(self, combat_log, bus):
        bus.publish("pdc_torpedo_engage", {
            "ship_id": "corvette_1",
            "pdc_mount": "pdc_2",
            "torpedo_id": "torp_2",
            "distance": 3000.0,
            "hit": True,
            "destroyed": False,
            "rounds_fired": 10,
            "burst_hits": 2,
        })

        entry = combat_log.get_entries()[0]
        assert entry["severity"] == "hit"
        assert "damaged" in entry["summary"].lower()

    def test_pdc_miss(self, combat_log, bus):
        bus.publish("pdc_torpedo_engage", {
            "ship_id": "corvette_1",
            "pdc_mount": "pdc_1",
            "torpedo_id": "torp_3",
            "distance": 4500.0,
            "hit": False,
            "destroyed": False,
            "rounds_fired": 10,
            "burst_hits": 0,
        })

        entry = combat_log.get_entries()[0]
        assert entry["severity"] == "miss"
        assert "survived" in entry["summary"].lower()

    def test_pdc_range_formatting(self, combat_log, bus):
        """Range should be formatted in human-readable units."""
        bus.publish("pdc_torpedo_engage", {
            "ship_id": "corvette_1",
            "pdc_mount": "pdc_1",
            "torpedo_id": "torp_4",
            "distance": 2500.0,
            "hit": True,
            "destroyed": True,
            "rounds_fired": 10,
            "burst_hits": 5,
        })

        entry = combat_log.get_entries()[0]
        # 2500m should be formatted as "2.5km" in the summary
        assert "2.5km" in entry["summary"]


# ── Ship Damage Events ────────────────────────────────────────


class TestShipDamaged:
    """ship_damaged: ship takes hull damage from any source."""

    def test_damage_entry(self, combat_log, bus):
        bus.publish("ship_damaged", {
            "ship_id": "corvette_1",
            "damage": 25.0,
            "hull_before": 100.0,
            "hull_after": 75.0,
            "source": "freighter_1:UNE-440 Railgun",
            "destroyed": False,
            "target_subsystem": "propulsion",
            "subsystem_result": {"subsystem": "propulsion", "status": "impaired"},
        })

        entry = combat_log.get_entries()[0]
        assert entry["event_type"] == "ship_damage"
        assert entry["severity"] == "damage"
        assert entry["ship_id"] == "corvette_1"
        assert entry["details"]["damage"] == 25.0
        assert "25.0" in entry["summary"]
        assert "corvette_1" in entry["summary"]

    def test_critical_severity_when_low_hull(self, combat_log, bus):
        """Hull below 25% should flag as critical severity."""
        bus.publish("ship_damaged", {
            "ship_id": "corvette_1",
            "damage": 80.0,
            "hull_before": 100.0,
            "hull_after": 20.0,
            "source": "torpedo",
            "destroyed": False,
        })

        entry = combat_log.get_entries()[0]
        assert entry["severity"] == "critical"

    def test_chain_includes_subsystem_info(self, combat_log, bus):
        bus.publish("ship_damaged", {
            "ship_id": "corvette_1",
            "damage": 15.0,
            "hull_before": 80.0,
            "hull_after": 65.0,
            "source": "pdc_burst",
            "destroyed": False,
            "target_subsystem": "sensors",
            "subsystem_result": {"subsystem": "sensors", "status": "damaged"},
        })

        chain = combat_log.get_entries()[0]["chain"]
        assert any("sensors" in step for step in chain)


# ── Ship Destroyed Events ─────────────────────────────────────


class TestShipDestroyed:
    """ship_destroyed: kill confirmation."""

    def test_destroyed_entry(self, combat_log, bus):
        bus.publish("ship_destroyed", {
            "ship_id": "freighter_1",
            "source": "corvette_1:UNE-440 Railgun",
        })

        entry = combat_log.get_entries()[0]
        assert entry["event_type"] == "ship_destroyed"
        assert entry["severity"] == "critical"
        assert "TARGET DESTROYED" in entry["summary"]
        assert "freighter_1" in entry["summary"]

    def test_destroyed_chain_mentions_source(self, combat_log, bus):
        bus.publish("ship_destroyed", {
            "ship_id": "freighter_1",
            "source": "corvette_1:UNE-440 Railgun",
        })

        chain = combat_log.get_entries()[0]["chain"]
        assert any("corvette_1" in step for step in chain)
        assert any("0%" in step for step in chain)

    def test_destroyed_details_include_source(self, combat_log, bus):
        bus.publish("ship_destroyed", {
            "ship_id": "enemy_cruiser",
            "source": "torpedo_impact",
        })

        entry = combat_log.get_entries()[0]
        assert entry["details"]["source"] == "torpedo_impact"


# ── Integration: Multiple Events in Sequence ──────────────────


class TestCombatSequence:
    """Verify a realistic combat sequence produces the right log trail."""

    def test_fire_impact_damage_destroy_sequence(self, combat_log, bus):
        """Simulate: railgun fires -> slug hits -> ship damaged -> ship destroyed."""
        # 1. Slug launched
        bus.publish("projectile_spawned", {
            "projectile_id": "proj_10",
            "weapon": "UNE-440 Railgun",
            "shooter": "corvette_1",
            "target": "freighter_1",
        })

        # 2. Slug impacts and hits
        bus.publish("projectile_impact", {
            "projectile_id": "proj_10",
            "weapon": "UNE-440 Railgun",
            "shooter": "corvette_1",
            "target": "freighter_1",
            "hit": True,
            "damage": 35.0,
            "subsystem_hit": "propulsion",
            "subsystem_damage": 17.5,
            "flight_time": 2.5,
            "confidence_at_fire": 0.9,
        })

        # 3. Ship takes damage
        bus.publish("ship_damaged", {
            "ship_id": "freighter_1",
            "damage": 35.0,
            "hull_before": 35.0,
            "hull_after": 0.0,
            "source": "corvette_1:UNE-440 Railgun",
            "destroyed": True,
        })

        # 4. Ship destroyed
        bus.publish("ship_destroyed", {
            "ship_id": "freighter_1",
            "source": "corvette_1:UNE-440 Railgun",
        })

        entries = combat_log.get_entries(limit=50)
        assert len(entries) == 4

        types = [e["event_type"] for e in entries]
        assert types == [
            "projectile_fired",
            "projectile_hit",
            "ship_damage",
            "ship_destroyed",
        ]

        # Final entry is the kill confirmation
        assert "TARGET DESTROYED" in entries[-1]["summary"]
        assert entries[-1]["severity"] == "critical"

    def test_pdc_intercept_then_torpedo_events(self, combat_log, bus):
        """PDC intercepts a torpedo, then torpedo_intercepted also fires."""
        bus.publish("pdc_torpedo_engage", {
            "ship_id": "corvette_1",
            "pdc_mount": "pdc_1",
            "torpedo_id": "torp_1",
            "distance": 1200.0,
            "hit": True,
            "destroyed": True,
        })

        bus.publish("torpedo_intercepted", {
            "torpedo_id": "torp_1",
            "shooter": "enemy_1",
            "target": "corvette_1",
            "intercepted_by": "pdc_1",
        })

        entries = combat_log.get_entries()
        assert len(entries) == 2
        assert entries[0]["event_type"] == "pdc_intercept"
        assert entries[1]["event_type"] == "torpedo_miss"
