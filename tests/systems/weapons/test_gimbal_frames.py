"""Exercise real firing solutions on rotated, rate-limited weapon mounts.

Geometry uses the heading convention of the existing firing-arc contract.
Expected body angles come from specified local vectors, rather than from
the world-to-body bearing helper being tested through the weapon pipeline.
"""

import math

import pytest

from hybrid.systems.combat.projectile_manager import ProjectileManager
from hybrid.systems.power_system import PowerSystem
from hybrid.systems.weapons.truth_weapons import create_railgun, create_pdc
from hybrid.utils.quaternion import Quaternion


ORIGIN = {"x": 1200.0, "y": -800.0, "z": 400.0}
ZERO = {"x": 0.0, "y": 0.0, "z": 0.0}


def _mount(factory=create_railgun):
    weapon = factory()
    weapon.gimbal_enabled = True
    weapon._gimbal_max_rate = weapon.specs.tracking_speed
    weapon._gimbal_az_limits = (-30.0, 30.0)
    weapon._gimbal_el_limits = (-15.0, 25.0)
    weapon.firing_arc = {
        "azimuth_min": -30.0, "azimuth_max": 30.0,
        "elevation_min": -15.0, "elevation_max": 25.0,
    }
    return weapon


def _direction(yaw, pitch, distance):
    yaw, pitch = math.radians(yaw), math.radians(pitch)
    return (distance * math.cos(pitch) * math.cos(yaw),
            distance * math.cos(pitch) * math.sin(yaw),
            distance * math.sin(pitch))


def _world_vector(heading, body_vector):
    # Forward rotation constructs the fixture independently of the
    # inverse rotation used by firing-arc and gimbal aim calculations.
    rotation = Quaternion.from_euler(
        -heading["pitch"], heading["yaw"], heading["roll"]
    )
    return dict(zip(("x", "y", "z"), rotation.rotate_vector(body_vector)))


def _target(heading, yaw, pitch, distance=1000.0):
    offset = _world_vector(heading, _direction(yaw, pitch, distance))
    return {axis: ORIGIN[axis] + offset[axis] for axis in ORIGIN}


def _solution(weapon, target, heading, sim_time=0.0, target_vel=None):
    return weapon.calculate_solution(
        shooter_pos=ORIGIN, shooter_vel=ZERO,
        target_pos=target, target_vel=target_vel or ZERO,
        target_id="contact_1", sim_time=sim_time,
        shooter_heading=heading,
    )


@pytest.mark.parametrize("factory", [create_railgun, create_pdc])
@pytest.mark.parametrize("heading", [
    {"pitch": 0.0, "yaw": 90.0, "roll": 0.0},
    {"pitch": 40.0, "yaw": 0.0, "roll": 0.0},
    {"pitch": 0.0, "yaw": 0.0, "roll": 90.0},
    {"pitch": 25.0, "yaw": 125.0, "roll": -40.0},
], ids=["yaw", "pitch", "roll", "combined"])
def test_rotated_mount_tracks_body_angles(factory, heading):
    weapon = _mount(factory)
    target = _target(heading, yaw=10.0, pitch=8.0)
    solution = _solution(weapon, target, heading)
    world_lead = dict(solution.lead_angle)
    world_intercept = dict(solution.intercept_point)
    assert solution.in_arc

    # Tick the real slew and charge state machines before checking ready.
    for step in range(1, 26):
        weapon.tick(0.1, step * 0.1)
        solution = _solution(weapon, target, heading, step * 0.1)

    assert weapon.current_azimuth == pytest.approx(10.0)
    assert weapon.current_elevation == pytest.approx(8.0)
    assert solution.tracking
    assert solution.ready_to_fire
    assert solution.lead_angle == pytest.approx(world_lead)
    assert solution.intercept_point == pytest.approx(world_intercept)


