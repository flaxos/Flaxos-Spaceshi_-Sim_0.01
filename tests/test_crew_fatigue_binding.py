# tests/test_crew_fatigue_binding.py
"""Tests for crew fatigue integration with CrewBindingSystem.get_multiplier().

Validates that g-load / combat-stress fatigue from CrewFatigueSystem is
folded into the crew performance multiplier returned to gameplay systems
(RCS, targeting, sensors, ops).
"""

import pytest
from unittest.mock import MagicMock, patch

from hybrid.systems.crew_binding_system import CrewBindingSystem
from server.stations.station_types import StationType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_shared_state():
    """Ensure class-level shared state is clean between tests."""
    old_mgr = CrewBindingSystem._shared_crew_manager
    old_binder = CrewBindingSystem._shared_binder
    yield
    CrewBindingSystem._shared_crew_manager = old_mgr
    CrewBindingSystem._shared_binder = old_binder


def _make_ship(fatigue_performance: float | None = None) -> MagicMock:
    """Build a minimal mock ship with an optional crew_fatigue system.

    Args:
        fatigue_performance: If not None, a CrewFatigueSystem mock is
            attached that returns this value from get_station_performance()
            for any station.  If None, no crew_fatigue key exists.
    """
    ship = MagicMock()
    ship.id = "test_ship"
    ship.systems = {}

    if fatigue_performance is not None:
        fatigue_sys = MagicMock()
        fatigue_sys.get_station_performance.return_value = fatigue_performance
        ship.systems["crew_fatigue"] = fatigue_sys

    return ship


def _install_binder(skill_multiplier: float = 0.8) -> MagicMock:
    """Install a mock binder that returns a fixed skill multiplier."""
    binder = MagicMock()
    binder._slots = {"test_ship": True}
    binder.get_station_multiplier.return_value = skill_multiplier
    CrewBindingSystem._shared_binder = binder
    return binder


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetMultiplierBackwardCompat:
    """Calling get_multiplier without ship= must behave exactly as before."""

    def test_no_binder_returns_1(self):
        CrewBindingSystem._shared_binder = None
        result = CrewBindingSystem.get_multiplier("any_ship", StationType.HELM)
        assert result == 1.0

    def test_no_ship_slots_returns_1(self):
        binder = MagicMock()
        binder._slots = {}
        CrewBindingSystem._shared_binder = binder
        result = CrewBindingSystem.get_multiplier("unknown", StationType.HELM)
        assert result == 1.0

    def test_skill_only_without_ship_arg(self):
        """Without ship=, fatigue is never applied (backward compat)."""
        _install_binder(skill_multiplier=0.8)
        result = CrewBindingSystem.get_multiplier("test_ship", StationType.HELM)
        assert result == pytest.approx(0.8)


class TestFatigueIntegration:
    """Fatigue from CrewFatigueSystem combines multiplicatively with skill."""

    def test_nominal_fatigue_no_change(self):
        """Fatigue performance 1.0 means no degradation."""
        _install_binder(skill_multiplier=0.9)
        ship = _make_ship(fatigue_performance=1.0)
        result = CrewBindingSystem.get_multiplier("test_ship", StationType.HELM, ship=ship)
        assert result == pytest.approx(0.9)

    def test_partial_fatigue_reduces_multiplier(self):
        """50% fatigue performance halves the effective multiplier."""
        _install_binder(skill_multiplier=0.8)
        ship = _make_ship(fatigue_performance=0.5)
        result = CrewBindingSystem.get_multiplier("test_ship", StationType.HELM, ship=ship)
        assert result == pytest.approx(0.4)

    def test_blackout_drops_to_zero(self):
        """Full blackout (performance 0.0) zeroes the multiplier."""
        _install_binder(skill_multiplier=0.8)
        ship = _make_ship(fatigue_performance=0.0)
        result = CrewBindingSystem.get_multiplier("test_ship", StationType.TACTICAL, ship=ship)
        assert result == pytest.approx(0.0)

    def test_different_stations_query_correct_value(self):
        """The station name is forwarded to get_station_performance."""
        _install_binder(skill_multiplier=1.0)
        ship = _make_ship(fatigue_performance=0.7)
        fatigue_sys = ship.systems["crew_fatigue"]

        CrewBindingSystem.get_multiplier("test_ship", StationType.OPS, ship=ship)
        fatigue_sys.get_station_performance.assert_called_once_with("ops")

    def test_no_fatigue_system_on_ship(self):
        """Ship exists but has no crew_fatigue system -- skill only."""
        _install_binder(skill_multiplier=0.85)
        ship = _make_ship(fatigue_performance=None)
        result = CrewBindingSystem.get_multiplier("test_ship", StationType.SCIENCE, ship=ship)
        assert result == pytest.approx(0.85)

    def test_ship_without_systems_attr(self):
        """Ship object without a systems dict -- degrade gracefully."""
        _install_binder(skill_multiplier=0.9)
        ship = MagicMock(spec=[])  # no attributes at all
        ship.id = "test_ship"
        result = CrewBindingSystem.get_multiplier("test_ship", StationType.HELM, ship=ship)
        # Should still return skill-only, not crash
        assert result == pytest.approx(0.9)


class TestNoBinderWithFatigue:
    """When binder is None, base=1.0, but fatigue still applies."""

    def test_no_binder_with_fatigued_ship(self):
        CrewBindingSystem._shared_binder = None
        ship = _make_ship(fatigue_performance=0.6)
        result = CrewBindingSystem.get_multiplier("test_ship", StationType.HELM, ship=ship)
        # base 1.0 * fatigue 0.6
        assert result == pytest.approx(0.6)
