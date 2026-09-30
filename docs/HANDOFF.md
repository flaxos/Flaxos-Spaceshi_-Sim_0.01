# HANDOFF

## Delivery review and owner decision — 2026-10-01

Current scope is roadmap item 1 only: finish the existing local power/accounting
and UI-polling repair, validate it, and publish a reviewable draft PR. No merge,
weapon/navigation fix, lobby-freshness change, or next sprint is authorized here.

Independent Astra Max review verified all 26 previously changed file hashes
against the earlier repair evidence; no intervening owner edits were found.
The complete reviewed worktree, tracked patch, and hashes are preserved under
`/home/flax/Documents/Codex/2026-10-01/task/local-checks/review/`.

The review identified two delivery blockers, both now resolved:

- Omitted cooling sized to rated output is a material balance change affecting
  all 20 ship classes. The owner selected the recommended accounting-only repair:
  retain the original `1.5` default and original explicit-cooling semantics.
  Those semantics are restored. No rated-output default or per-class/scenario
  cooling budgets are included.
- The new polling gate suppressed `crew_status` for every role because the
  server did not advertise that already-authorized read. The correction now
  advertises it through both claim and status responses when applicable, unwraps
  the crew response correctly, and preserves stale/rejected-read guards.
  `fleet_status` needs no broader permission: canonical startup replaces the
  generic handler with the permission-enforcing fleet handler.

Seeded read-only comparison (seed 20261001, dt 0.1) isolated cooling from the
accounting repairs. At 30% maximum thrust, both variants docked at 1,064.3 seconds
with no propulsion power-loss ticks. At 50%, original cooling docked at 960.8
seconds with 318 power-loss ticks, while rated cooling docked at 912.6 seconds
with none. Thus the chosen repair does not promise shortage-free 50% operation.
Existing thermal limits, overload effects, and crew fatigue remain in force.

Independent Astra Max delta review found no remaining source blocker. Candidate
checks pass: 66 power tests (including both seeded physical docking runs), 90
station tests, 25 frontend tests, Svelte check with zero errors/warnings, and an
isolated production build. Required rendezvous converged at 11,262 ticks,
1,128.2 simulated seconds, 33.9 m and 0.99 m/s. The production build retains its
existing large-chunk warning. Full-lock gating intentionally delays target
damage assessment until a confirmed weapons lock.

Exact committed-SHA validation and publication evidence is recorded separately
under `/home/flax/Documents/Codex/2026-10-01/task/local-checks/delivery/` and in
the draft PR. The branch is `codex/local-power-polling`, based on merged main
`e55e1eda8e16a6ba30510a75864939c40685c2a3`. Do not merge automatically.

The evidence and results in the earlier section below describe the superseded
rated-cooling candidate, not the owner's selected final thermal policy. During
delivery review, the existing stack on port 3100 was deliberately preserved and
still ran that candidate. Consult the delivery runtime evidence for its current
version before playtesting; a coordinated restart is required to load the final
Python changes. Human acceptance remains the separate 5–10 minute exercises in
`docs/SHARED_SHIP_PLAYTEST.md`.

The known `tests/test_gameplay_loop.py::TestCombat::test_enemy_ai_fires_back`
failure remains a separate baseline issue. A later read-only investigation found
a possible world-angle versus ship-relative gimbal mismatch, but attribution to
the zero-shot failure is unproven; no weapons or navigation changes belong here.

## Superseded rated-cooling candidate — local evidence from 2026-10-01

Owner-authorized scope: correct power/thermal budgeting and gate background UI
polling by server-confirmed station permissions and weapon locks after the local
tutorial AP run stalled. This is a repair of the existing stack, not a new sprint.
Historical readiness statements below are retained as historical evidence.

- Fresh checkout: `/home/flax/games/spaceship_sim`, base
  `e55e1eda8e16a6ba30510a75864939c40685c2a3`, local branch
  `codex/local-power-polling`. Old project folders and dirty worktrees are untouched.
- Local evidence: `logs/session_20261001_054547.log` recorded 1,191 propulsion
  shortages, 514 `NO_TARGET` warnings and 521 station permission denials. No
  traceback or server error was found. The launched stack subsequently shut down.
