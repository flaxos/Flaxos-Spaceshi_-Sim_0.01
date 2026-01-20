# Demo Slice Runbook

This runbook captures the minimum repeatable steps to exercise the demo slice on
desktop Python and Android/Pydroid.

## Desktop Demo (CLI + Socket)

1. Install dependencies (optional but recommended):

   ```bash
   pip install -r requirements.txt
   ```

2. Start the TCP server:

   ```bash
   python -m server.run_server --port 8765
   ```

3. In another terminal, send a minimal request:

   ```bash
   python - <<'PY'
import socket, json
s = socket.create_connection(("localhost", 8765), 5)
s.sendall((json.dumps({"cmd":"get_state"}) + "\n").encode("utf-8"))
print(s.recv(4096).decode("utf-8", "replace"))
PY
   ```

## Android / Pydroid Demo (Parity Smoke Test)

> Goal: verify core imports + sim tick work on Android (no GUI deps).

1. Copy the repo to your device (Git clone, or transfer the folder).
2. In Pydroid, install dependencies if needed:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the Android-safe smoke test:

   ```bash
   python tools/android_smoke.py
   ```

Expected output (example):

```json
{
  "ok": true,
  "ticks": 3,
  "dt": 0.1,
  "time": 0.30000000000000004,
  "ship": "sample_ship",
  "position": {"x": 0.0, "y": 0.0, "z": 0.0},
  "velocity": {"x": 0.0, "y": 0.0, "z": 0.0}
}
```

### Optional: Android Loopback Socket Smoke

If your device supports local TCP loopback in Pydroid, you can also run:

```bash
python -m server.run_server --host 127.0.0.1 --port 8765
```

And in another Pydroid terminal/session:

```bash
python - <<'PY'
import socket, json
s = socket.create_connection(("127.0.0.1", 8765), 5)
s.sendall((json.dumps({"cmd":"get_state"}) + "\n").encode("utf-8"))
print(s.recv(4096).decode("utf-8", "replace"))
PY
```
