# tests/systems/targeting/test_contact_lock_state.py
"""Tests for the CONTACT lock state (Phase 1E).

The CONTACT state is the 1-2 second sensor correlation phase between
designating a target and actively tracking it. It represents the sensor
computer correlating radar returns, IR signatures, and passive emissions
into a coherent target track.

Validates:
- designate_target enters CONTACT (not TRACKING)
- Correlation progresses with dt
- Transition to TRACKING after correlation_time elapses
- No firing solution exists during CONTACT
- Sensor damage slows correlation
- Target lost during correlation returns to NONE
- Re-designating same target does NOT reset correlation
- Designating a new target starts fresh correlation
- Close range (<1km) skips correlation entirely
"""

import pytest
from unittest.mock import MagicMock

from hybrid.systems.targeting.targeting_system import TargetingSystem, LockState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_ship(contact_ids=None, contact_range=50000.0):
    """Create a mock ship with sensors that know about given contact IDs.

    Args:
        contact_ids: List of contact IDs sensors can see.
        contact_range: Distance to place contacts at (metres).
    """
    ship = MagicMock()
    ship.id = "player_ship"
    ship.position = {"x": 0, "y": 0, "z": 0}
    ship.velocity = {"x": 0, "y": 0, "z": 0}

    sensor_system = MagicMock()
    contacts = {}
    for cid in (contact_ids or []):
        contact = MagicMock()
        contact.id = cid
        contact.position = {"x": contact_range, "y": 0, "z": 0}
        contact.velocity = {"x": 0, "y": 0, "z": 0}
        contact.confidence = 0.9
        contact.last_update = 10.0
        contact.detection_method = "ir"
        contact.bearing = {"az": 0, "el": 0}
        contact.distance = contact_range
        contact.signature = 1.0e7  # Bright drive plume
        contact.classification = "hostile"
        contact.name = f"Target-{cid}"
        contact.faction = "enemy"
        contacts[cid] = contact

    sensor_system.get_contact = lambda cid: contacts.get(cid)
    sensor_system.get_contacts = lambda: contacts

    ship.systems = {
        "sensors": sensor_system,
        "targeting": None,
        "weapons": None,
        "crew_fatigue": None,
    }

    ship.get_effective_factor = MagicMock(return_value=1.0)
    ship.damage_model = MagicMock()
    ship.damage_model.get_degradation_factor = MagicMock(return_value=1.0)
    ship._all_ships_ref = []

    return ship


@pytest.fixture
def targeting():
    """TargetingSystem with 1.0s correlation time."""
    ts = TargetingSystem({
        "lock_time": 0.5,
        "lock_range": 500000,
        "correlation_time": 1.0,
        "correlation_skip_range": 1000.0,
    })
    ts._sensor_factor = 1.0
    ts._targeting_factor = 1.0
    ts._sim_time = 10.0
    return ts


# ---------------------------------------------------------------------------
# Core CONTACT state tests
# ---------------------------------------------------------------------------


class TestContactStateEntry:
    """Verify designate_target enters CONTACT, not TRACKING."""

    def test_designate_enters_contact(self, targeting):
        """Designating a target at normal range should enter CONTACT."""
        ship = _make_mock_ship(["C001"], contact_range=50000.0)
        targeting._ship_ref = ship

        result = targeting.lock_target("C001", sim_time=10.0)

        assert result["ok"] is True
        assert targeting.lock_state == LockState.CONTACT
        assert result["lock_state"] == "contact"
        assert targeting._correlation_progress == 0.0

    def test_track_quality_zero_during_contact(self, targeting):
        """Track quality must be 0 during CONTACT phase."""
        ship = _make_mock_ship(["C001"], contact_range=50000.0)
        targeting._ship_ref = ship
        targeting.lock_target("C001", sim_time=10.0)

        assert targeting.track_quality == 0.0

    def test_no_firing_solution_during_contact(self, targeting):
        """No firing solutions should exist during CONTACT."""
        ship = _make_mock_ship(["C001"], contact_range=50000.0)
        targeting._ship_ref = ship
        targeting.lock_target("C001", sim_time=10.0)

        solution = targeting.get_target_solution()
        assert solution.get("ok") is not True
        assert targeting.firing_solutions == {}


# ---------------------------------------------------------------------------
# Correlation progress
# ---------------------------------------------------------------------------


