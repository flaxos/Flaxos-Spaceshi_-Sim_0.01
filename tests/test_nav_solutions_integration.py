# tests/test_nav_solutions_integration.py
"""
Integration tests for nav solutions pipeline (PRs 194-196).

Covers:
  Phase 1: NAV_PROFILES import from rendezvous module
  Phase 2: calculate_nav_solutions() return structure
  Phase 3: _cmd_get_nav_solutions response format
  Phase 4: RendezvousAutopilot creation and profile application
  Phase 5: AutopilotFactory.create with profile param
  Phase 6: get_state() includes profile
  Phase 7: compute() ticks don't crash
  Phase 8: GoToPositionAutopilot profile wiring
  Phase 9: NavigationSystem.command("get_nav_solutions") pipeline
  Phase 10: Type annotation consistency (returns Dict not List)
"""

import math
import pytest
from typing import Dict, Optional
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

class MockSystems:
    """dict-like container with .get() that mirrors SystemsDict used in ship."""

    def __init__(self, mapping=None):
        self._d = mapping or {}

    def get(self, key, default=None):
        return self._d.get(key, default)

    def __getitem__(self, key):
        return self._d[key]

    def __contains__(self, key):
        return key in self._d

    def items(self):
        return self._d.items()

    def values(self):
        return self._d.values()


class MockPropulsion:
    def __init__(self, max_thrust=50000.0):
        self.max_thrust = max_thrust


class MockRCS:
    def estimate_rotation_time(self, angle_deg: float, ship) -> float:
        # Simple model: 180 degrees takes 20 seconds
        return max(0.0, angle_deg / 9.0)


class MockContact:
    """Minimal sensor contact that looks like a target to calculate_relative_motion."""
    def __init__(self, position=None, velocity=None):
        self.position = position or {"x": 10_000.0, "y": 0.0, "z": 0.0}
        self.velocity = velocity or {"x": 0.0, "y": 0.0, "z": 0.0}
        self.contact_id = "C001"


class MockSensors:
    def __init__(self, contacts=None):
        self._contacts = contacts or {}

    def get_contact(self, contact_id: str):
        return self._contacts.get(contact_id)


class MockEventBus:
    def publish(self, event_type, data):
        pass