@pytest.mark.parametrize("yaw,pitch,in_arc", [
    (29.999999, 0.0, True), (30.000001, 0.0, False),
    (-29.999999, 0.0, True), (-30.000001, 0.0, False),
    (0.0, 24.999999, True), (0.0, 25.000001, False),
    (0.0, -14.999999, True), (0.0, -15.000001, False),
])
def test_rotated_mount_preserves_arc_edges_and_clamps(yaw, pitch, in_arc):
    heading = {"pitch": 20.0, "yaw": 100.0, "roll": -35.0}
    weapon = _mount()
    target = _target(heading, yaw, pitch)
    solution = _solution(weapon, target, heading)
    for step in range(1, 26):
        weapon.tick(0.1, step * 0.1)
        solution = _solution(weapon, target, heading, step * 0.1)

    assert solution.in_arc is in_arc
    assert weapon.current_azimuth == pytest.approx(max(-30.0, min(30.0, yaw)))
    assert weapon.current_elevation == pytest.approx(max(-15.0, min(25.0, pitch)))
    if not in_arc:
        assert not solution.ready_to_fire


def test_hull_turn_changes_body_aim_with_existing_slew_rate():
    weapon = _mount()
    heading = {"pitch": 0.0, "yaw": 90.0, "roll": 0.0}
    target = _target(heading, yaw=0.0, pitch=0.0)
    _solution(weapon, target, heading)
    weapon.tick(0.1, 0.1)
    assert weapon.current_azimuth == pytest.approx(0.0)

    heading["yaw"] = 75.0  # Same world target is now 15 degrees off the bow.
    _solution(weapon, target, heading, 0.1)
    weapon.tick(0.1, 0.2)
    solution = _solution(weapon, target, heading, 0.2)
    assert weapon.current_azimuth == pytest.approx(1.5)  # 15 deg/s * 0.1 s
    assert not solution.tracking
    assert not solution.ready_to_fire

    for step in range(3, 26):
        weapon.tick(0.1, step * 0.1)
        solution = _solution(weapon, target, heading, step * 0.1)
    assert weapon.current_azimuth == pytest.approx(15.0)
    assert solution.tracking
    assert solution.ready_to_fire


def test_moving_target_keeps_world_ballistics_and_real_fire_gates():
    heading = {"pitch": 20.0, "yaw": 110.0, "roll": 35.0}
    weapon = _mount()
    target = _target(heading, yaw=10.0, pitch=5.0, distance=10000.0)
    target_vel = _world_vector(heading, (0.0, 200.0, 50.0))
    power = PowerSystem({"initial": 50.0})
    projectiles = ProjectileManager()
    solution = _solution(weapon, target, heading, target_vel=target_vel)
    assert not solution.ready_to_fire
    assert weapon.fire(0.0, power)["reason"] == "charging"
    assert power.stored_power == 50.0

    for step in range(1, 26):
        weapon.tick(0.1, step * 0.1)
        solution = _solution(weapon, target, heading, step * 0.1, target_vel)
    assert solution.ready_to_fire
    assert solution.intercept_point == pytest.approx({
        axis: target[axis] + target_vel[axis] * solution.time_of_flight
        for axis in target
    })
    aim = {axis: solution.intercept_point[axis] - ORIGIN[axis] for axis in ORIGIN}
    aim_length = math.sqrt(sum(v * v for v in aim.values()))
    assert aim_length == pytest.approx(weapon.specs.muzzle_velocity * solution.time_of_flight)

    ammo_before = weapon.ammo
    result = weapon.fire(2.5, power, projectile_manager=projectiles,
                         shooter_pos=ORIGIN, shooter_vel=ZERO, ship_id="shooter")
    assert result["ok"]
    assert projectiles.active_count == 1
    projectile = projectiles._projectiles[0]
    assert projectile.velocity == pytest.approx({
        axis: value / aim_length * weapon.specs.muzzle_velocity
        for axis, value in aim.items()
    })
    assert weapon.ammo == ammo_before - 1
    assert weapon.heat > 0.0
    assert power.stored_power == 50.0 - weapon.specs.power_per_shot
    assert weapon.fire(2.5, power)["reason"] == "cycling"
