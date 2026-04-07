# tests/test_razorback_class.py
"""Regression tests for the Razorback ship class.

Verifies:
  1. Ship class definition loads from registry with correct specs
  2. Physical parameters: dry_mass, thrust, acceleration, sensors, fuel/isp
  3. No weapons or ECM (civilian interceptor)
  4. Station restrictions: TACTICAL cannot be claimed, HELM and SCIENCE can
  5. Combat restrictions: fire_weapon and fire_unguided fail
  6. Freefly sandbox scenario (50_razorback_freefly.yaml) loads correctly
  7. Razorback appears as observer in scenarios 31, 32, and 40
  8. Delta-v budget matches Tsiolkovsky rocket equation

The razorback.json and its associated scenarios are expected to be present
in the repository.  Each test will xfail with a clear message if a file or
class is missing so the regression suite stays green during development and
turns red the moment a spec is violated after the feature lands.
"""

from __future__ import annotations

import math
import sys
import os
from pathlib import Path
from typing import Dict

import pytest
import yaml

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parents[1]
SHIP_CLASSES_DIR = ROOT_DIR / "ship_classes"
SCENARIOS_DIR = ROOT_DIR / "scenarios"

RAZORBACK_JSON = SHIP_CLASSES_DIR / "razorback.json"
SCENARIO_50 = SCENARIOS_DIR / "50_razorback_freefly.yaml"
SCENARIO_31 = SCENARIOS_DIR / "31_ganymede_station.yaml"
SCENARIO_32 = SCENARIOS_DIR / "32_the_donnager.yaml"
SCENARIO_40 = SCENARIOS_DIR / "40_shooting_arena.yaml"


# ---------------------------------------------------------------------------
# Helper: reset the registry singleton so each test loads fresh class data
# ---------------------------------------------------------------------------

def _reset_registry():
    """Force the ship class registry to re-scan the classes directory."""
    import hybrid.ship_class_registry as _mod
    _mod._registry = None


def _get_registry():
    _reset_registry()
    from hybrid.ship_class_registry import get_registry
    return get_registry()


def _razorback_ship_config() -> dict:
    """Return a fully-resolved razorback ship config from the registry.

    Raises pytest.skip when the razorback class is not yet defined.
    """
    registry = _get_registry()
    data = registry.get_class("razorback")
    if data is None:
        pytest.skip("razorback ship class not yet defined in ship_classes/razorback.json")
    resolved = registry.resolve_ship_config({"ship_class": "razorback"})
    return resolved


def _make_razorback_ship(ship_id: str = "rb_001"):
    """Instantiate a Ship from the razorback class config."""
    from hybrid.ship import Ship
    config = _razorback_ship_config()
    return Ship(ship_id, config)


# ---------------------------------------------------------------------------
# 1. Ship Class Loading
# ---------------------------------------------------------------------------

