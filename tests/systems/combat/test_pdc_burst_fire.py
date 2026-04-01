# tests/systems/combat/test_pdc_burst_fire.py
"""Tests for PDC burst fire mechanics in auto-defense mode.

Phase 1B: Each PDC trigger pull fires burst_count rounds, where every
round has its own independent hit roll, consumes 1 ammo, and generates
heat. A torpedo is destroyed if ANY round in the burst connects.

Covers:
- Ammo consumption: exactly burst_count rounds per trigger pull
- Per-round hit rolls: not a single binary outcome
- Heat accumulation: proportional to rounds fired
- Torpedo destruction: any hit in burst kills the torpedo
- Ammo exhaustion mid-burst: stops firing when empty
- Combat log: burst details in event payload
"""

import pytest
from unittest.mock import patch
from dataclasses import dataclass
from typing import Dict, List


# ---------------------------------------------------------------------------
# Helpers -- reuse the same lightweight stand-ins from test_pdc_defense_modes
# ---------------------------------------------------------------------------

@dataclass
class FakeTorpedo:
    """Minimal torpedo for PDC interception tests."""
    id: str
    target_id: str
    shooter_id: str = "enemy"
    position: Dict[str, float] = None
    velocity: Dict[str, float] = None
    hull_health: float = 100.0
    alive: bool = True

    def __post_init__(self):
        if self.position is None:
            self.position = {"x": 0, "y": 0, "z": 0}
        if self.velocity is None:
            self.velocity = {"x": 0, "y": 0, "z": 0}


class FakeTorpedoManager:
    """Minimal torpedo manager tracking per-round damage application."""

    def __init__(self, torpedoes: List[FakeTorpedo] = None):
        self._torpedoes = list(torpedoes or [])
        self.active_count = len(self._torpedoes)
        # Track every apply_pdc_damage call for assertion
        self.damage_calls: List[dict] = []

    def get_torpedoes_targeting(self, ship_id: str) -> List[FakeTorpedo]:
        return [t for t in self._torpedoes if t.alive and t.target_id == ship_id]

    def apply_pdc_damage(self, torpedo_id: str, damage: float, source: str = "") -> dict:
        self.damage_calls.append({
            "torpedo_id": torpedo_id,
            "damage": damage,
            "source": source,
        })
        for torp in self._torpedoes:
            if torp.id == torpedo_id and torp.alive:
                torp.hull_health -= damage
                if torp.hull_health <= 0:
                    torp.alive = False
                    return {"ok": True, "destroyed": True, "torpedo_id": torpedo_id}
                return {
                    "ok": True, "destroyed": False,
                    "torpedo_id": torpedo_id,
                    "hull_remaining": torp.hull_health,
                }
        return {"ok": False, "reason": "torpedo_not_found"}


def _make_ship(ship_id: str, pdcs: int = 1, position: Dict[str, float] = None):
    """Create a minimal Ship with a CombatSystem for testing."""
    from hybrid.ship import Ship

    pos = position or {"x": 0, "y": 0, "z": 0}
    config = {
        "id": ship_id,
        "position": pos,
        "velocity": {"x": 0, "y": 0, "z": 0},
        "systems": {
            "combat": {"railguns": 0, "pdcs": pdcs},
            "targeting": {},
            "sensors": {"passive": {"range": 50000}},
            "power_management": {
                "primary": {"output": 200},
                "secondary": {"output": 100},
            },
        },
    }
    ship = Ship(ship_id, config)
    ship.sim_time = 10.0  # Ensure weapons are off cooldown
    return ship


# ---------------------------------------------------------------------------
# Tests: Ammo consumption per burst
# ---------------------------------------------------------------------------