class TestCorrelationProgress:
    """Verify correlation advances with dt and transitions to TRACKING."""

    def test_half_second_still_contact(self, targeting):
        """After 0.5s of a 1.0s correlation, should still be CONTACT."""
        ship = _make_mock_ship(["C001"], contact_range=50000.0)
        targeting._ship_ref = ship
        event_bus = MagicMock()

        targeting.lock_target("C001", sim_time=10.0)
        # Tick 0.5s
        targeting.tick(0.5, ship, event_bus)

        assert targeting.lock_state == LockState.CONTACT
        assert 0.45 <= targeting._correlation_progress <= 0.55

    def test_full_correlation_transitions_to_tracking(self, targeting):
        """After 1.1s total, correlation should be complete -> TRACKING."""
        ship = _make_mock_ship(["C001"], contact_range=50000.0)
        targeting._ship_ref = ship
        event_bus = MagicMock()

        targeting.lock_target("C001", sim_time=10.0)

        # Tick in two steps: 0.5s + 0.6s = 1.1s total
        targeting.tick(0.5, ship, event_bus)
        assert targeting.lock_state == LockState.CONTACT

        targeting.tick(0.6, ship, event_bus)
        assert targeting.lock_state == LockState.TRACKING

    def test_correlation_event_published(self, targeting):
        """target_correlated event should fire when entering TRACKING."""
        ship = _make_mock_ship(["C001"], contact_range=50000.0)
        targeting._ship_ref = ship
        event_bus = MagicMock()

        targeting.lock_target("C001", sim_time=10.0)
        targeting.tick(1.1, ship, event_bus)

        event_bus.publish.assert_any_call("target_correlated", {
            "ship_id": "player_ship",
            "target_id": "C001",
        })


# ---------------------------------------------------------------------------
# Sensor damage affects correlation
# ---------------------------------------------------------------------------


class TestSensorDamageCorrelation:
    """Damaged sensors should slow correlation."""

    def test_degraded_sensors_slow_correlation(self, targeting):
        """With 50% sensor health, correlation takes ~2x longer."""
        ship = _make_mock_ship(["C001"], contact_range=50000.0)
        # tick() reads sensor factor from ship.get_effective_factor("sensors")
        # so we need the mock to return 0.5 for that call.
        ship.get_effective_factor = lambda sys: 0.5 if sys == "sensors" else 1.0
        targeting._ship_ref = ship
        event_bus = MagicMock()

        targeting.lock_target("C001", sim_time=10.0)

        # With 50% sensors, effective_time = 1.0 / 0.5 = 2.0s
        # After 1.0s of ticking, progress should be ~0.5 (not 1.0)
        targeting.tick(1.0, ship, event_bus)
        assert targeting.lock_state == LockState.CONTACT
        assert 0.45 <= targeting._correlation_progress <= 0.55

        # After another 1.1s, total 2.1s -- should now be TRACKING
        targeting.tick(1.1, ship, event_bus)
        assert targeting.lock_state == LockState.TRACKING


# ---------------------------------------------------------------------------
# Target lost during correlation
# ---------------------------------------------------------------------------


class TestContactLostDuringCorrelation:
    """If the contact disappears during CONTACT, go back to NONE."""

    def test_lost_contact_aborts_correlation(self, targeting):
        """Losing sensor contact during CONTACT reverts to NONE."""
        ship = _make_mock_ship(["C001"], contact_range=50000.0)
        targeting._ship_ref = ship
        event_bus = MagicMock()

        targeting.lock_target("C001", sim_time=10.0)
        assert targeting.lock_state == LockState.CONTACT

        # Tick partway through correlation
        targeting.tick(0.3, ship, event_bus)
        assert targeting.lock_state == LockState.CONTACT

        # Now remove the contact from sensors
        ship.systems["sensors"].get_contact = lambda cid: None

        targeting.tick(0.3, ship, event_bus)
        assert targeting.lock_state == LockState.NONE
        assert targeting._correlation_progress == 0.0


# ---------------------------------------------------------------------------
# Re-designation behavior
# ---------------------------------------------------------------------------


class TestRedesignation:
    """Re-designating same vs new targets."""

    def test_redesignate_same_target_keeps_state(self, targeting):
        """Re-designating the same target should NOT reset correlation."""
        ship = _make_mock_ship(["C001"], contact_range=50000.0)
        targeting._ship_ref = ship
        event_bus = MagicMock()

        targeting.lock_target("C001", sim_time=10.0)
        targeting.tick(0.5, ship, event_bus)
        assert targeting.lock_state == LockState.CONTACT

        # Re-designate same target
        result = targeting.lock_target("C001", sim_time=10.5)
        assert result["ok"] is True
        # Should still be CONTACT with progress preserved (not reset to 0)
        assert targeting.lock_state == LockState.CONTACT

    def test_redesignate_same_target_past_contact_keeps_tracking(self, targeting):
        """Re-designating a target already in TRACKING should stay there."""
        ship = _make_mock_ship(["C001"], contact_range=50000.0)
        targeting._ship_ref = ship
        event_bus = MagicMock()

        targeting.lock_target("C001", sim_time=10.0)
        targeting.tick(1.1, ship, event_bus)
        assert targeting.lock_state == LockState.TRACKING

        # Re-designate same target -- should keep TRACKING
        result = targeting.lock_target("C001", sim_time=11.1)
        assert result["ok"] is True
        assert targeting.lock_state == LockState.TRACKING

    def test_designate_new_target_resets(self, targeting):
        """Designating a different target should start fresh CONTACT."""
        ship = _make_mock_ship(["C001", "C002"], contact_range=50000.0)
        targeting._ship_ref = ship
        event_bus = MagicMock()

        targeting.lock_target("C001", sim_time=10.0)
        targeting.tick(1.1, ship, event_bus)
        assert targeting.lock_state == LockState.TRACKING

        # Now designate a different target
        result = targeting.lock_target("C002", sim_time=11.1)
        assert result["ok"] is True
        assert targeting.lock_state == LockState.CONTACT
        assert targeting._correlation_progress == 0.0


