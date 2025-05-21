# spaceship_sim/sim/physics.py

import math

def orientation_to_unit_vector(orientation):
    """Convert pitch/yaw in degrees to a normalized forward vector."""
    pitch_rad = math.radians(orientation['pitch'])
    yaw_rad = math.radians(orientation['yaw'])

    x = math.cos(pitch_rad) * math.cos(yaw_rad)
    y = math.sin(pitch_rad)
    z = math.cos(pitch_rad) * math.sin(yaw_rad)

    magnitude = math.sqrt(x**2 + y**2 + z**2)
    return {'x': x / magnitude, 'y': y / magnitude, 'z': z / magnitude}

def update_position(ship, dt):
    orientation = ship['orientation']
    throttle = ship['throttle']
    mass = ship['mass']
    max_thrust = 500000  # Newtons, could be loaded from config

    # If throttle is zero, just apply velocity to position
    if throttle > 0:
        thrust_force = max_thrust * throttle
        acceleration = thrust_force / mass

        forward = orientation_to_unit_vector(orientation)

        # Apply acceleration to velocity
        ship['velocity']['x'] += forward['x'] * acceleration * dt
        ship['velocity']['y'] += forward['y'] * acceleration * dt
        ship['velocity']['z'] += forward['z'] * acceleration * dt

    # Apply velocity to position
    ship['position']['x'] += ship['velocity']['x'] * dt
    ship['position']['y'] += ship['velocity']['y'] * dt
    ship['position']['z'] += ship['velocity']['z'] * dt

    # Log movement
    ship['event_log'].append({
        'event': 'tick',
        'position': ship['position'].copy(),
        'velocity': ship['velocity'].copy()
    })

    print(f"[TICK] Position updated to x={ship['position']['x']:.1f}, y={ship['position']['y']:.1f}, z={ship['position']['z']:.1f}")
