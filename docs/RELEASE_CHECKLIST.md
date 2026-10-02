# Ten-task release checklist

Snapshot **2026-10-02 23:31 UTC** against main
`1ceec6256f207bdaccb0072b4d3905bdfb9cb8ce` and live PR metadata. This is a
readiness snapshot, not release approval. PR418, PR419 and PR422 are merged;
PR420, PR421, PR423, PR424, PR425, PR426 and PR427 are open drafts. Historical PR bodies saying “keep draft”
do not override the actual merge state. Draft features are absent from this main.

Source-PR checks apply to their linked revisions; PR427's combined-candidate
results are recorded separately below. Native-stack and headless evidence are
distinguished. **Owner human UAT remains pending.**

## Requested tasks 1–10

| Task | Implementation / delivery | Unit and CI evidence | Live evidence | Remaining gate |
|---|---|---|---|---|
| 1. Power accounting / station polling | [PR419](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/419) **merged**; original cooling | 25 frontend; Python 2,361 pass + known failure; seeded **headless** docking; [CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36784311586) | Recorded local Chrome/WS/TCP role, telemetry and permission smoke | Human crew/solo UAT; high-load shortages remain possible |
| 2. Enemy-fire / gimbal frame | [PR420](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/420) **draft**; partial repair | 18 new / 424 focused; 25 frontend; Python 2,379 pass + known failure; [CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36792992141) | **Headless** combat traces; captured failure still fires zero shots | Selected coast-and-aim implementation/validation and combat UAT |
| 3. Truthful lobby refresh | [PR421](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/421) **draft** | 34 frontend, 9 lobby; Python 2,361 pass + known failure; [CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36802513043) | Same-host contexts; 8 native groups: peer changes, stale replies, visibility, Refresh/reconnect | Human lobby UAT and review |
| 4. Post-dock cutoff controls | [PR422](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/422) **merged**; bounded runtime reliability follow-up [PR426](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/426) **draft** | PR426: 38 frontend; local Python 2,364 pass + known failure; [final-head CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36939846743): 2,362 pass + known failure; independent review complete | Clean 6daf1b9: 9 real two-context groups, including stale-zero/repeat/rapid cutoff, retirement, running nonzero and actual zero / zero fuel burn | Review and human docking/cutoff/fuel check; cutoff stays manual |
| 5. First tutorial guidance | **Merged in PR422** | Same PR422 checks; scenario structure unchanged | Sequential native text/coverage/control smoke; no completed flight or live completion-text check | Human First Contact completion/reminder check |
| 6. CPU thermal assistance | Authorized bounded field repair in [PR425](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/425) **draft** | 16 new; 27 frontend; local Python 2,380 pass + known failure; [CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36932906315); independent review complete | Final-head native heating → visible MANUAL proposals → selected denial/approval; owned-stack cleanup passes | Review and thermal human UAT; broader automation separately scoped |
| 7. NPC combat follow-through | Coast-and-aim **selected**; separate implementation in progress | Task 2 diagnosis; new validation pending | No new playtest recorded | Separate implementation/validation and combat UAT |
| 8. Repeatable crew smoke | [PR423](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/423) **draft**; readiness guard and marked Console-read compatibility | 14 harness + 27 frontend; CI Python 2,362 pass + known failure; [current CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36939193914); independent review complete | Clean 1e4aaa6: unmodified runner passes 5 groups and cleanup; earlier ea44da4/282e8fa evidence retained | Review and human UAT; runtime correction remains a separate unmerged PR426; no completed docking |
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
| PR423 | [1e4aaa6](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/1e4aaa6f057af47c47ccda87c29d0d486b728374) | Unmerged |
| PR425 | [282e8fa](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/282e8fa950e1da4a09ce9b0b6566bb9e2cac78f9) | Unmerged |
| PR426 | [6daf1b9](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/6daf1b96ccabffabb034809e08eb3c759f2b8db0) | Unmerged |
| [PR427 combined candidate](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/427) | [e943ecc](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/e943eccfc6a13da9c2f4541d1b737149b6f4eddf) | Unmerged |

PR418 retains 17 native phases: crewed docking at 792.8 sim seconds and solo at
812.9, at its earlier SHA. These automated flights do not establish later-head
or human acceptance. The [historical handoff](HANDOFF.md) preserves the superseded
rated-cooling candidate; PR419 restored original cooling. Failed attempts,
baseline failures and exact-SHA evidence remain privately retained; links are omitted.

