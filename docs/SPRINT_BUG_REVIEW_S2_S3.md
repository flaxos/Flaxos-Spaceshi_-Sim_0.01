# Sprint Bug Review (Last Two Sprints)

**Scope**: Sprint S2 (Phase 2: Multi-Crew & Fleet) and Sprint S3 (Physics Update: Attitude/RCS)
**Version Context**: 0.2.x → 0.5.0

This review summarizes known bug fixes, resolved blockers, and remaining risk areas based on the
project changelog and sprint preparation notes. It is intended to support regression testing and
triage after significant gameplay feature updates.

---

## Sprint S2 (Phase 2: Multi-Crew & Fleet)

### Resolved Bugs & Fixes to Verify

1. **Station event streaming (`get_events`)**
   - **Fix status**: Resolved, event log wired and populated across systems.
   - **Regression risk**: High, because station UI and telemetry depend on consistent event delivery.
   - **Reference**: Known issues entry indicates the event bus now feeds `event_log` and `get_events`.

2. **Station command lists**
   - **Fix status**: Resolved, dispatcher now filters to registered commands only.
   - **Regression risk**: Medium, as station definitions can diverge from dispatcher registry.
   - **Reference**: Known issues entry for station command lists.

3. **Telemetry snapshot errors in `server.run_server`**
   - **Fix status**: Resolved, power management config parsing now guards against non-dict values.
   - **Regression risk**: Medium, new ship configs or power thresholds could reintroduce load errors.
   - **Reference**: Known issues entry for telemetry snapshot errors.

### Ongoing Limitations Impacting Gameplay

- **Fleet formation math depends on NumPy**
  - **Impact**: Fleet formations unavailable without NumPy, which affects fleet-level tactics.
  - **Reference**: Known issues entry on NumPy dependency for fleet formations.

- **AI behaviors are limited (IDLE/PATROL/INTERCEPT/ESCORT/ATTACK)**
  - **Impact**: Tactical depth limited; AI may fail to respond to advanced scenarios.
  - **Reference**: Known issues entry on AI behavior limitations.

---

## Sprint S3 (Physics Update: Quaternion Attitude & RCS Torque)

### Resolved Blockers & Fixes to Verify

1. **Moment of inertia added to ship physics**
   - **Fix status**: Resolved, `moment_of_inertia` added to Ship state.
   - **Regression risk**: Medium, ship configs without explicit inertia rely on default heuristic.
   - **Reference**: S3 preparation notes for added moment of inertia.

2. **Angular acceleration tracking**
   - **Fix status**: Resolved, `angular_acceleration` introduced for rotational dynamics.
   - **Regression risk**: Medium, downstream systems need consistent updates each tick.
   - **Reference**: S3 preparation notes for angular acceleration tracking.

3. **Gimbal lock detection and warnings**
   - **Fix status**: Resolved, warnings and event publishing added for high pitch angles.
   - **Regression risk**: Medium, telemetry clients may rely on these warnings for safety.
   - **Reference**: S3 preparation notes for gimbal lock detection.

4. **Closing speed calculation for contacts**
   - **Fix status**: Resolved, contact tracking now calculates closing speed from relative velocity.
   - **Regression risk**: Medium, targeting/AI intercept logic depends on this value.
   - **Reference**: S3 preparation notes for closing speed.

5. **Hardpoint physical positioning**
   - **Fix status**: Resolved, hardpoints now have offsets/orientation/limits.
   - **Regression risk**: High, incorrect hardpoint config breaks aim fidelity and weapon alignment.
   - **Reference**: S3 preparation notes for hardpoint positioning.

6. **AI controller property bugs**
   - **Fix status**: Resolved, property access corrected to use position/velocity dicts.
   - **Regression risk**: Medium, AI logic depends on correct kinematic reads.
   - **Reference**: S3 preparation notes for AI controller property fixes.

### Remaining Physics Risk Areas

- **Quaternion attitude integration is planned, not fully documented as complete**
  - **Impact**: Euler → Quaternion transition could introduce drift or mismatched telemetry if not
    fully synced.
  - **Reference**: Physics update notes for quaternion attitude integration plan.

- **RCS torque integration depends on ship moment of inertia**
  - **Impact**: Incorrect inertia defaults produce unstable rotation or unrealistic maneuvering.
  - **Reference**: Physics update notes for torque-based dynamics.

---

## Recommended Regression Checks

### Station & Fleet (Sprint S2)
- Validate `get_events` streaming across stations during combat and navigation flows.
- Verify station command lists after role claim/release sequences.
- Smoke-test `server.run_server` telemetry snapshots with varied ship configurations.
- Run fleet formation commands with/without NumPy to confirm fallback behavior.

### Physics & Aim (Sprint S3)
- Confirm gimbal lock warnings emit events and log at the expected pitch thresholds.
- Validate contact closing speed values for approaching and receding targets.
- Confirm hardpoint offsets and rotation limits apply in targeting/weapon telemetry.
- Compare angular acceleration integration against expected torque outputs.

---

## Source References

- Changelog entries for recent fixes and documentation updates.
- Known issues summary for resolved and open items.
- Sprint S3 preparation notes for physics and AI fixes.
- Physics update notes for quaternion and RCS torque integration plans.
