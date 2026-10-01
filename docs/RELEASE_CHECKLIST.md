# Ten-task release checklist

Verified **2026-10-01 UTC** against main
`1ceec6256f207bdaccb0072b4d3905bdfb9cb8ce` and live PR metadata. This is a
readiness snapshot, not release approval. PR418, PR419 and PR422 are merged;
PR420, PR421, PR423, PR424 and PR425 are open drafts. Historical PR bodies saying “keep draft”
do not override the actual merge state. Draft features are absent from this main.

Checks apply to their linked revisions, not a combined candidate. Native-stack
and headless evidence are distinguished below. **Owner human UAT remains pending.**

## Requested tasks 1–10

| Task | Implementation / delivery | Unit and CI evidence | Live evidence | Remaining gate |
|---|---|---|---|---|
| 1. Power accounting / station polling | [PR419](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/419) **merged**; original cooling | 25 frontend; Python 2,361 pass + known failure; seeded **headless** docking; [CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36784311586) | Recorded local Chrome/WS/TCP role, telemetry and permission smoke | Human crew/solo UAT; high-load shortages remain possible |
| 2. Enemy-fire / gimbal frame | [PR420](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/420) **draft**; partial repair | 18 new / 424 focused; 25 frontend; Python 2,379 pass + known failure; [CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36792992141) | **Headless** combat traces; captured failure still fires zero shots | NPC policy decision and combat UAT |
| 3. Truthful lobby refresh | [PR421](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/421) **draft** | 34 frontend, 9 lobby; Python 2,361 pass + known failure; [CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36802513043) | Same-host contexts; 8 native groups: peer changes, stale replies, visibility, Refresh/reconnect | Human lobby UAT and review |
| 4. Post-dock cutoff controls | [PR422](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/422) **merged** | 27 frontend; Python 2,362 pass + known failure; [CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36804117035) | Actual CPU ASSIST → MANUAL → Manual Flight; accepted 20% → 0% | Human docking/cutoff/fuel check; cutoff stays manual |
| 5. First tutorial guidance | **Merged in PR422** | Same PR422 checks; scenario structure unchanged | Sequential native text/coverage/control smoke; no completed flight or live completion-text check | Human First Contact completion/reminder check |
| 6. CPU thermal assistance | Authorized bounded field repair in [PR425](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/425) **draft** | 16 new; 27 frontend; local Python 2,380 pass + known failure; [CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36932906315); independent review complete | Final-head native heating → visible MANUAL proposals → selected denial/approval; owned-stack cleanup passes | Review and thermal human UAT; broader automation separately scoped |
| 7. NPC combat follow-through | **Blocked**; no additional implementation | Task 2 diagnosis; no separate checks | No new playtest | Same NPC policy decision |
| 8. Repeatable crew smoke | [PR423](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/423) **draft**; UI-readiness guard | 13 harness + 27 frontend; CI Python 2,362 pass + known failure; [current CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36935647085); independent review complete | Clean heads ea44da4 and 282e8fa: 5 native groups each; controlled stale-read failure/pass pair retained | Runtime Console/UI stale-display hazard; human UAT; no completed docking |
| 9. Two actual computers | **Pending / untested** | No device/network acceptance | Same-host contexts do **not** establish this | Verified second physical device/path; no network/security/local-runtime changes here |
| 10. Documentation reconciliation | Docs-only checklist | Link/diff checks; independent consistency review; no gameplay rerun | No new playtest | Owner review and gates below |

## Tested revisions and evidence history