Every listed Python CI retains active
`tests/test_gameplay_loop.py::TestCombat::test_enemy_ai_fires_back`.
Main and PR422/423/426 CI selections report **2,362 passes / 1 failure**. PR420 does
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

At ea44da4, PR423 added a wait for a correlated normal UI poll reporting the preceding actual
throttle, then the rendered number/display, before its next edit. Console full
snapshots and optimistic DOM alone cannot satisfy readiness. It adds three
focused regressions (13 total), captures action values/times/poll IDs, and uses
one edit/command with the existing 10s limits. Its completed CI passes 27
frontend/13 harness tests, check and build; unsuppressed Python reports 2,362
passes / 1 known enemy-fire failure. The CI merge tree equals ea44da4. The
thermal repair source and head remain unchanged. At that historical head, shared-cache Console/UI desynchronization was
**not repaired**: a visible 0% alone could be stale while thrust remained 20%.
There is no evidence of an accepted-zero command being rejected or ineffective.
These same-host checks do not establish human, two-device or completed-docking
acceptance. Human UAT must check actual zero and zero fuel burn with the display.

The authorized bounded runtime follow-up is now in draft PR426 at clean
6daf1b9. The existing 200 ms UI chain requests self-contained snapshots, even
when another same-client read advances the shared delta cursor. Numeric input
retains its draft during telemetry; explicit zero commits on blur even without
change, and CUT THRUST uses the normal authorized command. Only numeric zero
bypasses the existing 50 ms transport throttle. Captured ship/revision guards,
a stable 40 ms timer owner and explicit retirement of both DOM drafts prevent
old edits from surviving crew changes or unmount. Server permissions, explicit
rejoin, nonzero throttling, physics, cooling and thermal policy remain unchanged.

Current-main focused regressions report 20 passes / 9 failures; a clean-main
real paused-server reproduction confirms actual 20% / displayed 0% and no zero request.
Three subsequent runtime native attempts remain retained. The first passed six
groups but incorrectly treated a MISSION tab change as an unmount; views remain
mounted under CSS. The second used the real MANUAL-to-ARCADE unmount and exposed
a retired draft still visible after release. The strengthened regression also
reproduced numeric/range DOM reset failures in the partial repair. Final 6daf1b9
passes all nine groups with zero page errors and completed owned-stack cleanup.
It includes full and non-full real read ordering, one unchanged real 20% response
held 849 ms while numeric zero and repeat zero are accepted, a normal button
cutoff 41.5 ms after nonzero, actual unmount and release/rejoin retirement, and
running normal 20% / range 35% with positive fuel burn followed by actual zero and both
canonical/Engineering burn rates zero. Scripted timing/DOM controls are labelled;
these are automated same-host checks, not human or completed-flight acceptance.

Final PR426 frontend has 38 passes, check 0 errors/warnings and build pass.
Unsuppressed local root Python reports 2,364 passes / 1 known enemy-fire failure /
1 existing collection warning (162.86s). Exact-head CI reports 2,362 passes /
1 same active failure (270.38s); its merge 6b27fa8 has the identical tree to 6daf1b9.
Independent source, atomic event, native correlation and evidence review is
complete. All failed attempts remain retained. Full snapshots increase paused
traffic: approximate serialized sizes of sampled, parsed ship-targeted responses
have median 5.7 KB Helm and 8.8 KB Engineering. These are payload estimates,
not a capacity benchmark; larger Captain/fleet load is not benchmarked.

PR423's separate harness-only head 1e4aaa6 marks its own Console reads, allowing
full UI polls and legacy deltas to satisfy readiness while excluding Console
responses. An unmodified clean-head run passes all five groups and cleanup;
14 harness/27 frontend tests, check and build pass in CI 36939193914. Python
retains 2,362 passes / 1 known enemy-fire failure (260.28s); merge 8662170 has the
identical tree. The runtime proof uses an explicitly versioned private helper
extension at 6daf1b9; it is not a combined-draft or unchanged-helper claim.
PR425 remains unchanged at 282e8fa. Human UAT, two-device play and completed
docking remain pending, and the shared server delta protocol is not redesigned.

## Combined integration candidate

Draft PR427 at `e943eccfc6a13da9c2f4541d1b737149b6f4eddf`, based on main
`1ceec6256f207bdaccb0072b4d3905bdfb9cb8ce`, combines the authorized PR421
`345c4d4`, PR423 `1e4aaa6`, PR425 `282e8fa` and PR426 `6daf1b9` heads through
four auditable merge commits retaining their ancestry. Source heads remain
separate from this candidate. PR424 remains documentation-only; all these
drafts remain unmerged into main. No GitHub PR merge or deployment is authorized.

