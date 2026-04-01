# tests/systems/test_environment.py
"""Tests for environmental hazards: asteroid fields, hazard zones, and the
environment manager that ties them together.

Coverage:
- Asteroid field generation (count, placement within radius)
- Ship-asteroid collision detection and damage scaling
- Projectile-asteroid obstruction
- Hazard zone containment, sensor modifiers, LOS blocking
- Torpedo degradation (debris damage, nebula datalink loss)
- Scenario YAML parsing via EnvironmentManager.load_from_scenario()
"""

import math
import pytest

from hybrid.environment.asteroid_field import AsteroidField, Asteroid
from hybrid.environment.hazard_zone import HazardZone, HazardType
from hybrid.environment.environment_manager import EnvironmentManager


# ---------------------------------------------------------------------------
# AsteroidField tests
# ---------------------------------------------------------------------------

class TestAsteroidField:
    """Tests for asteroid generation and collision detection."""

    def test_generation_count(self):
        """Field generates the requested number of asteroids."""
        af = AsteroidField(
            field_id="test", center={"x": 0, "y": 0, "z": 0},
            radius=10000, count=50, seed=42,
        )
        assert len(af.asteroids) == 50

    def test_generation_within_radius(self):
        """All asteroids are placed within the field's bounding sphere."""
        af = AsteroidField(
            field_id="test", center={"x": 1000, "y": 2000, "z": 3000},
            radius=5000, count=100, seed=99,
        )
        for ast in af.asteroids:
            dx = ast.position["x"] - af.center["x"]
            dy = ast.position["y"] - af.center["y"]
            dz = ast.position["z"] - af.center["z"]
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            assert dist <= af.radius + 1.0  # tiny float tolerance

    def test_generation_deterministic(self):
        """Same seed produces identical fields."""
        af1 = AsteroidField("a", {"x": 0, "y": 0, "z": 0}, 5000, 20, seed=7)
        af2 = AsteroidField("a", {"x": 0, "y": 0, "z": 0}, 5000, 20, seed=7)
        for a1, a2 in zip(af1.asteroids, af2.asteroids):
            assert a1.position == a2.position
            assert a1.radius == a2.radius

    def test_asteroid_radius_range(self):
        """Asteroid radii are within 10-500 m."""
        af = AsteroidField("t", {"x": 0, "y": 0, "z": 0}, 50000, 200, seed=1)
        for ast in af.asteroids:
            assert 10.0 <= ast.radius <= 500.0

    def test_tick_advances_position(self):
        """Asteroids drift by velocity * dt each tick."""
        af = AsteroidField("t", {"x": 0, "y": 0, "z": 0}, 10000, 1, seed=10)
        ast = af.asteroids[0]
        old_x = ast.position["x"]
        vx = ast.velocity["x"]
        af.tick(1.0)
        assert ast.position["x"] == pytest.approx(old_x + vx, abs=1e-6)

    def test_ship_collision_hit(self):
        """Ship overlapping an asteroid triggers collision."""
        af = AsteroidField("t", {"x": 0, "y": 0, "z": 0}, 10000, 0)
        # Manually place one asteroid at origin, radius 100m
        af.asteroids.append(Asteroid(
            id="manual", position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0}, radius=100, mass=1e6,
        ))
        # Ship at 50m from origin with radius 25m -- overlap (50 < 100+25)
        result = af.check_ship_collision(
            {"x": 50, "y": 0, "z": 0}, {"x": 500, "y": 0, "z": 0}, 25.0,
        )
        assert result is not None
        asteroid, rel_speed = result
        assert asteroid.id == "manual"
        assert rel_speed > 0

    def test_ship_collision_miss(self):
        """Ship far from asteroid reports no collision."""
        af = AsteroidField("t", {"x": 0, "y": 0, "z": 0}, 10000, 0)
        af.asteroids.append(Asteroid(
            id="far", position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0}, radius=100, mass=1e6,
        ))
        result = af.check_ship_collision(
            {"x": 5000, "y": 0, "z": 0}, {"x": 100, "y": 0, "z": 0}, 25.0,
        )
        assert result is None

    def test_projectile_obstruction_hit(self):
        """Projectile path passing through asteroid is obstructed."""
        af = AsteroidField("t", {"x": 0, "y": 0, "z": 0}, 10000, 0)
        af.asteroids.append(Asteroid(
            id="blocker", position={"x": 500, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0}, radius=200, mass=1e8,
        ))
        # Projectile travels from x=0 to x=1000, passing through asteroid at x=500
        hit = af.check_projectile_obstruction(
            {"x": 0, "y": 0, "z": 0}, {"x": 1000, "y": 0, "z": 0},
        )
        assert hit is not None
        assert hit.id == "blocker"

    def test_projectile_obstruction_miss(self):
        """Projectile path that misses asteroid is not obstructed."""
        af = AsteroidField("t", {"x": 0, "y": 0, "z": 0}, 10000, 0)
        af.asteroids.append(Asteroid(
            id="blocker", position={"x": 500, "y": 1000, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0}, radius=100, mass=1e8,
        ))
        hit = af.check_projectile_obstruction(
            {"x": 0, "y": 0, "z": 0}, {"x": 1000, "y": 0, "z": 0},
        )
        assert hit is None

    def test_get_state(self):
        """get_state returns serialisable dict."""
        af = AsteroidField("belt", {"x": 100, "y": 0, "z": 0}, 5000, 10, seed=1)
        state = af.get_state()
        assert state["field_id"] == "belt"
        assert len(state["asteroids"]) == 10
        assert "position" in state["asteroids"][0]
        assert "radius" in state["asteroids"][0]


