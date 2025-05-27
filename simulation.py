# simulation.py
from utils.logger import logger
from math import radians, cos, sin

def simulation_loop(sectors, dt=0.1):
    while True:
        for sector_key, ships in sectors.items():
            for ship in ships:
                update_orientation(ship, dt)
                update_position(ship, dt)
                pos = ship.position
                logger.debug(f"[TICK] {ship.id} in sector {sector_key} @ ({pos['x']:.2f}, {pos['y']:.2f}, {pos['z']:.2f})")
        yield

def update_orientation(ship, dt):
    for axis in ["pitch", "yaw", "roll"]:
        ship.orientation[axis] += ship.angular_velocity.get(axis, 0.0) * dt
        ship.orientation[axis] %= 360.0

def update_position(ship, dt):
    pitch = radians(ship.orientation["pitch"])
    yaw = radians(ship.orientation["yaw"])
    roll = radians(ship.orientation["roll"])

    tx, ty, tz = ship.thrust["x"], ship.thrust["y"], ship.thrust["z"]
    thrust_world = rotate_vector(tx, ty, tz, pitch, yaw, roll)

    ax, ay, az = (thrust_world[0] / ship.mass,
                  thrust_world[1] / ship.mass,
                  thrust_world[2] / ship.mass)

    ship.velocity["x"] += ax * dt
    ship.velocity["y"] += ay * dt
    ship.velocity["z"] += az * dt

    ship.position["x"] += ship.velocity["x"] * dt
    ship.position["y"] += ship.velocity["y"] * dt
    ship.position["z"] += ship.velocity["z"] * dt

def rotate_vector(x, y, z, pitch, yaw, roll):
    x1 = x*cos(roll) - y*sin(roll)
    y1 = x*sin(roll) + y*cos(roll)
    z1 = z

    x2 = x1
    y2 = y1*cos(pitch) - z1*sin(pitch)
    z2 = y1*sin(pitch) + z1*cos(pitch)

    x3 = x2*cos(yaw) + z2*sin(yaw)
    y3 = y2
    z3 = -x2*sin(yaw) + z2*cos(yaw)

    return (x3, y3, z3)
