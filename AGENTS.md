# 🧠 Project Overview
Flaxos Spaceship Sim is a modular 3D spaceflight simulator with a tactical command layer. Ships simulate real-world movement, system loadouts, and now realistic power management using kinetic units (kW).

This document helps AI agents (e.g. Codex, ChatGPT) understand project structure, conventions, and how/where to inject or extend logic.

---

## 📦 Version: `v0.5.0`
- ✅ Realistic Power Management System added (warm-up, output ramp, battery, bus allocation)
- ✅ CLI commands for power routing, toggling systems
- ✅ System draw modeled in physical units (kW)
- 🛠️ GUI sliders + visual power meters TBD in `v0.5.1`

---

## 📁 Key Files and Roles

| File | Purpose |
|------|---------|
| `tick.py` | Runs ship simulation tick per frame. Hook power system here. |
| `send.py` | CLI entry point for ship commands (e.g., `reactor_start`, `toggle_system`) |
| `ship_factory.py` | Instantiates ship objects and injects system logic from `systems_schema.py` |
| `systems_schema.py` | Defines default system values, including power specs per ship |
| `power_management.py` | New: Handles reactor warm-up, battery, bus distribution, and system toggles |
| `gui.py` | Optional: Future GUI frontend (Tkinter); not yet integrated with power system |

---

## ⚡ Power Management System

### Structure
- `Reactor` ramps output over time:
  - States: `COLD → SPOOLING_UP → READY`
  - Max output in kW (e.g., 1000 kW)
  - Ramp rate = max_output / 10 per tick

- `PowerBus` (3 types):
  - `primary`: propulsion, railgun, active sensors
  - `secondary`: RCS, PDC, drones, comms (battery-powered)
  - `tertiary`: life support, nav computer, bio monitor (low draw)

- `Battery`: powers secondary bus, charges/discharges each tick

- `PowerManagementSystem`:
  - Receives reactor output
  - Allocates based on `power_allocation` ratios
  - Tracks draw/supply and toggled systems

### Tick Integration
Call this in `tick.py`:
```python
ship.power_system.tick()
```

---

🧪 CLI Commands (defined in send.py)

python send.py reactor_start --ship test_ship_001
python send.py get_power_status --ship test_ship_001
python send.py toggle_system --ship test_ship_001 --system railgun --state 0
python send.py set_power_allocation --ship test_ship_001 --primary 0.5 --secondary 0.3 --tertiary 0.2

All commands modify the ship’s live state via ship.power_system.

---

🧠 Agent Notes

Units are kinetic (kW) — do not use percentages for draw; only for bus allocation.

All systems have .enabled flags and power_draw values.

Buses are modular and can be extended.

Battery handles overflow/underflow for secondary.

GUI and CLI should share the same internal logic (e.g., use power_system.toggle_system()).

Avoid hardcoding bus or system names; they come from systems_schema.py.

---

📌 TODOs / Future Work

[ ] GUI integration: sliders for allocation, system toggles, meters

[ ] Auto-shutdown on low battery

[ ] Optional: Reactor fuel use or overheat modeling

[ ] Extend send.py to include power profiles or presets

[ ] Add get_draw_profile command to summarize draw state by bus

---