# ---------------------------------------------------------------------------
# HazardZone tests
# ---------------------------------------------------------------------------

class TestHazardZone:
    """Tests for hazard zone containment and effects."""

    def test_contains_inside(self):
        """Position inside zone is contained."""
        hz = HazardZone("z1", {"x": 0, "y": 0, "z": 0}, 1000, "radiation")
        assert hz.contains({"x": 500, "y": 0, "z": 0})

    def test_contains_outside(self):
        """Position outside zone is not contained."""
        hz = HazardZone("z1", {"x": 0, "y": 0, "z": 0}, 1000, "radiation")
        assert not hz.contains({"x": 2000, "y": 0, "z": 0})

    def test_contains_boundary(self):
        """Position exactly on boundary is contained."""
        hz = HazardZone("z1", {"x": 0, "y": 0, "z": 0}, 1000, "radiation")
        assert hz.contains({"x": 1000, "y": 0, "z": 0})

    def test_radiation_sensor_modifier(self):
        """Radiation zone reduces sensor range significantly."""
        hz = HazardZone("rad", {"x": 0, "y": 0, "z": 0}, 1000, "radiation", intensity=1.0)
        mod = hz.get_sensor_modifier()
        assert mod < 0.5  # Severe reduction
        assert mod > 0.0  # Not zero (that's nebula)

    def test_nebula_sensor_modifier(self):
        """Nebula zone zeroes sensor range."""
        hz = HazardZone("neb", {"x": 0, "y": 0, "z": 0}, 1000, "nebula", intensity=1.0)
        mod = hz.get_sensor_modifier()
        assert mod == 0.0

    def test_debris_no_sensor_effect(self):
        """Debris zone doesn't affect sensors."""
        hz = HazardZone("deb", {"x": 0, "y": 0, "z": 0}, 1000, "debris", intensity=1.0)
        mod = hz.get_sensor_modifier()
        assert mod == 1.0

    def test_intensity_scales_modifier(self):
        """Lower intensity means less severe sensor penalty."""
        hz_full = HazardZone("r1", {"x": 0, "y": 0, "z": 0}, 1000, "radiation", intensity=1.0)
        hz_half = HazardZone("r2", {"x": 0, "y": 0, "z": 0}, 1000, "radiation", intensity=0.5)
        assert hz_half.get_sensor_modifier() > hz_full.get_sensor_modifier()

    def test_debris_munition_dps(self):
        """Debris zone deals positive DPS to munitions."""
        hz = HazardZone("deb", {"x": 0, "y": 0, "z": 0}, 1000, "debris", intensity=1.0)
        assert hz.get_munition_dps() > 0

    def test_radiation_no_munition_dps(self):
        """Radiation zone does not damage munitions."""
        hz = HazardZone("rad", {"x": 0, "y": 0, "z": 0}, 1000, "radiation")
        assert hz.get_munition_dps() == 0.0

    def test_nebula_blocks_los(self):
        """Nebula blocks line-of-sight."""
        hz = HazardZone("neb", {"x": 0, "y": 0, "z": 0}, 1000, "nebula")
        assert hz.blocks_los()

    def test_radiation_no_los_block(self):
        """Radiation does not block LOS."""
        hz = HazardZone("rad", {"x": 0, "y": 0, "z": 0}, 1000, "radiation")
        assert not hz.blocks_los()

    def test_nebula_blocks_datalink(self):
        """Nebula severs torpedo datalink."""
        hz = HazardZone("neb", {"x": 0, "y": 0, "z": 0}, 1000, "nebula")
        assert hz.blocks_datalink()

    def test_debris_no_datalink_block(self):
        """Debris does not affect datalink."""
        hz = HazardZone("deb", {"x": 0, "y": 0, "z": 0}, 1000, "debris")
        assert not hz.blocks_datalink()

    def test_unknown_type_defaults_debris(self):
        """Unknown hazard type falls back to debris."""
        hz = HazardZone("unk", {"x": 0, "y": 0, "z": 0}, 1000, "alien_goo")
        assert hz.hazard_type == HazardType.DEBRIS

    def test_get_state(self):
        """get_state returns serialisable dict."""
        hz = HazardZone("z1", {"x": 100, "y": 200, "z": 300}, 5000, "nebula", 0.7)
        state = hz.get_state()
        assert state["zone_id"] == "z1"
        assert state["hazard_type"] == "nebula"
        assert state["intensity"] == 0.7


