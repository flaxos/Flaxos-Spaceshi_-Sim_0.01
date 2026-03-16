"""Tests for RendezvousAutopilot: nav profiles, flip/brake math, phase transitions."""

import pytest
import math
from unittest.mock import MagicMock
from hybrid.navigation.autopilot.rendezvous import RendezvousAutopilot, NAV_PROFILES


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

class MockPropulsion:
    def __init__(self, max_thrust=50000.0):
        self.max_thrust = max_thrust


class MockRCS:
    """RCS stub with controllable estimate_rotation_time."""

    def __init__(self, flip_time=10.0):
        self._flip_time = flip_time

    def estimate_rotation_time(self, angle_degrees: float, ship) -> float:
        return self._flip_time


class SystemsDict:
    """dict-like container that supports .get() with system objects as values."""

    def __init__(self, mapping):
        self._d = mapping

    def get(self, key, default=None):
        return self._d.get(key, default)

    def __getitem__(self, key):
        return self._d[key]

    def __setitem__(self, key, value):
        self._d[key] = value


class MockShip:
    def __init__(
        self,
        position=None,
        velocity=None,
        orientation=None,
        mass=10000.0,
        moment_of_inertia=None,
        max_thrust=50000.0,
        rcs_flip_time=10.0,
        target=None,
    ):
        self.id = "player_ship"
        self.mass = mass
        self.moment_of_inertia = moment_of_inertia or (mass * 10.0)
        self.position = position or {"x": 0.0, "y": 0.0, "z": 0.0}
        self.velocity = velocity or {"x": 0.0, "y": 0.0, "z": 0.0}
        self.orientation = orientation or {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        self.angular_velocity = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}

        propulsion = MockPropulsion(max_thrust)
        rcs = MockRCS(rcs_flip_time)

        sensors = MagicMock()
        sensors.get_contact = MagicMock(return_value=target)

        self.systems = SystemsDict({
            "propulsion": propulsion,
            "rcs": rcs,
            "sensors": sensors,
        })
        self._all_ships_ref = []


def _make_ship(**kwargs):
    return MockShip(**kwargs)


def _make_target(position, velocity=None):
    t = MagicMock()
    t.position = position
    t.velocity = velocity or {"x": 0.0, "y": 0.0, "z": 0.0}
    return t


# ---------------------------------------------------------------------------
# Profile initialisation tests
# ---------------------------------------------------------------------------

class TestProfileDefaults:
    def test_profile_defaults_to_balanced(self):
        """No profile param → balanced profile values."""
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(target=target)
        ap = RendezvousAutopilot(ship, target_id="T001")

        assert ap.profile_name == "balanced"
        assert ap.max_thrust == pytest.approx(NAV_PROFILES["balanced"]["max_thrust"])
        assert ap.brake_margin == pytest.approx(NAV_PROFILES["balanced"]["brake_margin"])
        assert ap.flip_safety_factor == pytest.approx(NAV_PROFILES["balanced"]["flip_safety_factor"])

    def test_profile_aggressive(self):
        """Aggressive profile sets high thrust and tight margin."""
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(target=target)
        ap = RendezvousAutopilot(ship, target_id="T001",
                                 params={"profile": "aggressive"})

        assert ap.profile_name == "aggressive"
        assert ap.max_thrust == pytest.approx(NAV_PROFILES["aggressive"]["max_thrust"])
        assert ap.brake_margin == pytest.approx(NAV_PROFILES["aggressive"]["brake_margin"])
        assert ap.flip_safety_factor == pytest.approx(NAV_PROFILES["aggressive"]["flip_safety_factor"])

    def test_profile_conservative(self):
        """Conservative profile sets low thrust and generous margin."""
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(target=target)
        ap = RendezvousAutopilot(ship, target_id="T001",
                                 params={"profile": "conservative"})

        assert ap.profile_name == "conservative"
        assert ap.max_thrust == pytest.approx(NAV_PROFILES["conservative"]["max_thrust"])
        assert ap.brake_margin == pytest.approx(NAV_PROFILES["conservative"]["brake_margin"])
        assert ap.flip_safety_factor == pytest.approx(NAV_PROFILES["conservative"]["flip_safety_factor"])

    def test_explicit_param_overrides_profile(self):
        """Individual param beats the profile default."""
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(target=target)
        ap = RendezvousAutopilot(
            ship,
            target_id="T001",
            params={"profile": "aggressive", "max_thrust": 0.3},
        )

        assert ap.profile_name == "aggressive"
        # The explicit max_thrust=0.3 must win over profile's 1.0
        assert ap.max_thrust == pytest.approx(0.3)

    def test_unknown_profile_falls_back_to_balanced(self):
        """An unrecognised profile name silently uses balanced values."""
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(target=target)
        ap = RendezvousAutopilot(ship, target_id="T001",
                                 params={"profile": "ludicrous_speed"})

        # profile_name is stored as given, but values come from balanced
        assert ap.max_thrust == pytest.approx(NAV_PROFILES["balanced"]["max_thrust"])


# ---------------------------------------------------------------------------
# Braking distance / flip time accounting
# ---------------------------------------------------------------------------

