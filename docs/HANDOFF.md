# HANDOFF
## Demo Slice Status
- D1 (Two-ship fleet boots reliably): ✅ Verified via smoke tests
- D2–D6: Not validated this session (would require multi-client integration tests)
- D7 (Desktop demo repeatable): ✅ All smoke tests pass cleanly
- Platform parity: Desktop ✅, Android ✅ (smoke tests pass, on-device run pending)
## What Works (exact commands)
- `python -m pytest -q` — 134 tests pass
- `python tools/desktop_demo_smoke.py` — Server starts, client connects, 2 ships loaded
- `python tools/android_smoke.py` — Core sim import + tick works
- `python tools/android_socket_smoke.py` — Loopback server + client works
- `python -m server.run_server --port 8765` — Server runs without errors
## What's Broken (max 3)
- None currently blocking demo slice
## Next 1–3 Actions
1) Run `python tools/android_smoke.py` on a real Android/Pydroid device and capture output.
2) Run `python tools/android_socket_smoke.py` on-device to confirm loopback socket connectivity.
3) Validate D2–D6 requirements (multi-client, stations, combat) with integration tests or manual demo script.
## Guardrails (Do Not Touch)
- Avoid UI dependencies in core sim/server modules to preserve Android parity.
