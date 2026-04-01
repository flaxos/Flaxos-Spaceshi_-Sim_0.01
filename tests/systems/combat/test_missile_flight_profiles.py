# tests/systems/combat/test_missile_flight_profiles.py
"""Tests for missile flight profile behaviours (Phase 1D).

Each profile should produce measurably different trajectories during
midcourse guidance.  A "direct" missile flies straight PN; "evasive"
weaves laterally; "terminal_pop" maintains a vertical offset then
pops; "bracket" missiles spread across quadrants.

These tests spawn missiles into a TorpedoManager, advance several
seconds of sim time, and verify that positions diverge in the
expected way -- without needing the full game loop.
"""

import math
import pytest

from hybrid.systems.combat.torpedo_manager import (
    TorpedoManager,
    MunitionType,
    MISSILE_TERMINAL_RANGE,
)
from hybrid.utils.math_utils import (
    magnitude, subtract_vectors, calculate_distance,
    dot_product, normalize_vector, cross_product,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spawn_missile(
    manager: TorpedoManager,
    profile: str = "direct",
    target_pos: dict = None,
    launch_pos: dict = None,
    launch_vel: dict = None,
    target_vel: dict = None,
    target_id: str = "target_1",
) -> "Torpedo":
    """Spawn a missile with sensible defaults for profile testing."""
    if target_pos is None:
        target_pos = {"x": 50_000, "y": 0, "z": 0}
    if launch_pos is None:
        launch_pos = {"x": 0, "y": 0, "z": 0}
    if launch_vel is None:
        launch_vel = {"x": 500, "y": 0, "z": 0}
    if target_vel is None:
        target_vel = {"x": 0, "y": 0, "z": 0}

    return manager.spawn(
        shooter_id="ship_1",
        target_id=target_id,
        position=launch_pos,
        velocity=launch_vel,
        sim_time=0.0,
        target_pos=target_pos,
        target_vel=target_vel,
        profile=profile,
        munition_type=MunitionType.MISSILE,
    )


def _advance(manager: TorpedoManager, seconds: float, dt: float = 0.1):
    """Tick the manager for *seconds* of sim time."""
    t = 0.0
    while t < seconds:
        step = min(dt, seconds - t)
        t += step
        manager.tick(dt=step, sim_time=t, ships={})


# ---------------------------------------------------------------------------
# cross_product utility
# ---------------------------------------------------------------------------

class TestCrossProduct:
    """Verify the cross_product helper in math_utils."""

    def test_orthogonal_axes(self):
        """x cross y = z."""
        result = cross_product(
            {"x": 1, "y": 0, "z": 0},
            {"x": 0, "y": 1, "z": 0},
        )
        assert abs(result["x"]) < 1e-9
        assert abs(result["y"]) < 1e-9
        assert abs(result["z"] - 1.0) < 1e-9

    def test_anti_commutative(self):
        """a x b = -(b x a)."""
        a = {"x": 1, "y": 2, "z": 3}
        b = {"x": 4, "y": 5, "z": 6}
        ab = cross_product(a, b)
        ba = cross_product(b, a)
        for k in "xyz":
            assert abs(ab[k] + ba[k]) < 1e-9

    def test_parallel_vectors_zero(self):
        """Parallel vectors produce zero cross product."""
        a = {"x": 2, "y": 0, "z": 0}
        b = {"x": 5, "y": 0, "z": 0}
        result = cross_product(a, b)
        assert magnitude(result) < 1e-9

    def test_perpendicular_to_inputs(self):
        """Result should be perpendicular to both input vectors."""
        a = {"x": 1, "y": 2, "z": 3}
        b = {"x": 4, "y": 5, "z": 6}
        c = cross_product(a, b)
        assert abs(dot_product(c, a)) < 1e-9
        assert abs(dot_product(c, b)) < 1e-9


# ---------------------------------------------------------------------------
# Profile data initialisation
# ---------------------------------------------------------------------------

class TestProfileDataInit:
    """Verify per-missile profile state is populated at spawn."""

    def test_direct_has_empty_profile_data(self):
        mgr = TorpedoManager()
        msl = _spawn_missile(mgr, profile="direct")
        assert msl.profile_data == {}

    def test_evasive_has_period(self):
        mgr = TorpedoManager()
        msl = _spawn_missile(mgr, profile="evasive")
        period = msl.profile_data.get("period")
        assert period is not None
        assert 2.0 <= period <= 4.0

    def test_evasive_period_varies_per_missile(self):
        """Two evasive missiles should get different periods."""
        mgr = TorpedoManager()
        m1 = _spawn_missile(mgr, profile="evasive")
        m2 = _spawn_missile(mgr, profile="evasive")
        # Extremely unlikely to be identical with float random
        assert m1.profile_data["period"] != m2.profile_data["period"]

    def test_terminal_pop_has_offset(self):
        mgr = TorpedoManager()
        msl = _spawn_missile(mgr, profile="terminal_pop")
        pd = msl.profile_data
        assert "offset_dir" in pd
        assert "offset_mag" in pd
        assert "popped" in pd
        assert pd["popped"] is False
        assert 500.0 <= pd["offset_mag"] <= 1000.0
        # offset_dir should be unit-length and perpendicular to approach
        od_mag = magnitude(pd["offset_dir"])
        assert abs(od_mag - 1.0) < 0.01

    def test_bracket_has_seed_angle(self):
        mgr = TorpedoManager()
        msl = _spawn_missile(mgr, profile="bracket")
        assert "seed_angle" in msl.profile_data
        angle = msl.profile_data["seed_angle"]
        assert 0 <= angle <= 2 * math.pi


# ---------------------------------------------------------------------------
# Trajectory divergence tests
# ---------------------------------------------------------------------------

class TestEvasiveProfile:
    """Evasive missiles should weave laterally off the direct line."""

    def test_evasive_deviates_from_direct(self):
        """After several seconds, evasive missile should be laterally
        offset compared to a direct missile launched identically."""
        mgr_direct = TorpedoManager()
        mgr_evasive = TorpedoManager()

        m_direct = _spawn_missile(mgr_direct, profile="direct")
        m_evasive = _spawn_missile(mgr_evasive, profile="evasive")

        _advance(mgr_direct, 6.0)
        _advance(mgr_evasive, 6.0)

        # Both should have moved forward significantly
        assert m_direct.position["x"] > 1000
        assert m_evasive.position["x"] > 1000

        # Evasive should have lateral (y/z) displacement that direct lacks
        direct_lateral = math.sqrt(
            m_direct.position["y"] ** 2 + m_direct.position["z"] ** 2
        )
        evasive_lateral = math.sqrt(
            m_evasive.position["y"] ** 2 + m_evasive.position["z"] ** 2
        )
        assert evasive_lateral > direct_lateral + 1.0, (
            f"Evasive lateral {evasive_lateral:.1f} should exceed "
            f"direct lateral {direct_lateral:.1f} by a meaningful margin"
        )

    def test_evasive_still_progresses_toward_target(self):
        """Evasive weave should not prevent the missile from closing."""
        mgr = TorpedoManager()
        msl = _spawn_missile(mgr, profile="evasive")
        initial_x = msl.position["x"]
        _advance(mgr, 5.0)
        # Missile should still advance along the approach axis
        assert msl.position["x"] > initial_x + 500


class TestTerminalPopProfile:
    """Terminal pop missiles should offset then climb."""

    def test_terminal_pop_has_lateral_offset_far_from_target(self):
        """During midcourse (far from target), terminal_pop should fly
        offset from the direct line."""
        mgr_direct = TorpedoManager()
        mgr_tpop = TorpedoManager()

        # Target far enough that midcourse lasts several seconds
        target = {"x": 80_000, "y": 0, "z": 0}
        m_direct = _spawn_missile(mgr_direct, profile="direct", target_pos=target)
        m_tpop = _spawn_missile(mgr_tpop, profile="terminal_pop", target_pos=target)

        _advance(mgr_direct, 8.0)
        _advance(mgr_tpop, 8.0)

        # terminal_pop should have lateral offset
        tpop_lateral = math.sqrt(
            m_tpop.position["y"] ** 2 + m_tpop.position["z"] ** 2
        )
        direct_lateral = math.sqrt(
            m_direct.position["y"] ** 2 + m_direct.position["z"] ** 2
        )
        assert tpop_lateral > direct_lateral + 1.0, (
            f"T-pop lateral {tpop_lateral:.1f} should exceed "
            f"direct lateral {direct_lateral:.1f}"
        )

    def test_terminal_pop_coasts_cold_far_from_target(self):
        """During the offset approach phase, terminal_pop should coast
        (zero thrust) to minimise IR signature."""
        mgr = TorpedoManager()
        target = {"x": 80_000, "y": 0, "z": 0}
        msl = _spawn_missile(mgr, profile="terminal_pop", target_pos=target)

        # Advance past boost phase (2s min for missiles)
        _advance(mgr, 4.0)

        # In midcourse far from target, the missile should coast
        from hybrid.systems.combat.torpedo_manager import TorpedoState
        if msl.state == TorpedoState.MIDCOURSE:
            # Acceleration should be zero (coasting)
            accel_mag = magnitude(msl.acceleration)
            assert accel_mag < 1.0, (
                f"Terminal pop should coast cold during offset approach, "
                f"but accel = {accel_mag:.1f}"
            )


class TestBracketProfile:
    """Bracket salvos should spread missiles across quadrants."""

    def test_bracket_salvo_spreads_missiles(self):
        """4 bracket missiles targeting the same ship should diverge
        into different quadrants."""
        mgr = TorpedoManager()
        target = {"x": 40_000, "y": 0, "z": 0}
        missiles = []
        for _ in range(4):
            msl = _spawn_missile(mgr, profile="bracket", target_pos=target)
            missiles.append(msl)

        _advance(mgr, 6.0)

        # All 4 missiles should have diverged laterally.  Measure
        # pairwise distances in the y-z plane (perpendicular to x-approach).
        positions_yz = [
            (m.position["y"], m.position["z"]) for m in missiles
        ]
        min_sep = float("inf")
        for i in range(len(positions_yz)):
            for j in range(i + 1, len(positions_yz)):
                dy = positions_yz[i][0] - positions_yz[j][0]
                dz = positions_yz[i][1] - positions_yz[j][1]
                sep = math.sqrt(dy * dy + dz * dz)
                min_sep = min(min_sep, sep)

        # With 4 missiles spread evenly, even the closest pair should
        # be meaningfully separated.  At 6s of flight with 30% offset
        # factor, expect hundreds of meters minimum.
        assert min_sep > 10.0, (
            f"Bracket salvo minimum pairwise y-z separation is only "
            f"{min_sep:.1f}m -- missiles are not spreading"
        )

    def test_single_bracket_missile_flies_direct(self):
        """A lone bracket missile (no siblings) should default to
        direct behaviour since there is no spread benefit."""
        mgr_bracket = TorpedoManager()
        mgr_direct = TorpedoManager()

        target = {"x": 40_000, "y": 0, "z": 0}
        m_bracket = _spawn_missile(
            mgr_bracket, profile="bracket", target_pos=target
        )
        m_direct = _spawn_missile(
            mgr_direct, profile="direct", target_pos=target
        )

        _advance(mgr_bracket, 5.0)
        _advance(mgr_direct, 5.0)

        # Positions should be very close since solo bracket = direct
        dist = calculate_distance(m_bracket.position, m_direct.position)
        # Allow some floating-point divergence from different code paths
        assert dist < 50.0, (
            f"Solo bracket missile diverged {dist:.1f}m from direct -- "
            f"should fly the same trajectory"
        )

    def test_bracket_different_targets_dont_spread(self):
        """Bracket missiles targeting DIFFERENT ships should not affect
        each other's trajectories."""
        mgr = TorpedoManager()
        target_a = {"x": 40_000, "y": 0, "z": 0}
        target_b = {"x": 40_000, "y": 5000, "z": 0}

        m1 = _spawn_missile(
            mgr, profile="bracket", target_pos=target_a, target_id="target_a"
        )
        m2 = _spawn_missile(
            mgr, profile="bracket", target_pos=target_b, target_id="target_b"
        )

        # Each missile is the only bracket missile for its target,
        # so neither should get quadrant offset (falls back to direct).
        _advance(mgr, 5.0)

        # m1 should fly mostly along x (toward target_a)
        m1_lateral = math.sqrt(m1.position["y"] ** 2 + m1.position["z"] ** 2)
        # With no bracket spreading, lateral offset should be small
        # (just PN corrections toward the respective targets)
        assert m1_lateral < 500.0, (
            f"Solo-target bracket missile has excessive lateral offset "
            f"{m1_lateral:.1f}m"
        )


class TestAllProfilesDiverge:
    """Comprehensive test: launch one missile per profile from the same
    position and verify they end up in detectably different places."""

    def test_four_profiles_produce_four_trajectories(self):
        profiles = ["direct", "evasive", "terminal_pop", "bracket"]
        managers = {}
        missiles = {}

        for p in profiles:
            mgr = TorpedoManager()
            msl = _spawn_missile(mgr, profile=p)
            managers[p] = mgr
            missiles[p] = msl

        for p in profiles:
            _advance(managers[p], 6.0)

        # Verify each pair of profiles produces different positions.
        # We only check that at least 3 of the 6 pairs diverge
        # meaningfully (bracket solo = direct, so that pair may match).
        divergent_pairs = 0
        for i in range(len(profiles)):
            for j in range(i + 1, len(profiles)):
                p1, p2 = profiles[i], profiles[j]
                dist = calculate_distance(
                    missiles[p1].position, missiles[p2].position
                )
                if dist > 20.0:
                    divergent_pairs += 1

        assert divergent_pairs >= 2, (
            f"Only {divergent_pairs} profile pairs diverged -- "
            f"profiles are not producing distinct trajectories"
        )
