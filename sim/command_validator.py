# spaceship_sim/commands/handlers.py

from sim.rcs import rotate_axis
from sim.command_validator import validate_command

def handle_command(ship, input_str):
    parts = input_str.strip().split()
    if not parts:
        print("[WARN] Empty command.")
        return

    command = parts[0]
    args = parts[1:]

    # Validate against command registry
    try:
        validate_command(ship, command)
    except Exception as e:
        print(f"[BLOCKED] {e}")
        return

    if command == "set_throttle":
        try:
            throttle = float(args[0])
            if not 0.0 <= throttle <= 1.0:
                raise ValueError
            ship['throttle'] = throttle
            ship['event_log'].append({'event': 'set_throttle', 'value': throttle})
            print(f"[INFO] Throttle set to {throttle}")
        except (IndexError, ValueError):
            print("[ERROR] Usage: set_throttle <0.0 to 1.0>")

    elif command in ["rotate_pitch", "rotate_yaw", "rotate_roll"]:
        try:
            axis = command.split("_")[1]
            angle = float(args[0])
            rotate_axis(ship, axis, angle)
        except (IndexError, ValueError) as e:
            print(f"[ERROR] Usage: {command} <angle_in_degrees>")
            print(f"[DEBUG] {e}")

    elif command == "get_position":
        pos = ship['position']
        print(f"[POSITION] x={pos['x']:.2f}, y={pos['y']:.2f}, z={pos['z']:.2f}")

    elif command == "get_orientation":
        ori = ship['orientation']
        print(f"[ORIENTATION] pitch={ori['pitch']:.1f}, yaw={ori['yaw']:.1f}, roll={ori['roll']:.1f}")

    else:
        print(f"[ERROR] Unknown command: {command}")
