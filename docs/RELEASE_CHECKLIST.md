# Ten-task release checklist

Snapshot **2026-10-03 12:30 Australia/Sydney** against main
`de20f5e777775e86283725200f261bc6d743c078` and live PR metadata. This is a
readiness snapshot, not release approval. PR418, PR419, PR422, PR427 and PR429
are merged into main. PR429 merged externally on 2026-10-03 at 10:46
Australia/Sydney (00:46 UTC); main has the identical tree to tested `c5c5c40`.
PR421, PR423, PR425 and PR426 remain source drafts, with their features included
through PR427. PR420 remains a source draft; its PR428 continuation is included
on main through PR429. Documentation-only PR424 remains a draft. Historical PR
bodies saying “keep draft” do not override actual merge states.

Source-PR checks apply to their linked revisions. The original crew integration,
NPC source and new bounded combined candidate are recorded separately below;
source results do not establish combined acceptance. Native-stack and headless
evidence are distinguished. **Owner human UAT remains pending.**

## Requested tasks 1–10

| Task | Implementation / delivery | Unit and CI evidence | Live evidence | Remaining gate |
|---|---|---|---|---|
| 1. Power accounting / station polling | [PR419](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/419) **merged**; original cooling | 25 frontend; Python 2,361 pass + known failure; seeded **headless** docking; [CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36784311586) | Recorded local Chrome/WS/TCP role, telemetry and permission smoke | Human crew/solo UAT; high-load shortages remain possible |
| 2. Enemy-fire / gimbal frame | [PR420](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/420) **source draft**, included on main via PR429; now includes [PR428](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/428), merged into its branch | Original b9a87be: 18 new / 424 focused; 25 frontend; Python 2,379 pass + active failure; [historical CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36792992141). Later source and passing combined results below | Original captured failure fires zero shots; later NPC source and combined head have real gated fire | Human combat UAT; hit/mission success not established |
| 3. Truthful lobby refresh | [PR421](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/421) **draft**, included on main via merged PR427 | 34 frontend, 9 lobby; Python 2,361 pass + historical failure; [CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36802513043) | Same-host contexts; 8 native groups: peer changes, stale replies, visibility, Refresh/reconnect; PR427 checks below | Human lobby UAT |
| 4. Post-dock cutoff controls | [PR422](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/422) **merged**; bounded [PR426](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/426) **draft**, included on main via PR427 | PR426: 38 frontend; local Python 2,364 pass + historical failure; [final-head CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36939846743): 2,362 pass + same failure; independent review complete | Clean 6daf1b9: 9 real two-context groups, including stale-zero/repeat/rapid cutoff, retirement, running nonzero and actual zero / zero fuel burn; PR427 checks below | Human docking/cutoff/fuel check; cutoff stays manual |
| 5. First tutorial guidance | **Merged in PR422** | Same PR422 checks; scenario structure unchanged | Sequential native text/coverage/control smoke; no completed flight or live completion-text check | Human First Contact completion/reminder check |
| 6. CPU thermal assistance | Authorized bounded field repair in [PR425](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/425) **draft**, included on main via PR427 | 16 new; 27 frontend; local Python 2,380 pass + historical failure; [CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36932906315); independent review complete | Final-head native heating → visible MANUAL proposals → selected denial/approval; owned-stack cleanup passes; PR427 checks below | Thermal human UAT; broader automation separately scoped |
| 7. NPC combat follow-through | Selected coast-and-aim implemented at PR428 a42e892; merged into PR420 at cd4d691, included on main via PR429 | Source root 2,410 pass; [source CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/37078962485) 2,408 Python / 25 frontend pass; independent source review complete. Combined root 2,427 pass / CI 2,425 pass; details below | Source and combined seeds 0/1/42: 9 shots each, hull damage 22/0/0; source TCP runs and combined TCP run each have 2 unique projectiles, zero successful hits | Human combat UAT; hit/mission success not established |
| 8. Repeatable crew smoke | [PR423](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/423) **draft**, included on main via PR427; readiness guard and marked Console-read compatibility | 14 harness + 27 frontend; CI Python 2,362 pass + historical failure; [source CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36939193914); independent review complete | Clean 1e4aaa6: unmodified runner passes 5 groups and cleanup; earlier ea44da4/282e8fa evidence retained; PR427 checks below | Human UAT; runtime correction is included via PR427; no completed docking |
| 9. Two actual computers | **Pending / untested** | No device/network acceptance | Same-host contexts do **not** establish this | Verified second physical device/path; no network/security/local-runtime changes here |
| 10. Documentation reconciliation | Documentation-only PR424 draft | Link/diff checks; independent closeout review recorded below | No new playtest from documentation work | Owner review/publication and gates below |

