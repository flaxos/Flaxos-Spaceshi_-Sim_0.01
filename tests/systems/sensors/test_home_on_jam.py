# tests/systems/sensors/test_home_on_jam.py
"""Tests for Home-on-Jam (HoJ) wiring into the sensor tick loop.

Verifies that toggling HoJ on the ECCM subsystem actually produces
bearing-only ghost contacts from enemy jammer emissions, and that
those contacts do not overwrite higher-quality sensor data.
"""

import math
import types

import pytest

from hybrid.core.event_bus import EventBus
from hybrid.systems.sensors.sensor_system import SensorSystem
from hybrid.systems.sensors.contact import ContactData, compute_contact_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ecm_system(jammer_enabled: bool = False,
                     jammer_power: float = 50_000.0) -> types.SimpleNamespace:
    """Create a minimal ECM system namespace for a target ship."""
    ecm = types.SimpleNamespace(
        jammer_enabled=jammer_enabled,
        jammer_power=jammer_power,
        _ecm_factor=1.0,
        emcon_active=False,
    )
    ecm.is_chaff_active = lambda: False
    ecm.is_flare_active = lambda: False
    ecm.get_chaff_rcs_multiplier = lambda: 1.0
    ecm.get_chaff_noise_radius = lambda: 0.0
    ecm.get_flare_ir_power = lambda: 0.0
    ecm.get_emcon_ir_modifier = lambda: 1.0
    ecm.get_emcon_rcs_modifier = lambda: 1.0

    def get_jammer_effect_at_range(distance):
        if not jammer_enabled or distance <= 0:
            return 1.0
        flux = jammer_power / (4.0 * math.pi * distance * distance)
        noise_floor = 1.0e-12
        jam_ratio = flux / noise_floor
        if jam_ratio <= 1.0:
            return 1.0
        deg = 1.0 / (1.0 + math.log10(jam_ratio))
        return max(0.05, min(1.0, deg))

    ecm.get_jammer_effect_at_range = get_jammer_effect_at_range
    return ecm


def _make_ship(ship_id: str, position: dict,
               ecm: types.SimpleNamespace | None = None) -> types.SimpleNamespace:
    """Create a minimal ship namespace for sensor system tests."""
    systems = {}
    if ecm is not None:
        systems["ecm"] = ecm

    ship = types.SimpleNamespace(
        id=ship_id,
        position=dict(position),
        velocity={"x": 0, "y": 0, "z": 0},
        systems=systems,
        mass=5000,
        ship_class="corvette",
        name=ship_id,
        faction="UNE",
        sim_time=0.0,
    )
    return ship


def _make_sensor_system() -> SensorSystem:
    """Create a SensorSystem with default config."""
    return SensorSystem({})


def _run_sensor_tick(sensors: SensorSystem, own_ship, all_ships,
                     dt: float = 0.25) -> None:
    """Run one sensor tick, wiring up the all_ships reference."""
    own_ship._all_ships_ref = all_ships
    own_ship.sim_time = sensors.sim_time + dt
    eb = EventBus.get_instance()
    eb.listeners.clear()
    sensors.tick(dt, own_ship, eb)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHoJOff:
    """When HoJ is disabled, no HoJ contacts should be created."""

    def test_hoj_off_no_contacts(self):
        """Target is jamming but HoJ is off -- no ghost contact."""
        sensors = _make_sensor_system()
        # HoJ is off by default
        assert sensors.eccm.hoj_active is False

        own = _make_ship("player", {"x": 0, "y": 0, "z": 0})
        target = _make_ship(
            "jammer",
            {"x": 400_000, "y": 0, "z": 0},
            ecm=_make_ecm_system(jammer_enabled=True, jammer_power=50_000),
        )

        _run_sensor_tick(sensors, own, [own, target])

        # No contacts should exist from HoJ
        contacts = sensors.contact_tracker.get_all_contacts(sensors.sim_time)
        hoj_contacts = [
            c for c in contacts.values()
            if c.detection_method == "home_on_jam"
        ]
        assert len(hoj_contacts) == 0