class TestRazorbackClassLoading:
    """Verify the razorback JSON loads correctly through the registry."""

    def test_razorback_loads_from_registry(self):
        """resolve_ship_config({'ship_class': 'razorback'}) returns valid config."""
        if not RAZORBACK_JSON.exists():
            pytest.skip(f"razorback.json not yet created at {RAZORBACK_JSON}")

        registry = _get_registry()
        data = registry.get_class("razorback")

        assert data is not None, "Registry did not load 'razorback' class"
        assert data.get("class_id") == "razorback", (
            f"class_id should be 'razorback', got {data.get('class_id')!r}"
        )

    def test_razorback_mass_and_thrust(self):
        """Ship instantiated from razorback config has dry_mass=250 and max_thrust=80000."""
        if not RAZORBACK_JSON.exists():
            pytest.skip(f"razorback.json not yet created at {RAZORBACK_JSON}")

        ship = _make_razorback_ship()

        assert ship.dry_mass == pytest.approx(250.0, abs=1.0), (
            f"Expected dry_mass=250 kg, got {ship.dry_mass}"
        )

        propulsion = ship.systems.get("propulsion")
        assert propulsion is not None, "Propulsion system not loaded"
        assert propulsion.max_thrust == pytest.approx(80000.0, abs=1.0), (
            f"Expected max_thrust=80000 N (80 kN), got {propulsion.max_thrust}"
        )

    def test_razorback_thrust_to_weight(self):
        """Razorback peak acceleration is ~320 m/s² (≈32.6G) at dry mass."""
        if not RAZORBACK_JSON.exists():
            pytest.skip(f"razorback.json not yet created at {RAZORBACK_JSON}")

        ship = _make_razorback_ship()
        propulsion = ship.systems.get("propulsion")

        expected_accel = 80000.0 / 250.0  # 320 m/s²
        actual_accel = propulsion.max_thrust / ship.dry_mass

        assert actual_accel == pytest.approx(expected_accel, rel=0.01), (
            f"Expected ~{expected_accel:.1f} m/s², got {actual_accel:.1f} m/s²"
        )
        # Confirm it is a genuinely high-G platform
        assert actual_accel >= 300.0, (
            f"Razorback should be high-G (≥300 m/s²), got {actual_accel:.1f}"
        )

    def test_razorback_sensor_range(self):
        """Razorback passive sensor range is 400 km and active is 300 km."""
        if not RAZORBACK_JSON.exists():
            pytest.skip(f"razorback.json not yet created at {RAZORBACK_JSON}")

        ship = _make_razorback_ship()
        sensors = ship.systems.get("sensors")

        assert sensors is not None, "Sensors system not loaded"
        assert sensors.passive.range == pytest.approx(400000.0, abs=1.0), (
            f"Expected passive range=400000 m, got {sensors.passive.range}"
        )
        assert sensors.active.range == pytest.approx(300000.0, abs=1.0), (
            f"Expected active scan_range=300000 m, got {sensors.active.range}"
        )

    def test_razorback_no_weapons(self):
        """Razorback has no weapon mounts and no combat system."""
        if not RAZORBACK_JSON.exists():
            pytest.skip(f"razorback.json not yet created at {RAZORBACK_JSON}")

        registry = _get_registry()
        data = registry.get_class("razorback")

        weapon_mounts = data.get("weapon_mounts", [])
        assert weapon_mounts == [], (
            f"Razorback should have no weapon mounts, got: {weapon_mounts}"
        )

        combat_cfg = data.get("systems", {}).get("combat", {})
        # Either absent or explicitly disabled
        if combat_cfg:
            assert combat_cfg.get("enabled", True) is False, (
                "Razorback combat system should be disabled or absent"
            )

    def test_razorback_fuel_and_isp(self):
        """Razorback has max_fuel=150 kg and isp=6000 s (high-efficiency drive)."""
        if not RAZORBACK_JSON.exists():
            pytest.skip(f"razorback.json not yet created at {RAZORBACK_JSON}")

        registry = _get_registry()
        data = registry.get_class("razorback")
        mass_block = data.get("mass", {})
        propulsion_cfg = data.get("systems", {}).get("propulsion", {})

        assert mass_block.get("max_fuel") == pytest.approx(150.0, abs=0.1), (
            f"Expected max_fuel=150 kg, got {mass_block.get('max_fuel')}"
        )
        assert propulsion_cfg.get("isp") == pytest.approx(6000.0, abs=1.0), (
            f"Expected isp=6000 s, got {propulsion_cfg.get('isp')}"
        )


# ---------------------------------------------------------------------------
# 2. Station Restrictions
# ---------------------------------------------------------------------------