## Tested revisions and evidence history

| Source | Tested head | Actual merge into main |
|---|---|---|
| [PR418 precursor](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/418) | [3a338fc](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/3a338fc8eb8be6d07b6fcd63dfa035bf660a5e24) | [e55e1ed](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/e55e1eda8e16a6ba30510a75864939c40685c2a3) |
| PR419 | [8fc73a6](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/8fc73a6f27afa88d9d3c3adc373adcf8eb0dc07b) | [3cbaebf](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/3cbaebf1c32b9132f05635c6b64b7272e031511a) |
| PR420 original frame repair | [b9a87be](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/b9a87be2a5e1409d449dcebb967931980facd75b) | Included via PR429 at de20f5e; current source branch includes PR428 at cd4d691 |
| PR421 | [345c4d4](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/345c4d4926f90cf00ca405d68788b3841ea26b33) | Included via PR427 at 6e6dabf; source PR remains draft |
| PR422 | [54b632a](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/54b632ab8caa643a8c9e2052d3b9c2edb62db306) | [1ceec62](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/1ceec6256f207bdaccb0072b4d3905bdfb9cb8ce) |
| PR423 | [1e4aaa6](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/1e4aaa6f057af47c47ccda87c29d0d486b728374) | Included via PR427 at 6e6dabf; source PR remains draft |
| PR425 | [282e8fa](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/282e8fa950e1da4a09ce9b0b6566bb9e2cac78f9) | Included via PR427 at 6e6dabf; source PR remains draft |
| PR426 | [6daf1b9](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/6daf1b96ccabffabb034809e08eb3c759f2b8db0) | Included via PR427 at 6e6dabf; source PR remains draft |
| [PR427 crew integration](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/427) | [e943ecc](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/e943eccfc6a13da9c2f4541d1b737149b6f4eddf) | [6e6dabf](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/6e6dabf4d8c0cec006650f9d93d92711addfe8ae); identical tree |
| [PR428 NPC continuation](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/428) | [a42e892](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/a42e89205bd0f88659feff98ed2c2c8e36680c17) | Included via PR429 at de20f5e; first merged into PR420 at [cd4d691](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/cd4d69117f7244303acc0bb7adfdd8b29cc0ab39), identical source tree |
| [PR429 NPC + crew candidate](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/429) | [c5c5c40](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/c5c5c40cfdb572591f7e9f74a85fe1bc06551aeb) | Merged externally at de20f5e; identical tested tree; combined checks below |

PR418 retains 17 native phases: crewed docking at 792.8 sim seconds and solo at
812.9, at its earlier SHA. These automated flights do not establish later-head
or human acceptance. The [historical handoff](HANDOFF.md) preserves the superseded
rated-cooling candidate; PR419 restored original cooling. Failed attempts,
baseline failures and exact-SHA evidence remain privately retained; links are omitted.