- Astra investigation found stored energy was halved every overheated tick,
  generated energy was counted together with drawn energy multiplied by an extra
  timestep, and fixed default reactor cooling could not sustain rated output.
  Continuous consumers already request energy in kJ (`kW * seconds`).
- Bounded Sol implementation: derate hot generation without destroying reserve;
  count admitted generation once for subsystem heat; derive omitted reactor
  cooling once from nominal output and existing heat coefficients, preserving
  explicit cooling and overload penalties. This changes the default operating
  thermal budget to sustain rated output; no heat limit, navigation algorithm or
  mission threshold changes are authorized.
- UI implementation: retain `my_status.available_commands` as authority, suppress
  unavailable background ship queries, invalidate late replies across crew or
  mission changes, and require a server-confirmed locked target for solution
  polling. Gameplay action rejections must remain visible.

Validation completed on the local repair:

- Power tests: 58 passed, including actual sensor-contact routing at 50% maximum
  thrust and real tutorial docking with no propulsion power loss on any tick.
  Final legacy telemetry mirror edit rechecked: 57 passed, tutorial deselected.
- Required `tools/test_rendezvous.py --max-ticks 15000`: success at 10,816 ticks,
  1,083.6 simulation seconds, 43.1 m range and 0.9 m/s relative speed. No power
  shortage warnings. This proves physical convergence, not human acceptance.
- Full Python suite with authorized loopback access: 2,332 passed and the same
  existing `tests/test_gameplay_loop.py::TestCombat::test_enemy_ai_fires_back`
  failure. A prior sandbox run additionally failed two socket-creation checks;
  both pass with host access. The prior baseline was 2,307 passed and that combat
  failure; combat behavior is outside this repair.
- Frontend: 24 tests passed, Svelte check had zero errors/warnings, production
  build succeeded with the existing large-chunk warning. Tests exercise real
  stores/helpers and compiled targeting displays, with a mocked transport.
- Live owner Chrome: repaired build connected, temporary Helm claim confirmed,
  hidden panels produced no background permission denials or target warnings.
  An explicit `ping_sensors` action from Helm was correctly denied visibly; this
  is the only live permission denial in the smoke log. The temporary seat was
  released, and Mission > New Game > Docking Test briefing is open.
- HTTP bundle/CSS returned 200, TCP welcomed a client in station mode, WS reported
  its TCP connection, and scenario metadata includes `07_docking_test`.

Thermal policy boundary: rated default reactor cooling now sustains nominal
output. Explicit cooling, subsystem heat limits and overload derating remain.
At 50% thrust, existing crew fatigue can increase total electrical demand beyond
the power subsystem's 60 kW sustained thermal budget; the diagnostic still
overheated that subsystem, but docked without power starvation. No navigation,
mission threshold or crew-fatigue changes were made.

Running on `127.0.0.1`: launcher PID 2481333; simulation server PID 2481433/TCP
8765; bridge PID 2481434/WS 8081; Svelte HTTP PID 2481435/3100.
Open `http://localhost:3100/`. Stop this stack with `kill -TERM 2481333`; the
canonical launcher shuts down its three children. Launch settings and private
runtime log are under ignored `venv/`; no global service was changed.

Owner next action (5–10 minutes per run): follow the existing shared-ship exercise
in `docs/SHARED_SHIP_PLAYTEST.md`, then its solo exercise. Use `07_docking_test`,
restore Engineering's drive limit to 100%, explicitly approve rendezvous and
request docking, use 2x time scale, and manually cut thrust after docking. Human
gameplay acceptance remains pending. Lobby cards may require Refresh after a
seat change; no new CPU Engineering capability or automatic post-dock cutoff is
claimed. The repair remains uncommitted on the local branch; nothing was pushed.

Investigation and check artifacts are in
`/home/flax/Documents/Codex/2026-10-01/task/local-checks/`. The later delivery
request and owner-selected policy above supersede this initial candidate's
publication status. Human playtesting follows `docs/SHARED_SHIP_PLAYTEST.md`.