class TestBurstAmmoConsumption:
    """Verify that exactly burst_count rounds of ammo are consumed per trigger pull."""

    def test_full_burst_consumes_burst_count_ammo(self):
        """A full burst with no interruptions consumes exactly burst_count rounds."""
        from hybrid.simulator import Simulator
        from hybrid.systems.weapons.truth_weapons import PDC_SPECS

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender")
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        weapon = ship.systems["combat"].truth_weapons["pdc_1"]
        initial_ammo = weapon.ammo
        assert initial_ammo == PDC_SPECS.ammo_capacity  # 3000

        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
            hull_health=1000.0,  # Won't die from one burst
        )
        sim.torpedo_manager = FakeTorpedoManager([torp])

        # Force all rounds to miss so torpedo survives
        with patch("hybrid.simulator.random.random", return_value=1.0):
            sim._process_pdc_torpedo_intercept([ship])

        # Exactly burst_count rounds consumed
        assert weapon.ammo == initial_ammo - PDC_SPECS.burst_count
        assert weapon.ammo == 3000 - 10

    def test_three_hundred_bursts_drains_magazine(self):
        """At burst_count=10, a 3000-round magazine lasts exactly 300 trigger pulls."""
        from hybrid.simulator import Simulator
        from hybrid.systems.weapons.truth_weapons import PDC_SPECS

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender")
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        weapon = ship.systems["combat"].truth_weapons["pdc_1"]

        # Simulate repeated bursts until dry
        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
            hull_health=999999.0,  # Effectively indestructible
        )

        bursts_fired = 0
        with patch("hybrid.simulator.random.random", return_value=1.0):
            while weapon.ammo > 0:
                weapon.last_fired = -10.0  # Reset cooldown
                weapon.heat = 0.0  # Reset heat
                torp.alive = True
                torp.hull_health = 999999.0
                sim.torpedo_manager = FakeTorpedoManager([torp])
                sim._process_pdc_torpedo_intercept([ship])
                bursts_fired += 1

        assert bursts_fired == PDC_SPECS.ammo_capacity // PDC_SPECS.burst_count
        assert bursts_fired == 300
        assert weapon.ammo == 0

    def test_ammo_exhaustion_mid_burst(self):
        """If the PDC has fewer rounds than burst_count, it fires what it has."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender")
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        weapon = ship.systems["combat"].truth_weapons["pdc_1"]
        # Set ammo to 3 -- less than burst_count (10)
        weapon.ammo = 3

        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
            hull_health=1000.0,
        )
        mgr = FakeTorpedoManager([torp])
        sim.torpedo_manager = mgr

        with patch("hybrid.simulator.random.random", return_value=1.0):
            sim._process_pdc_torpedo_intercept([ship])

        # Only 3 rounds fired, not 10
        assert weapon.ammo == 0


# ---------------------------------------------------------------------------
# Tests: Per-round hit rolls (burst mechanics, not single-shot)
# ---------------------------------------------------------------------------

class TestBurstHitRolls:
    """Verify that each round in the burst gets its own independent hit roll."""

    def test_partial_hits_in_burst(self):
        """Some rounds hit and some miss within the same burst."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender")
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
            hull_health=1000.0,  # Very tough -- survives all hits
        )
        mgr = FakeTorpedoManager([torp])
        sim.torpedo_manager = mgr

        # Return values for 10 rounds: alternating hit/miss
        # hit_chance at 500m is ~0.95, so random < 0.95 hits, >= 0.95 misses
        # Use values that produce exactly 5 hits and 5 misses against ~0.95 chance
        roll_values = iter([0.0, 0.99, 0.0, 0.99, 0.0, 0.99, 0.0, 0.99, 0.0, 0.99])
        with patch("hybrid.simulator.random.random", side_effect=roll_values):
            sim._process_pdc_torpedo_intercept([ship])

        # 5 hits at base_damage=5.0 each = 25 total damage
        # Verify damage was applied in individual calls, not one lump
        hit_calls = [c for c in mgr.damage_calls if c["torpedo_id"] == "torp_1"]
        assert len(hit_calls) == 5
        for call in hit_calls:
            assert call["damage"] == 5.0  # base_damage per round, not burst total

    def test_all_miss_zero_damage(self):
        """If every round in the burst misses, no damage is applied."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender")
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
            hull_health=100.0,
        )
        mgr = FakeTorpedoManager([torp])
        sim.torpedo_manager = mgr

        with patch("hybrid.simulator.random.random", return_value=1.0):
            sim._process_pdc_torpedo_intercept([ship])

        # No damage calls at all
        assert len(mgr.damage_calls) == 0
        assert torp.hull_health == 100.0

    def test_torpedo_destroyed_by_any_hit(self):
        """A torpedo with low health is destroyed by the first hit in a burst."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender")
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        # Torpedo with very low health -- dies on first hit (base_damage=5.0)
        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
            hull_health=3.0,
        )
        mgr = FakeTorpedoManager([torp])
        sim.torpedo_manager = mgr

        with patch("hybrid.simulator.random.random", return_value=0.0):
            sim._process_pdc_torpedo_intercept([ship])

        assert not torp.alive
        # First hit destroys it; remaining rounds fire into debris.
        # Only one damage call connects (the destroying hit).
        # Subsequent rounds still fire (ammo consumed) but the torpedo
        # is already dead so the hit rolls skip damage application.
        assert len(mgr.damage_calls) == 1


# ---------------------------------------------------------------------------
# Tests: Heat accumulation per burst
# ---------------------------------------------------------------------------