The earlier linked PR419–427 Python CIs retain active
`tests/test_gameplay_loop.py::TestCombat::test_enemy_ai_fires_back`.
Main at `1ceec62` and PR422/423/426 CI selections report **2,362 passes /
1 failure**. Original PR420 at `b9a87be` does not resolve the captured zero-shot
case. **Those historical CIs are not all green**; later source/combined results
do not rewrite them. No skipping, weakened assertion or passing retry closes
that historical failure. PR421 review retained 30 passes /
4 fixture-import failures versus root/CI's 34 passes; that source work did not
resolve the unrelated cleanup race.

PR425's final-head unsuppressed root-discovery run reports **2,380 passes /
1 known enemy-fire failure** (including two tools tests outside the CI's
`tests/` selection). Its Svelte CI passes; full CI status is available in the
linked run. That thermal-only source retains the active local failure; these
historical checks are not an all-green claim.
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

The authorized bounded runtime follow-up was validated in PR426 at clean
6daf1b9. The existing 200 ms UI chain requests self-contained snapshots, even
when another same-client read advances the shared delta cursor. Numeric input
retains its draft during telemetry; explicit zero commits on blur even without
change, and CUT THRUST uses the normal authorized command. Only numeric zero
bypasses the existing 50 ms transport throttle. Captured ship/revision guards,
a stable 40 ms timer owner and explicit retirement of both DOM drafts prevent
old edits from surviving crew changes or unmount. Server permissions, explicit
rejoin, nonzero throttling, physics, cooling and thermal policy remain unchanged.

Then-current main `1ceec62` focused regressions report 20 passes / 9 failures; a clean-main
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

## Original crew integration

PR427 at `e943eccfc6a13da9c2f4541d1b737149b6f4eddf`, based on earlier main
`1ceec6256f207bdaccb0072b4d3905bdfb9cb8ce`, combines the authorized PR421
`345c4d4`, PR423 `1e4aaa6`, PR425 `282e8fa` and PR426 `6daf1b9` heads through
four auditable merge commits retaining their ancestry. Source heads remain
separate from this candidate. PR427 was merged externally into main at `6e6dabf`
on 2026-10-02 23:44 UTC; that merge has the identical tested tree. The source
PRs remain drafts. PR424 remains documentation-only. This work performs no
GitHub PR merge or deployment.

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
**These original crew checks are not all green.** These same-host automated checks
do not establish human, two-device, completed-docking or Captain/fleet load
acceptance; all owned ports were released.

## NPC source and new bounded combined candidate

The selected coast-and-aim policy is implemented in PR428 at
`a42e89205bd0f88659feff98ed2c2c8e36680c17`, above original PR420
`b9a87be2a5e1409d449dcebb967931980facd75b`. PR428 merged externally into
PR420's branch at `cd4d69117f7244303acc0bb7adfdd8b29cc0ab39`; both have tree
`7b5b134e8a73cfcfe4318139a08bd2d694469b47`. Original PR420's source content
and its zero-shot diagnosis remain historical evidence. The unchanged diagnosis
document's “Neither option is implemented” describes `b9a87be`; coast-and-aim
is now implemented at the later NPC source and combined heads.

At the NPC source head, unsuppressed root Python passes **2,410 tests / zero
failures / zero skips**; [exact-head source CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/37078962485)
passes **2,408 Python / 25 frontend tests**, check and build. The two extra root
tests are outside CI's `tests/` selection. The historical failing RNG replay
now fires nine real gated shots at this later head; the original assertion and
60-second window remain active. Independent source review is complete.

Predeclared source seeds 0 / 1 / 42 each produce nine actual shots with normal
lock, readiness, range, arc, tracking, charge, power, heat and ammunition
accounting, and real projectiles. Hull damage is **22 / 0 / 0**. Two native
station-server runs use independent TCP seats and the existing
`02_combat_destroy` mission: each produces two projectiles, with **zero
successful hits**. Unauthorized Tactical thrust is denied. Native firing is
proved; full browser combat and human acceptance, hit success and mission victory remain
pending. These are source-head results, not new combined validation.

