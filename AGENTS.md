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
| `hybrid/simulator.py` | Main simulation loop ticking all ships |
| `hybrid/cli.py` | Command line interface for sending ship commands |
| `hybrid/ship_factory.py` | Instantiates ship systems from configuration |
| `hybrid/systems/power/management.py` | Handles reactors, buses, and toggles |
| `hybrid/gui/run_gui.py` | Optional Tkinter frontend |

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
The simulator tick loop already calls `tick()` on each system, so no manual
call is required from the caller.
```python
# handled inside Ship.tick()
```

---

🧪 CLI Commands (via `hybrid.cli`)

```bash
python -m hybrid.cli --ship test_ship_001 --command '{"command": "get_power_state"}'
python -m hybrid.cli --ship test_ship_001 --command '{"command": "set_power_profile", "profile": "offensive"}'
python -m hybrid.cli --ship test_ship_001 --command '{"command": "get_power_profiles"}'
python -m hybrid.cli --ship test_ship_001 --command '{"command": "set_power_allocation", "allocation": {"primary": 0.5, "secondary": 0.3, "tertiary": 0.2}}'
```

All commands update the live ship state through the power system.

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

[ ] Extend `hybrid.cli` to include power profiles or presets

[ ] Add get_draw_profile command to summarize draw state by bus

---