def make_mock_ship(
    ship_id: str = "test_ship",
    mass: float = 10_000.0,
    position: Optional[Dict] = None,
    velocity: Optional[Dict] = None,
    orientation: Optional[Dict] = None,
    with_propulsion: bool = True,
    with_rcs: bool = True,
    with_sensors: bool = True,
    sensor_contacts: Optional[Dict] = None,
):
    """Build a minimal mock ship for navigation testing."""
    ship = MagicMock()
    ship.id = ship_id
    ship.mass = mass
    ship.position = position or {"x": 0.0, "y": 0.0, "z": 0.0}
    ship.velocity = velocity or {"x": 0.0, "y": 0.0, "z": 0.0}
    ship.orientation = orientation or {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
    ship.angular_velocity = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
    ship.sim_time = 0.0
    ship.event_bus = MockEventBus()
    ship._all_ships_ref = []

    systems_map = {}
    if with_propulsion:
        systems_map["propulsion"] = MockPropulsion()
    if with_rcs:
        systems_map["rcs"] = MockRCS()
    if with_sensors:
        contacts = sensor_contacts or {"C001": MockContact()}
        systems_map["sensors"] = MockSensors(contacts)

    ship.systems = MockSystems(systems_map)
    return ship


# ---------------------------------------------------------------------------
# Phase 1: NAV_PROFILES import
# ---------------------------------------------------------------------------

class TestNavProfilesImport:
    """Phase 1: The NAV_PROFILES constant must be importable and well-formed."""

    def test_nav_profiles_importable(self):
        """Import must not raise; this is the critical crash path."""
        from hybrid.navigation.autopilot.rendezvous import NAV_PROFILES
        assert NAV_PROFILES is not None

    def test_nav_profiles_has_three_keys(self):
        from hybrid.navigation.autopilot.rendezvous import NAV_PROFILES
        assert set(NAV_PROFILES.keys()) == {"aggressive", "balanced", "conservative"}

    def test_nav_profiles_each_has_required_fields(self):
        from hybrid.navigation.autopilot.rendezvous import NAV_PROFILES
        required = {"max_thrust", "brake_margin", "flip_safety_factor",
                    "description", "risk_level"}
        for name, profile in NAV_PROFILES.items():
            missing = required - set(profile.keys())
            assert not missing, f"NAV_PROFILES['{name}'] missing keys: {missing}"

    def test_nav_profiles_max_thrust_range(self):
        from hybrid.navigation.autopilot.rendezvous import NAV_PROFILES
        for name, profile in NAV_PROFILES.items():
            assert 0.0 < profile["max_thrust"] <= 1.0, (
                f"NAV_PROFILES['{name}']['max_thrust'] = {profile['max_thrust']} "
                "should be in (0, 1]"
            )

    def test_goto_profiles_importable(self):
        """GOTO_PROFILES in goto_position.py must also be importable."""
        from hybrid.navigation.autopilot.goto_position import GOTO_PROFILES
        assert set(GOTO_PROFILES.keys()) == {"aggressive", "balanced", "conservative"}


# ---------------------------------------------------------------------------
# Phase 2: calculate_nav_solutions() return structure
# ---------------------------------------------------------------------------

class TestCalculateNavSolutions:
    """Phase 2: NavigationController.calculate_nav_solutions() return format."""

    def setup_method(self):
        from hybrid.navigation.navigation_controller import NavigationController
        self.ship = make_mock_ship()
        self.ctrl = NavigationController(self.ship)

    def test_returns_dict_not_none_with_sensor_contact(self):
        result = self.ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None, "Should find contact C001 in mock sensors"
        assert isinstance(result, dict), (
            f"calculate_nav_solutions must return dict, got {type(result)}"
        )

    def test_top_level_keys_present(self):
        result = self.ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None
        for key in ("solutions", "target_id", "range", "closing_speed"):
            assert key in result, f"Top-level key '{key}' missing from result"

    def test_solutions_is_dict_not_list(self):
        """Critical: GUI expects solutions as dict keyed by profile name."""
        result = self.ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None
        assert isinstance(result["solutions"], dict), (
            f"result['solutions'] must be a dict, got {type(result['solutions'])}"
        )

    def test_solutions_has_three_profiles(self):
        result = self.ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None
        assert set(result["solutions"].keys()) == {"aggressive", "balanced", "conservative"}

    def test_each_solution_has_required_fields(self):
        result = self.ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None
        required = {"profile", "total_time", "fuel_cost", "accuracy",
                    "risk_level", "description"}
        for name, sol in result["solutions"].items():
            missing = required - set(sol.keys())
            assert not missing, f"Solution '{name}' missing keys: {missing}"

    def test_range_is_numeric_and_positive(self):
        result = self.ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None
        assert isinstance(result["range"], (int, float))
        assert result["range"] > 0

    def test_closing_speed_is_numeric(self):
        result = self.ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None
        assert isinstance(result["closing_speed"], (int, float))

    def test_returns_none_when_target_not_found(self):
        result = self.ctrl.calculate_nav_solutions(target_id="NONEXISTENT")
        assert result is None, "Should return None when target cannot be resolved"

    def test_returns_none_when_no_target_specified(self):
        result = self.ctrl.calculate_nav_solutions()
        assert result is None, "Should return None when no target or position specified"

    def test_with_target_position_fallback(self):
        """calculate_nav_solutions should also work with an explicit position dict."""
        result = self.ctrl.calculate_nav_solutions(
            target_position={"x": 5000.0, "y": 0.0, "z": 0.0}
        )
        assert result is not None, "Should work with target_position fallback"
        assert isinstance(result["solutions"], dict)

    def test_aggressive_has_highest_thrust(self):
        result = self.ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None
        sols = result["solutions"]
        assert sols["aggressive"]["max_thrust"] >= sols["balanced"]["max_thrust"]
        assert sols["balanced"]["max_thrust"] >= sols["conservative"]["max_thrust"]

    def test_aggressive_is_fastest(self):
        """Aggressive profile should have smallest total_time."""
        result = self.ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None
        sols = result["solutions"]
        assert sols["aggressive"]["total_time"] <= sols["balanced"]["total_time"], (
            "Aggressive should be faster than balanced"
        )
        assert sols["balanced"]["total_time"] <= sols["conservative"]["total_time"], (
            "Balanced should be faster than conservative"
        )

    def test_fuel_cost_in_0_1_range(self):
        result = self.ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None
        for name, sol in result["solutions"].items():
            fc = sol["fuel_cost"]
            assert 0.0 <= fc <= 1.0, (
                f"fuel_cost for '{name}' = {fc} outside [0, 1]"
            )

    def test_risk_levels_match_expected(self):
        result = self.ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None
        sols = result["solutions"]
        assert sols["aggressive"]["risk_level"] == "high"
        assert sols["balanced"]["risk_level"] == "medium"
        assert sols["conservative"]["risk_level"] == "low"

    def test_total_time_is_finite(self):
        result = self.ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None
        for name, sol in result["solutions"].items():
            t = sol["total_time"]
            assert math.isfinite(t), f"total_time for '{name}' is not finite: {t}"
            assert t >= 0.0, f"total_time for '{name}' should not be negative: {t}"


# ---------------------------------------------------------------------------
# Phase 3: _cmd_get_nav_solutions response format (NavigationSystem level)
# ---------------------------------------------------------------------------

class TestCmdGetNavSolutions:
    """Phase 3: NavigationSystem._cmd_get_nav_solutions wraps in success_dict."""

    def _make_nav_system(self):
        from hybrid.systems.navigation.navigation import NavigationSystem
        nav = NavigationSystem({})
        ship = make_mock_ship()
        # Prime the controller (normally happens on first tick)
        from hybrid.navigation.navigation_controller import NavigationController
        nav.controller = NavigationController(ship)
        return nav, ship

    def test_cmd_returns_ok_true_with_valid_target(self):
        nav, ship = self._make_nav_system()
        result = nav.command("get_nav_solutions", {
            "target_id": "C001",
            "ship": ship,
            "event_bus": ship.event_bus,
        })
        assert result.get("ok") is True, f"Expected ok=True, got: {result}"

    def test_cmd_returns_solutions_dict_in_result(self):
        nav, ship = self._make_nav_system()
        result = nav.command("get_nav_solutions", {
            "target_id": "C001",
            "ship": ship,
            "event_bus": ship.event_bus,
        })
        assert "solutions" in result, f"'solutions' key missing from result: {result.keys()}"
        assert isinstance(result["solutions"], dict), (
            f"result['solutions'] should be dict, got {type(result['solutions'])}"
        )

    def test_cmd_returns_range_and_closing_speed(self):
        nav, ship = self._make_nav_system()
        result = nav.command("get_nav_solutions", {
            "target_id": "C001",
            "ship": ship,
        })
        assert "range" in result, f"'range' missing from result: {result.keys()}"
        assert "closing_speed" in result, f"'closing_speed' missing from result: {result.keys()}"

    def test_cmd_error_when_no_target(self):
        nav, ship = self._make_nav_system()
        result = nav.command("get_nav_solutions", {
            "ship": ship,
        })
        assert result.get("ok") is False, (
            "Should return error when neither target_id nor target_position given"
        )

    def test_cmd_error_when_contact_not_found(self):
        nav, ship = self._make_nav_system()
        result = nav.command("get_nav_solutions", {
            "target_id": "GHOST",
            "ship": ship,
        })
        assert result.get("ok") is False, (
            "Should return error when contact ID is unknown"
        )

    def test_cmd_with_inline_xyz(self):
        """target_position can be passed as inline x/y/z params."""
        nav, ship = self._make_nav_system()
        result = nav.command("get_nav_solutions", {
            "x": 5000.0,
            "y": 0.0,
            "z": 0.0,
            "ship": ship,
        })
        assert result.get("ok") is True, f"Expected ok=True with inline xyz: {result}"

    def test_cmd_not_initialized_returns_error(self):
        from hybrid.systems.navigation.navigation import NavigationSystem
        nav = NavigationSystem({})
        # Don't set controller — simulates pre-first-tick state
        result = nav.command("get_nav_solutions", {"target_id": "C001"})
        assert result.get("ok") is False, (
            "Should return error when controller is not yet initialized"
        )


# ---------------------------------------------------------------------------
# Phase 4: RendezvousAutopilot creation and profile params
# ---------------------------------------------------------------------------

class TestRendezvousAutopilotCreation:
    """Phase 4: RendezvousAutopilot with each profile sets correct params."""

    def _make_rendezvous(self, profile="balanced", extra_params=None):
        from hybrid.navigation.autopilot.rendezvous import RendezvousAutopilot, NAV_PROFILES
        ship = make_mock_ship()
        params = {"profile": profile}
        if extra_params:
            params.update(extra_params)
        ap = RendezvousAutopilot(ship, "C001", params)
        return ap, NAV_PROFILES

    def test_aggressive_profile_sets_max_thrust_1(self):
        ap, profiles = self._make_rendezvous("aggressive")
        expected = profiles["aggressive"]["max_thrust"]
        assert ap.max_thrust == expected, (
            f"aggressive max_thrust should be {expected}, got {ap.max_thrust}"
        )

    def test_conservative_profile_sets_lower_thrust(self):
        ap, profiles = self._make_rendezvous("conservative")
        expected = profiles["conservative"]["max_thrust"]
        assert ap.max_thrust == expected

    def test_balanced_profile_sets_brake_margin(self):
        ap, profiles = self._make_rendezvous("balanced")
        expected = profiles["balanced"]["brake_margin"]
        assert ap.brake_margin == expected

    def test_profile_name_stored_on_instance(self):
        for profile_name in ("aggressive", "balanced", "conservative"):
            ap, _ = self._make_rendezvous(profile_name)
            assert ap.profile_name == profile_name, (
                f"profile_name should be '{profile_name}', got '{ap.profile_name}'"
            )

    def test_invalid_profile_falls_back_to_balanced(self):
        """Unknown profile name should fall back to balanced, not crash."""
        from hybrid.navigation.autopilot.rendezvous import RendezvousAutopilot, NAV_PROFILES
        ship = make_mock_ship()
        ap = RendezvousAutopilot(ship, "C001", {"profile": "ludicrous"})
        # Should use balanced values
        expected_thrust = NAV_PROFILES["balanced"]["max_thrust"]
        assert ap.max_thrust == expected_thrust, (
            f"Unknown profile should fall back to balanced max_thrust={expected_thrust}"
        )

    def test_no_target_sets_error_status(self):
        from hybrid.navigation.autopilot.rendezvous import RendezvousAutopilot
        ship = make_mock_ship()
        ap = RendezvousAutopilot(ship, None, {})
        assert ap.status == "error", "No target_id should set status='error'"

    def test_explicit_max_thrust_overrides_profile(self):
        """Explicit max_thrust param should override the profile default."""
        from hybrid.navigation.autopilot.rendezvous import RendezvousAutopilot
        ship = make_mock_ship()
        ap = RendezvousAutopilot(ship, "C001",
                                  {"profile": "aggressive", "max_thrust": 0.6})
        assert ap.max_thrust == pytest.approx(0.6), (
            "Explicit max_thrust should override profile default"
        )

    def test_get_state_includes_profile(self):
        """get_state() must include 'profile' key for GUI display."""
        from hybrid.navigation.autopilot.rendezvous import RendezvousAutopilot
        ship = make_mock_ship()
        ap = RendezvousAutopilot(ship, "C001", {"profile": "conservative"})
        state = ap.get_state()
        assert "profile" in state, f"get_state() missing 'profile' key: {state.keys()}"
        assert state["profile"] == "conservative"

    def test_get_state_includes_phase(self):
        from hybrid.navigation.autopilot.rendezvous import RendezvousAutopilot
        ship = make_mock_ship()
        ap = RendezvousAutopilot(ship, "C001", {})
        state = ap.get_state()
        assert "phase" in state, f"get_state() missing 'phase' key: {state.keys()}"

    def test_aggressive_braking_margin_greater_than_conservative(self):
        """Aggressive needs MORE brake_margin than conservative because it
        arrives at the flip point faster, so the post-flip alignment transient
        (where delivered thrust is only 20-40% of theoretical) costs more
        distance at high speed.  See feedback_rendezvous_rca.md rule 5."""
        from hybrid.navigation.autopilot.rendezvous import RendezvousAutopilot
        ship = make_mock_ship()
        agg = RendezvousAutopilot(ship, "C001", {"profile": "aggressive"})
        con = RendezvousAutopilot(ship, "C001", {"profile": "conservative"})
        assert agg.brake_margin > con.brake_margin, (
            f"aggressive brake_margin {agg.brake_margin} should be > "
            f"conservative {con.brake_margin}"
        )


# ---------------------------------------------------------------------------
# Phase 5: AutopilotFactory.create with profile param
# ---------------------------------------------------------------------------

class TestAutopilotFactoryWithProfile:
    """Phase 5: Factory creates autopilot instances with correct profile."""

    def test_factory_creates_rendezvous_with_profile(self):
        from hybrid.navigation.autopilot.factory import AutopilotFactory
        ship = make_mock_ship()
        ap = AutopilotFactory.create("rendezvous", ship, "C001",
                                      {"profile": "aggressive"})
        assert ap is not None
        assert ap.profile_name == "aggressive"

    def test_factory_creates_rendezvous_default_profile(self):
        """No profile param -> should default to 'balanced'."""
        from hybrid.navigation.autopilot.factory import AutopilotFactory
        ship = make_mock_ship()
        ap = AutopilotFactory.create("rendezvous", ship, "C001", {})
        assert ap is not None
        assert ap.profile_name == "balanced"

    def test_factory_creates_goto_with_profile(self):
        from hybrid.navigation.autopilot.factory import AutopilotFactory
        ship = make_mock_ship()
        ap = AutopilotFactory.create("goto_position", ship, None, {
            "x": 1000.0, "y": 0.0, "z": 0.0,
            "profile": "conservative",
        })
        assert ap is not None
        assert ap.profile_name == "conservative"

    def test_factory_off_returns_none(self):
        from hybrid.navigation.autopilot.factory import AutopilotFactory
        ship = make_mock_ship()
        result = AutopilotFactory.create("off", ship, None, {})
        assert result is None

    def test_factory_unknown_program_raises_value_error(self):
        from hybrid.navigation.autopilot.factory import AutopilotFactory
        ship = make_mock_ship()
        with pytest.raises(ValueError):
            AutopilotFactory.create("warp_drive", ship, None, {})

    def test_factory_dock_approach_alias_creates_rendezvous(self):
        """dock_approach is an alias for rendezvous in the factory."""
        from hybrid.navigation.autopilot.factory import AutopilotFactory
        from hybrid.navigation.autopilot.rendezvous import RendezvousAutopilot
        ship = make_mock_ship()
        ap = AutopilotFactory.create("dock_approach", ship, "C001", {})
        assert isinstance(ap, RendezvousAutopilot)


# ---------------------------------------------------------------------------
# Phase 6: get_state() on rendezvous autopilot
# ---------------------------------------------------------------------------

class TestRendezvousGetState:
    """Phase 6: get_state() on RendezvousAutopilot returns a rich dict."""

    def test_get_state_no_target_returns_status_text(self):
        """With no resoluble target, get_state should not crash."""
        from hybrid.navigation.autopilot.rendezvous import RendezvousAutopilot
        ship = make_mock_ship()
        # Create with a contact ID that doesn't exist in sensors
        ap = RendezvousAutopilot(ship, "GHOST_TARGET", {})
        state = ap.get_state()
        assert isinstance(state, dict)
        assert "status_text" in state or "status" in state

    def test_get_state_with_target_has_range(self):
        from hybrid.navigation.autopilot.rendezvous import RendezvousAutopilot
        ship = make_mock_ship()
        ap = RendezvousAutopilot(ship, "C001", {"profile": "balanced"})
        state = ap.get_state()
        assert "range" in state, f"get_state() should include 'range': {state.keys()}"

    def test_get_state_with_target_has_closing_speed(self):
        from hybrid.navigation.autopilot.rendezvous import RendezvousAutopilot
        ship = make_mock_ship()
        ap = RendezvousAutopilot(ship, "C001", {})
        state = ap.get_state()
        assert "closing_speed" in state


# ---------------------------------------------------------------------------
# Phase 7: compute() ticks don't crash
# ---------------------------------------------------------------------------

class TestRendezvousCompute:
    """Phase 7: compute() must not throw exceptions during normal operation."""

    def _run_ticks(self, ship, target_id, profile, n_ticks=10, dt=0.1):
        from hybrid.navigation.autopilot.rendezvous import RendezvousAutopilot
        ap = RendezvousAutopilot(ship, target_id, {"profile": profile})
        results = []
        for i in range(n_ticks):
            cmd = ap.compute(dt, i * dt)
            results.append(cmd)
        return ap, results

    def test_compute_burn_phase_aggressive(self):
        ship = make_mock_ship()
        ap, results = self._run_ticks(ship, "C001", "aggressive")
        # At least some ticks should return a command dict
        non_none = [r for r in results if r is not None]
        assert len(non_none) > 0, "compute() should return thrust commands"

    def test_compute_burn_phase_balanced(self):
        ship = make_mock_ship()
        ap, results = self._run_ticks(ship, "C001", "balanced")
        non_none = [r for r in results if r is not None]
        assert len(non_none) > 0

    def test_compute_burn_phase_conservative(self):
        ship = make_mock_ship()
        ap, results = self._run_ticks(ship, "C001", "conservative")
        non_none = [r for r in results if r is not None]
        assert len(non_none) > 0

    def test_compute_returns_dict_with_thrust_and_heading(self):
        ship = make_mock_ship()
        ap, results = self._run_ticks(ship, "C001", "balanced", n_ticks=1)
        cmd = results[0]
        assert cmd is not None
        assert "thrust" in cmd, f"compute() result missing 'thrust': {cmd}"
        assert "heading" in cmd, f"compute() result missing 'heading': {cmd}"

    def test_compute_thrust_clamped_0_to_1(self):
        ship = make_mock_ship()
        ap, results = self._run_ticks(ship, "C001", "aggressive", n_ticks=20)
        for cmd in results:
            if cmd is not None:
                t = cmd["thrust"]
                assert 0.0 <= t <= 1.0, f"Thrust {t} out of [0, 1]"

    def test_compute_no_target_returns_none(self):
        from hybrid.navigation.autopilot.rendezvous import RendezvousAutopilot
        ship = make_mock_ship()
        ap = RendezvousAutopilot(ship, "GHOST", {})
        cmd = ap.compute(0.1, 0.0)
        assert cmd is None, "compute() with no target should return None"

    def test_compute_with_all_profiles_no_exception(self):
        """Smoke test: all 3 profiles run 50 ticks without exception."""
        for profile in ("aggressive", "balanced", "conservative"):
            ship = make_mock_ship()
            ap, results = self._run_ticks(ship, "C001", profile, n_ticks=50)
            # Just verifying no exception was raised

    def test_profile_affects_thrust_output(self):
        """Aggressive should produce higher thrust command than conservative
        at the same range (burn phase)."""
        ship_agg = make_mock_ship()
        ship_con = make_mock_ship()

        from hybrid.navigation.autopilot.rendezvous import RendezvousAutopilot
        ap_agg = RendezvousAutopilot(ship_agg, "C001", {"profile": "aggressive"})
        ap_con = RendezvousAutopilot(ship_con, "C001", {"profile": "conservative"})

        # Both start in burn phase at same range
        cmd_agg = ap_agg.compute(0.1, 0.0)
        cmd_con = ap_con.compute(0.1, 0.0)

        if cmd_agg and cmd_con:
            assert cmd_agg["thrust"] >= cmd_con["thrust"], (
                f"Aggressive thrust {cmd_agg['thrust']} should be >= "
                f"conservative thrust {cmd_con['thrust']}"
            )


# ---------------------------------------------------------------------------
# Phase 8: GoToPositionAutopilot profile wiring
# ---------------------------------------------------------------------------

class TestGoToPositionProfile:
    """Phase 8: GoToPositionAutopilot respects the profile parameter."""

    def test_aggressive_higher_thrust_than_conservative(self):
        from hybrid.navigation.autopilot.goto_position import GoToPositionAutopilot
        ship = make_mock_ship()
        agg = GoToPositionAutopilot(ship, None,
                                     {"x": 10000.0, "y": 0.0, "z": 0.0,
                                      "profile": "aggressive"})
        con = GoToPositionAutopilot(ship, None,
                                     {"x": 10000.0, "y": 0.0, "z": 0.0,
                                      "profile": "conservative"})
        assert agg.max_thrust >= con.max_thrust

    def test_profile_name_stored(self):
        from hybrid.navigation.autopilot.goto_position import GoToPositionAutopilot
        ship = make_mock_ship()
        ap = GoToPositionAutopilot(ship, None,
                                    {"x": 5000.0, "y": 0.0, "z": 0.0,
                                     "profile": "conservative"})
        assert ap.profile_name == "conservative"

    def test_get_state_includes_profile(self):
        from hybrid.navigation.autopilot.goto_position import GoToPositionAutopilot
        ship = make_mock_ship()
        ap = GoToPositionAutopilot(ship, None,
                                    {"x": 5000.0, "y": 0.0, "z": 0.0,
                                     "profile": "balanced"})
        state = ap.get_state()
        assert "profile" in state, f"GoToPosition get_state missing 'profile': {state.keys()}"
        assert state["profile"] == "balanced"

    def test_invalid_destination_sets_error_status(self):
        from hybrid.navigation.autopilot.goto_position import GoToPositionAutopilot
        ship = make_mock_ship()
        ap = GoToPositionAutopilot(ship, None, {})  # No coordinates
        assert ap.status == "error"

    def test_compute_returns_command_toward_target(self):
        from hybrid.navigation.autopilot.goto_position import GoToPositionAutopilot
        ship = make_mock_ship(position={"x": 0.0, "y": 0.0, "z": 0.0})
        ap = GoToPositionAutopilot(ship, None,
                                    {"x": 5000.0, "y": 0.0, "z": 0.0,
                                     "profile": "balanced"})
        cmd = ap.compute(0.1, 0.0)
        assert cmd is not None, "compute() should return a command"
        assert cmd["thrust"] > 0.0, "Should be accelerating toward target"


# ---------------------------------------------------------------------------
# Phase 9: NavigationController route_command integration
# ---------------------------------------------------------------------------

class TestRouteCommandGetNavSolutions:
    """Phase 9: route_command pipes get_nav_solutions through to the nav system."""

    def test_route_command_get_nav_solutions_returns_dict(self):
        """End-to-end: route_command("get_nav_solutions") should not crash."""
        from hybrid.command_handler import route_command
        ship = make_mock_ship()

        # Navigation system needs the 'navigation' system on ship.systems
        from hybrid.systems.navigation.navigation import NavigationSystem
        from hybrid.navigation.navigation_controller import NavigationController
        nav_sys = NavigationSystem({})
        nav_sys.controller = NavigationController(ship)

        ship.systems._d["navigation"] = nav_sys

        command_data = {
            "command": "get_nav_solutions",
            "ship": ship.id,
            "target_id": "C001",
        }
        result = route_command(ship, command_data)
        assert isinstance(result, dict), f"route_command returned non-dict: {type(result)}"

    def test_route_command_get_nav_solutions_no_error_key_on_success(self):
        from hybrid.command_handler import route_command
        ship = make_mock_ship()

        from hybrid.systems.navigation.navigation import NavigationSystem
        from hybrid.navigation.navigation_controller import NavigationController
        nav_sys = NavigationSystem({})
        nav_sys.controller = NavigationController(ship)
        ship.systems._d["navigation"] = nav_sys

        command_data = {
            "command": "get_nav_solutions",
            "ship": ship.id,
            "target_id": "C001",
        }
        result = route_command(ship, command_data)
        assert "error" not in result or result.get("ok") is True, (
            f"Expected success response, got error: {result}"
        )

    def test_route_command_missing_nav_system_returns_error(self):
        from hybrid.command_handler import route_command
        ship = make_mock_ship(with_sensors=True)
        # No 'navigation' in systems

        command_data = {
            "command": "get_nav_solutions",
            "ship": ship.id,
            "target_id": "C001",
        }
        result = route_command(ship, command_data)
        assert "error" in result, (
            "Without navigation system, should return error dict"
        )


# ---------------------------------------------------------------------------
# Phase 10: Type annotation consistency
# ---------------------------------------------------------------------------

class TestTypeAnnotationConsistency:
    """Phase 10: No code should treat calculate_nav_solutions result as a list."""

    def test_result_not_iterable_as_list(self):
        """Verify the return value cannot be mistaken for a list of solutions."""
        from hybrid.navigation.navigation_controller import NavigationController
        ship = make_mock_ship()
        ctrl = NavigationController(ship)
        result = ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None
        # Result is a dict — iterating over it gives keys, not solution objects
        assert not isinstance(result, list), "Result must be dict, not list"
        # The solutions themselves are in result["solutions"]
        assert isinstance(result["solutions"], dict)

    def test_solutions_dict_values_are_dicts(self):
        """Each value in result['solutions'] must be a dict (not a string or number)."""
        from hybrid.navigation.navigation_controller import NavigationController
        ship = make_mock_ship()
        ctrl = NavigationController(ship)
        result = ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None
        for name, sol in result["solutions"].items():
            assert isinstance(sol, dict), (
                f"solutions['{name}'] should be dict, got {type(sol)}"
            )

    def test_cmd_get_nav_solutions_result_has_solutions_at_top_level(self):
        """success_dict(**result) should put 'solutions' at the TOP level
        of the response, not nested under a 'data' key."""
        from hybrid.systems.navigation.navigation import NavigationSystem
        from hybrid.navigation.navigation_controller import NavigationController
        nav = NavigationSystem({})
        ship = make_mock_ship()
        nav.controller = NavigationController(ship)

        result = nav.command("get_nav_solutions", {
            "target_id": "C001",
            "ship": ship,
        })
        # The GUI expects: raw?.response?.solutions OR raw?.solutions
        # success_dict(**result) spreads solutions at the top level
        assert "solutions" in result, (
            f"'solutions' should be top-level key in response. Got: {result.keys()}"
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestNavSolutionEdgeCases:
    """Edge case coverage: zero distance, zero mass, missing systems."""

    def test_zero_distance_does_not_crash(self):
        """Ship at same position as target should not divide by zero."""
        from hybrid.navigation.navigation_controller import NavigationController
        ship = make_mock_ship(position={"x": 0.0, "y": 0.0, "z": 0.0})
        # Target is also at 0,0,0
        contacts = {"C001": MockContact(position={"x": 0.0, "y": 0.0, "z": 0.0})}
        ship.systems._d["sensors"] = MockSensors(contacts)
        ctrl = NavigationController(ship)
        # Should not raise ZeroDivisionError
        result = ctrl.calculate_nav_solutions(target_id="C001")
        # Result may be None or a dict with inf/0 times - just no exception

    def test_ship_without_propulsion_uses_floor_accel(self):
        """Missing propulsion should use floor acceleration, not crash."""
        from hybrid.navigation.navigation_controller import NavigationController
        ship = make_mock_ship(with_propulsion=False)
        ctrl = NavigationController(ship)
        result = ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None
        # With minimal accel, times will be large but should be finite
        for name, sol in result["solutions"].items():
            assert math.isfinite(sol["total_time"]), (
                f"total_time for '{name}' should be finite even without propulsion"
            )

    def test_ship_without_rcs_uses_fallback_flip_time(self):
        """Missing RCS system should use 20s fallback for flip_time."""
        from hybrid.navigation.navigation_controller import NavigationController
        ship = make_mock_ship(with_rcs=False)
        ctrl = NavigationController(ship)
        result = ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None
        # estimated_flip_time * flip_safety_factor should be in the result
        for name, sol in result["solutions"].items():
            assert "estimated_flip_time" in sol, (
                f"'estimated_flip_time' missing from solution '{name}'"
            )

    def test_very_far_target_finite_eta(self):
        """10M km range should still produce finite ETA estimates."""
        from hybrid.navigation.navigation_controller import NavigationController
        ship = make_mock_ship()
        far_contact = MockContact(position={"x": 10_000_000_000.0, "y": 0.0, "z": 0.0})
        ship.systems._d["sensors"] = MockSensors({"C001": far_contact})
        ctrl = NavigationController(ship)
        result = ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None
        for name, sol in result["solutions"].items():
            assert math.isfinite(sol["total_time"]), (
                f"ETA for '{name}' at 10M km should be finite"
            )

    def test_closing_ship_closing_speed_non_negative(self):
        """Closing speed should always be >= 0 (negative means opening, not closing)."""
        from hybrid.navigation.navigation_controller import NavigationController
        ship = make_mock_ship(velocity={"x": 100.0, "y": 0.0, "z": 0.0})
        ctrl = NavigationController(ship)
        result = ctrl.calculate_nav_solutions(target_id="C001")
        assert result is not None
        assert result["closing_speed"] >= 0.0, (
            f"closing_speed should be >= 0, got {result['closing_speed']}"
        )

    def test_rendezvous_compute_with_zero_mass_ship_fallback(self):
        """Zero-mass ship should use floor acceleration, not crash with ZeroDivisionError."""
        from hybrid.navigation.autopilot.rendezvous import RendezvousAutopilot
        ship = make_mock_ship(mass=0.0)
        ap = RendezvousAutopilot(ship, "C001", {"profile": "balanced"})
        # Should not raise
        cmd = ap.compute(0.1, 0.0)
        # Command may be None or dict, just no exception