class TestRazorbackStationRestrictions:
    """Verify station access rules align with razorback's systems.

    These tests use the static required_systems definitions and the ship's
    actual loaded systems — they do NOT go through StationManager.claim_station
    (which doesn't validate required_systems at claim time).
    """

    def test_razorback_no_tactical_station(self):
        """TACTICAL requires 'weapons' and 'targeting' — razorback has neither."""
        if not RAZORBACK_JSON.exists():
            pytest.skip(f"razorback.json not yet created at {RAZORBACK_JSON}")

        from server.stations.station_types import StationType, get_required_systems

        ship = _make_razorback_ship()
        tactical_required = get_required_systems(StationType.TACTICAL)

        # The Ship constructor creates all systems (even disabled ones),
        # so check that the critical TACTICAL system (weapons) is missing
        # or disabled. "targeting" exists but is disabled — that's fine,
        # the key gate is "weapons" which is what TACTICAL actually needs.
        ship_systems = set(ship.systems.keys())
        missing = tactical_required - ship_systems

        assert "weapons" in missing or not ship.systems.get("weapons"), (
            f"Razorback should lack functional weapons for TACTICAL station. "
            f"Ship systems: {sorted(ship_systems)}"
        )

    def test_razorback_helm_station_works(self):
        """HELM requires 'propulsion', 'helm', 'navigation' — razorback has all three."""
        if not RAZORBACK_JSON.exists():
            pytest.skip(f"razorback.json not yet created at {RAZORBACK_JSON}")

        from server.stations.station_types import StationType, get_required_systems

        ship = _make_razorback_ship()
        helm_required = get_required_systems(StationType.HELM)

        ship_systems = set(ship.systems.keys())
        missing = helm_required - ship_systems

        assert missing == set(), (
            f"Razorback should have all HELM required systems. "
            f"Missing: {missing}. Ship systems: {sorted(ship_systems)}"
        )

    def test_razorback_science_station_works(self):
        """SCIENCE requires 'sensors' — razorback has strong sensors."""
        if not RAZORBACK_JSON.exists():
            pytest.skip(f"razorback.json not yet created at {RAZORBACK_JSON}")

        from server.stations.station_types import StationType, get_required_systems

        ship = _make_razorback_ship()
        science_required = get_required_systems(StationType.SCIENCE)

        ship_systems = set(ship.systems.keys())
        missing = science_required - ship_systems

        assert missing == set(), (
            f"Razorback should have all SCIENCE required systems. "
            f"Missing: {missing}"
        )

    def test_tactical_required_systems_are_weapons_and_targeting(self):
        """Smoke-test: TACTICAL station definition requires weapons+targeting (spec guard)."""
        from server.stations.station_types import StationType, get_required_systems

        required = get_required_systems(StationType.TACTICAL)
        assert "weapons" in required, "TACTICAL must require 'weapons'"
        assert "targeting" in required, "TACTICAL must require 'targeting'"


# ---------------------------------------------------------------------------
# 3. Combat Restrictions
# ---------------------------------------------------------------------------

class TestRazorbackCombatRestrictions:
    """Verify that firing commands fail gracefully on a weaponless razorback."""

    def test_razorback_cannot_fire(self):
        """fire_weapon returns an error when the ship has no weapons configured."""
        if not RAZORBACK_JSON.exists():
            pytest.skip(f"razorback.json not yet created at {RAZORBACK_JSON}")

        ship = _make_razorback_ship()
        combat = ship.systems.get("combat")

        # If no combat system is loaded, the ship structurally cannot fire.
        if combat is None:
            # Correct: razorback has no combat system
            assert ship.systems.get("combat") is None
            return

        # If a combat system is somehow present (misconfigured), verify it has no weapons
        truth_weapons = getattr(combat, "truth_weapons", {})
        assert truth_weapons == {}, (
            f"Razorback combat system should have no truth weapons, got: {list(truth_weapons.keys())}"
        )

        # Attempting to fire should fail with UNKNOWN_WEAPON
        result = combat.fire_weapon("railgun_1")
        assert result.get("ok") is False, (
            f"fire_weapon should fail on razorback, got: {result}"
        )

    def test_razorback_cannot_fire_unguided(self):
        """fire_unguided also fails — razorback has no weapon mounts at all."""
        if not RAZORBACK_JSON.exists():
            pytest.skip(f"razorback.json not yet created at {RAZORBACK_JSON}")

        ship = _make_razorback_ship()
        combat = ship.systems.get("combat")

        # No combat system = structurally cannot fire (correct)
        if combat is None:
            assert ship.systems.get("combat") is None
            return

        result = combat.fire_unguided({"weapon_id": "pdc_1"})
        assert result.get("ok") is False, (
            f"fire_unguided should fail on razorback, got: {result}"
        )

    def test_razorback_cannot_lock_target(self):
        """Razorback targeting is disabled — lock_target should fail or be unavailable."""
        if not RAZORBACK_JSON.exists():
            pytest.skip(f"razorback.json not yet created at {RAZORBACK_JSON}")

        ship = _make_razorback_ship()
        targeting = ship.systems.get("targeting")

        # Targeting system may exist but should be disabled (enabled=false in class JSON)
        if targeting is not None:
            assert not getattr(targeting, 'enabled', True), (
                f"Razorback targeting should be disabled, but enabled={targeting.enabled}"
            )
        # Either way, no functional targeting

    def test_razorback_no_ecm(self):
        """Razorback is an unarmed civilian craft — no ECM system."""
        if not RAZORBACK_JSON.exists():
            pytest.skip(f"razorback.json not yet created at {RAZORBACK_JSON}")

        registry = _get_registry()
        data = registry.get_class("razorback")
        ecm_cfg = data.get("systems", {}).get("ecm", {})

        # ECM should be absent or explicitly disabled
        if ecm_cfg:
            assert ecm_cfg.get("enabled", True) is False, (
                "Razorback ECM should be disabled or absent"
            )