class TestBurstHeatAccumulation:
    """Verify that heat accumulates per round, not per trigger pull."""

    def test_heat_per_round(self):
        """Each round in the burst adds heat. A full burst adds burst_count * 1.0."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender")
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        weapon = ship.systems["combat"].truth_weapons["pdc_1"]
        weapon.heat = 0.0

        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
            hull_health=1000.0,
        )
        sim.torpedo_manager = FakeTorpedoManager([torp])

        with patch("hybrid.simulator.random.random", return_value=1.0):
            sim._process_pdc_torpedo_intercept([ship])

        # 10 rounds * 1.0 heat per round = 10.0 total heat
        assert weapon.heat == pytest.approx(10.0)

    def test_single_burst_does_not_overheat(self):
        """A single 10-round burst should not push the PDC past the overheat threshold."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender")
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        weapon = ship.systems["combat"].truth_weapons["pdc_1"]
        weapon.heat = 0.0

        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
            hull_health=1000.0,
        )
        sim.torpedo_manager = FakeTorpedoManager([torp])

        with patch("hybrid.simulator.random.random", return_value=1.0):
            sim._process_pdc_torpedo_intercept([ship])

        # 10 heat << 95 (overheat threshold at 95% of max_heat=100)
        assert weapon.heat < weapon.max_heat * 0.95

    def test_overheat_stops_burst_early(self):
        """If heat reaches the overheat threshold mid-burst, remaining rounds are skipped."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender")
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        weapon = ship.systems["combat"].truth_weapons["pdc_1"]
        # Start just below overheat threshold so burst is cut short
        # Overheat at 95% of max_heat=100 = 95.0
        # Each round adds 1.0 heat; start at 92.0 so 3 rounds push to 95.0
        weapon.heat = 92.0
        initial_ammo = weapon.ammo

        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
            hull_health=1000.0,
        )
        sim.torpedo_manager = FakeTorpedoManager([torp])

        with patch("hybrid.simulator.random.random", return_value=1.0):
            sim._process_pdc_torpedo_intercept([ship])

        # Should have fired fewer than burst_count rounds
        rounds_fired = initial_ammo - weapon.ammo
        assert rounds_fired < weapon.specs.burst_count
        # Exactly 3 rounds: 92 -> 93 -> 94 -> 95 (hits threshold, stops)
        assert rounds_fired == 3


# ---------------------------------------------------------------------------
# Tests: Event payload includes burst details
# ---------------------------------------------------------------------------

class TestBurstEventPayload:
    """Verify the pdc_torpedo_engage event includes per-burst stats."""

    def test_event_includes_rounds_fired_and_burst_hits(self):
        """Event payload contains rounds_fired and burst_hits fields."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender")
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
            hull_health=1000.0,
        )
        sim.torpedo_manager = FakeTorpedoManager([torp])

        events = []
        sim._event_bus.subscribe(
            "pdc_torpedo_engage", lambda payload: events.append(payload)
        )

        # 10 rounds, all hit
        with patch("hybrid.simulator.random.random", return_value=0.0):
            sim._process_pdc_torpedo_intercept([ship])

        assert len(events) == 1
        evt = events[0]
        assert evt["rounds_fired"] == 10
        assert evt["burst_hits"] == 10
        assert evt["hit"] is True
        assert evt["destroyed"] is False  # hull_health=1000, 10*5=50 damage

    def test_event_zero_hits_on_miss(self):
        """Event reports 0 burst_hits when all rounds miss."""
        from hybrid.simulator import Simulator

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender")
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
            hull_health=1000.0,
        )
        sim.torpedo_manager = FakeTorpedoManager([torp])

        events = []
        sim._event_bus.subscribe(
            "pdc_torpedo_engage", lambda payload: events.append(payload)
        )

        with patch("hybrid.simulator.random.random", return_value=1.0):
            sim._process_pdc_torpedo_intercept([ship])

        assert len(events) == 1
        evt = events[0]
        assert evt["rounds_fired"] == 10
        assert evt["burst_hits"] == 0
        assert evt["hit"] is False


# ---------------------------------------------------------------------------
# Tests: Auto-PDC uses burst mechanics (integration)
# ---------------------------------------------------------------------------

class TestAutoPDCBurstIntegration:
    """Integration test: auto-PDC defense fires bursts, not single shots."""

    def test_auto_pdc_applies_per_round_damage(self):
        """Auto-PDC fires 10 rounds with per-round damage, not a single lump."""
        from hybrid.simulator import Simulator
        from hybrid.systems.weapons.truth_weapons import PDC_SPECS

        sim = Simulator(dt=0.1)
        ship = _make_ship("defender")
        sim.add_ship("defender", {})
        sim.ships["defender"] = ship

        # Torpedo with enough health to survive all 10 hits
        torp = FakeTorpedo(
            id="torp_1", target_id="defender",
            position={"x": 500, "y": 0, "z": 0},
            hull_health=1000.0,
        )
        mgr = FakeTorpedoManager([torp])
        sim.torpedo_manager = mgr

        # All 10 rounds hit
        with patch("hybrid.simulator.random.random", return_value=0.0):
            sim._process_pdc_torpedo_intercept([ship])

        # 10 individual damage applications, each base_damage (5.0)
        assert len(mgr.damage_calls) == 10
        total_damage = sum(c["damage"] for c in mgr.damage_calls)
        assert total_damage == PDC_SPECS.base_damage * PDC_SPECS.burst_count
        assert total_damage == 50.0

        # Torpedo took exactly 50 damage: 1000 - 50 = 950
        assert torp.hull_health == pytest.approx(950.0)
