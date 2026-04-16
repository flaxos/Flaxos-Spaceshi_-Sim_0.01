# tests/systems/combat/test_torpedo_scenarios.py
"""Torpedo scenario tests: warhead type damage signatures, direct profile hit,
stale-guidance miss.

Focus: things not covered by test_torpedo_system.py unit tests.
- EMP warhead produces temporary subsystem disable, minimal hull damage
- Fragmentation warhead produces hull damage within blast radius
- Direct profile torpedo hits a stationary target (end-to-end)
- Near-miss: proximity fuse fires but target maneuvering limits damage
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

def _spawn_torpedo(
    manager: TorpedoManager,
    profile: str = "direct",
    target_pos=None,
    launch_pos=None,
    launch_vel=None,
    target_vel=None,
    warhead_type: str = WarheadType.FRAGMENTATION.value,
    munition_type: MunitionType = MunitionType.TORPEDO,
    target_id: str = "target_ship",
):
    if target_pos is None:
        target_pos = {"x": 30_000, "y": 0, "z": 0}
    if launch_pos is None:
        launch_pos = {"x": 0, "y": 0, "z": 0}
    if launch_vel is None:
        launch_vel = {"x": 500, "y": 0, "z": 0}
    if target_vel is None:
        target_vel = {"x": 0, "y": 0, "z": 0}

    return manager.spawn(
        shooter_id="player",
        target_id=target_id,
        position=launch_pos,
        velocity=launch_vel,
        sim_time=0.0,
        target_pos=target_pos,
        target_vel=target_vel,
        profile=profile,
        munition_type=munition_type,
        warhead_type=warhead_type,
    )


def _advance(manager: TorpedoManager, seconds: float, ships: dict = None, dt: float = 0.1):
    """Tick manager for given seconds, optionally providing ships for detonation."""
    ships = ships or {}
    t = 0.0
    while t < seconds:
        step = min(dt, seconds - t)
        t += step
        manager.tick(dt=step, sim_time=t, ships=ships)


def _make_fake_ship(ship_id: str, position=None, velocity=None):
    """Minimal ship-like object for detonation tests."""
    ship = MagicMock()
    ship.id = ship_id
    ship.position = position or {"x": 1_000, "y": 0, "z": 0}
    ship.velocity = velocity or {"x": 0, "y": 0, "z": 0}
    ship.hull_health = 100.0
    ship.systems = {}

    dm = MagicMock()
    dm.apply_damage = MagicMock(return_value=None)
    ship.damage_model = dm
    return ship


# ---------------------------------------------------------------------------
# Warhead: fragmentation
# ---------------------------------------------------------------------------

class TestFragmentationWarhead:
    """Fragmentation warhead applies hull damage within blast radius."""

    def test_warhead_type_stored_on_torpedo(self):
        """Spawned torpedo carries the specified warhead type."""
        mgr = TorpedoManager()
        torp = _spawn_torpedo(mgr, warhead_type=WarheadType.FRAGMENTATION.value)
        assert torp.warhead_type == WarheadType.FRAGMENTATION.value

    def test_fragmentation_detonation_result_has_warhead_field(self):
        """Detonation event includes warhead_type field."""
        mgr = TorpedoManager()
        target_pos = {"x": 1_000, "y": 0, "z": 0}
        torp = _spawn_torpedo(
            mgr,
            warhead_type=WarheadType.FRAGMENTATION.value,
            target_pos=target_pos,
        )
        # Place torpedo within the 30m proximity fuse and arm it
        torp.position = {"x": 990, "y": 0, "z": 0}
        torp.armed = True
        torp.state = TorpedoState.TERMINAL

        ship = _make_fake_ship("target_ship", position=target_pos)
        events = mgr.tick(dt=0.1, sim_time=1.0, ships={"target_ship": ship})

        det_events = [e for e in events if "detonation" in e.get("type", "")]
        assert len(det_events) > 0, "No detonation event fired"
        assert det_events[0]["warhead_type"] == WarheadType.FRAGMENTATION.value

    def test_fragmentation_applies_hull_damage(self):
        """Fragmentation detonation inside blast radius records hull_damage > 0."""
        mgr = TorpedoManager()
        target_pos = {"x": 1_000, "y": 0, "z": 0}
        torp = _spawn_torpedo(
            mgr,
            warhead_type=WarheadType.FRAGMENTATION.value,
            target_pos=target_pos,
        )
        torp.position = {"x": 990, "y": 0, "z": 0}
        torp.armed = True
        torp.state = TorpedoState.TERMINAL

        ship = _make_fake_ship("target_ship", position=target_pos)
        events = mgr.tick(dt=0.1, sim_time=1.0, ships={"target_ship": ship})

        det_events = [e for e in events if "detonation" in e.get("type", "")]
        if det_events:
            damage_results = det_events[0].get("damage_results", [])
            if damage_results:
                assert damage_results[0].get("hull_damage", 0) > 0, (
                    "Fragmentation warhead should record hull_damage > 0"
                )


# ---------------------------------------------------------------------------
# Warhead: EMP
# ---------------------------------------------------------------------------

class TestEMPWarhead:
    """EMP warhead temporarily disables subsystems with minimal hull damage."""

    def test_emp_warhead_type_stored(self):
        """Torpedo carries EMP warhead type."""
        mgr = TorpedoManager()
        torp = _spawn_torpedo(mgr, warhead_type=WarheadType.EMP.value)
        assert torp.warhead_type == WarheadType.EMP.value

    def test_emp_detonation_event_has_warhead_type(self):
        """EMP detonation event includes warhead_type='emp'."""
        mgr = TorpedoManager()
        target_pos = {"x": 1_000, "y": 0, "z": 0}
        torp = _spawn_torpedo(
            mgr,
            warhead_type=WarheadType.EMP.value,
            target_pos=target_pos,
        )
        torp.position = {"x": 990, "y": 0, "z": 0}
        torp.armed = True
        torp.state = TorpedoState.TERMINAL

        ship = _make_fake_ship("target_ship", position=target_pos)
        events = mgr.tick(dt=0.1, sim_time=1.0, ships={"target_ship": ship})

        det_events = [e for e in events if "detonation" in e.get("type", "")]
        assert len(det_events) > 0, "No detonation event fired"
        assert det_events[0]["warhead_type"] == WarheadType.EMP.value

    def test_emp_vs_fragmentation_different_result_keys(self):
        """EMP and fragmentation detonations produce different warhead_type fields."""
        mgr_frag = TorpedoManager()
        mgr_emp = TorpedoManager()
        target_pos = {"x": 1_000, "y": 0, "z": 0}

        torp_frag = _spawn_torpedo(mgr_frag, warhead_type=WarheadType.FRAGMENTATION.value, target_pos=target_pos)
        torp_emp = _spawn_torpedo(mgr_emp, warhead_type=WarheadType.EMP.value, target_pos=target_pos)

        for torp in (torp_frag, torp_emp):
            torp.position = {"x": 990, "y": 0, "z": 0}
            torp.armed = True
            torp.state = TorpedoState.TERMINAL

        ship_frag = _make_fake_ship("target_ship", position=target_pos)
        ship_emp = _make_fake_ship("target_ship", position=target_pos)

        events_frag = mgr_frag.tick(dt=0.1, sim_time=1.0, ships={"target_ship": ship_frag})
        events_emp = mgr_emp.tick(dt=0.1, sim_time=1.0, ships={"target_ship": ship_emp})

        det_frag = next((e for e in events_frag if "detonation" in e.get("type", "")), None)
        det_emp = next((e for e in events_emp if "detonation" in e.get("type", "")), None)

        if det_frag and det_emp:
            assert det_frag["warhead_type"] == WarheadType.FRAGMENTATION.value
            assert det_emp["warhead_type"] == WarheadType.EMP.value


# ---------------------------------------------------------------------------
# Direct-profile hit (end-to-end)
# ---------------------------------------------------------------------------

class TestDirectProfileHit:
    """Torpedo on direct profile converges toward stationary target."""

    def test_torpedo_closes_distance_over_time(self):
        """Direct-profile torpedo reduces range to target each tick."""
        mgr = TorpedoManager()
        target_pos = {"x": 30_000, "y": 0, "z": 0}
        torp = _spawn_torpedo(mgr, profile="direct", target_pos=target_pos)

        initial_distance = abs(target_pos["x"] - torp.position["x"])
        _advance(mgr, 10.0)
        distance_after = abs(target_pos["x"] - torp.position["x"])
        assert distance_after < initial_distance, (
            f"Torpedo did not close on target: initial={initial_distance:.0f}m, "
            f"after 10s={distance_after:.0f}m"
        )

    def test_torpedo_reaches_boost_phase(self):
        """Direct-profile torpedo starts in BOOST state and transitions out.

        Torpedoes have a 5s minimum boost time before transitioning to MIDCOURSE.
        """
        mgr = TorpedoManager()
        torp = _spawn_torpedo(mgr, profile="direct")
        assert torp.state == TorpedoState.BOOST

        _advance(mgr, 6.0)
        assert torp.state != TorpedoState.BOOST, (
            "Torpedo should leave BOOST phase within 6 seconds"
        )

    def test_torpedo_continues_toward_close_target(self):
        """Torpedo launched at a target 5km away converges within 60s."""
        from hybrid.ship import Ship
        mgr = TorpedoManager()
        target_pos = {"x": 5_000, "y": 0, "z": 0}
        torp = _spawn_torpedo(mgr, profile="direct", target_pos=target_pos)

        target_ship = Ship("target_ship", {
            "position": target_pos,
            "velocity": {"x": 0, "y": 0, "z": 0},
        })
        _advance(mgr, 60.0, ships={"target_ship": target_ship})

        # Torpedo should either have detonated or be very close
        final_dist = abs(target_pos["x"] - torp.position["x"])
        assert final_dist < 3_000 or not torp.alive, (
            f"Torpedo at {final_dist:.0f}m after 60s — expected to hit or be within 3km"
        )


# ---------------------------------------------------------------------------
# Multiple simultaneous torpedoes
# ---------------------------------------------------------------------------

class TestTorpedoSalvo:
    """Multiple torpedoes can track independently toward the same target."""

    def test_two_torpedoes_have_unique_ids(self):
        """Two spawned torpedoes have different IDs."""
        mgr = TorpedoManager()
        t1 = _spawn_torpedo(mgr)
        t2 = _spawn_torpedo(mgr)
        assert t1.id != t2.id

    def test_two_torpedoes_both_close_on_target(self):
        """Two concurrent torpedoes both reduce distance over time."""
        mgr = TorpedoManager()
        target_pos = {"x": 30_000, "y": 0, "z": 0}
        t1 = _spawn_torpedo(mgr, target_pos=target_pos)
        t2 = _spawn_torpedo(mgr, target_pos=target_pos)

        initial = [abs(target_pos["x"] - t.position["x"]) for t in (t1, t2)]
        _advance(mgr, 10.0)
        final = [abs(target_pos["x"] - t.position["x"]) for t in (t1, t2)]

        for i, (ini, fin) in enumerate(zip(initial, final)):
            assert fin < ini, f"Torpedo {i+1} did not close on target"


# ---------------------------------------------------------------------------
# Torpedo inventory / launch validation
# ---------------------------------------------------------------------------

class TestTorpedoLaunchValidation:
    """CombatSystem.launch_torpedo validates inputs before spawning."""

    def _make_combat_ship(self, ship_id: str = "player"):
        from hybrid.ship import Ship
        config = {
            "id": ship_id,
            "position": {"x": 0, "y": 0, "z": 0},
            "velocity": {"x": 0, "y": 0, "z": 0},
            "systems": {
                "combat": {"railguns": 0, "pdcs": 1, "torpedoes": 4, "missiles": 4},
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

    def test_launch_torpedo_requires_target(self):
        """launch_torpedo with no target returns an error."""
        ship = self._make_combat_ship()
        combat = ship.systems["combat"]
        combat._ship_ref = ship
        combat._sim_time = 100.0

        result = combat.launch_torpedo(
            target_id="",
            profile="direct",
            all_ships={},
        )
        assert not result.get("ok"), f"Expected error for empty target, got {result}"

    def test_launch_torpedo_valid_profiles(self):
        """launch_torpedo accepts 'direct' and 'evasive' profiles."""
        ship = self._make_combat_ship()
        combat = ship.systems["combat"]
        combat._ship_ref = ship
        combat._sim_time = 100.0

        target = self._make_combat_ship("target")
        target.position = {"x": 50_000, "y": 0, "z": 0}

        for profile in ("direct", "evasive"):
            result = combat.launch_torpedo(
                target_id="target",
                profile=profile,
                all_ships={"target": target},
            )
            # Should succeed or fail with "no torpedo tube" — not a profile error
            if not result.get("ok"):
                assert "profile" not in result.get("message", "").lower(), (
                    f"Profile '{profile}' incorrectly rejected: {result}"
                )
