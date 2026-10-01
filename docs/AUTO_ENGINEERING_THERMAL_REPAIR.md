# Auto-Engineering thermal telemetry repair

The two temperature-triggered proposal generators now read the actual
`ThermalSystem.get_state()` field, `temperature_percent` (0–100), and divide by
100 before applying their existing fractional threshold and confidence. Before
this repair they read absent `hull_temp_pct`, defaulted to zero, and never
proposed a reactor reduction or radiator deployment from heat alone.

The existing strict **greater than 60%** threshold stays in place. Thermal
percentage is measured from the 2.7 K background to the configured maximum
temperature, rounded to one decimal place by the provider. For a 500 K maximum,
60% corresponds to about 301.1 K; it is not the 400 K warning threshold or the
fallback CPU's 95%-of-warning trigger. Changing this threshold is a separate
design decision.

Auto-Engineering still starts disabled. Selecting the CPU ASSIST tier does not
enable it. After explicit enablement, MANUAL mode creates proposals without
changing reactor output or radiator deployment until an authorized approval.
MANUAL proposals expire after eight wall-clock seconds when the system ticks;
AUTO mode retains its existing eight-second automatic execution. Scan cadence,
cooldown, recent-damage radiator guards and all station permissions stay intact.
No cooling, heat-sink, crew competence or execution policy is changed.

## Verification scope

`tests/test_auto_engineering_thermal.py` uses the actual Hunter thermal provider,
engineering commands and simulator. It covers units and the strict threshold,
default-disabled and unfitted states, radiator/damage guards, approval/denial,
MANUAL expiry, AUTO delay, switching to MANUAL, cooldown and physical heating.
It also checks that proposal generation leaves plant settings and finite sinks
alone and that original reactor cooling remains 1.5.

Native validation must use the real Svelte → WebSocket → station-server path,
explicit MANUAL mode and ordinary commands to warm a fitted thermal ship.
Retain the tested SHA, accepted command responses and visible proposals. The
existing repeatable crew smoke from draft PR423 can also be run against this
repair head with its harness provenance recorded separately. Same-host browser
contexts do not establish two actual computers or owner human UAT. Private
evidence is retained separately; this document does not publish it.

The full Python suite retains the active known failure
`tests/test_gameplay_loop.py::TestCombat::test_enemy_ai_fires_back`. This thermal
repair does not resolve the pending NPC combat policy in PR420.

## Short owner playtest

Use an isolated checkout with a thermally fitted ship such as UNS Hunter;
First Contact has no thermal system. Keep the running local playtest untouched.

1. Claim Engineering, select CPU ASSIST, and verify Auto-Engineering is disabled.
   Set Engineering mode to **MANUAL** before explicitly enabling it.
2. With no incoming fire, set reactor output to 100%, thrust to 0% and retract
   radiators. Let actual thermal telemetry rise above 60%. Within a scan, expect
   **REDUCE REACTOR** and **DEPLOY RADIATORS**, with confidence/reason matching
   the thermal percentage. No action should occur merely from a MANUAL proposal.
3. Before expiry, deny one proposal and approve the other. Confirm only the
   approved action changes its setting. A captain can pause to inspect a
   pending proposal; pause stops simulation ticks but not the displayed clock.
4. Disable Auto-Engineering, deploy balanced radiators, set reactor to 10% and
   leave Manual Flight thrust at 0%. Report the SHA, observed settings and any
   discrepancy. This is a thermal proposal check, not sustained CPU crew or
   docking acceptance.
