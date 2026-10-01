# Ten-task release checklist

Verified **2026-10-01 UTC** against main
`1ceec6256f207bdaccb0072b4d3905bdfb9cb8ce` and live PR metadata. This is a
readiness snapshot, not release approval. PR418, PR419 and PR422 are merged;
PR420, PR421 and PR423 are open drafts. Historical PR bodies saying “keep draft”
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
| 6. CPU thermal assistance | Read-only current-main validation; **no repair PR** | 30 private diagnostics; 27 frontend; Python 2,362 pass + known failure; no new CI | Native release/resume/sink exhaustion; hot proposals absent | Telemetry repair approval; thermal UAT; broader automation separately scoped |
| 7. NPC combat follow-through | **Blocked**; no additional implementation | Task 2 diagnosis; no separate checks | No new playtest | Same NPC policy decision |
| 8. Repeatable crew smoke | [PR423](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/pull/423) **draft** | 10 harness + 27 frontend; Python 2,362 pass + known failure; [CI](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/actions/runs/36808103722) | Same-host contexts; 5 native groups: ownership, permissions, explicit rejoin, shared state, 20% → 0%; teardown probes | Human UAT; no completed docking |
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
| PR423 | [25d6655](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/commit/25d6655bcd12c9b6a9d68c6731c3b4aa01052ba3) | Unmerged |

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

## Assistance limits and next owner gates

The [fallback Engineering CPU](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/1ceec6256f207bdaccb0072b4d3905bdfb9cb8ce/server/stations/ai_crew.py#L183)
can activate fitted sinks when unclaimed and running. The tested
[Hunter configuration](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/1ceec6256f207bdaccb0072b4d3905bdfb9cb8ce/scenarios/intercept_scenario.json#L96) has sinks holding
500 kJ and dump at 50 kW: roughly ten simulated seconds at full rate, while net
heating can remain positive. First Contact has no thermal system. This is not
sustained reactor/radiator/governor management or a full replacement crew.
Solo navigation still requires explicit station changes, approval and manual
post-dock cutoff.

The separate [Auto-Engineering proposal system](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/1ceec6256f207bdaccb0072b4d3905bdfb9cb8ce/hybrid/systems/auto_engineering.py#L35)
starts disabled; choosing CPU ASSIST does not enable it. It reads fractional
`hull_temp_pct`, while [actual thermal telemetry](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/1ceec6256f207bdaccb0072b4d3905bdfb9cb8ce/hybrid/systems/thermal_system.py#L526)
provides `temperature_percent` (0–100); task 6 reproduced absent hot proposals.
Repair is **awaiting approval**, not implemented. Threshold/timing and broader
behavior need owner direction; MANUAL proposals can expire after eight seconds.

- [ ] Choose coast-and-aim versus sensor-aware velocity matching in the [PR420 diagnosis](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/b9a87be2a5e1409d449dcebb967931980facd75b/docs/ENEMY_FIRE_DIAGNOSIS.md); approve the bounded thermal telemetry repair or defer it.
- [ ] Review/test [draft lobby behavior](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/345c4d4926f90cf00ca405d68788b3841ea26b33/docs/LOBBY_OCCUPANCY_REFRESH.md) and [draft crew smoke](https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/blob/25d6655bcd12c9b6a9d68c6731c3b4aa01052ba3/docs/SHARED_SHIP_PLAYTEST.md#repeatable-short-crew-smoke-real-stack) at their separate pinned heads.
- [ ] Report crewed, solo and [first-tutorial UAT](FIRST_TUTORIAL_DOCKING_GUIDANCE.md), including rejoin and MANUAL → Manual Flight → Throttle 0%. Use the [isolated main setup](SHARED_SHIP_PLAYTEST.md#safe-linux-checkout-and-build), preserving the running local playtest.
- [ ] Supply task 9's second actual computer and verified path, then authorize a separate two-device check. No same-host substitution or network/security change here.
- [ ] After authorized integration, record the candidate SHA and rerun unsuppressed checks/UAT; separate draft results do not establish combined acceptance.

This ten-task pass ends at these acceptance and decision gates. No merge, PR
closure, new capability or network/local-runtime change is performed here.