| Source | Tested head | Actual merge into main |
|---|---|---|
| [PR418 precursor](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/418) | [3a338fc](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/3a338fc8eb8be6d07b6fcd63dfa035bf660a5e24) | [e55e1ed](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/e55e1eda8e16a6ba30510a75864939c40685c2a3) |
| PR419 | [8fc73a6](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/8fc73a6f27afa88d9d3c3adc373adcf8eb0dc07b) | [3cbaebf](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/3cbaebf1c32b9132f05635c6b64b7272e031511a) |
| PR420 | [b9a87be](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/b9a87be2a5e1409d449dcebb967931980facd75b) | Unmerged |
| PR421 | [345c4d4](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/345c4d4926f90cf00ca405d68788b3841ea26b33) | Unmerged |
| PR422 | [54b632a](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/54b632ab8caa643a8c9e2052d3b9c2edb62db306) | [1ceec62](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/1ceec6256f207bdaccb0072b4d3905bdfb9cb8ce) |
| PR423 | [ea44da4](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/ea44da46fa2d2c67e3cb2e06f506aee1a51794f2) | Unmerged |
| PR425 | [282e8fa](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/282e8fa950e1da4a09ce9b0b6566bb9e2cac78f9) | Unmerged |

PR418 retains 17 native phases: crewed docking at 792.8 sim seconds and solo at
812.9, at its earlier SHA. These automated flights do not establish later-head
or human acceptance. The [historical handoff](HANDOFF.md) preserves the superseded
rated-cooling candidate; PR419 restored original cooling. Failed attempts,
baseline failures and exact-SHA evidence remain privately retained; links are omitted.

Every listed Python CI retains active
`tests/test_gameplay_loop.py::TestCombat::test_enemy_ai_fires_back`.
Current-main task 6 and PR422/423 report **2,362 passes / 1 failure**. PR420 does
not resolve the captured zero-shot case. **CI is not all green**; no skipping,
weakened assertion or passing retry closes it. PR421 review retained 30 passes /
4 fixture-import failures versus root/CI's 34 passes; the unrelated cleanup race
also remains unresolved.

PR425's final-head unsuppressed root-discovery run reports **2,380 passes /
1 known enemy-fire failure** (including two tools tests outside the CI's
`tests/` selection). Its Svelte CI passes; full CI status is available in the
linked run. The local failure remains active; this is not an all-green claim.
Native thermal proof uses two same-host contexts, a private fleet
copying Hunter's original systems, actual heating and existing UI commands.
No temperature or transport is replaced. The initial cleanup probe and a
case-sensitive CSS text assertion failed; both attempts remain retained.
The final thermal run and teardown pass. Independent review's fixture-isolation
finding was corrected and rechecked before final-head validation.

The old PR423 harness at 25d6655 was run against PR425's clean head from an
external copy, changing only the CLI checkout path. The first run passed three
crew groups and accepted 20% thrust, then timed out before any native 0% request
was captured. One unchanged repeat passed all five groups. Both remain retained;
the original run lacked DOM/action timestamps, so its exact input event cannot
be proved retrospectively.

The follow-up used six new native attempts: two instrumented ordinary/dwell runs
passed; a controlled stale-read run failed at the same missing-zero request; the
same read ordering with the corrected guard passed; clean-head ordinary runs at
PR423 ea44da4 and unchanged PR425 282e8fa passed all five groups and teardown.
The controlled runs use a real paused station server and one extra real full
read after accepted 20%, with no response replacement. Recorded DOM events show
actual 20% while the number/display revert to 0%; filling that unchanged zero
and blurring emits no change event or cutoff request. A later UI poll restores
20%. This demonstrates the mechanism matching the historical trace, rather
than erasing its missing DOM evidence or counting a retry as resolution.

PR423 now waits for a correlated normal UI poll reporting the preceding actual
throttle, then the rendered number/display, before its next edit. Console full
snapshots and optimistic DOM alone cannot satisfy readiness. It adds three
focused regressions (13 total), captures action values/times/poll IDs, and uses
one edit/command with the existing 10s limits. Its completed CI passes 27
frontend/13 harness tests, check and build; unsuppressed Python reports 2,362
passes / 1 known enemy-fire failure. The CI merge tree equals ea44da4. The
thermal repair source and head remain unchanged. The underlying shared-cache Console/UI desynchronization
is **not repaired**: a visible 0% alone can be stale while thrust remains 20%.
There is no evidence of an accepted-zero command being rejected or ineffective.
These same-host checks do not establish human, two-device or completed-docking
acceptance. Human UAT must check actual zero and zero fuel burn with the display.