# ---------------------------------------------------------------------------
# EnvironmentManager tests
# ---------------------------------------------------------------------------

class TestEnvironmentManager:
    """Tests for the central environment manager."""

    def test_load_from_scenario(self):
        """Parses scenario environment section correctly."""
        em = EnvironmentManager()
        em.load_from_scenario({
            "asteroid_fields": [
                {"id": "belt", "center": {"x": 0, "y": 0, "z": 0},
                 "radius": 10000, "count": 30, "seed": 1},
            ],
            "hazard_zones": [
                {"id": "rad1", "center": {"x": 5000, "y": 0, "z": 0},
                 "radius": 3000, "type": "radiation", "intensity": 0.8},
                {"id": "neb1", "center": {"x": -5000, "y": 0, "z": 0},
                 "radius": 4000, "type": "nebula"},
            ],
        })
        assert len(em.asteroid_fields) == 1
        assert len(em.hazard_zones) == 2
        assert em.asteroid_fields[0].field_id == "belt"
        assert em.hazard_zones[0].hazard_type == HazardType.RADIATION
        assert em.hazard_zones[1].hazard_type == HazardType.NEBULA

    def test_load_from_empty(self):
        """Loading None or empty dict is a no-op."""
        em = EnvironmentManager()
        em.load_from_scenario(None)
        em.load_from_scenario({})
        assert len(em.asteroid_fields) == 0
        assert len(em.hazard_zones) == 0

    def test_sensor_modifier_outside_zones(self):
        """Sensor modifier is 1.0 (no penalty) outside all zones."""
        em = EnvironmentManager()
        em.hazard_zones.append(
            HazardZone("rad", {"x": 10000, "y": 0, "z": 0}, 1000, "radiation"),
        )
        mod = em.get_sensor_modifier({"x": 0, "y": 0, "z": 0})
        assert mod == 1.0

    def test_sensor_modifier_inside_radiation(self):
        """Sensor modifier is reduced inside a radiation zone."""
        em = EnvironmentManager()
        em.hazard_zones.append(
            HazardZone("rad", {"x": 0, "y": 0, "z": 0}, 5000, "radiation", 1.0),
        )
        mod = em.get_sensor_modifier({"x": 100, "y": 0, "z": 0})
        assert mod < 1.0

    def test_sensor_modifier_worst_wins(self):
        """When inside multiple zones, the most severe modifier wins."""
        em = EnvironmentManager()
        em.hazard_zones.append(
            HazardZone("rad", {"x": 0, "y": 0, "z": 0}, 5000, "radiation", 0.5),
        )
        em.hazard_zones.append(
            HazardZone("neb", {"x": 0, "y": 0, "z": 0}, 5000, "nebula", 1.0),
        )
        mod = em.get_sensor_modifier({"x": 100, "y": 0, "z": 0})
        assert mod == 0.0  # Nebula wins

    def test_los_blocked_by_nebula(self):
        """LOS between two positions is blocked when nebula is between them."""
        em = EnvironmentManager()
        em.hazard_zones.append(
            HazardZone("neb", {"x": 500, "y": 0, "z": 0}, 200, "nebula"),
        )
        blocked = em.check_los_blocked(
            {"x": 0, "y": 0, "z": 0}, {"x": 1000, "y": 0, "z": 0},
        )
        assert blocked

    def test_los_not_blocked_by_radiation(self):
        """Radiation zones do not block LOS."""
        em = EnvironmentManager()
        em.hazard_zones.append(
            HazardZone("rad", {"x": 500, "y": 0, "z": 0}, 200, "radiation"),
        )
        blocked = em.check_los_blocked(
            {"x": 0, "y": 0, "z": 0}, {"x": 1000, "y": 0, "z": 0},
        )
        assert not blocked

    def test_los_not_blocked_when_nebula_offline(self):
        """Nebula off to the side does not block LOS."""
        em = EnvironmentManager()
        em.hazard_zones.append(
            HazardZone("neb", {"x": 500, "y": 5000, "z": 0}, 200, "nebula"),
        )
        blocked = em.check_los_blocked(
            {"x": 0, "y": 0, "z": 0}, {"x": 1000, "y": 0, "z": 0},
        )
        assert not blocked

    def test_torpedo_degradation_in_debris(self):
        """Torpedo inside debris zone takes damage."""
        em = EnvironmentManager()
        em.hazard_zones.append(
            HazardZone("deb", {"x": 0, "y": 0, "z": 0}, 5000, "debris", 1.0),
        )
        damage, datalink_lost = em.check_torpedo_degradation(
            {"x": 100, "y": 0, "z": 0}, dt=0.1,
        )
        assert damage > 0
        assert not datalink_lost

    def test_torpedo_degradation_in_nebula(self):
        """Torpedo inside nebula loses datalink but takes no damage."""
        em = EnvironmentManager()
        em.hazard_zones.append(
            HazardZone("neb", {"x": 0, "y": 0, "z": 0}, 5000, "nebula"),
        )
        damage, datalink_lost = em.check_torpedo_degradation(
            {"x": 100, "y": 0, "z": 0}, dt=0.1,
        )
        assert damage == 0.0
        assert datalink_lost

    def test_torpedo_degradation_outside_zones(self):
        """Torpedo outside all zones is unaffected."""
        em = EnvironmentManager()
        em.hazard_zones.append(
            HazardZone("deb", {"x": 50000, "y": 0, "z": 0}, 1000, "debris"),
        )
        damage, datalink_lost = em.check_torpedo_degradation(
            {"x": 0, "y": 0, "z": 0}, dt=0.1,
        )
        assert damage == 0.0
        assert not datalink_lost

    def test_projectile_obstruction_through_manager(self):
        """Manager delegates projectile obstruction to asteroid fields."""
        em = EnvironmentManager()
        af = AsteroidField("t", {"x": 0, "y": 0, "z": 0}, 10000, 0)
        af.asteroids.append(Asteroid(
            id="rock", position={"x": 500, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0}, radius=200, mass=1e8,
        ))
        em.asteroid_fields.append(af)

        hit = em.check_projectile_obstruction(
            {"x": 0, "y": 0, "z": 0}, {"x": 1000, "y": 0, "z": 0},
        )
        assert hit is not None
        assert hit.id == "rock"

    def test_get_state(self):
        """get_state produces serialisable telemetry dict."""
        em = EnvironmentManager()
        em.load_from_scenario({
            "asteroid_fields": [
                {"id": "belt", "center": {"x": 0, "y": 0, "z": 0},
                 "radius": 5000, "count": 5, "seed": 1},
            ],
            "hazard_zones": [
                {"id": "z1", "center": {"x": 0, "y": 0, "z": 0},
                 "radius": 3000, "type": "nebula"},
            ],
        })
        state = em.get_state()
        assert len(state["asteroid_fields"]) == 1
        assert len(state["hazard_zones"]) == 1
        assert state["asteroid_fields"][0]["field_id"] == "belt"
        assert state["hazard_zones"][0]["hazard_type"] == "nebula"

    def test_clear(self):
        """clear() removes all environment objects."""
        em = EnvironmentManager()
        em.load_from_scenario({
            "asteroid_fields": [
                {"id": "b", "center": {"x": 0, "y": 0, "z": 0},
                 "radius": 5000, "count": 5, "seed": 1},
            ],
            "hazard_zones": [
                {"id": "z", "center": {"x": 0, "y": 0, "z": 0},
                 "radius": 3000, "type": "debris"},
            ],
        })
        em.clear()
        assert len(em.asteroid_fields) == 0
        assert len(em.hazard_zones) == 0

    def test_tick_advances_asteroids(self):
        """Manager tick propagates to asteroid field ticks."""
        em = EnvironmentManager()
        af = AsteroidField("t", {"x": 0, "y": 0, "z": 0}, 10000, 0)
        af.asteroids.append(Asteroid(
            id="drifter", position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 10, "y": 0, "z": 0}, radius=50, mass=1e5,
        ))
        em.asteroid_fields.append(af)

        em.tick(1.0)
        assert af.asteroids[0].position["x"] == pytest.approx(10.0)
