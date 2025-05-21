# spaceship_sim/sim/rcs.py
def rotate_axis(ship, axis, angle):
    if ship['systems'].get('reaction_control_system') != 'online':
        raise Exception("RCS is offline")

    if axis not in ['pitch', 'yaw', 'roll']:
        raise ValueError("Invalid axis for rotation")

    # Apply rotation
    ship['orientation'][axis] += angle

    # Clamp to [-180, 180] for clarity
    if ship['orientation'][axis] > 180:
        ship['orientation'][axis] -= 360
    elif ship['orientation'][axis] < -180:
        ship['orientation'][axis] += 360

    ship['event_log'].append({
        'event': 'rotate',
        'axis': axis,
        'angle': angle
    })

    print(f"[INFO] Rotated {axis} by {angle} degrees.")