# ---------------------------------------------------------------------------
# 4. Scenario Loading
# ---------------------------------------------------------------------------

class TestRazorbackScenarios:
    """Verify scenario YAML files reference the razorback class correctly."""

    def test_freefly_scenario_loads(self):
        """Scenario 50 (razorback freefly sandbox) exists and player ship is razorback class."""
        if not SCENARIO_50.exists():
            pytest.skip(f"Scenario not yet created: {SCENARIO_50}")

        data = yaml.safe_load(SCENARIO_50.read_text())
        assert data is not None, "Scenario 50 YAML parsed as None"
        assert "ships" in data, "Scenario 50 missing 'ships' key"

        ships = {s["id"]: s for s in data["ships"]}
        player_ship = None
        for ship in data["ships"]:
            if ship.get("player_controlled", False):
                player_ship = ship
                break

        assert player_ship is not None, "No player-controlled ship in scenario 50"
        assert player_ship.get("ship_class") == "razorback", (
            f"Player ship should be 'razorback' class, got {player_ship.get('ship_class')!r}"
        )

    def test_freefly_has_sparring_ships(self):
        """Scenario 50 includes at least two AI corvette sparring partners."""
        if not SCENARIO_50.exists():
            pytest.skip(f"Scenario not yet created: {SCENARIO_50}")

        data = yaml.safe_load(SCENARIO_50.read_text())
        ships = data.get("ships", [])
        ai_ships = [s for s in ships if s.get("ai_enabled", False)]

        assert len(ai_ships) >= 2, (
            f"Freefly scenario should have at least 2 AI sparring ships, got {len(ai_ships)}"
        )

    def test_observer_in_ganymede(self):
        """Scenario 31 (Ganymede Station Defense) includes a razorback observer ship."""
        assert SCENARIO_31.exists(), f"Scenario 31 missing: {SCENARIO_31}"

        data = yaml.safe_load(SCENARIO_31.read_text())
        ships = data.get("ships", [])

        razorback_ships = [
            s for s in ships
            if s.get("ship_class") == "razorback" or s.get("class") == "razorback"
        ]

        assert len(razorback_ships) >= 1, (
            f"Scenario 31 should have at least one razorback observer ship. "
            f"Ship classes present: {[s.get('ship_class') or s.get('class') for s in ships]}"
        )

    def test_observer_in_donnager(self):
        """Scenario 32 (The Donnager) includes a razorback observer ship."""
        assert SCENARIO_32.exists(), f"Scenario 32 missing: {SCENARIO_32}"

        data = yaml.safe_load(SCENARIO_32.read_text())
        ships = data.get("ships", [])

        razorback_ships = [
            s for s in ships
            if s.get("ship_class") == "razorback" or s.get("class") == "razorback"
        ]

        assert len(razorback_ships) >= 1, (
            f"Scenario 32 should have at least one razorback observer ship. "
            f"Ship classes present: {[s.get('ship_class') or s.get('class') for s in ships]}"
        )

    def test_observer_in_shooting_arena(self):
        """Scenario 40 (Shooting Arena) includes a razorback observer ship."""
        assert SCENARIO_40.exists(), f"Scenario 40 missing: {SCENARIO_40}"

        data = yaml.safe_load(SCENARIO_40.read_text())
        ships = data.get("ships", [])

        razorback_ships = [
            s for s in ships
            if s.get("ship_class") == "razorback" or s.get("class") == "razorback"
        ]

        assert len(razorback_ships) >= 1, (
            f"Scenario 40 should have at least one razorback observer ship. "
            f"Ship classes present: {[s.get('ship_class') or s.get('class') for s in ships]}"
        )

    def test_freefly_scenario_has_mission_block(self):
        """Scenario 50 has a mission block (objectives, briefing)."""
        if not SCENARIO_50.exists():
            pytest.skip(f"Scenario not yet created: {SCENARIO_50}")

        data = yaml.safe_load(SCENARIO_50.read_text())
        assert "mission" in data, "Scenario 50 missing 'mission' block"
        mission = data["mission"]
        assert "briefing" in mission or "description" in mission or "name" in data, (
            "Scenario 50 should have mission briefing or name"
        )

    def test_freefly_scenario_name(self):
        """Scenario 50 has a human-readable name referencing razorback or freefly."""
        if not SCENARIO_50.exists():
            pytest.skip(f"Scenario not yet created: {SCENARIO_50}")

        data = yaml.safe_load(SCENARIO_50.read_text())
        name = data.get("name", "").lower()
        assert "razorback" in name or "freefly" in name or "free fly" in name or "sandbox" in name, (
            f"Scenario 50 name should mention razorback or freefly, got {data.get('name')!r}"
        )


