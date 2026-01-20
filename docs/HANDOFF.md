# HANDOFF
## Demo Slice Status
- D1–D6: Not validated this session.
- Platform parity: Desktop ✅ (tests + smoke script), Android ⚠️ (on-device run pending).
## What Works (exact commands)
- `python -m pytest -q`
- `python tools/android_smoke.py`
## What’s Broken (max 3)
- `server.run_server` telemetry still logs `ActiveSensor` serialization errors (known issue in `docs/KNOWN_ISSUES.md`).
- Inline socket probe in validation script reported `/bin/bash: line 4: python: command not found` when run in a multi-line command block.
## Next 1–3 Actions
1) Run `python tools/android_smoke.py` on a real Android/Pydroid device and capture output.
2) If feasible, run `python -m server.run_server --host 127.0.0.1 --port 8765` and a loopback socket probe on-device.
3) Investigate why inline `python - <<'PY'` failed in the validation block despite `python` being available.
## Guardrails (Do Not Touch)
- Avoid UI dependencies in core sim/server modules to preserve Android parity.