class TestBrakingDistanceFlipTime:
    """The corrected braking trigger distance must exceed the naive v²/2a
    point so the ship starts flipping early enough to avoid overshoot."""

    def test_braking_trigger_larger_than_naive_kinematic(self):
        """d_trigger > v²/2a for any positive closing speed."""
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            target=target,
            mass=10000.0,
            max_thrust=50000.0,
            rcs_flip_time=10.0,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")

        # Max accel = 50000 / 10000 = 5 m/s²
        a_max = ap._get_max_accel()
        closing_speed = 500.0  # m/s

        naive_d = (closing_speed ** 2) / (2.0 * a_max)
        corrected_d = ap._corrected_braking_distance(closing_speed, a_max)

        assert corrected_d > naive_d, (
            f"Corrected distance {corrected_d:.1f} m must exceed "
            f"naive {naive_d:.1f} m at {closing_speed} m/s"
        )

    def test_braking_trigger_includes_flip_coast_distance(self):
        """The extra distance accounts for coasting during flip."""
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        flip_time = 15.0
        ship = _make_ship(
            target=target,
            mass=10000.0,
            max_thrust=50000.0,
            rcs_flip_time=flip_time,
        )
        ap = RendezvousAutopilot(ship, target_id="T001",
                                 params={"profile": "balanced"})

        closing_speed = 200.0
        a_max = ap._get_max_accel()

        d_brake = ap._braking_distance(closing_speed, a_max)
        flip_coast = closing_speed * flip_time * ap.flip_safety_factor
        expected = d_brake * ap.brake_margin + flip_coast

        actual = ap._corrected_braking_distance(closing_speed, a_max)

        assert actual == pytest.approx(expected, rel=1e-6)

    def test_higher_flip_time_gives_larger_trigger(self):
        """Slower RCS (longer flip) must produce a larger safety margin."""
        target = _make_target({"x": 500000.0, "y": 0.0, "z": 0.0})
        closing_speed = 300.0
        a_max_val = 5.0

        ship_fast_rcs = _make_ship(target=target, rcs_flip_time=5.0)
        ship_slow_rcs = _make_ship(target=target, rcs_flip_time=30.0)

        ap_fast = RendezvousAutopilot(ship_fast_rcs, target_id="T001")
        ap_slow = RendezvousAutopilot(ship_slow_rcs, target_id="T001")

        d_fast = ap_fast._corrected_braking_distance(closing_speed, a_max_val)
        d_slow = ap_slow._corrected_braking_distance(closing_speed, a_max_val)

        assert d_slow > d_fast, (
            "Slower RCS should require a larger braking trigger distance"
        )


# ---------------------------------------------------------------------------
# Phase transitions
# ---------------------------------------------------------------------------

