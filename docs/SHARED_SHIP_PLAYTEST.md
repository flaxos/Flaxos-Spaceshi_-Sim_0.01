# Shared ship testing

This is a bounded repair of the current Svelte → WebSocket bridge → station-aware
Python server. Two people operate one physical ship at Helm and Engineering.
Physics, navigation algorithms and combat AI remain the existing simulation.
The first acceptance mission is the existing `07_docking_test` scenario.

## Safe Linux checkout and build

Use a separate checkout if your current tree contains work. The commands below
stop on local changes or a diverged branch; they do not reset, stash or overwrite
anything. Run them in the repository root. Fetch the draft branch only when you
are ready to test unpublished changes.

```bash
set -e
test -z "$(git status --porcelain)" || {
  echo 'STOP: commit your work or use a separate clone.' >&2
  exit 1
}
git fetch origin main codex/trustworthy-shared-ship
if git show-ref --verify --quiet refs/heads/codex/trustworthy-shared-ship; then
  git switch codex/trustworthy-shared-ship
else
  git switch --track origin/codex/trustworthy-shared-ship
fi
test "$(git rev-list --count origin/codex/trustworthy-shared-ship..HEAD)" -eq 0 || {
  echo 'STOP: local branch has commits absent from the draft branch.' >&2
  exit 1
}
git merge --ff-only origin/codex/trustworthy-shared-ship
git rev-parse HEAD

# Keep the environment outside the working tree.
python3 -m venv ../flaxos-shared-ship-venv
../flaxos-shared-ship-venv/bin/python -m pip install -r requirements.txt pytest
../flaxos-shared-ship-venv/bin/python -m pytest tests/ -q
cd gui-svelte
npm ci
npm test
npm run check
npm run build
cd ..
```

Record the printed commit SHA with your results. Tested tool versions and exact
pass/failure counts accompany the implementation report. The full Python baseline
contains an intermittent `test_enemy_ai_fires_back` failure; record it if it occurs.
Do not skip the test or interpret a passing retry as resolution of combat AI.

Start the station-mode stack on loopback:

```bash
../flaxos-shared-ship-venv/bin/python tools/start_gui_stack.py \
  --rcon-password 'choose-a-local-testing-password'
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
   this slice.

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