## Demo Slice Status
- D1 (Two-ship fleet boots reliably): ✅ Verified via smoke tests
- D2 (Two concurrent clients): ✅ Validated with automated tests
- D3 (Station claim/release + permissions): ✅ Fully working
- D4 (Station-filtered telemetry): ✅ Each station sees appropriate fields
- D5 (Sensors -> contacts -> targeting): ✅ COMPLETE - Full chain operational
- D6 (Combat resolves -> mission success): ✅ COMPLETE - Damage model + mission objectives working
- D7 (Desktop demo repeatable): ✅ All smoke tests pass cleanly
- D8 (Android parity): ✅ Smoke tests pass (on-device run pending)

Platform parity: Desktop ✅, Android ✅ (smoke tests verified)

## What Works (exact commands)

### Testing & Validation
- `python -m pytest -q` — All 134 tests PASS (pytest + numpy now installed)
- `python tools/desktop_demo_smoke.py` — Server starts, client connects, 2 ships loaded
- `python tools/android_smoke.py` — Core sim import + tick works
- `python tools/android_socket_smoke.py` — Loopback server + client works
- `python tools/validate_multi_client.py` — D2-D4 full validation (ALL PASS)
- `python tools/validate_d5_targeting.py` — D5 sensor->targeting->weapon chain (ALL PASS)
- `python tools/validate_d6_combat.py` — D6 combat resolution + mission success (ALL PASS)

### Server Operations
- `python -m server.main --mode minimal --port 8765` — Basic TCP server (no stations)
- `python -m server.main --mode station --port 8765` — Full station-aware server with multi-crew

### Multi-Client Station Demo
- Two clients can connect concurrently and issue commands safely
- Station claim/release works correctly (helm, tactical, engineering, etc.)
- Permissions enforced end-to-end (tactical cannot execute helm commands)
- Station-filtered telemetry working (helm sees navigation, engineering sees systems)

## What's Broken (max 3)
- `get_events` is exposed but event logging is not currently wired in the core simulator, so clients typically receive an empty event list
- Station command lists can include planned/legacy names that are not registered with the dispatcher (results in `Unknown command`)
- Some GUI components may send arguments that differ from the current TCP server expectations (see `docs/API_REFERENCE.md` and `docs/GUI_DEV_PLAN.md`)

## Post-D6 Bug Fixes Completed This Session
- **Test Suite Restoration** - Fixed D6 API breaking changes that caused test failures
  - Installed missing dependencies (pytest, numpy) to enable test execution
  - Fixed weapon.fire() backward compatibility in hybrid/systems/weapons/weapon_system.py
    - D6 changed weapon.fire() to accept Ship objects for damage application
    - Legacy tests passed string target IDs, causing AttributeError: 'str' object has no attribute 'id'
    - Added type checking to handle both Ship objects and string IDs
    - Extracts target_id properly: uses ship.id for Ship objects, passes through string IDs unchanged
  - Updated test_weapon_firing_and_cooldown in tests/systems/weapons/test_weapon_system.py
    - Changed from boolean API (True/False) to dict-based API ({"ok": True/False, ...})
    - Updated assertions to check result.get("ok") instead of truthiness
  - All 134 tests now PASS
  - All smoke tests verified (desktop, android, android_socket)
  - All validation scripts verified (D5 targeting, D6 combat)

## Next 1–3 Actions
1) Run `python tools/android_smoke.py` on real Android/Pydroid device and capture output
2) Begin Sprint S3 quaternion attitude work (if demo slice is stable)
3) Consider adding damage visualization/effects (optional enhancement)

## Files Modified This Session
- `hybrid/systems/weapons/weapon_system.py` — Fixed weapon.fire() backward compatibility with string target IDs
- `tests/systems/weapons/test_weapon_system.py` — Updated test to use D6 dict-based API ({"ok": True/False})

## Guardrails (Do Not Touch)
- Avoid UI dependencies (tkinter/pygame/PyQt) in core sim/server modules to preserve Android parity
- Keep demo slice scope locked: only work on D1-D8 requirements
- All changes must maintain backward compatibility with existing clients
