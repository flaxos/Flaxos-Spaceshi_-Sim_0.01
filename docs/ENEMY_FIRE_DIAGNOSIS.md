# Enemy firing diagnosis — roadmap task 2

This draft repairs one weapon-frame correctness error. The existing
`test_enemy_ai_fires_back` zero-shot case remains visible and needs an owner
decision about NPC maneuver/aim priority. No later roadmap task is included.

## Published base and scope

Fresh GitHub state on 2026-09-30 confirmed that PR419 was merged. This branch
starts at main `3cbaebf1c32b9132f05635c6b64b7272e031511a`, containing the
reviewed `8fc73a6f27afa88d9d3c3adc373adcf8eb0dc07b` accounting/polling repair
and its original cooling policy. Work and checks use a separate cloud worktree;
the owner's checkout, stack and playtest have not been accessed.

`TruthWeapon.calculate_solution()` retains world-space `lead_angle` and
`intercept_point`. It now also derives `body_aim` with the same existing 3D
bearing transform used by firing arcs. The gimbal slews toward that body aim.
Previously it treated world yaw/pitch as ship-relative angles: for example,
a yaw-90 ship with a target 10 degrees off its bow tried to aim at world yaw
100 and clamped at the mount's 30-degree limit.

Arc limits, slew rates, tracking thresholds, sensor confidence, lock, charge,
power, heat, ammunition and physical projectiles retain their existing rules.
NPC tactics, navigation, jinking and command ownership are unchanged. The test's
60-second window and positive-shot assertion are unchanged; its obsolete
hostility/xfail description is replaced with the observed lock/readiness state.

## Reproduced zero-shot case

The unmodified fresh-main suite, with Python/NumPy seed 0 and
`PYTHONHASHSEED=0`, failed twice with **2,361 passed, 1 failed**. The sole
failure was `tests/test_gameplay_loop.py::TestCombat::test_enemy_ai_fires_back`.
Capturing its RNG state immediately before the test and replaying that state
in isolation reproduced the same zero shots, before and after the frame repair.

The passive trace covers all 600 combat ticks and engagement decisions:

- Pirates/neutral hostility is true; the pirate stays in `ATTACK` for all 600 ticks.
- Full lock holds for 553 ticks. A solution is in range for 580 ticks.
- All 27 engagement decisions after full lock have the target outside the arc.
  At 8.2 s, the hull is at yaw 49.56 degrees, while body aim is yaw -49.80
  degrees; the railgun's unchanged azimuth limits are -30 to +30 degrees.
- The capacitor is ready. No weapon `fire()` call or weapon power request occurs;
  this case does not demonstrate a power rejection.
- The AI selects `match` inside 20 km. Its heading command follows estimated
  velocity differences of roughly 0.3–2.2 m/s in this case. Sensor noise and the
  existing velocity-matching policy move the hull away from the target.

Before/after replay has identical contact data, hull headings, navigation
commands, lock state, range and reactor state for every tick. Gimbal tracking
now reflects the body aim; it cannot make an out-of-arc target fireable.

## Combat checks and deterministic regression

The isolated seed matrix was fixed at 0, 1 and 42 before observing results.
Neither the scenario nor AI was altered for these checks beyond the position
and velocity setup already in the existing test.

| RNG start | Fresh-main shots | Repaired shots |
|---|---:|---:|
| Isolated seed 0 | 4 | 4 |
| Isolated seed 1 | 4 | 4 |
| Isolated seed 42 | 1 | 0 |
| Captured full-suite seed-0 state | 0 | 0 |

The successful repaired runs use actual NPC lock, charge, arc/tracking gates,
15 kJ power draws, ammunition consumption, heat generation and ballistic
projectile creation. They demonstrate functioning fire paths, not resolution
of the zero-shot failure. The original seed-42 shot reported zero tracking error
despite approximately 25.17 degrees of body-aim error. Removing that false
tracking result exposes another zero-shot outcome; it is not a passing-seed fix.

All **18** added frame regressions fail on the original weapon implementation.
They cover railgun/PDC yaw, pitch, roll and combined rotation; both sides of
each arc boundary; clamp and slew limits during a hull turn; moving-target
world ballistics; and real charge, power, ammo, heat and cycle gates. The focused
weapons/combat suites pass **424** tests after repair. Full-suite and exact-head
CI results, independent Astra Max review and the evidence bundle are recorded
in the draft PR; failures remain unsuppressed.

## Owner decision and human acceptance

Further elimination of the zero-shot outcome requires choosing NPC policy.
Two bounded options for a later owner-authorized change are:

1. Give an NPC in weapon range a coast-and-aim phase that yields velocity-match
   heading control while the physical RCS brings its target into the gun arc.
2. Give NPC velocity matching a sensor-aware completion tolerance/deadband,
   with owner-selected scope and thresholds. A general match-velocity change
   would also affect navigation users and requires a separate decision.

Neither option is implemented. The unsupported jink `set_heading` path is
untouched. Do not merge this draft as completion of task 2 or treat an isolated
passing run as acceptance of NPC tactics.

Human combat UAT remains pending: on the reviewed head, run the existing
`02_combat_destroy` mission through normal sensor/lock/weapon commands and
inspect a rotated mount, returned fire, heat/power/ammunition accounting and
out-of-arc refusal. This is separate from automated headless evidence and from
the existing [shared-ship playtest](SHARED_SHIP_PLAYTEST.md).

## Migration and evidence

No config migration, GUI change or command/API change is required. Existing
world-space lead telemetry and projectile calculations remain intact.
`body_aim` is appended to the internal firing-solution dataclass; manually
constructed solutions without it retain the legacy angle fallback.

Local logs, JUnit reports, passive JSON traces, the captured RNG state, diagnostic
harnesses and checksums are retained in `/workspace/spacesim-task2-evidence/`.
The draft PR links the public exact-head CI results. The evidence bundle is
retained privately in the owner's ChatGPT Library.