# ---------------------------------------------------------------------------
# Close-range skip
# ---------------------------------------------------------------------------


class TestCloseRangeSkip:
    """At very close range (<1km), CONTACT phase is skipped entirely."""

    def test_close_range_skips_to_tracking(self, targeting):
        """Designation within 1km should jump directly to TRACKING."""
        ship = _make_mock_ship(["C001"], contact_range=500.0)
        targeting._ship_ref = ship

        result = targeting.lock_target("C001", sim_time=10.0)

        assert result["ok"] is True
        assert targeting.lock_state == LockState.TRACKING
        assert targeting._correlation_progress == 1.0

    def test_far_range_enters_contact(self, targeting):
        """Designation beyond 1km should enter CONTACT normally."""
        ship = _make_mock_ship(["C001"], contact_range=5000.0)
        targeting._ship_ref = ship

        result = targeting.lock_target("C001", sim_time=10.0)

        assert result["ok"] is True
        assert targeting.lock_state == LockState.CONTACT


# ---------------------------------------------------------------------------
# Telemetry / get_state
# ---------------------------------------------------------------------------


class TestContactStateTelemetry:
    """Verify CONTACT state appears correctly in telemetry."""

    def test_get_state_includes_correlation_progress(self, targeting):
        """get_state should include correlation_progress field."""
        ship = _make_mock_ship(["C001"], contact_range=50000.0)
        targeting._ship_ref = ship
        event_bus = MagicMock()

        targeting.lock_target("C001", sim_time=10.0)
        targeting.tick(0.5, ship, event_bus)

        state = targeting.get_state()
        assert state["lock_state"] == "contact"
        assert "correlation_progress" in state
        assert 0.4 <= state["correlation_progress"] <= 0.6

    def test_get_state_contact_string_value(self, targeting):
        """lock_state in telemetry should be the string 'contact'."""
        ship = _make_mock_ship(["C001"], contact_range=50000.0)
        targeting._ship_ref = ship

        targeting.lock_target("C001", sim_time=10.0)

        state = targeting.get_state()
        assert state["lock_state"] == "contact"
        assert isinstance(state["lock_state"], str)


# ---------------------------------------------------------------------------
# Unlock during CONTACT
# ---------------------------------------------------------------------------


class TestUnlockDuringContact:
    """Unlocking during CONTACT should clean up correlation state."""

    def test_unlock_resets_correlation(self, targeting):
        """Unlocking during CONTACT should reset all correlation state."""
        ship = _make_mock_ship(["C001"], contact_range=50000.0)
        targeting._ship_ref = ship
        event_bus = MagicMock()

        targeting.lock_target("C001", sim_time=10.0)
        targeting.tick(0.3, ship, event_bus)

        result = targeting.unlock_target()
        assert result["ok"] is True
        assert targeting.lock_state == LockState.NONE
        assert targeting._correlation_progress == 0.0


class TestContactStateBugFixes:
    """Regression tests for QA-discovered bugs."""

    def test_lost_contact_clears_locked_target(self, targeting):
        """Bug 1: _degrade_lock during CONTACT must clear locked_target."""
        ship = _make_mock_ship(["C001"], contact_range=50000.0)
        targeting._ship_ref = ship
        event_bus = MagicMock()

        targeting.lock_target("C001", sim_time=10.0)
        assert targeting.lock_state == LockState.CONTACT
        assert targeting.locked_target == "C001"

        # Remove contact from sensors
        ship_no_contacts = _make_mock_ship([], contact_range=50000.0)
        targeting._ship_ref = ship_no_contacts
        targeting.tick(0.1, ship_no_contacts, event_bus)

        assert targeting.lock_state == LockState.NONE
        assert targeting.locked_target is None  # Bug 1: was non-None before fix
        assert targeting._correlation_progress == 0.0

    def test_exact_1km_boundary_enters_contact(self, targeting):
        """At exactly 1000m, strict < means CONTACT is entered (not skipped)."""
        ship = _make_mock_ship(["C001"], contact_range=1000.0)
        targeting._ship_ref = ship
        event_bus = MagicMock()

        targeting.lock_target("C001", sim_time=10.0)
        # At exactly 1000m, 1000 < 1000 is False → CONTACT, not skip
        assert targeting.lock_state == LockState.CONTACT
