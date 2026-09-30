# Shared ship testing

This is a bounded repair of the current Svelte → WebSocket bridge → station-aware
Python server. Two people operate one physical ship at Helm and Engineering.
Physics, navigation algorithms and combat AI remain the existing simulation.
The first acceptance mission is the existing `07_docking_test` scenario.

## Safe Linux checkout and build

Use a fresh clone, especially if existing worktrees contain changes or already
hold the draft branch. These commands create a unique directory and never switch,
reset, stash or overwrite an existing checkout. The draft is unmerged. Compare
the printed SHA with the final tested SHA in PR #417's validation report before
testing; if it differs, stop and obtain that exact revision.

```bash
FLAXOS_TEST_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/flaxos-playtest.XXXXXX")
export FLAXOS_TEST_ROOT
(
  set -e
  git clone --single-branch --branch codex/trustworthy-shared-ship \
    https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01.git "$FLAXOS_TEST_ROOT/repo"
  cd "$FLAXOS_TEST_ROOT/repo"
  git checkout --detach
  git rev-parse HEAD
  python3 -m venv "$FLAXOS_TEST_ROOT/venv"
  "$FLAXOS_TEST_ROOT/venv/bin/python" -m pip install -r requirements.txt pytest
  cd gui-svelte
  npm ci
)
```

Run each verification command separately and record its exit status and output.
A Python failure must remain visible and does not prevent running frontend checks
in the next command. None of these commands skips or suppresses a failed test.

```bash
(cd "$FLAXOS_TEST_ROOT/repo" && "$FLAXOS_TEST_ROOT/venv/bin/python" -m pytest tests/ -q)
```

```bash
(cd "$FLAXOS_TEST_ROOT/repo/gui-svelte" && npm test)
```

```bash
(cd "$FLAXOS_TEST_ROOT/repo/gui-svelte" && npm run check)
```

```bash
(cd "$FLAXOS_TEST_ROOT/repo/gui-svelte" && npm run build)
```

Record the printed SHA with your results. Tested versions and exact counts are in
the report. The full Python baseline has an intermittent
`test_enemy_ai_fires_back` failure; record it if it occurs. Do not interpret a
passing retry as resolution of combat AI. `npm test` runs deterministic mocked
transport/store regressions; the optional `crew-ui.acceptance.cjs` also mocks
WebSockets and is outside npm test/CI. Neither proves the live two-client stack.
The separately recorded live Chromium run uses actual WS/TCP/server commands.

Start the station-mode stack on loopback:

```bash
(
  set -e
  cd "$FLAXOS_TEST_ROOT/repo"
  test -z "$(git status --porcelain)" || {
    echo 'STOP: this testing checkout now contains local changes.' >&2
    exit 1
  }
  "$FLAXOS_TEST_ROOT/venv/bin/python" tools/start_gui_stack.py \
    --rcon-password 'choose-a-local-testing-password'
)
```

Open `http://localhost:3100/` in two independent browser profiles or one normal
window and one private window. Separate tabs in the same profile are also separate
connections, but separate contexts make session mistakes easier to spot. TCP is
8765 and WebSocket is 8081. Stop the launcher with Ctrl+C after testing. For remote
players, use the existing authenticated LAN instructions in the README; this
loopback procedure does not establish LAN/ZeroTier acceptance.

## Two-person exercise: roughly 5–10 minutes

1. **Launch and join.** Client A opens Mission → New Game, selects
   “Docking Test: Short Range Approach” and launches. Join ship `player` as Helm.
   Client B uses Join Game and claims Engineering on the same ship. Release an
   existing captain seat before claiming a different seat. Both headers should
   show the server-confirmed ship and station. Have B release Engineering, then
   attempt to claim the occupied Helm seat: it must be denied visibly and leave
   A's claim intact. B then rejoins Engineering.
2. **Operate together.** Use MANUAL on A for a short 80% throttle request. On B,
   Engineering's drive governor limits the output to 50%, then 0%. Both clients
   should observe the same speed, fuel and hull, allowing for their sampling
   interval. A's throttle display shows actual governed output. Fuel must not say
   empty while Engineering has fuel; full 150/150 integrity must read 100%.
   RCT shows Engineering's existing reactor output setting; this does not verify
   actual power-management generation in kW.
   Mission Console can probe permissions with `set_thrust {"thrust":0.2}` from B
   and `set_reactor_output {"output":0.5}` from A. Both must be denied.
3. **Recover explicitly.** Refresh A's page (or disconnect/reconnect its transport). The UI must clearly
   show unassigned observer state with an explicit rejoin action. It must not
   silently reclaim Helm. Rejoin `player`/Helm; ensure B remains Engineering and
   live telemetry and commands recover. An occupied seat remains protected.
4. **Start a clean flight.** B opens Mission → Server, authenticates with the
   testing password, pauses and resets the current mission. Both clocks should
   return to zero and retain the same valid crew claims. Set time scale to 2x.
   Restore the drive governor to 100%. On A select the station from Navigation
   Contacts, choose CPU-ASSIST, and approve the existing rendezvous program. In
   Nav Tools, request docking with the same station. Commands should be ready
   even while the freshly reset mission is paused. Resume; let real flight run.
5. **Observe a shared result.** The unmodified 200 km docking mission takes around
   6½ minutes at 2x in the baseline diagnostic. Both clients should show the same
   real success after detection, approach and docking. Briefly pause/resume and
   compare clocks during flight. A failure must display MISSION FAILED. Current
   mission replay/reset should clear the old outcome for both clients; replay
   remains subject to captain/admin authority. Next Mission progression is outside
   this slice. After docking, manually set Helm thrust to zero and confirm actual
   output is zero: existing docking can constrain motion while drive/fuel use
   continues. Automatic thrust cutoff has not been established.

The CPU-ASSIST choice above uses the existing navigation program. It is not proof
of a full solo crew replacing every human station. Existing crew execution and
auto-system regressions are reported separately; new CPU behavior is excluded.

## Acceptance record

Record the SHA, browser versions, two station identities, result, mission time and
any console/server error. Save screenshots of complementary controls, explicit
rejoin and the shared outcome. Automated results accompany the implementation
report; owner human acceptance remains pending until this exercise is reported.

Outside this slice: combat AI reliability, campaign ammunition/fleets, next-mission
progression, Android/legacy UI, new stealth or missile mechanics, a GUI rebuild,
physics changes and navigation algorithm changes.
