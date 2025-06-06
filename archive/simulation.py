# simulation.py
import numpy as np
from systems_tick import tick_all_systems
from utils.logger import logger
from math import radians

def simulation_loop(sectors, dt=0.1):
    """Main simulation loop that updates all ships in all sectors"""
    while True:
        # Flatten ships list for system-wide interactions
        all_ships = [ship for sector in sectors.values() for ship in sector]

        # Process each ship in each sector
        for sector_key, ships in sectors.items():
            for ship in ships:
                update_orientation(ship, dt)
                update_position(ship, dt)
                tick_all_systems(ship, all_ships, dt)

                # Log ship position
                pos = ship.position
                logger.debug(f"[TICK] {ship.id} in sector {sector_key} @ ({pos['x']:.2f}, {pos['y']:.2f}, {pos['z']:.2f})")
        yield

def update_orientation(ship, dt):
    """Update ship orientation based on angular velocity"""
    for axis in ["pitch", "yaw", "roll"]:
        # Get current angular velocity (default to 0 if not set)
        angular_vel = ship.angular_velocity.get(axis, 0.0)
        
        # Update orientation
        ship.orientation[axis] += angular_vel * dt
        
        # Normalize to 0-360 degrees
        ship.orientation[axis] %= 360.0

def update_position(ship, dt):
    """Update ship position based on thrust and physics"""
    # Convert orientation to radians
    pitch = radians(ship.orientation["pitch"])
    yaw = radians(ship.orientation["yaw"])
    roll = radians(ship.orientation["roll"])

    # Determine thrust vector
    if ship.systems.get("navigation", {}).get("helm_override"):
        thrust = ship.thrust
    else:
        # Get thrust from propulsion system or use zero thrust as default
        thrust = ship.systems["propulsion"]["main_drive"].get("thrust", {"x": 0.0, "y": 0.0, "z": 0.0})

    # Extract thrust components
    tx, ty, tz = thrust["x"], thrust["y"], thrust["z"]
    
    # Rotate thrust vector to world coordinates
    thrust_world = rotate_vector(tx, ty, tz, pitch, yaw, roll)

    # Calculate acceleration (F = ma)
    ax = thrust_world[0] / ship.mass
    ay = thrust_world[1] / ship.mass
    az = thrust_world[2] / ship.mass
    
    # Store acceleration for other systems (like bio_monitor)
    ship.acceleration = {"x": ax, "y": ay, "z": az}

    # Update velocity (v = v₀ + a·t)
    ship.velocity["x"] += ax * dt
    ship.velocity["y"] += ay * dt
    ship.velocity["z"] += az * dt

    # Update position (p = p₀ + v·t)
    ship.position["x"] += ship.velocity["x"] * dt
    ship.position["y"] += ship.velocity["y"] * dt
    ship.position["z"] += ship.velocity["z"] * dt

def rotate_vector(x, y, z, pitch, yaw, roll):
    """
    Rotate a vector from ship coordinates to world coordinates
    Using rotation matrices for better performance and clarity
    """
    # Create rotation matrices
    # Roll rotation (around x-axis)
    roll_matrix = np.array([
        [1, 0, 0],
        [0, np.cos(roll), -np.sin(roll)],
        [0, np.sin(roll), np.cos(roll)]
    ])
    
    # Pitch rotation (around y-axis)
    pitch_matrix = np.array([
        [np.cos(pitch), 0, np.sin(pitch)],
        [0, 1, 0],
        [-np.sin(pitch), 0, np.cos(pitch)]
    ])
    
    # Yaw rotation (around z-axis)
    yaw_matrix = np.array([
        [np.cos(yaw), -np.sin(yaw), 0],
        [np.sin(yaw), np.cos(yaw), 0],
        [0, 0, 1]
    ])
    
    # Original vector
    vec = np.array([x, y, z])
    
    # Apply rotations in sequence (roll, then pitch, then yaw)
    rotated_vec = yaw_matrix @ pitch_matrix @ roll_matrix @ vec
    
    return tuple(rotated_vec)