The bounded combined candidate was published as
[PR429](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/429) at
`c5c5c40cfdb572591f7e9f74a85fe1bc06551aeb`, based on main `6e6dabf` and merging
the verified PR420 source head `cd4d691` with retained ancestry. Its tree is
`afdcbb411d617bf41023a3e220da82a6f761467e`. The ten-path delta from main is
inherited PR420/428 content; this integration adds no gameplay changes. It is
now merged externally into main at `de20f5e`, with the identical tested tree.
Completed checks at this exact combined head:

- 47 frontend tests, 14 harness regressions and 16 focused thermal regressions;
  type check 0 errors / 0 warnings and production build pass with the existing
  chunk-size warning. The initial frontend environment failure and corrected
  unchanged-head run with system Chromium are both retained.
- Unsuppressed root-discovery Python: **2,427 passes / zero failures /
  1 existing collection warning**, 174.25 seconds. The active enemy-fire test
  passes at this new head; no skip, weakened assertion or timeout extension
  replaces the historical failed runs.
- Unmodified official native crew runner: five groups, zero page errors and
  completed owned-stack cleanup, through the real two-browser WS/TCP stack.
- Controlled native runtime check: nine groups, zero page errors and completed
  cleanup. It covers stale/repeated/rapid zero, actual zero and zero fuel burn,
  real unmount and release/rejoin retirement. Scripted real read ordering and a
  held original response are labelled; no replacement response is used.
- Native thermal check: seven groups, zero page errors and completed cleanup.
  Actual Hunter heating produces visible MANUAL proposals without automatic
  plant changes; denial preserves the setting and selective approval changes
  only the chosen plant action.
- Native lobby check: eight groups, zero page errors and completed cleanup,
  including peer changes, hidden view, real unmount, controlled visibility and
  original stale reply, manual Refresh, reconnect/explicit rejoin and observer
  denial.
- Predeclared combined seeds 0 / 1 / 42: nine actual shots each, with original
  fire/power calls forwarded once and normal gates/accounting. Positive impacts
  are 4 / 0 / 0 and hull damage is 22 / 0 / 0.
- Real `02_combat_destroy` station-server run with two independent TCP seats,
  physical dt 0.1s and captain-authorized time scale 10: two unique pirate
  projectiles at 433.7 / 483.7 simulated seconds. One impact reports
  `hit=false / damage=0`; the other projectile expires. There are **zero
  successful hits**, final hull is 150, and the normal 600-second mission
  timeout reports failure. Projectile IDs are counted once; repeated raw
  mutable event entries remain retained. The owned server is stopped.

[PR429 CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/37080211582)
passes both jobs. [Python](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/37080211582/job/111078841475)
reports **2,425 passes**, 261.97 seconds, using the full `tests/` selection.
[Svelte](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/37080211582/job/111078841614)
passes **47 frontend / 14 harness tests**, check 0 errors / 0 warnings and build.
The two extra root-discovery tests are outside CI's `tests/` selection. Both jobs
check out merge `0144cd661a1aed36fed25ef31daf7e7dc62d222a`, bound to exact
base `6e6dabf` / head `c5c5c40`, with tree
`afdcbb411d617bf41023a3e220da82a6f761467e`, identical to the candidate.

Independent combined source/native/focused review is complete: 121 Python and
52 Node checks pass, with no new runtime finding. The resumed independent
closeout audit verifies final CI checkout, counts and identical tree, and the
corrected two-event TCP accounting. Browser/checklist closeout review is
recorded separately from those earlier checks.

