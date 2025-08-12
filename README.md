# Spacesim — Sprint 2 (Reissue)
Hard sci‑fi sim (Expanse‑inspired). This drop includes missiles/torps/nukes, ECM/ECCM, and auto point-defense (PDC), plus a simple HUD and TCP sim server.

## Quickstart
```bash
python -m pip install pytest
python -m pytest -q

# Terminal 1: start server
python -m server.run_server --fleet-dir hybrid_fleet --dt 0.1 --port 8765

# Terminal 2: HUD
python hybrid/gui/gui.py
```

## Demo
- **Interceptor** (torp launcher) vs **Target** (PDC + ECM=0.4, evasive AI).
- In HUD: click `Target` to lock, press **F** to fire, **P** to ping, **A** toggle autopilot, **R** record.

## What’s in Sprint 2
- **Missiles/Torps/Nukes**: PN-like guidance; seeker FOV; ECM/ECCM (wider FOV + turn authority); proximity fusing; nuke AoE.
- **Point Defense**: Automatic engagement inside arc/range/FOV.
- **Server API**: `get_state`, `get_events`, `get_mission`, `fire_weapon`, `set_target`, `ping_sensors`, recording controls.