Completed automated checks at clean `e943ecc`:

- 47 frontend tests, 14 harness regressions and 16 focused thermal regressions;
  type check 0 errors / 0 warnings and production build pass.
- Unsuppressed root-discovery Python: **2,380 passes / 1 known enemy-fire failure /
  1 existing collection warning**, 167.40 seconds.
- Unmodified official native crew runner: five groups, zero page errors and
  completed owned-stack cleanup.
- Controlled native runtime check: nine groups, zero page errors and completed
  cleanup. Scripted real read ordering and a held original response are labelled;
  no response replacement or human playtest is claimed.
- Native thermal check: seven groups, zero page errors and completed cleanup.
  Actual Hunter heating from 300.9 to 311.5 K (62%) produces visible MANUAL
  proposals without automatic plant changes. Native denial leaves the reactor
  unchanged; selective approval deploys the chosen radiators.
- Native lobby check: eight groups, zero page errors and completed cleanup.
  Peer claim appears in about 1.97 seconds; release/header changes, hidden view,
  real unmount, controlled visibility/original stale reply, manual Refresh,
  leave/return, reconnect/explicit rejoin and observer denial are covered.

[PR427 CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/37077357196)
Svelte passes 47 frontend / 14 harness tests, check and build. Unsuppressed
Python `tests/` reports **2,378 passes / 1 failure**, 234.82 seconds, solely the
active `tests/test_gameplay_loop.py::TestCombat::test_enemy_ai_fires_back`.
The root-discovery run includes two tools tests outside this CI selection.
CI merge checkout `78a94f2caa698926389691e66382f4326fee2a9c` has tree
`43a7d079fe3036469802c83e0cd3b3b8f02959b7`, identical to clean `e943ecc`.
Independent combined review is complete; no new material integration finding.
**Combined checks are not all green.** These same-host automated checks
do not establish human, two-device, completed-docking or Captain/fleet load
acceptance; all owned ports were released.

The owner also selected NPC coast-and-aim. Its implementation is proceeding
separately from this four-PR integration. PR420 was last verified at `b9a87be`
on **2026-10-02 23:27 UTC**; no new coast-and-aim code or validation results are
claimed by this snapshot.

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

- [x] Select coast-and-aim; the [pinned PR420 diagnosis](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/b9a87be2a5e1409d449dcebb967931980facd75b/docs/ENEMY_FIRE_DIAGNOSIS.md) retains the earlier alternatives. Separate implementation/validation and combat UAT remain pending.
- [x] Authorize the bounded thermal field repair; implemented in draft PR425. Review and human thermal UAT remain pending.
- [ ] Review/test [draft lobby behavior](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/345c4d4926f90cf00ca405d68788b3841ea26b33/docs/LOBBY_OCCUPANCY_REFRESH.md) and [draft crew smoke](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/1e4aaa6f057af47c47ccda87c29d0d486b728374/docs/SHARED_SHIP_PLAYTEST.md#repeatable-short-crew-smoke-real-stack) at their separate pinned heads.
- [ ] Report crewed, solo and [first-tutorial UAT](FIRST_TUTORIAL_DOCKING_GUIDANCE.md), including rejoin and MANUAL → Manual Flight → Throttle 0%. Use an isolated checkout at the selected exact revision; for PR427, pin `e943ecc`, adapting the [isolated setup](SHARED_SHIP_PLAYTEST.md#safe-linux-checkout-and-build) and preserving the running local playtest.
- [x] Authorize the bounded runtime reliability repair; implemented in draft PR426.
- [ ] Review PR426 at 6daf1b9 and human-check numeric 0% / CUT THRUST, actual zero / zero fuel burn, observer reconnect and explicit rejoin. The PR423 guard remains a separate harness feature.
- [ ] Supply task 9's second actual computer and verified path, then authorize a separate two-device check. No same-host substitution or network/security change here.
- [x] Authorize bounded integration of PR421/423/425/426; draft PR427 records candidate `e943ecc` separately from the source heads.
- [x] Independently review PR427's recorded combined checks at its exact SHA; no new material integration finding. The known failure and human UAT gates remain open.
- [ ] Benchmark larger Captain/fleet load separately; the retained snapshot payload estimates are not a capacity benchmark.

This ten-task pass ends at these acceptance and decision gates. No GitHub PR
merge, PR closure, deployment or network/local-playtest change is performed by
this documentation reconciliation.