The resumed native browser run uses two independent Captain/Engineering
contexts on the exact clean `c5c5c40` tree, without transport or simulation
replacement. Numeric 20% → 0% and 20% → CUT THRUST are accepted; both seats
report actual zero and zero fuel burn. Engineering's time-scale command is
denied. Two NPC projectile IDs are visible, first at 430.4 simulated seconds.
Mission timeout reports failure at 600 seconds, with final observation at
604.1 seconds; launches do not establish successful hits or victory. Zero page
errors and owned-stack/port cleanup are recorded. Scenario02 reports its
thermal subsystem as **disabled/unavailable**, so this run does **not** exercise
thermal MANUAL denial/approval. The separate Hunter heating proof remains the
thermal evidence; no hardware or temperatures were injected to force coverage.
The helper's overall pass applies to its executed assertions, not that missing
thermal observation.

No source result or textual merge compatibility is counted as combined acceptance. Same-host automated
contexts do not establish human, two-device, completed-docking or larger
Captain/fleet-load acceptance. Passing automated checks do not close those gates.

The NPC-only phase uses fresh finite sensor contacts and the existing Navigation
→ Helm → RCS path, yields to operator/queued Helm control, holds on contact
loss and releases only its own autopilot slot. Server-authoritative seats,
observer denial, explicit rejoin, manual cutoff and explicit MANUAL thermal
approval gates remain intact. Existing weapon and role/retreat/salvo gates,
shared velocity matching, jink, cooling and thermal policy remain intact. This
integration makes no further combat-policy change and does not repair the
known physical-pitch/bearing conflict or inherited projectile-velocity defect.

## Assistance limits and next owner gates

