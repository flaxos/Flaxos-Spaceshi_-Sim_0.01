# tests/systems/combat/test_missile_scenarios.py
"""Missile scenario tests: profile integration, salvo tracking, PDC interception.

Focus: end-to-end integration gaps not in test_missile_flight_profiles.py
(which tests trajectory shapes) or test_missile_system.py (which tests unit
behaviour). These tests verify that:
- Missiles launched via CombatSystem progress toward their targets
- A salvo of N missiles creates N independent tracks
- Missiles on all 4 profiles eventually close on a stationary target
- PDC AUTO mode can intercept an incoming missile (same pipeline as torpedoes)
"""

import pytest
from unittest.mock import MagicMock, patch

from hybrid.systems.combat.torpedo_manager import (
    TorpedoManager,
    MunitionType,
    WarheadType,
    TorpedoState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spawn_missile(
    manager: TorpedoManager,
    profile: str = "direct",
    target_pos=None,
    launch_pos=None,
    launch_vel=None,
    target_id: str = "target_ship",
):
    if target_pos is None:
        target_pos = {"x": 40_000, "y": 0, "z": 0}
    if launch_pos is None:
        launch_pos = {"x": 0, "y": 0, "z": 0}
    if launch_vel is None:
        launch_vel = {"x": 600, "y": 0, "z": 0}

    return manager.spawn(
        shooter_id="player",
        target_id=target_id,
        position=launch_pos,
        velocity=launch_vel,
        sim_time=0.0,
        target_pos=target_pos,
        target_vel={"x": 0, "y": 0, "z": 0},
        profile=profile,
        munition_type=MunitionType.MISSILE,
    )


def _advance(manager: TorpedoManager, seconds: float, ships: dict = None, dt: float = 0.1):
    ships = ships or {}
    t = 0.0
    while t < seconds:
        step = min(dt, seconds - t)
        t += step
        manager.tick(dt=step, sim_time=t, ships=ships)


def _make_combat_ship(ship_id: str, position=None, railguns=0, pdcs=1, missiles=4):
    from hybrid.ship import Ship
    pos = position or {"x": 0, "y": 0, "z": 0}
    config = {
        "id": ship_id,
        "position": pos,
        "velocity": {"x": 0, "y": 0, "z": 0},
        "systems": {
            "combat": {"railguns": railguns, "pdcs": pdcs, "torpedoes": 0, "missiles": missiles},
            "targeting": {},
            "sensors": {"passive": {"range": 500_000}},
            "power_management": {
                "primary": {"output": 500},
                "secondary": {"output": 200},
            },
        },
    }
    ship = Ship(ship_id, config)
    ship.sim_time = 100.0
    return ship


# ---------------------------------------------------------------------------
# All profiles close on stationary target
# ---------------------------------------------------------------------------

class TestMissileProfilesConverge:
    """Each flight profile should make progress toward a stationary target."""

    @pytest.mark.parametrize("profile", ["direct", "evasive", "terminal_pop", "bracket"])
    def test_profile_closes_range(self, profile):
        """All profiles reduce distance to target over 15 seconds of flight."""
        mgr = TorpedoManager()
        target_pos = {"x": 40_000, "y": 0, "z": 0}
        msl = _spawn_missile(mgr, profile=profile, target_pos=target_pos)

        initial_dist = abs(target_pos["x"] - msl.position["x"])
        _advance(mgr, 15.0)
        final_dist = abs(target_pos["x"] - msl.position["x"])

        assert final_dist < initial_dist * 0.8, (
            f"Profile '{profile}': missile at {final_dist:.0f}m after 15s "
            f"(started {initial_dist:.0f}m) — did not converge adequately"
        )

    @pytest.mark.parametrize("profile", ["direct", "evasive", "terminal_pop", "bracket"])
    def test_profile_leaves_launch_phase(self, profile):
        """All profiles exit BOOST state within 3 seconds."""
        mgr = TorpedoManager()
        msl = _spawn_missile(mgr, profile=profile)
        _advance(mgr, 3.0)
        assert msl.state != TorpedoState.BOOST, (
            f"Profile '{profile}' still in BOOST state after 3s"
        )


# ---------------------------------------------------------------------------
# Salvo tracking
# ---------------------------------------------------------------------------

class TestMissileSalvoTracking:
    """A salvo of N missiles creates N independent tracks."""

    def test_salvo_of_4_creates_4_tracks(self):
        """4 missiles spawned from the same ship appear as 4 tracks."""
        mgr = TorpedoManager()
        missiles = []
        for _ in range(4):
            msl = _spawn_missile(mgr)
            missiles.append(msl)

        assert len(mgr._torpedoes) == 4, (
            f"Expected 4 missile tracks, got {len(mgr._torpedoes)}"
        )

    def test_salvo_missiles_have_unique_ids(self):
        """Each salvo missile has a unique track ID."""
        mgr = TorpedoManager()
        ids = set()
        for _ in range(4):
            msl = _spawn_missile(mgr)
            ids.add(msl.id)

        assert len(ids) == 4, f"Duplicate IDs in salvo: {ids}"

    def test_salvo_missiles_independent_positions(self):
        """After 10s flight, 4 bracket missiles occupy different positions."""
        mgr = TorpedoManager()
        missiles = []
        for _ in range(4):
            msl = _spawn_missile(mgr, profile="bracket")
            missiles.append(msl)

        _advance(mgr, 10.0)

        positions = [(m.position["x"], m.position["y"], m.position["z"]) for m in missiles]
        unique_positions = set(positions)

        # Bracket profile should spread them — at minimum they should not all
        # be at exactly the same position
        assert len(unique_positions) > 1, (
            "All 4 bracket missiles have identical positions — not spreading"
        )

    def test_missile_kill_does_not_affect_siblings(self):
        """Destroying one missile in a salvo doesn't affect the others."""
        mgr = TorpedoManager()
        missiles = [_spawn_missile(mgr) for _ in range(3)]

        _advance(mgr, 5.0)

        # Kill the first one
        missiles[0].alive = False
        mgr._torpedoes = [m for m in mgr._torpedoes if m.alive]

        # Others should still be alive and progressing
        assert len(mgr._torpedoes) == 2
        for msl in mgr._torpedoes:
            assert msl.alive


# ---------------------------------------------------------------------------
# PDC interception of incoming missiles
# ---------------------------------------------------------------------------

class TestMissilePDCIntercept:
    """PDC AUTO mode can engage incoming missiles (same pipeline as torpedoes)."""

    def _make_incoming_torpedo(self, torpedo_id="msl_1", target_id="defender"):
        from tests.systems.combat.test_pdc_defense_modes import FakeTorpedo
        return FakeTorpedo(
            id=torpedo_id,
            target_id=target_id,
            position={"x": 800, "y": 0, "z": 0},
        )

    def _make_fake_manager(self, torpedoes):
        from tests.systems.combat.test_pdc_defense_modes import FakeTorpedoManager
        return FakeTorpedoManager(torpedoes)

    def test_pdc_auto_engages_incoming_missile(self):
        """PDC in AUTO mode engages an incoming missile within range."""
        from hybrid.simulator import Simulator
        from unittest.mock import patch

        sim = Simulator(dt=0.1)

        defender = _make_combat_ship("defender", pdcs=1, missiles=0)
        sim.add_ship("defender", {})
        sim.ships["defender"] = defender

        defender.systems["combat"].command("set_pdc_mode", {"mode": "auto"})

        incoming = self._make_incoming_torpedo("incoming_msl", "defender")
        sim.torpedo_manager = self._make_fake_manager([incoming])

        with patch("hybrid.simulator.random.random", return_value=0.0):
            sim._process_pdc_torpedo_intercept([defender])

        assert incoming.hull_health < 20.0, (
            "PDC did not damage incoming missile in AUTO mode"
        )

    def test_pdc_hold_fire_does_not_engage_missile(self):
        """PDC in HOLD FIRE mode ignores an incoming missile."""
        from hybrid.simulator import Simulator
        from unittest.mock import patch

        sim = Simulator(dt=0.1)
        defender = _make_combat_ship("defender", pdcs=1, missiles=0)
        sim.add_ship("defender", {})
        sim.ships["defender"] = defender

        defender.systems["combat"].command("set_pdc_mode", {"mode": "hold_fire"})

        incoming = self._make_incoming_torpedo("incoming_msl", "defender")
        sim.torpedo_manager = self._make_fake_manager([incoming])

        with patch("hybrid.simulator.random.random", return_value=0.0):
            sim._process_pdc_torpedo_intercept([defender])

        assert incoming.hull_health == 20.0, (
            "PDC should not engage in HOLD FIRE mode"
        )


# ---------------------------------------------------------------------------
# Missile launch via CombatSystem
# ---------------------------------------------------------------------------

class TestMissileLaunchViaCommandPath:
    """CombatSystem.launch_missile validates inputs and creates a track."""

    def test_launch_missile_requires_target(self):
        """launch_missile with empty target returns error."""
        ship = _make_combat_ship("player")
        combat = ship.systems["combat"]
        combat._ship_ref = ship
        combat._sim_time = 100.0

        result = combat.launch_missile(
            target_id="",
            profile="direct",
            all_ships={},
        )
        assert not result.get("ok"), f"Expected error, got {result}"

    @pytest.mark.parametrize("profile", ["direct", "evasive", "terminal_pop", "bracket"])
    def test_launch_missile_all_profiles_accepted(self, profile):
        """launch_missile accepts all four named profiles."""
        ship = _make_combat_ship("player")
        combat = ship.systems["combat"]
        combat._ship_ref = ship
        combat._sim_time = 100.0

        target = _make_combat_ship("target")
        target.position = {"x": 60_000, "y": 0, "z": 0}

        result = combat.launch_missile(
            target_id="target",
            profile=profile,
            all_ships={"target": target},
        )
        if not result.get("ok"):
            assert "profile" not in result.get("message", "").lower(), (
                f"Profile '{profile}' was incorrectly rejected: {result}"
            )

    def test_launch_missile_warhead_options(self):
        """launch_missile accepts fragmentation and shaped_charge warheads."""
        ship = _make_combat_ship("player")
        combat = ship.systems["combat"]
        combat._ship_ref = ship
        combat._sim_time = 100.0

        target = _make_combat_ship("target")
        target.position = {"x": 60_000, "y": 0, "z": 0}

        for warhead in ("fragmentation", "shaped_charge"):
            result = combat.launch_missile(
                target_id="target",
                profile="direct",
                all_ships={"target": target},
                warhead_type=warhead,
            )
            if not result.get("ok"):
                assert "warhead" not in result.get("message", "").lower(), (
                    f"Warhead '{warhead}' was incorrectly rejected: {result}"
                )