class TestHoJCreatesGhost:
    """When HoJ is on and target is jamming, a ghost contact appears."""

    def test_hoj_creates_ghost_contact(self):
        """HoJ enabled + target jamming = ghost contact with bearing."""
        sensors = _make_sensor_system()
        sensors.eccm.set_home_on_jam(True)
        assert sensors.eccm.hoj_active is True

        own = _make_ship("player", {"x": 0, "y": 0, "z": 0})
        target = _make_ship(
            "jammer",
            {"x": 400_000, "y": 0, "z": 0},
            ecm=_make_ecm_system(jammer_enabled=True, jammer_power=50_000),
        )

        _run_sensor_tick(sensors, own, [own, target])

        contacts = sensors.contact_tracker.get_all_contacts(sensors.sim_time)
        hoj_contacts = [
            c for c in contacts.values()
            if c.detection_method == "home_on_jam"
        ]
        assert len(hoj_contacts) == 1

        contact = hoj_contacts[0]
        # Confidence should be bearing_quality * 0.25 -- always below ghost threshold
        assert contact.confidence < 0.3
        assert contact.contact_state == "ghost"
        assert contact.detection_method == "home_on_jam"
        # Bearing should exist (direction to jammer)
        assert contact.bearing is not None

    def test_hoj_no_contact_when_target_not_jamming(self):
        """HoJ enabled but target jammer is OFF -- no contact."""
        sensors = _make_sensor_system()
        sensors.eccm.set_home_on_jam(True)

        own = _make_ship("player", {"x": 0, "y": 0, "z": 0})
        target = _make_ship(
            "silent_ship",
            {"x": 400_000, "y": 0, "z": 0},
            ecm=_make_ecm_system(jammer_enabled=False),
        )

        _run_sensor_tick(sensors, own, [own, target])

        contacts = sensors.contact_tracker.get_all_contacts(sensors.sim_time)
        hoj_contacts = [
            c for c in contacts.values()
            if c.detection_method == "home_on_jam"
        ]
        assert len(hoj_contacts) == 0


class TestHoJDoesNotOverwrite:
    """HoJ should not overwrite contacts with higher confidence."""

    def test_hoj_does_not_overwrite_confirmed(self):
        """Existing confirmed contact should NOT be downgraded by HoJ."""
        sensors = _make_sensor_system()
        sensors.eccm.set_home_on_jam(True)

        own = _make_ship("player", {"x": 0, "y": 0, "z": 0})
        target = _make_ship(
            "jammer",
            {"x": 400_000, "y": 0, "z": 0},
            ecm=_make_ecm_system(jammer_enabled=True, jammer_power=50_000),
        )

        # Manually inject a high-confidence contact for the target
        existing = ContactData(
            id="jammer",
            position={"x": 400_000, "y": 0, "z": 0},
            velocity={"x": 50, "y": 0, "z": 0},
            confidence=0.9,
            last_update=0.0,
            detection_method="passive",
            classification="corvette",
        )
        sensors.contact_tracker.update_contact("jammer", existing, 0.0)

        # Verify it's confirmed before tick
        pre_contact = sensors.contact_tracker.get_contact("jammer")
        assert pre_contact.confidence == 0.9
        assert pre_contact.contact_state == "confirmed"

        _run_sensor_tick(sensors, own, [own, target])

        # After tick, the contact should still be high confidence.
        # HoJ should NOT have overwritten it.
        post_contact = sensors.contact_tracker.get_contact("jammer")
        assert post_contact.confidence >= 0.9
        assert post_contact.detection_method != "home_on_jam"


class TestHoJToggle:
    """Toggling HoJ off stops creating new contacts."""

    def test_hoj_off_stops_updating(self):
        """HoJ on creates contact, HoJ off means no further updates."""
        sensors = _make_sensor_system()
        sensors.eccm.set_home_on_jam(True)

        own = _make_ship("player", {"x": 0, "y": 0, "z": 0})
        target = _make_ship(
            "jammer",
            {"x": 400_000, "y": 0, "z": 0},
            ecm=_make_ecm_system(jammer_enabled=True, jammer_power=50_000),
        )

        # Tick 1: HoJ on, should create contact
        _run_sensor_tick(sensors, own, [own, target])
        contacts = sensors.contact_tracker.get_all_contacts(sensors.sim_time)
        hoj_contacts = [
            c for c in contacts.values()
            if c.detection_method == "home_on_jam"
        ]
        assert len(hoj_contacts) == 1
        first_update = hoj_contacts[0].last_update

        # Turn HoJ off
        sensors.eccm.set_home_on_jam(False)
        assert sensors.eccm.hoj_active is False

        # Tick 2: HoJ off, existing contact should NOT get a fresh update
        _run_sensor_tick(sensors, own, [own, target])

        contacts = sensors.contact_tracker.get_all_contacts(sensors.sim_time)
        # The old contact may still exist (not pruned yet), but its
        # last_update should not have been refreshed by HoJ
        for c in contacts.values():
            if c.detection_method == "home_on_jam":
                # If the contact still exists, it should have the old timestamp
                assert c.last_update == first_update