## Assistance limits and next owner gates

The [fallback Engineering CPU](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/1ceec6256f207bdaccb0072b4d3905bdfb9cb8ce/server/stations/ai_crew.py#L183)
can activate fitted sinks when unclaimed and running. The tested
[Hunter configuration](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/1ceec6256f207bdaccb0072b4d3905bdfb9cb8ce/scenarios/intercept_scenario.json#L96) has sinks holding
500 kJ and dump at 50 kW: roughly ten simulated seconds at full rate, while net
heating can remain positive. First Contact has no thermal system. This is not
sustained reactor/radiator/governor management or a full replacement crew.
Solo navigation still requires explicit station changes, approval and manual
post-dock cutoff.

The separate [Auto-Engineering proposal system on main](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/1ceec6256f207bdaccb0072b4d3905bdfb9cb8ce/hybrid/systems/auto_engineering.py#L35)
starts disabled; choosing CPU ASSIST does not enable it. Main reads fractional
`hull_temp_pct`, while [actual thermal telemetry](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/1ceec6256f207bdaccb0072b4d3905bdfb9cb8ce/hybrid/systems/thermal_system.py#L526)
provides `temperature_percent` (0–100); task 6 reproduced absent hot proposals.
The owner authorized the bounded telemetry repair, now implemented in draft
PR425: both generators divide the actual percentage by 100. It is **unmerged**.
The existing strict >60% threshold, disabled default, 3s scans, cooldown,
recent-damage guards and execution gates remain unchanged. For a 500 K maximum,
60% is about 301.1 K, distinct from the 400 K warning and fallback sink trigger.
MANUAL proposals expire after eight wall seconds when ticking; AUTO retains
its existing eight-second execution. Cooling, sink capacity, crew competence
and station authority are unchanged. Broader threshold/timing or CPU autonomy
work remains separately scoped. Use the [short owner thermal check](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/282e8fa950e1da4a09ce9b0b6566bb9e2cac78f9/docs/AUTO_ENGINEERING_THERMAL_REPAIR.md#short-owner-playtest).

- [ ] Choose coast-and-aim versus sensor-aware velocity matching in the [PR420 diagnosis](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/b9a87be2a5e1409d449dcebb967931980facd75b/docs/ENEMY_FIRE_DIAGNOSIS.md).
- [x] Authorize the bounded thermal field repair; implemented in draft PR425. Review and human thermal UAT remain pending.
- [ ] Review/test [draft lobby behavior](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/345c4d4926f90cf00ca405d68788b3841ea26b33/docs/LOBBY_OCCUPANCY_REFRESH.md) and [draft crew smoke](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/ea44da46fa2d2c67e3cb2e06f506aee1a51794f2/docs/SHARED_SHIP_PLAYTEST.md#repeatable-short-crew-smoke-real-stack) at their separate pinned heads.
- [ ] Report crewed, solo and [first-tutorial UAT](FIRST_TUTORIAL_DOCKING_GUIDANCE.md), including rejoin and MANUAL → Manual Flight → Throttle 0%. Use the [isolated main setup](SHARED_SHIP_PLAYTEST.md#safe-linux-checkout-and-build), preserving the running local playtest.
- [ ] Scope/review the separately open Console/UI telemetry desynchronization; the PR423 guard improves the smoke and does not repair the runtime display hazard.
- [ ] Supply task 9's second actual computer and verified path, then authorize a separate two-device check. No same-host substitution or network/security change here.
- [ ] After authorized integration, record the candidate SHA and rerun unsuppressed checks/UAT; separate draft results do not establish combined acceptance.

This ten-task pass ends at these acceptance and decision gates. No merge, PR
closure, new capability or network/local-runtime change is performed here.
