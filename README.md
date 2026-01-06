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

## Android/Pydroid UAT (TCP JSON)
The sim server speaks **newline-delimited JSON over TCP** (one JSON object per line). The Android UI can run in Pydroid and connect over your LAN.

### 1) Install dependencies in Pydroid
```bash
pip install numpy pyyaml flask
```

### 2) Start the server (desktop recommended)
Run the sim server from your desktop/laptop so it can host the simulation loop:
```bash
python -m server.run_server --fleet-dir hybrid_fleet --dt 0.1 --host 0.0.0.0 --port 8765
```

> If you must run the server on Android, use the same entrypoint/flags in Pydroid; just be mindful of device performance.

### 3) Run the Android UI client (Pydroid)
From the repo root on the Android device:
```bash
python mobile_ui/app.py
```
Then open `http://<android-ip>:5000` in a mobile browser. Use the form to set the sim server host/port.

#### Optional: all-in-one runtime (server + UI in one command)
If you want a single Pydroid command that runs both the sim server and the mobile UI:
```bash
python pydroid_run.py --server-host 127.0.0.1 --server-port 8765 --ui-port 5000
```
Then open `http://<android-ip>:5000` and set the host/port to `127.0.0.1:8765`.

### 4) Port/host + LAN requirements
- **Server host/port:** bind to `0.0.0.0:8765` on the desktop to accept LAN traffic.
- **Client host/port:** in the UI, set host to the desktop's LAN IP (e.g. `192.168.1.20`) and port `8765`.
- **Network:** both devices must be on the same Wi‑Fi/LAN and firewall must allow TCP 8765.

### Smoke test (connectivity)
Run from any machine on the LAN (including Pydroid) to verify the TCP JSON protocol:
```bash
python - <<'PY'
import json, socket
host = "192.168.1.20"  # replace with your server IP
port = 8765
with socket.create_connection((host, port), timeout=3) as sock:
    sock.sendall((json.dumps({"cmd": "get_state"}) + "\n").encode())
    print(sock.recv(4096).decode().strip())
PY
```

## Demo
- **Interceptor** (torp launcher) vs **Target** (PDC + ECM=0.4, evasive AI).
- In HUD: click `Target` to lock, press **F** to fire, **P** to ping, **A** toggle autopilot, **R** record.

## What’s in Sprint 2
- **Missiles/Torps/Nukes**: PN-like guidance; seeker FOV; ECM/ECCM (wider FOV + turn authority); proximity fusing; nuke AoE.
- **Point Defense**: Automatic engagement inside arc/range/FOV.
- **Server API**: `get_state`, `get_events`, `get_mission`, `fire_weapon`, `set_target`, `ping_sensors`, recording controls.
