# PHASE 4 GUI ENHANCEMENT: Full telemetry + cooldown + parsed returns + cooldown light + placeholder expansions

import tkinter as tk
from tkinter import ttk, scrolledtext
import subprocess
import json

SHIP_IDS = ["test_ship_001", "test_ship_002"]

# --- Command Runner ---
def run_command(command, args, ship, box=None, return_json=False):
    cmd = ["python", "send.py", "--ship", ship, command]
    for k, v in args.items():
        if v != "":
            cmd.extend([f"--{k}", str(v)])
    try:
        out = subprocess.run(cmd, capture_output=True, text=True)
        result = out.stdout.strip()
        parsed = None
        try:
            parsed = json.loads(result.replace("[RESPONSE]", "", 1).strip())
        except:
            parsed = None

        if box:
            box.config(state='normal')
            box.insert(tk.END, f"\n$ {' '.join(cmd)}\n{json.dumps(parsed, indent=2) if parsed else result}\n")
            box.see(tk.END)
            box.config(state='disabled')

        if return_json:
            return parsed
        return result

    except Exception as e:
        if box:
            box.config(state='normal')
            box.insert(tk.END, f"\n[ERROR] {e}\n")
            box.config(state='disabled')
        return ""

# --- GUI Layout ---
def create_gui():
    root = tk.Tk()
    root.title("Ship Console GUI")
    root.geometry("1400x800")

    ship_var = tk.StringVar(value=SHIP_IDS[0])

    left = ttk.Frame(root)
    left.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

    ttk.Label(left, text="Ship ID:").pack()
    ttk.Combobox(left, textvariable=ship_var, values=SHIP_IDS).pack(pady=5)

    # --- NAV Controls ---
    ttk.Label(left, text="Navigation").pack(pady=(10, 2))
    nav_frame = ttk.Frame(left)
    nav_frame.pack()
    nav_fields = {}
    for axis in ["x", "y", "z"]:
        ttk.Label(nav_frame, text=f"{axis.upper()}: ").grid(row=0, column={"x":0,"y":2,"z":4}[axis])
        nav_fields[axis] = ttk.Entry(nav_frame, width=6)
        nav_fields[axis].grid(row=0, column={"x":1,"y":3,"z":5}[axis])
    ttk.Button(left, text="Set Course", command=lambda: run_command("set_course", {k: nav_fields[k].get() for k in nav_fields}, ship_var.get(), output_box)).pack(pady=2)
    ttk.Button(left, text="Enable Autopilot", command=lambda: run_command("autopilot", {"enabled": 1}, ship_var.get(), output_box)).pack()

    # --- Thrust ---
    ttk.Label(left, text="Thrust Control").pack(pady=(10, 2))
    thrust_frame = ttk.Frame(left)
    thrust_frame.pack()
    thrust_fields = {}
    for axis in ["x", "y", "z"]:
        ttk.Label(thrust_frame, text=f"{axis.upper()}: ").grid(row=0, column={"x":0,"y":2,"z":4}[axis])
        thrust_fields[axis] = ttk.Entry(thrust_frame, width=6)
        thrust_fields[axis].grid(row=0, column={"x":1,"y":3,"z":5}[axis])
    ttk.Button(left, text="Set Thrust", command=lambda: run_command("set_thrust", {k: thrust_fields[k].get() for k in thrust_fields}, ship_var.get(), output_box)).pack(pady=2)
    ttk.Button(left, text="Manual Helm On", command=lambda: run_command("helm_override", {"enabled": 1}, ship_var.get(), output_box)).pack()

    # --- Sensors ---
    ttk.Label(left, text="Sensors & Bio").pack(pady=(10, 2))
    cooldown_label = ttk.Label(left, text="Cooldown: N/A", foreground="blue")
    cooldown_label.pack()
    def ping_and_check():
        parsed = run_command("ping_sensors", {}, ship_var.get(), output_box, return_json=True)
        if parsed:
            cooldown = parsed.get("cooldown_started") or parsed.get("error")
            cooldown_label.config(text=f"Cooldown: {cooldown}")
    ttk.Button(left, text="Ping Sensors", command=ping_and_check).pack(pady=1)
    ttk.Button(left, text="Override Bio Monitor", command=lambda: run_command("override_bio_monitor", {}, ship_var.get(), output_box)).pack(pady=1)

    # --- Output Panels ---
    right = ttk.Frame(root)
    right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

    output_box = scrolledtext.ScrolledText(right, height=10, state='disabled')
    output_box.pack(fill=tk.BOTH, expand=True)
    ttk.Label(right, text="Raw Output Log").pack()

    state_frame = ttk.LabelFrame(right, text="Live Ship State")
    state_frame.pack(fill=tk.X, padx=5, pady=5)

    state_vars = {}
    for field in ["pitch", "yaw", "roll", "vx", "vy", "vz", "gx", "tx", "ty", "tz", "wx", "wy", "wz", "spike"]:
        row = ttk.Frame(state_frame)
        row.pack(fill=tk.X, padx=2, pady=1)
        ttk.Label(row, text=f"{field.upper()}:", width=8).pack(side=tk.LEFT)
        var = tk.StringVar()
        ttk.Entry(row, textvariable=var, width=20, state="readonly").pack(side=tk.LEFT)
        state_vars[field] = var

    contacts_output = scrolledtext.ScrolledText(right, height=6, state='disabled')
    contacts_output.pack(fill=tk.X)
    ttk.Label(right, text="Sensor Contacts").pack()

    def refresh_panels():
        parsed = run_command("get_state", {}, ship_var.get(), output_box, return_json=True)
        if parsed:
            state_vars["pitch"].set(parsed["orientation"].get("pitch", 0))
            state_vars["yaw"].set(parsed["orientation"].get("yaw", 0))
            state_vars["roll"].set(parsed["orientation"].get("roll", 0))
            state_vars["vx"].set(parsed["velocity"].get("x", 0))
            state_vars["vy"].set(parsed["velocity"].get("y", 0))
            state_vars["vz"].set(parsed["velocity"].get("z", 0))
            state_vars["gx"].set(parsed["bio_monitor"].get("current_g", 0))
            thrust = parsed.get("thrust", {})
            state_vars["tx"].set(thrust.get("x", 0))
            state_vars["ty"].set(thrust.get("y", 0))
            state_vars["tz"].set(thrust.get("z", 0))
            angv = parsed.get("angular_velocity", {})
            state_vars["wx"].set(angv.get("pitch", 0))
            state_vars["wy"].set(angv.get("yaw", 0))
            state_vars["wz"].set(angv.get("roll", 0))
            state_vars["spike"].set(parsed.get("sensors", {}).get("spike_until", ""))
            cooldown_val = parsed.get("sensors", {}).get("active", {}).get("cooldown")
            if cooldown_val is not None:
                cooldown_label.config(text=f"Cooldown: {cooldown_val:.1f}s")

        contacts = run_command("get_contacts", {}, ship_var.get(), output_box, return_json=True)
        contacts_output.config(state='normal')
        contacts_output.delete("1.0", tk.END)
        if contacts and contacts.get("contacts"):
            for c in contacts["contacts"]:
                contacts_output.insert(tk.END, f"{c.get('target_id', '?')} @ {c.get('distance', '?')} km [{c.get('method', '?')}]\n")
        else:
            contacts_output.insert(tk.END, "No contacts or sensor failure.\n")
        contacts_output.config(state='disabled')

    ttk.Button(left, text="Refresh Panels", command=refresh_panels).pack(pady=8)

    root.mainloop()

if __name__ == "__main__":
    create_gui()