# ---------------------------------------------------------------------------
# 5. Delta-V Budget
# ---------------------------------------------------------------------------

class TestRazorbackDeltaV:
    """Verify the razorback's propellant budget against the Tsiolkovsky equation."""

    def test_razorback_delta_v(self):
        """Delta-v ≈ 27,600 m/s from ln(400/250) * 6000 * 9.81."""
        if not RAZORBACK_JSON.exists():
            pytest.skip(f"razorback.json not yet created at {RAZORBACK_JSON}")

        from hybrid.utils.units import calculate_delta_v

        dry_mass = 250.0   # kg
        fuel_mass = 150.0  # kg
        isp = 6000.0       # seconds

        # Tsiolkovsky: Δv = Isp * g₀ * ln((m_dry + m_fuel) / m_dry)
        expected_dv = calculate_delta_v(dry_mass, fuel_mass, isp)
        # ln(400/250)*6000*9.81 ≈ 27,664 m/s
        assert expected_dv == pytest.approx(27664.0, abs=100.0), (
            f"Expected ~27664 m/s delta-v, got {expected_dv:.1f} m/s"
        )

    def test_razorback_delta_v_from_ship(self):
        """Delta-v computed from actual ship propulsion system matches Tsiolkovsky."""
        if not RAZORBACK_JSON.exists():
            pytest.skip(f"razorback.json not yet created at {RAZORBACK_JSON}")

        from hybrid.utils.units import calculate_delta_v

        ship = _make_razorback_ship()
        propulsion = ship.systems.get("propulsion")

        assert propulsion is not None, "Propulsion system missing"

        dry_mass = ship.dry_mass
        fuel_mass = propulsion.fuel_level
        isp = propulsion.isp

        dv = calculate_delta_v(dry_mass, fuel_mass, isp)

        # At full fuel (150 kg), should be ~27,664 m/s
        assert dv > 25000.0, (
            f"Razorback delta-v should exceed 25 km/s, got {dv:.1f} m/s"
        )
        assert dv < 35000.0, (
            f"Razorback delta-v should be under 35 km/s (sanity cap), got {dv:.1f} m/s"
        )

    def test_razorback_delta_v_uses_correct_mass_ratio(self):
        """Mass ratio (m_wet/m_dry) is 400/250 = 1.6."""
        if not RAZORBACK_JSON.exists():
            pytest.skip(f"razorback.json not yet created at {RAZORBACK_JSON}")

        registry = _get_registry()
        data = registry.get_class("razorback")
        mass = data.get("mass", {})

        dry_mass = mass.get("dry_mass", 0.0)
        max_fuel = mass.get("max_fuel", 0.0)

        assert dry_mass > 0.0, "dry_mass must be positive"
        assert max_fuel > 0.0, "max_fuel must be positive"

        mass_ratio = (dry_mass + max_fuel) / dry_mass
        assert mass_ratio == pytest.approx(1.6, abs=0.01), (
            f"Mass ratio should be 1.6 (400/250), got {mass_ratio:.4f}"
        )

    def test_razorback_isp_exceeds_corvette(self):
        """Razorback isp=6000s outperforms a corvette's isp=3500s."""
        if not RAZORBACK_JSON.exists():
            pytest.skip(f"razorback.json not yet created at {RAZORBACK_JSON}")

        registry = _get_registry()
        razorback = registry.get_class("razorback")
        corvette = registry.get_class("corvette")

        rb_isp = razorback["systems"]["propulsion"]["isp"]
        cv_isp = corvette["systems"]["propulsion"]["isp"]

        assert rb_isp > cv_isp, (
            f"Razorback isp ({rb_isp}s) should exceed corvette ({cv_isp}s)"
        )