class TestPhaseTransitions:
    def test_initial_phase_is_burn(self):
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(target=target)
        ap = RendezvousAutopilot(ship, target_id="T001")
        assert ap.phase == "burn"

    def test_burn_to_flip_when_inside_trigger(self):
        """Ship in burn phase transitions to flip when range <= d_trigger.

        Ship at origin, target at x=1000 m, ship velocity x=200 m/s
        (closing at 200 m/s). With a_max=5 m/s² and flip_time=10 s:
            naive d_brake = 200²/(2*5) = 4000 m
            flip_coast = 200 * 10 * 1.5 = 3000 m   (balanced flip_safety=1.5)
            corrected = 4000*1.3 + 3000 = 8200 m    (balanced brake_margin=1.3)
        range = 1000 m < 8200 m → trigger fires immediately.
        """
        target = _make_target({"x": 1000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 200.0, "y": 0.0, "z": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "burn"

        ap.compute(0.1, 0.0)

        assert ap.phase == "flip", (
            f"Expected flip phase, got {ap.phase!r}"
        )

    def test_flip_to_brake_when_retrograde_aligned(self):
        """Ship flips to brake when heading is within FLIP_TOLERANCE_DEG of retrograde.

        Ship approaching target along +X at 50 m/s. Target velocity = 0.
        rel_vel = target_vel - ship_vel = {-50, 0, 0}.
        Retrograde heading points along +rel_vel i.e. along {-50,0,0}.
        vector_to_heading({-50,0,0}) gives yaw ≈ 180°.
        We set ship orientation to yaw=178° (within 10° tolerance).

        Target at 10 km (> STATIONKEEP_RANGE=5 km) so the early stationkeep
        shortcut does not fire before we can check the flip->brake transition.
        """
        target = _make_target({"x": 10000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 50.0, "y": 0.0, "z": 0.0},
            orientation={"pitch": 0.0, "yaw": 178.0, "roll": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "flip"

        ap.compute(0.1, 0.0)

        assert ap.phase == "brake", (
            f"Expected brake phase after retrograde alignment, got {ap.phase!r}"
        )

    def test_brake_to_approach_when_closing_speed_lost(self):
        """Brake phase exits to approach when speed drops to zero, regardless of range.

        BRAKE never re-enters BURN -- the old path caused oscillation.
        """
        target = _make_target({"x": 50000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},  # no relative velocity
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "brake"

        # range=50 km, closing_speed=0 → approach (never re-enters burn)
        ap.compute(0.1, 0.0)

        assert ap.phase == "approach", (
            f"Expected approach (BRAKE never re-enters BURN), got {ap.phase!r}"
        )

    def test_stationkeep_entered_within_range_and_speed(self):
        """Within stationkeep_range and below stationkeep_speed → stationkeep phase."""
        target = _make_target({"x": 50.0, "y": 0.0, "z": 0.0})  # 50 m away
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},  # relative speed ≈ 0
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")

        ap.compute(0.1, 0.0)

        assert ap.phase == "stationkeep"
        assert ap.status == "stationkeeping"


# ---------------------------------------------------------------------------
# get_state telemetry
# ---------------------------------------------------------------------------

class TestGetState:
    def test_get_state_includes_profile_and_phase(self):
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(target=target)
        ap = RendezvousAutopilot(ship, target_id="T001",
                                 params={"profile": "conservative"})

        state = ap.get_state()

        assert state["profile"] == "conservative"
        assert state["phase"] == "burn"

    def test_get_state_includes_flip_time_estimate(self):
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(target=target, rcs_flip_time=12.5)
        ap = RendezvousAutopilot(ship, target_id="T001")

        state = ap.get_state()

        assert "flip_time_estimate" in state
        assert state["flip_time_estimate"] == pytest.approx(12.5)

    def test_get_state_includes_braking_distance(self):
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 100.0, "y": 0.0, "z": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")

        state = ap.get_state()

        assert "braking_distance" in state
        assert state["braking_distance"] >= 0.0

    def test_get_state_without_target_has_status_text(self):
        """get_state gracefully handles missing target."""
        ship = _make_ship()  # sensors return None (no target)
        ap = RendezvousAutopilot(ship, target_id="MISSING")

        state = ap.get_state()

        assert "status_text" in state
        # Either the status_text mentions "lost" or the autopilot status is error
        assert ("lost" in state["status_text"].lower()
                or "error" in state.get("status", ""))


# ---------------------------------------------------------------------------
# Error state
# ---------------------------------------------------------------------------

class TestErrorState:
    def test_no_target_id_sets_error_status(self):
        ship = _make_ship()
        ap = RendezvousAutopilot(ship, target_id=None)
        assert ap.status == "error"
        assert ap.error_message is not None

    def test_compute_returns_none_on_error(self):
        ship = _make_ship()  # sensors return None for any contact
        ap = RendezvousAutopilot(ship, target_id="GHOST")
        result = ap.compute(0.1, 0.0)
        assert result is None


# ---------------------------------------------------------------------------
# Approach phase — new tests for the BRAKE→APPROACH intermediate phase
# ---------------------------------------------------------------------------
#
# The approach phase is inserted between BRAKE and stationkeep to prevent
# the oscillation where aggressive profile ships bounce between BURN and BRAKE
# without converging at close range.
#
# Expected behaviour after implementation:
#   - Each NAV_PROFILE gains an "approach_range" key (m).
#   - When in BRAKE with closing_speed ≈ 0 and range inside approach_range but
#     outside stationkeep_range → enter APPROACH (not BURN).
#   - In APPROACH, thrust is proportional to remaining distance.
#   - APPROACH → stationkeep when range ≤ 100 m and rel_speed < 1.0 m/s.
#   - Aggressive profile still behaves correctly from ~5 km out (converges).
# ---------------------------------------------------------------------------


class TestApproachPhaseStructure:
    """Verify the approach phase exists and profiles declare approach_range."""

    def test_approach_phase_exists(self):
        """Autopilot must be able to hold phase="approach" without error.

        After implementation the phase string "approach" is a first-class
        phase.  We force it here and confirm compute() does not crash.
        """
        target = _make_target({"x": 3000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "approach"

        # Must not raise; result may be a dict or None — just no exception
        try:
            result = ap.compute(0.1, 0.0)
        except Exception as exc:
            pytest.fail(
                f"compute() raised {type(exc).__name__} in 'approach' phase: {exc}"
            )

    def test_aggressive_profile_has_approach_range(self):
        """NAV_PROFILES['aggressive'] must declare 'approach_range' after implementation."""
        assert "approach_range" in NAV_PROFILES["aggressive"], (
            "NAV_PROFILES['aggressive'] missing 'approach_range' key"
        )

    def test_all_profiles_have_approach_range(self):
        """Every profile must declare 'approach_range' (an integer/float in metres)."""
        for profile_name, profile_data in NAV_PROFILES.items():
            assert "approach_range" in profile_data, (
                f"NAV_PROFILES[{profile_name!r}] missing 'approach_range' key"
            )
            value = profile_data["approach_range"]
            assert isinstance(value, (int, float)), (
                f"NAV_PROFILES[{profile_name!r}]['approach_range'] must be numeric, "
                f"got {type(value).__name__}"
            )
            assert value > 0, (
                f"NAV_PROFILES[{profile_name!r}]['approach_range'] must be positive"
            )

    def test_approach_range_ordering_conservative_ge_aggressive(self):
        """Conservative approach_range >= aggressive.

        High-G aggressive profiles brake so quickly that they need less
        approach range.  Conservative profiles use gentler thrust and
        need more distance for the P-controller to converge.
        """
        agg = NAV_PROFILES["aggressive"]["approach_range"]
        con = NAV_PROFILES["conservative"]["approach_range"]
        assert con >= agg, (
            f"Conservative approach_range ({con}) should be >= aggressive ({agg})"
        )


# ---------------------------------------------------------------------------
# Phase transitions involving APPROACH
# ---------------------------------------------------------------------------


class TestApproachPhaseTransitions:
    """Test the BRAKE → APPROACH and APPROACH → stationkeep transitions."""

    def _make_close_slow_ship_and_ap(self, range_m: float, profile: str = "balanced"):
        """Return (ship, ap) where ship is range_m from target with ~0 closing speed."""
        target = _make_target({"x": range_m, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            # Slightly drifting AWAY so closing_speed <= 0 triggers BRAKE exit
            velocity={"x": -0.05, "y": 0.0, "z": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001",
                                 params={"profile": profile})
        ap.phase = "brake"
        return ship, ap

    def test_brake_to_approach_when_inside_approach_range(self):
        """In BRAKE, closing_speed ≈ 0, range inside approach_range but outside
        stationkeep_range → should transition to APPROACH, not BURN.

        Uses balanced profile with approach_range=5000 m and a range of 3000 m.
        closing_speed ≈ 0 so the old code would transition to BURN, but the
        new code recognises we are inside approach_range and uses APPROACH instead.
        """
        approach_range = NAV_PROFILES["balanced"].get("approach_range", 5000)
        stationkeep_range = 100.0  # RendezvousAutopilot.STATIONKEEP_RANGE

        # Place ship inside approach_range but comfortably outside stationkeep
        test_range = (approach_range + stationkeep_range) / 2.0
        _, ap = self._make_close_slow_ship_and_ap(test_range, profile="balanced")

        ap.compute(0.1, 0.0)

        assert ap.phase == "approach", (
            f"Expected 'approach' phase at {test_range:.0f} m with closing_speed≈0, "
            f"got {ap.phase!r}"
        )

    def test_brake_to_approach_when_far_outside_approach_range(self):
        """In BRAKE, closing_speed ~ 0, range > approach_range -> APPROACH.

        BRAKE always exits to APPROACH (never back to BURN) to prevent
        the BURN->FLIP->BRAKE->BURN oscillation.  The APPROACH phase's
        proportional controller handles convergence from any distance.
        """
        approach_range = NAV_PROFILES["balanced"].get("approach_range", 50000)
        far_range = approach_range * 3.0  # well outside approach funnel

        _, ap = self._make_close_slow_ship_and_ap(far_range, profile="balanced")

        ap.compute(0.1, 0.0)

        assert ap.phase == "approach", (
            f"Expected 'approach' at {far_range:.0f} m (BRAKE never re-enters BURN), "
            f"got {ap.phase!r}"
        )

    def test_approach_to_stationkeep_when_range_and_speed_met(self):
        """From APPROACH phase, range ≤ 100 m and rel_speed < 1.0 m/s → stationkeep."""
        stationkeep_range = RendezvousAutopilot.STATIONKEEP_RANGE   # 100 m
        stationkeep_speed = RendezvousAutopilot.STATIONKEEP_SPEED   # 1.0 m/s

        target = _make_target({"x": 50.0, "y": 0.0, "z": 0.0})   # 50 m, inside range
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},   # matched velocity
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "approach"

        ap.compute(0.1, 0.0)

        assert ap.phase == "stationkeep", (
            f"Expected 'stationkeep' at {stationkeep_range/2:.0f} m with zero rel_speed, "
            f"got {ap.phase!r}"
        )
        assert ap.status == "stationkeeping"

    def test_approach_does_not_jump_to_stationkeep_when_too_fast(self):
        """APPROACH phase does NOT transition to stationkeep if rel_speed >= stationkeep_speed.

        Ship is inside stationkeep_range (5000 m) but still moving at 60 m/s
        toward the target — above the 50 m/s STATIONKEEP_SPEED threshold.
        Should stay in approach until speed bleeds off.
        """
        stationkeep_range = RendezvousAutopilot.STATIONKEEP_RANGE   # 5000 m
        stationkeep_speed = RendezvousAutopilot.STATIONKEEP_SPEED   # 50 m/s
        # Place ship inside stationkeep_range but closing faster than the speed limit
        target = _make_target({"x": 2000.0, "y": 0.0, "z": 0.0})   # 2000 m — inside 5 km range
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 60.0, "y": 0.0, "z": 0.0},   # 60 m/s — above 50 m/s speed limit
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "approach"

        ap.compute(0.1, 0.0)

        # Must NOT be stationkeep yet — speed is above STATIONKEEP_SPEED
        assert ap.phase != "stationkeep", (
            f"Should not enter stationkeep when closing at 60 m/s "
            f"(STATIONKEEP_SPEED={stationkeep_speed} m/s)"
        )

    def test_approach_does_not_transition_to_stationkeep_when_too_far(self):
        """APPROACH phase stays in approach when range > stationkeep_range, even at low speed.

        STATIONKEEP_RANGE is 5000 m.  A ship at 8000 m is outside that threshold
        so stationkeep must not be entered even with near-zero relative speed.
        """
        stationkeep_range = RendezvousAutopilot.STATIONKEEP_RANGE   # 5000 m

        # Use a range clearly outside STATIONKEEP_RANGE
        test_range = stationkeep_range * 1.6   # 8000 m — outside the 5 km handoff range
        target = _make_target({"x": test_range, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "approach"

        ap.compute(0.1, 0.0)

        assert ap.phase != "stationkeep", (
            f"Should not stationkeep at {test_range:.0f} m — "
            f"still outside STATIONKEEP_RANGE ({stationkeep_range:.0f} m)"
        )


# ---------------------------------------------------------------------------
# Approach phase thrust behaviour
# ---------------------------------------------------------------------------


class TestApproachThrustBehaviour:
    """Verify the thrust characteristics produced during APPROACH phase."""

    def _ap_in_approach(self, range_m: float, profile: str = "balanced"):
        """Return autopilot forced into approach phase at given range from target."""
        target = _make_target({"x": range_m, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001",
                                 params={"profile": profile})
        ap.phase = "approach"
        return ap

    def test_approach_produces_nonzero_thrust_toward_target(self):
        """Approach phase commands positive thrust (ship needs to close distance).

        Use a range well outside STATIONKEEP_RANGE (5000 m) so the approach
        P-controller is active and not immediately handed off to MatchVelocity.
        """
        ap = self._ap_in_approach(range_m=10000.0)

        result = ap.compute(0.1, 0.0)

        assert result is not None, "compute() should return a command dict in approach phase"
        assert result.get("thrust", 0.0) > 0.0, (
            "Approach phase must command positive thrust to close distance"
        )

    def test_approach_thrust_proportional_closer_range_gives_less_thrust(self):
        """Proportional thrust: a ship at 10 km should use less thrust than at 40 km.

        This is the core property that prevents oscillation — thrust tapers
        as the ship converges so it does not overshoot into another burn cycle.

        Both ranges are outside STATIONKEEP_RANGE (5000 m).  We use a very
        large approach_range override (5000 km) to keep both ranges well below
        the P-controller saturation point, so the proportional relationship
        is visible in the thrust values rather than being masked by the cap.
        """
        def _ap_with_large_approach_range(range_m):
            target = _make_target({"x": range_m, "y": 0.0, "z": 0.0})
            ship = _make_ship(
                position={"x": 0.0, "y": 0.0, "z": 0.0},
                velocity={"x": 0.0, "y": 0.0, "z": 0.0},
                target=target,
            )
            # Large approach_range keeps desired_closing below the saturation
            # threshold so the proportional control law is directly observable.
            ap = RendezvousAutopilot(
                ship, target_id="T001",
                params={"profile": "balanced", "approach_range": 5_000_000.0},
            )
            ap.phase = "approach"
            return ap

        ap_far = _ap_with_large_approach_range(range_m=40000.0)
        ap_near = _ap_with_large_approach_range(range_m=10000.0)

        result_far = ap_far.compute(0.1, 0.0)
        result_near = ap_near.compute(0.1, 0.0)

        assert result_far is not None and result_near is not None
        thrust_far = result_far.get("thrust", 0.0)
        thrust_near = result_near.get("thrust", 0.0)

        assert thrust_far > thrust_near, (
            f"Expected lower thrust at close range: far={thrust_far:.4f}, "
            f"near={thrust_near:.4f}"
        )

    def test_approach_thrust_capped_below_max_thrust(self):
        """Approach thrust must be strictly below the profile max_thrust.

        The approach phase is intentionally gentler than the main burn phase.
        This cap prevents the approach from degenerating into another full burn.
        """
        ap = self._ap_in_approach(range_m=4900.0, profile="aggressive")

        result = ap.compute(0.1, 0.0)

        assert result is not None
        thrust = result.get("thrust", 0.0)
        profile_max = NAV_PROFILES["aggressive"]["max_thrust"]

        assert thrust < profile_max, (
            f"Approach thrust {thrust:.4f} must be capped below profile max_thrust "
            f"{profile_max:.4f}"
        )

    def test_approach_thrust_never_exceeds_1(self):
        """Thrust value from approach phase must be in [0, 1] (physics limit)."""
        ap = self._ap_in_approach(range_m=2000.0)

        result = ap.compute(0.1, 0.0)

        assert result is not None
        thrust = result.get("thrust", 0.0)
        assert 0.0 <= thrust <= 1.0, (
            f"Thrust {thrust:.4f} is outside valid [0, 1] range"
        )

    def test_approach_heading_points_toward_target(self):
        """Approach phase heading should direct the ship toward the target.

        Target is directly on the +X axis, so yaw should be near 0°.
        """
        target = _make_target({"x": 2000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "approach"

        result = ap.compute(0.1, 0.0)

        assert result is not None
        assert "heading" in result, "Approach compute() must return a heading"
        yaw = result["heading"].get("yaw", None)
        assert yaw is not None
        # Target is at +X; yaw=0 is straight ahead along +X in atan2(y,x) convention
        assert abs(yaw) < 10.0, (
            f"Approach heading yaw {yaw:.1f}° should point toward +X target (≈0°)"
        )


# ---------------------------------------------------------------------------
# Telemetry — get_state() and status text for approach phase
# ---------------------------------------------------------------------------


class TestApproachTelemetry:
    """Verify get_state() and status text correctly reflect approach phase."""

    def test_approach_phase_in_get_state(self):
        """get_state() must report phase='approach' when autopilot is in that phase."""
        target = _make_target({"x": 3000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "approach"

        state = ap.get_state()

        assert state.get("phase") == "approach", (
            f"get_state() returned phase={state.get('phase')!r}, expected 'approach'"
        )

    def test_approach_status_text_is_informative(self):
        """Status text for approach phase must not be empty and must not be one
        of the other phases' default strings.

        The text must convey that the ship is approaching (not burning, flipping,
        or braking in the full-deceleration sense), e.g. 'Approaching...' or
        'Final approach'.
        """
        target = _make_target({"x": 2500.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "approach"

        state = ap.get_state()

        status_text = state.get("status_text", "")
        assert status_text, "status_text must not be empty in approach phase"

        # Must not silently fall through to burn/flip/brake/stationkeep strings
        forbidden_prefixes = (
            "Burning toward",
            "Flipping for",
            "Braking --",
            "Station-keeping",
        )
        for prefix in forbidden_prefixes:
            assert not status_text.startswith(prefix), (
                f"status_text {status_text!r} looks like a different phase. "
                f"'approach' needs its own distinct text."
            )

    def test_approach_status_field_set_during_approach(self):
        """ap.status attribute should reflect approach activity (not 'braking' or 'burning')."""
        target = _make_target({"x": 3000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "approach"
        ap.compute(0.1, 0.0)

        assert ap.status not in ("braking", "burning", "flipping", "error"), (
            f"ap.status {ap.status!r} should not be a different phase's value "
            f"while in approach phase"
        )


# ---------------------------------------------------------------------------
# Convergence simulation — aggressive profile must not oscillate
# ---------------------------------------------------------------------------


class TestAggressiveConvergence:
    """Multi-tick simulation verifying the approach phase prevents oscillation.

    The aggressive profile previously bounced between BURN and BRAKE when
    closing from ~5 km because the brake trigger distance kept firing.  The
    approach phase must allow the ship to converge to stationkeep within a
    bounded number of ticks.
    """

    def _run_sim(self, profile: str, start_range_m: float,
                 max_ticks: int = 2000, dt: float = 1.0):
        """Simulate the autopilot for up to max_ticks ticks.

        Each tick:
          1. compute() returns {thrust, heading}.
          2. We integrate thrust along the ship-to-target axis (1D model).
          3. Update ship position and velocity.

        Returns:
            dict with keys: final_phase, ticks_taken, oscillation_count,
                            converged (bool), final_range_m, phase_history.
        """
        import math as _math

        target_pos_x = start_range_m

        # Ship starts at origin, no initial velocity
        ship_pos_x = 0.0
        ship_vel_x = 0.0

        target = _make_target({"x": target_pos_x, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": ship_pos_x, "y": 0.0, "z": 0.0},
            velocity={"x": ship_vel_x, "y": 0.0, "z": 0.0},
            target=target,
            mass=10000.0,
            max_thrust=50000.0,   # 5 m/s² max accel
        )
        ap = RendezvousAutopilot(ship, target_id="T001",
                                 params={"profile": profile})

        a_max = 50000.0 / 10000.0  # 5 m/s²

        phase_history = []
        oscillation_count = 0
        prev_phase = ap.phase
        sim_time = 0.0

        for tick in range(max_ticks):
            # Sync mock ship state with simulation state
            ship.position = {"x": ship_pos_x, "y": 0.0, "z": 0.0}
            ship.velocity = {"x": ship_vel_x, "y": 0.0, "z": 0.0}

            result = ap.compute(dt, sim_time)
            sim_time += dt

            phase_history.append(ap.phase)

            # Count burn↔brake oscillations (the bug we are fixing)
            if ap.phase != prev_phase:
                if (prev_phase in ("burn", "brake") and
                        ap.phase in ("burn", "brake")):
                    oscillation_count += 1
            prev_phase = ap.phase

            if ap.phase == "stationkeep":
                return {
                    "final_phase": ap.phase,
                    "ticks_taken": tick + 1,
                    "oscillation_count": oscillation_count,
                    "converged": True,
                    "final_range_m": abs(target_pos_x - ship_pos_x),
                    "phase_history": phase_history,
                }

            if result is None:
                break

            # 1-D physics integration along X axis (ship vs stationary target)
            thrust_fraction = result.get("thrust", 0.0)
            heading = result.get("heading", {})
            commanded_yaw = heading.get("yaw", 0.0)

            # Simulate RCS rotation: move ship orientation toward commanded
            # heading at ~18 deg/s (180° flip in ~10s)
            current_yaw = ship.orientation.get("yaw", 0.0)
            yaw_err = commanded_yaw - current_yaw
            # Normalize to [-180, 180]
            while yaw_err > 180:
                yaw_err -= 360
            while yaw_err < -180:
                yaw_err += 360
            max_rot = 18.0 * dt  # deg per tick
            if abs(yaw_err) <= max_rot:
                current_yaw = commanded_yaw
            else:
                current_yaw += max_rot * (1 if yaw_err > 0 else -1)
            ship.orientation = {"pitch": 0.0, "yaw": current_yaw, "roll": 0.0}

            # Use ACTUAL ship orientation for thrust direction (not commanded)
            cos_yaw = _math.cos(_math.radians(current_yaw))

            accel = thrust_fraction * a_max * cos_yaw
            ship_vel_x += accel * dt
            ship_pos_x += ship_vel_x * dt

        return {
            "final_phase": ap.phase,
            "ticks_taken": max_ticks,
            "oscillation_count": oscillation_count,
            "converged": False,
            "final_range_m": abs(target_pos_x - ship_pos_x),
            "phase_history": phase_history,
        }

    def test_aggressive_convergence_from_5km(self):
        """Aggressive profile must converge to stationkeep from 5 km within 2000 s
        (1-second ticks) and must not oscillate more than once between burn and brake.

        This is the core regression test.  Before the approach phase, the
        aggressive profile would oscillate indefinitely between BURN and BRAKE
        at ~5 km range and never reach stationkeep.
        """
        result = self._run_sim(
            profile="aggressive",
            start_range_m=5000.0,
            max_ticks=2000,
            dt=1.0,
        )

        assert result["converged"], (
            f"Aggressive profile did NOT converge from 5 km in 2000 ticks. "
            f"Final phase: {result['final_phase']!r}, "
            f"final range: {result['final_range_m']:.1f} m, "
            f"oscillations: {result['oscillation_count']}"
        )

        assert result["oscillation_count"] <= 1, (
            f"Aggressive profile oscillated {result['oscillation_count']} times "
            f"between burn/brake — approach phase should prevent this. "
            f"Phase sequence (last 30): {result['phase_history'][-30:]}"
        )

    def test_balanced_enters_approach_phase(self):
        """Balanced profile enters the approach phase from 100 km, confirming
        it doesn't get stuck in a burn/brake oscillation.

        STATIONKEEP_RANGE is 5000 m.  Starting at 100 km ensures the ship
        has braked to < 150 m/s while still well outside the 5 km stationkeep
        handoff, so BRAKE exits to APPROACH rather than directly to stationkeep.

        The 1D convergence sim can't fully simulate balanced convergence
        (RCS rotation + low proportional thrust = slow settling), but we
        verify the approach phase is reached and the ship makes progress.
        """
        result = self._run_sim(
            profile="balanced",
            start_range_m=100_000.0,
            max_ticks=5000,
            dt=1.0,
        )

        assert "approach" in result["phase_history"], (
            "Balanced profile never entered 'approach' phase. "
            f"Phases seen: {sorted(set(result['phase_history']))}"
        )

        # Ship should make significant progress — well under the start range
        assert result["final_range_m"] < 50_000.0, (
            f"Balanced profile made no progress: final range {result['final_range_m']:.0f} m "
            f"from start of 100 km"
        )

    def test_approach_phase_appears_in_phase_history(self):
        """The 'approach' phase string must appear in phase history during convergence
        from a range large enough that BRAKE exits to APPROACH rather than stationkeep.

        STATIONKEEP_RANGE is 5000 m.  At 400 km with aggressive profile, the ship
        builds substantial speed, brakes hard, but still has > 5 km range when
        rel_speed drops below the brake_done_speed threshold — so BRAKE correctly
        exits to APPROACH.  Using 0.5 s ticks for better RCS rotation resolution.
        """
        result = self._run_sim(
            profile="aggressive",
            start_range_m=400_000.0,
            max_ticks=10000,
            dt=0.5,
        )

        assert "approach" in result["phase_history"], (
            "Phase history did not contain 'approach' — the phase was never entered. "
            f"Distinct phases seen: {sorted(set(result['phase_history']))}"
        )

    def test_long_range_convergence_balanced(self):
        """Balanced profile must converge from 400 km (Mission 1 distances).

        This is the primary regression test for the oscillation bug where the
        autopilot cycled BURN->FLIP->BRAKE->BURN indefinitely at long range.
        The fix uses rel_speed for BRAKE exit and snapshot headings for FLIP.

        Uses dt=0.5 for better RCS rotation resolution during the approach
        phase (the ship must rotate from retrograde back to prograde after
        braking, and coarse 1s ticks make this sluggish).
        """
        result = self._run_sim(
            profile="balanced",
            start_range_m=400_000.0,
            max_ticks=30000,
            dt=0.5,
        )

        assert result["converged"], (
            f"Balanced profile did NOT converge from 400 km in 15000 sim-seconds. "
            f"Final phase: {result['final_phase']!r}, "
            f"final range: {result['final_range_m']:.1f} m, "
            f"oscillations: {result['oscillation_count']}"
        )

        # Should converge in at most 2 burn-brake cycles (one main
        # deceleration plus possibly one correction).  The old bug
        # caused 10+ oscillations.
        assert result["oscillation_count"] <= 2, (
            f"Balanced profile oscillated {result['oscillation_count']} times "
            f"between burn/brake from 400 km -- should be at most 2. "
            f"Phase sequence (last 40): {result['phase_history'][-40:]}"
        )

    def test_long_range_convergence_aggressive(self):
        """Aggressive profile must converge from 400 km without excessive oscillation."""
        result = self._run_sim(
            profile="aggressive",
            start_range_m=400_000.0,
            max_ticks=30000,
            dt=0.5,
        )

        assert result["converged"], (
            f"Aggressive profile did NOT converge from 400 km in 15000 sim-seconds. "
            f"Final phase: {result['final_phase']!r}, "
            f"final range: {result['final_range_m']:.1f} m, "
            f"oscillations: {result['oscillation_count']}"
        )

        assert result["oscillation_count"] <= 2, (
            f"Aggressive profile oscillated {result['oscillation_count']} times "
            f"from 400 km -- should be at most 2."
        )


# ---------------------------------------------------------------------------
# FLIP snapshot heading -- regression tests for the flip timeout bug
# ---------------------------------------------------------------------------


class TestFlipSnapshotHeading:
    """Verify that FLIP uses a snapshot heading instead of live retrograde.

    The old code recomputed retrograde heading each tick during flip.  If the
    ship had lateral velocity, the retrograde direction shifted as it coasted,
    and the RCS chased a moving target.  This caused ~50% of flips to time out.
    """

    def test_flip_stores_snapshot_heading(self):
        """When transitioning BURN->FLIP, the autopilot must store
        _flip_target_heading as a snapshot of the retrograde heading."""
        target = _make_target({"x": 1000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 200.0, "y": 10.0, "z": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "burn"

        assert ap._flip_target_heading is None

        ap.compute(0.1, 0.0)

        # Should have transitioned to flip and stored the heading
        assert ap.phase == "flip"
        assert ap._flip_target_heading is not None
        assert "yaw" in ap._flip_target_heading

    def test_flip_heading_does_not_change_during_coast(self):
        """Once in FLIP, the snapshot heading must not change even if the
        ship's velocity vector shifts (simulating lateral drift during coast)."""
        target = _make_target({"x": 10000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 50.0, "y": 5.0, "z": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "burn"

        # Force into flip
        ap.compute(0.1, 0.0)
        if ap.phase != "flip":
            ap.phase = "flip"
            ap._flip_target_heading = {"yaw": 170.0, "pitch": 0.0, "roll": 0.0}

        snapshot = dict(ap._flip_target_heading)

        # Simulate drift: change ship velocity to alter retrograde direction
        ship.velocity = {"x": 50.0, "y": 30.0, "z": 0.0}
        ap.compute(0.1, 1.0)

        # Snapshot must be unchanged
        assert ap._flip_target_heading == snapshot, (
            f"Flip heading changed during coast: was {snapshot}, "
            f"now {ap._flip_target_heading}"
        )

    def test_flip_snapshot_cleared_on_brake_entry(self):
        """The snapshot heading should be cleared when transitioning to BRAKE.

        Target at 10 km (> STATIONKEEP_RANGE=5 km) to prevent the early
        stationkeep shortcut from firing before the flip->brake transition.
        """
        target = _make_target({"x": 10000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 50.0, "y": 0.0, "z": 0.0},
            # Ship already facing retrograde
            orientation={"pitch": 0.0, "yaw": 180.0, "roll": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "flip"
        ap._flip_target_heading = {"yaw": 180.0, "pitch": 0.0, "roll": 0.0}
        ap._flip_entered_time = 0.0

        ap.compute(0.1, 1.0)

        assert ap.phase == "brake"
        assert ap._flip_target_heading is None


# ---------------------------------------------------------------------------
# BRAKE exit uses rel_speed not clamped closing_speed
# ---------------------------------------------------------------------------


class TestBrakeRelSpeedThreshold:
    """Verify BRAKE phase uses rel_speed (full velocity magnitude) for exit,
    not just the radial closing_speed which was clamped to 0 when opening.

    The old bug: ship decelerates from 2000 m/s to 0 closing speed.  The
    range_rate flips slightly positive (ship starts drifting away).  The old
    code clamped closing_speed to 0 and immediately exited BRAKE, even though
    the ship still had massive velocity in the lateral component.
    """

    def test_brake_stays_when_high_rel_speed(self):
        """BRAKE must NOT exit when closing_speed is near zero but rel_speed
        is still high (e.g. ship has lateral velocity above brake_done_speed).

        brake_done_speed = APPROACH_SPEED_LIMIT (500) * factor (0.5) = 250 m/s.
        A ship with 400 m/s lateral velocity must stay in BRAKE.
        """
        target = _make_target({"x": 20000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            # Mostly lateral velocity: closing_speed ~ 0 but rel_speed = 400 m/s
            velocity={"x": 0.5, "y": 400.0, "z": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "brake"

        ap.compute(0.1, 0.0)

        # Should stay in brake because rel_speed (400 m/s) exceeds
        # brake_done_speed (250 m/s)
        assert ap.phase == "brake", (
            f"Expected to stay in brake with high lateral velocity, "
            f"got {ap.phase!r}"
        )

    def test_brake_exits_when_rel_speed_is_low(self):
        """BRAKE exits to APPROACH when rel_speed drops below threshold.

        BRAKE always exits to APPROACH regardless of range -- the old
        BRAKE->BURN path caused oscillation at ~300km.
        """
        target = _make_target({"x": 20000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            # Very low velocity in all components
            velocity={"x": -0.1, "y": 0.5, "z": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "brake"

        ap.compute(0.1, 0.0)

        # rel_speed ~ 0.5 m/s, well below threshold (250 m/s)
        # range 20km -- BRAKE always exits to APPROACH now
        assert ap.phase == "approach", (
            f"Expected BRAKE->APPROACH with low rel_speed at long range, "
            f"got {ap.phase!r}"
        )


# ---------------------------------------------------------------------------
# Alignment guard -- regression test for the BRAKE->APPROACH retrograde
# thrust bug.  After braking the ship is pointed retrograde.  APPROACH
# commands prograde thrust.  Without the guard the main drive fires
# retrograde for ~9 seconds (during RCS rotation), pushing the ship
# AWAY from the target and triggering APPROACH->BURN re-entry.
# ---------------------------------------------------------------------------


class TestAlignmentGuard:
    """The alignment guard must zero thrust when the ship's orientation
    is significantly misaligned with the commanded heading."""

    def test_heading_error_zero_when_aligned(self):
        """_heading_error returns ~0 when ship faces the commanded heading."""
        target = _make_target({"x": 10000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            orientation={"pitch": 0.0, "yaw": 45.0, "roll": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")

        err = ap._heading_error({"yaw": 45.0, "pitch": 0.0})
        assert err == pytest.approx(0.0, abs=0.01)

    def test_heading_error_yaw_only(self):
        """_heading_error detects yaw misalignment."""
        target = _make_target({"x": 10000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            orientation={"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")

        err = ap._heading_error({"yaw": 90.0, "pitch": 0.0})
        assert err == pytest.approx(90.0, abs=0.01)

    def test_heading_error_wraps_around_180(self):
        """_heading_error correctly handles the -180/+180 boundary."""
        target = _make_target({"x": 10000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            orientation={"pitch": 0.0, "yaw": 170.0, "roll": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")

        # 170 -> -170 is 20 degrees, not 340
        err = ap._heading_error({"yaw": -170.0, "pitch": 0.0})
        assert err == pytest.approx(20.0, abs=0.01)

    def test_heading_error_none_heading_returns_zero(self):
        """_heading_error returns 0 when desired_heading is None."""
        target = _make_target({"x": 10000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(target=target)
        ap = RendezvousAutopilot(ship, target_id="T001")

        assert ap._heading_error(None) == 0.0

    def test_burn_thrust_near_zero_when_misaligned(self):
        """In BURN phase, if ship faces away from target (90 deg error),
        thrust must be near zero (cosine scaling: cos(90°) ≈ 0).

        Ship at origin, target at +X, ship facing +Y (yaw=90).
        BURN wants to thrust toward +X (yaw~0).  At 90° the cosine
        alignment guard scales thrust to effectively zero.
        """
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            orientation={"pitch": 0.0, "yaw": 90.0, "roll": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "burn"

        result = ap.compute(0.1, 0.0)

        assert result is not None
        assert result["thrust"] < 0.01, (
            f"Thrust should be near zero when 90° misaligned, got {result['thrust']}"
        )
        # Heading must still be commanded so the RCS rotates the ship
        assert "heading" in result

    def test_burn_thrust_allowed_when_aligned(self):
        """In BURN phase, if ship is roughly aligned (<30 deg error),
        thrust must be positive.

        Ship at origin, target at +X, ship facing ~+X (yaw=10).
        10 deg error < 30 deg threshold, so thrust should be > 0.
        """
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            orientation={"pitch": 0.0, "yaw": 10.0, "roll": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "burn"

        result = ap.compute(0.1, 0.0)

        assert result is not None
        assert result["thrust"] > 0.0, (
            f"Thrust should be positive when only 10° misaligned, "
            f"got {result['thrust']}"
        )

    def test_brake_thrust_zeroed_when_misaligned(self):
        """In BRAKE phase, thrust is zeroed when ship orientation is far
        from the retrograde heading.

        Ship closing on target along +X at 500 m/s.  Retrograde heading
        is ~yaw=180.  Ship currently facing yaw=0 (prograde).  180 deg
        error >> 30 deg threshold, so thrust must be 0.
        """
        target = _make_target({"x": 50000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 500.0, "y": 0.0, "z": 0.0},
            orientation={"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "brake"

        result = ap.compute(0.1, 0.0)

        assert result is not None
        assert result["thrust"] == 0.0, (
            f"Brake thrust should be 0 when 180° from retrograde, "
            f"got {result['thrust']}"
        )
        # Heading must still point retrograde so RCS rotates the ship
        assert "heading" in result

    def test_approach_prograde_thrust_zeroed_when_facing_retrograde(self):
        """The primary regression scenario: BRAKE just exited to APPROACH.
        Ship is still facing retrograde (yaw~180) but APPROACH wants to
        thrust prograde (yaw~0) toward the target.  Without the guard
        the main drive fires retrograde, pushing the ship away.

        This is the exact bug from the logs:
          BRAKE -> APPROACH (decelerated to 167.4 m/s)
          APPROACH -> BURN (opening at 594.7 m/s)

        Target at 60 km — beyond the balanced profile approach_range (50 km)
        so the close-range alignment guard exemption does NOT apply.  At close
        range (< approach_range) the guard is intentionally exempt because the
        velocity-matching controller makes frequent small heading corrections and
        the guard would block thrust for ~10 s per correction.  Beyond
        approach_range the guard is still needed to prevent the retrograde-thrust
        bug on BRAKE->APPROACH transition at long range.
        """
        target = _make_target({"x": 60000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            # Low closing speed (just exited BRAKE)
            velocity={"x": 50.0, "y": 0.0, "z": 0.0},
            # Still facing retrograde from the braking maneuver
            orientation={"pitch": 0.0, "yaw": 180.0, "roll": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "approach"

        result = ap.compute(0.1, 0.0)

        assert result is not None
        assert result["thrust"] == 0.0, (
            f"APPROACH must not fire thrust while facing retrograde "
            f"(180° from prograde heading). Got thrust={result['thrust']}. "
            f"This is the BRAKE->APPROACH retrograde thrust bug."
        )

    def test_approach_thrust_restored_after_rotation(self):
        """After the ship has rotated to face the target (within 30 deg),
        APPROACH must resume thrusting."""
        target = _make_target({"x": 50000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 50.0, "y": 0.0, "z": 0.0},
            # Ship has rotated to face roughly toward target
            orientation={"pitch": 0.0, "yaw": 15.0, "roll": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "approach"

        result = ap.compute(0.1, 0.0)

        assert result is not None
        assert result["thrust"] > 0.0, (
            f"APPROACH must thrust when aligned within 30°. "
            f"Got thrust={result['thrust']}"
        )

    def test_flip_phase_not_affected_by_guard(self):
        """FLIP phase already sets thrust=0; the guard must not interfere
        with it or add unexpected side effects.

        Target at 10 km (> STATIONKEEP_RANGE=5 km) to prevent the early
        stationkeep shortcut from intercepting compute() before the flip
        phase handler runs.
        """
        target = _make_target({"x": 10000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 50.0, "y": 0.0, "z": 0.0},
            orientation={"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "flip"
        ap._flip_target_heading = {"yaw": 180.0, "pitch": 0.0, "roll": 0.0}
        ap._flip_entered_time = 0.0

        result = ap.compute(0.1, 1.0)

        assert result is not None
        assert result["thrust"] == 0.0, (
            "FLIP phase must keep thrust=0 regardless of alignment guard"
        )

    def test_guard_at_boundary_30_degrees(self):
        """At exactly the 30-degree threshold boundary, thrust should
        still be allowed (guard triggers ABOVE 30, not at 30)."""
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            orientation={"pitch": 0.0, "yaw": 30.0, "roll": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "burn"

        result = ap.compute(0.1, 0.0)

        assert result is not None
        assert result["thrust"] > 0.0, (
            f"At exactly 30° error, thrust should be allowed (guard is >30, "
            f"not >=30). Got thrust={result['thrust']}"
        )

    def test_guard_at_31_degrees_scales_thrust(self):
        """At 31 degrees, cosine guard scales thrust to ~86% (cos 31°)."""
        target = _make_target({"x": 100000.0, "y": 0.0, "z": 0.0})
        ship = _make_ship(
            position={"x": 0.0, "y": 0.0, "z": 0.0},
            velocity={"x": 0.0, "y": 0.0, "z": 0.0},
            orientation={"pitch": 0.0, "yaw": 31.0, "roll": 0.0},
            target=target,
        )
        ap = RendezvousAutopilot(ship, target_id="T001")
        ap.phase = "burn"

        result = ap.compute(0.1, 0.0)

        assert result is not None
        # cos(31°) ≈ 0.857, so thrust ≈ max_thrust * 0.857
        assert 0 < result["thrust"] < ap.max_thrust, (
            f"At 31° error, cosine guard should scale thrust. "
            f"Got thrust={result['thrust']}"
        )