The [fallback Engineering CPU](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/6e6dabf4d8c0cec006650f9d93d92711addfe8ae/server/stations/ai_crew.py#L183)
can activate fitted sinks when unclaimed and running. The tested
[Hunter configuration](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/6e6dabf4d8c0cec006650f9d93d92711addfe8ae/scenarios/intercept_scenario.json#L96) has sinks holding
500 kJ and dump at 50 kW: roughly ten simulated seconds at full rate, while net
heating can remain positive. First Contact has no thermal system. This is not
sustained reactor/radiator/governor management or a full replacement crew.
Solo navigation still requires explicit station changes, approval and manual
post-dock cutoff.

The separate [Auto-Engineering proposal system on main](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/6e6dabf4d8c0cec006650f9d93d92711addfe8ae/hybrid/systems/auto_engineering.py#L35)
starts disabled; choosing CPU ASSIST does not enable it. Earlier main `1ceec62`
read absent fractional `hull_temp_pct`, while [actual thermal telemetry](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/6e6dabf4d8c0cec006650f9d93d92711addfe8ae/hybrid/systems/thermal_system.py#L526)
provides `temperature_percent` (0–100); task 6 reproduced absent hot proposals.
The bounded PR425 telemetry repair is now included on main through PR427:
both generators divide the actual percentage by 100. PR425 itself remains draft.
Its pinned thermal document's active enemy-fire failure describes the earlier
thermal-only source head, not the later NPC continuation or combined head.
The existing strict >60% threshold, disabled default, 3s scans, cooldown,
recent-damage guards and execution gates remain unchanged. For a 500 K maximum,
60% is about 301.1 K, distinct from the 400 K warning and fallback sink trigger.
MANUAL proposals expire after eight wall seconds when ticking; AUTO retains
its existing eight-second execution. Cooling, sink capacity, crew competence
and station authority are unchanged. Broader threshold/timing or CPU autonomy
work remains separately scoped. Use the [short owner thermal check](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/282e8fa950e1da4a09ce9b0b6566bb9e2cac78f9/docs/AUTO_ENGINEERING_THERMAL_REPAIR.md#short-owner-playtest).

- [x] Select coast-and-aim; the [pinned original PR420 diagnosis](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/b9a87be2a5e1409d449dcebb967931980facd75b/docs/ENEMY_FIRE_DIAGNOSIS.md) retains the earlier alternatives. PR428 implements the selected policy; source and exact-head combined checks pass as recorded above. Human combat UAT remains pending.
- [x] Authorize the bounded thermal field repair; implemented in PR425 and included on main via PR427. Source and original combined review are complete; human thermal UAT remains pending.
- [ ] Human-check [lobby behavior](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/345c4d4926f90cf00ca405d68788b3841ea26b33/docs/LOBBY_OCCUPANCY_REFRESH.md) and [crew smoke steps](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/1e4aaa6f057af47c47ccda87c29d0d486b728374/docs/SHARED_SHIP_PLAYTEST.md#repeatable-short-crew-smoke-real-stack) on the selected combined revision; these links preserve the source-head instructions.
- [ ] Report crewed, solo and [first-tutorial UAT](FIRST_TUTORIAL_DOCKING_GUIDANCE.md), including completed docking, rejoin and MANUAL → Manual Flight → Throttle 0%. Use an isolated checkout at the selected exact revision; for the new combined candidate, pin `c5c5c40`, adapting the [isolated setup](SHARED_SHIP_PLAYTEST.md#safe-linux-checkout-and-build) and preserving the running local playtest.
- [x] Authorize the bounded runtime reliability repair; implemented in PR426 and included on main via PR427.
- [ ] Human-check numeric 0% / CUT THRUST, actual zero / zero fuel burn, observer reconnect and explicit rejoin on the selected combined revision. The PR423 guard remains a harness feature.
- [ ] Supply task 9's second actual computer and verified path, then authorize a separate two-device check. No same-host substitution or network/security change here.
- [x] Authorize bounded integration of PR421/423/425/426; PR427 records `e943ecc` separately from the source heads and is now merged into main at identical tree.
- [x] Independently review PR427's recorded crew checks at its exact SHA; no new material integration finding. Its historical enemy-fire failure remains recorded and human UAT gates remain open.
- [x] Authorize integration of the approved NPC source with the crew fixes; new candidate `c5c5c40` records the source ancestry and adds no gameplay changes.
- [x] Record exact-head new combined root/frontend/native checks separately from PR427 and PR428 source evidence.
- [x] Record final combined CI and actual review state. Both CI jobs pass; source/native/focused review is complete. Final CI closure and corrected TCP accounting are independently audited; resumed browser/checklist closeout is recorded above.
- [ ] Benchmark larger Captain/fleet load separately; the retained snapshot payload estimates are not a capacity benchmark.

For human UAT on the selected combined revision:

1. Use the isolated setup above. Check complementary Captain/Helm/Engineering
   seats, server-authoritative claims and observer command denial. Check lobby
   refresh, release and reconnect; reconnect must retain observer status until
   an explicit rejoin/claim succeeds.
2. Through the normal Manual Flight controls, apply nonzero thrust and confirm
   actual thrust and positive fuel burn. Commit numeric 0% and use CUT THRUST;
   confirm actual zero and zero fuel burn, including repeat/rapid cutoff and
   release/rejoin or a real view unmount retiring old edits.
3. Complete crewed and solo docking and the first tutorial through normal
   controls; verify the completion reminder and perform manual post-dock cutoff.
   An automated smoke or an earlier-head flight does not complete this gate.
4. On a thermally fitted Hunter, use the linked short thermal check: select CPU
   ASSIST, verify disabled default, explicitly enable Auto-Engineering in MANUAL
   and warm through ordinary controls. Visible proposals must leave plant
   settings unchanged. Deny one and approve only the selected other proposal;
   confirm only the authorized action occurs, then disable and restore the plant.
5. Run the existing `02_combat_destroy` mission through normal sensor, lock and
   weapon controls. Check returned fire, rotated-mount and out-of-arc behavior,
   charge/power/heat/ammunition accounting and operator Helm precedence. Record
   observed shots, hits, damage and mission outcome separately; firing evidence
   does not guarantee a hit or victory.
6. Separately supply and verify two actual computers and their network path for
   task 9. Same-host browser contexts remain automated evidence only.

This ten-task pass ends at these acceptance and decision gates. No GitHub PR
merge, PR closure, deployment or network/local-playtest change is performed by
this documentation reconciliation.
